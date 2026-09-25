from datetime import date, datetime, time, timedelta
from typing import Any

from ..extensions import db
from ..models import (
    Task,
    TaskStatus,
    TaskUpdate,
    UnexpectedActivity,
    User,
    UserRole,
    UserTeam,
    WeeklyReport,
    WeeklyReportStatus,
)
from ..models.utils import utc_now
from .audit_service import log_action


class ReportValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def get_week_bounds(target_date: date | None = None) -> tuple[date, date]:
    """Retourne le lundi (début) et le dimanche (fin) de la semaine calendaire."""
    if target_date is None:
        target_date = date.today()
    # weekday() : 0=Lundi, ..., 4=Vendredi, ..., 6=Dimanche
    start = target_date - timedelta(days=target_date.weekday())
    end = start + timedelta(days=6)
    return start, end


def get_or_create_weekly_report(
    user: User,
    target_date: date | None = None,
) -> tuple[WeeklyReport, bool]:
    """Récupère ou crée le rapport hebdomadaire en brouillon pour la semaine (RB-020, RB-021)."""
    start, end = get_week_bounds(target_date)

    report = (
        db.session.query(WeeklyReport)
        .filter_by(user_id=user.id, period_start=start)
        .one_or_none()
    )
    if report is not None:
        return report, False

    report = WeeklyReport(
        user_id=user.id,
        period_start=start,
        period_end=end,
        status=WeeklyReportStatus.BROUILLON,
    )
    db.session.add(report)
    db.session.flush()

    log_action(
        "create",
        "WeeklyReport",
        report.id,
        new_value=f"Rapport semaine {start}..{end} pour {user.full_name} (brouillon)",
    )
    db.session.commit()
    return report, True


def generate_weekly_reports_for_all(target_date: date | None = None) -> list[WeeklyReport]:
    """Génération hebdomadaire automatique pour tous les membres actifs (RB-020)."""
    active_users = db.session.query(User).filter_by(is_active_account=True).all()
    reports = []
    for u in active_users:
        rep, _ = get_or_create_weekly_report(u, target_date=target_date)
        reports.append(rep)
    return reports


def get_report_data(report: WeeklyReport) -> dict[str, Any]:
    """Agrège l'ensemble des données d'activités, tâches et statistiques de la semaine."""
    start = report.period_start
    end = report.period_end
    user_id = report.user_id

    # 1. Tâches de l'utilisateur concernées par cette semaine
    all_user_tasks = (
        db.session.query(Task)
        .filter((Task.responsible_id == user_id) | (Task.co_responsible_id == user_id))
        .all()
    )

    relevant_tasks: list[Task] = []
    for t in all_user_tasks:
        # A. Tâche dont l'échéance tombe dans la semaine
        has_due_in_week = t.due_date and start <= t.due_date <= end
        # B. Tâche ayant des mises à jour faites par l'utilisateur pendant la semaine
        has_update_in_week = any(
            start <= (u.created_at.date() if isinstance(u.created_at, datetime) else u.created_at) <= end
            and u.user_id == user_id
            for u in t.updates
        )
        # C. Tâche active (en cours, à faire, à valider, etc.) créée avant ou pendant la semaine
        created_date = t.created_at.date() if isinstance(t.created_at, datetime) else t.created_at
        is_active_in_week = (
            created_date <= end
            and t.status not in (TaskStatus.ANNULEE,)
        )

        if has_due_in_week or has_update_in_week or is_active_in_week:
            relevant_tasks.append(t)

    # Dédoublonner et trier
    unique_tasks = list({t.id: t for t in relevant_tasks}.values())
    unique_tasks.sort(key=lambda x: (x.due_date or date.max, x.id))

    # 2. Activités imprévues dans la période
    unexpected_activities = (
        db.session.query(UnexpectedActivity)
        .filter(
            UnexpectedActivity.user_id == user_id,
            UnexpectedActivity.activity_date >= start,
            UnexpectedActivity.activity_date <= end,
        )
        .order_by(UnexpectedActivity.activity_date.desc(), UnexpectedActivity.id.desc())
        .all()
    )

    # 3. Mises à jour quotidiennes de la semaine
    dt_start = datetime.combine(start, time.min)
    dt_end = datetime.combine(end, time.max)
    task_updates = (
        db.session.query(TaskUpdate)
        .filter(
            TaskUpdate.user_id == user_id,
            TaskUpdate.created_at >= dt_start,
            TaskUpdate.created_at <= dt_end,
        )
        .order_by(TaskUpdate.created_at.desc())
        .all()
    )

    # 4. Statistiques de performance et d'avancement
    completed = [t for t in unique_tasks if t.status == TaskStatus.TERMINEE]
    in_progress = [t for t in unique_tasks if t.status == TaskStatus.EN_COURS]
    to_do = [t for t in unique_tasks if t.status == TaskStatus.A_FAIRE]
    late = [t for t in unique_tasks if t.is_late(end)]

    avg_progress = 0
    if unique_tasks:
        avg_progress = round(sum(t.progress for t in unique_tasks) / len(unique_tasks))

    stats = {
        "total_tasks": len(unique_tasks),
        "completed_count": len(completed),
        "in_progress_count": len(in_progress),
        "to_do_count": len(to_do),
        "late_count": len(late),
        "unexpected_count": len(unexpected_activities),
        "average_progress": avg_progress,
    }

    return {
        "tasks": unique_tasks,
        "completed_tasks": completed,
        "in_progress_tasks": in_progress,
        "to_do_tasks": to_do,
        "late_tasks": late,
        "unexpected_activities": unexpected_activities,
        "task_updates": task_updates,
        "stats": stats,
    }


def update_weekly_report(
    report: WeeklyReport,
    user: User,
    data: dict[str, Any],
) -> WeeklyReport:
    """Met à jour les sections narratives et analyses d'un rapport en brouillon (RB-022)."""
    from ..permissions import can_edit_report

    if not can_edit_report(user, report):
        raise ReportValidationError(["Vous n'avez pas l'autorisation de modifier ce rapport."])

    narrative_summary = data.get("narrative_summary", "").strip()
    difficulties = data.get("difficulties", "").strip()
    solutions = data.get("solutions", "").strip()
    observations = data.get("observations", "").strip()

    report.narrative_summary = narrative_summary or None
    report.difficulties = difficulties or None
    report.solutions = solutions or None
    if observations:
        report.observations = observations

    log_action("update", "WeeklyReport", report.id, new_value="Mise à jour des analyses et synthèses")
    db.session.commit()
    return report


def submit_weekly_report(report: WeeklyReport, user: User) -> WeeklyReport:
    """Soumet le rapport hebdomadaire pour validation par le chef de service."""
    from ..permissions import can_submit_report

    if not can_submit_report(user, report):
        raise ReportValidationError(["Vous ne pouvez pas soumettre ce rapport."])

    if not report.can_transition_to(WeeklyReportStatus.SOUMIS):
        raise ReportValidationError([f"Transition impossible depuis le statut '{report.status.value}'."])

    report.status = WeeklyReportStatus.SOUMIS
    report.submitted_at = utc_now()

    log_action("submit", "WeeklyReport", report.id, new_value="Statut passé à SOUMIS")
    db.session.commit()

    from .notification_service import notify_report_submitted
    notify_report_submitted(report)

    return report


def validate_weekly_report(
    report: WeeklyReport,
    validator: User,
    observations: str | None = None,
) -> WeeklyReport:
    """Validation finale du rapport par le chef de service (RB-023)."""
    from ..permissions import can_validate_report

    if not can_validate_report(validator, report):
        raise ReportValidationError(["Seul le chef de service peut valider un rapport soumis."])

    if not report.can_transition_to(WeeklyReportStatus.VALIDE):
        raise ReportValidationError([f"Transition impossible depuis le statut '{report.status.value}'."])

    report.status = WeeklyReportStatus.VALIDE
    report.validated_at = utc_now()
    report.validated_by_id = validator.id
    if observations:
        report.observations = observations.strip()

    log_action("validate", "WeeklyReport", report.id, new_value="Statut passé à VALIDE")
    db.session.commit()

    from .notification_service import notify_report_validated
    notify_report_validated(report)

    return report


def reject_weekly_report_to_draft(
    report: WeeklyReport,
    validator: User,
    reason: str | None = None,
) -> WeeklyReport:
    """Renvoyer un rapport soumis en brouillon pour révision ou compléments."""
    if not validator.is_chef_service():
        raise ReportValidationError(["Seul le chef de service peut demander une révision."])

    if not report.can_transition_to(WeeklyReportStatus.BROUILLON):
        raise ReportValidationError([f"Transition impossible depuis le statut '{report.status.value}'."])

    report.status = WeeklyReportStatus.BROUILLON
    if reason:
        prefix = f"[Demande de révision - {date.today().strftime('%d/%m/%Y')}] : {reason.strip()}"
        if report.observations:
            report.observations = f"{report.observations}\n\n{prefix}"
        else:
            report.observations = prefix

    log_action("reject_to_draft", "WeeklyReport", report.id, new_value="Renvoyé en brouillon pour révision")
    db.session.commit()

    from .notification_service import notify_report_revision_requested
    notify_report_revision_requested(report, reason)

    return report


def get_visible_reports(
    user: User,
    status: str | None = None,
    team_id: int | None = None,
    user_id: int | None = None,
    period_start: date | None = None,
) -> list[WeeklyReport]:
    """Retourne la liste des rapports hebdomadaires filtrés et autorisés (RB-024)."""
    query = db.session.query(WeeklyReport)

    if user.is_chef_service():
        # Vision globale
        pass
    elif any(link.is_team_lead for link in user.team_links):
        # Chef d'équipe : ses rapports + les membres de ses équipes
        led_team_ids = {link.team_id for link in user.team_links if link.is_team_lead}
        subordinate_ids = {
            link.user_id
            for link in db.session.query(UserTeam).filter(UserTeam.team_id.in_(led_team_ids)).all()
        }
        subordinate_ids.add(user.id)
        query = query.filter(WeeklyReport.user_id.in_(subordinate_ids))
    else:
        # Collaborateur : uniquement ses propres rapports
        query = query.filter(WeeklyReport.user_id == user.id)

    # Filtres optionnels
    if status:
        try:
            status_enum = WeeklyReportStatus(status)
            query = query.filter(WeeklyReport.status == status_enum)
        except ValueError:
            pass

    if user_id:
        query = query.filter(WeeklyReport.user_id == user_id)

    if team_id:
        # Membres de cette équipe
        member_ids = {
            link.user_id
            for link in db.session.query(UserTeam).filter_by(team_id=team_id).all()
        }
        query = query.filter(WeeklyReport.user_id.in_(member_ids))

    if period_start:
        query = query.filter(WeeklyReport.period_start == period_start)

    return query.order_by(WeeklyReport.period_start.desc(), WeeklyReport.id.desc()).all()
