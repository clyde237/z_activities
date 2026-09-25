import calendar
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import or_

from ..extensions import db
from ..models import (
    MonthlyReport,
    MonthlyReportStatus,
    Task,
    TaskStatus,
    TaskUpdate,
    Team,
    UnexpectedActivity,
    User,
    UserTeam,
    WeeklyReport,
    WeeklyReportStatus,
)
from ..models.utils import utc_now
from .audit_service import log_action


def get_month_bounds(year: int, month: int) -> tuple[date, date]:
    """Retourne la date de début (1er du mois) et la date de fin du mois donné."""
    start_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)
    return start_date, end_date


def get_or_create_monthly_report(
    year: int,
    month: int,
    current_user: User,
) -> tuple[MonthlyReport, bool]:
    """Récupère ou crée le rapport mensuel départemental (CDC Section 17, RB-025, RB-026)."""
    report = (
        db.session.query(MonthlyReport)
        .filter_by(year=year, month=month)
        .one_or_none()
    )
    if report is not None:
        # On s'assure de lier les éventuels rapports hebdomadaires non encore attachés
        start_date, end_date = get_month_bounds(year, month)
        unlinked_weeklies = (
            db.session.query(WeeklyReport)
            .filter(
                WeeklyReport.monthly_report_id.is_(None),
                WeeklyReport.period_start <= end_date,
                WeeklyReport.period_end >= start_date,
            )
            .all()
        )
        if unlinked_weeklies:
            for w in unlinked_weeklies:
                w.monthly_report_id = report.id
            db.session.commit()
        return report, False

    start_date, end_date = get_month_bounds(year, month)
    report = MonthlyReport(
        year=year,
        month=month,
        status=MonthlyReportStatus.BROUILLON,
        created_by_id=current_user.id,
    )
    db.session.add(report)
    db.session.flush()

    # Rattachement automatique des rapports hebdomadaires de la période
    weeklies = (
        db.session.query(WeeklyReport)
        .filter(
            WeeklyReport.period_start <= end_date,
            WeeklyReport.period_end >= start_date,
        )
        .all()
    )
    for w in weeklies:
        w.monthly_report_id = report.id

    log_action(
        "create",
        "MonthlyReport",
        report.id,
        new_value=f"Rapport mensuel départemental {month}/{year} (brouillon)",
    )
    db.session.commit()
    return report, True


def get_monthly_report_data(monthly_report: MonthlyReport) -> dict[str, Any]:
    """Agrège et consolide l'ensemble des données d'activité départementale pour le mois."""
    start_date, end_date = get_month_bounds(monthly_report.year, monthly_report.month)
    dt_start = datetime.combine(start_date, time.min)
    dt_end = datetime.combine(end_date, time.max)

    # 1. Rapports hebdomadaires rattachés ou de la période
    weekly_reports = (
        db.session.query(WeeklyReport)
        .filter(
            or_(
                WeeklyReport.monthly_report_id == monthly_report.id,
                (WeeklyReport.period_start <= end_date) & (WeeklyReport.period_end >= start_date),
            )
        )
        .order_by(WeeklyReport.period_start.asc())
        .all()
    )

    reports_stats = {
        "total": len(weekly_reports),
        "valides": sum(1 for r in weekly_reports if r.status == WeeklyReportStatus.VALIDE),
        "soumis": sum(1 for r in weekly_reports if r.status == WeeklyReportStatus.SOUMIS),
        "brouillons": sum(1 for r in weekly_reports if r.status == WeeklyReportStatus.BROUILLON),
    }

    # 2. Tâches départementales actives dans le mois
    all_tasks = db.session.query(Task).all()
    tasks_of_month: list[Task] = []
    for t in all_tasks:
        # A. Créée dans le mois
        created_in_month = t.created_at and start_date <= t.created_at.date() <= end_date
        # B. Échéance dans le mois
        due_in_month = t.due_date and start_date <= t.due_date <= end_date
        # C. Mise à jour dans le mois
        updated_in_month = any(start_date <= u.created_at.date() <= end_date for u in t.updates)
        # D. En cours avec échéance postérieure
        active_in_period = t.status == TaskStatus.EN_COURS and (t.start_date is None or t.start_date <= end_date)

        if created_in_month or due_in_month or updated_in_month or active_in_period:
            tasks_of_month.append(t)

    # Dédoublonnage par ID
    unique_tasks_dict = {t.id: t for t in tasks_of_month}
    tasks_list = list(unique_tasks_dict.values())

    tasks_total = len(tasks_list)
    tasks_completed = sum(1 for t in tasks_list if t.status == TaskStatus.TERMINEE)
    tasks_in_progress = sum(1 for t in tasks_list if t.status == TaskStatus.EN_COURS)
    tasks_to_do = sum(1 for t in tasks_list if t.status == TaskStatus.A_FAIRE)
    tasks_blocked = sum(1 for t in tasks_list if t.status == TaskStatus.BLOQUEE)
    tasks_late = sum(1 for t in tasks_list if t.is_late(end_date))
    avg_progress = (
        round(sum(t.progress for t in tasks_list) / tasks_total, 1)
        if tasks_total > 0
        else 0.0
    )

    tasks_stats = {
        "total": tasks_total,
        "completed": tasks_completed,
        "in_progress": tasks_in_progress,
        "to_do": tasks_to_do,
        "blocked": tasks_blocked,
        "late": tasks_late,
        "avg_progress": avg_progress,
    }

    # 3. Activités imprévues du mois
    unexpected_activities = (
        db.session.query(UnexpectedActivity)
        .filter(
            UnexpectedActivity.activity_date >= start_date,
            UnexpectedActivity.activity_date <= end_date,
        )
        .order_by(UnexpectedActivity.activity_date.desc())
        .all()
    )

    # 4. Consolidation par équipe
    all_teams = db.session.query(Team).order_by(Team.name.asc()).all()
    teams_summary: list[dict[str, Any]] = []

    for team in all_teams:
        team_tasks = [t for t in tasks_list if t.team_id == team.id]
        t_total = len(team_tasks)
        t_completed = sum(1 for t in team_tasks if t.status == TaskStatus.TERMINEE)
        t_in_progress = sum(1 for t in team_tasks if t.status == TaskStatus.EN_COURS)
        t_late = sum(1 for t in team_tasks if t.is_late(end_date))
        t_avg = (
            round(sum(t.progress for t in team_tasks) / t_total, 1)
            if t_total > 0
            else 0.0
        )

        member_ids = {link.user_id for link in team.member_links}
        team_unexp = [act for act in unexpected_activities if act.user_id in member_ids]

        teams_summary.append({
            "team": team,
            "members_count": len(member_ids),
            "tasks_total": t_total,
            "tasks_completed": t_completed,
            "tasks_in_progress": t_in_progress,
            "tasks_late": t_late,
            "avg_progress": t_avg,
            "unexpected_count": len(team_unexp),
        })

    # 5. Consolidation individuelle des collaborateurs
    active_users = (
        db.session.query(User)
        .filter_by(is_active_account=True)
        .order_by(User.last_name.asc(), User.first_name.asc())
        .all()
    )
    members_summary: list[dict[str, Any]] = []

    for u in active_users:
        u_tasks = [
            t for t in tasks_list
            if t.responsible_id == u.id or t.co_responsible_id == u.id
        ]
        u_total = len(u_tasks)
        u_completed = sum(1 for t in u_tasks if t.status == TaskStatus.TERMINEE)
        u_late = sum(1 for t in u_tasks if t.is_late(end_date))
        u_avg = (
            round(sum(t.progress for t in u_tasks) / u_total, 1)
            if u_total > 0
            else 0.0
        )
        u_reports = [r for r in weekly_reports if r.user_id == u.id]
        u_unexp = [act for act in unexpected_activities if act.user_id == u.id]

        members_summary.append({
            "user": u,
            "teams": [link.team.name for link in u.team_links if link.team],
            "tasks_total": u_total,
            "tasks_completed": u_completed,
            "tasks_late": u_late,
            "avg_progress": u_avg,
            "reports_count": len(u_reports),
            "unexpected_count": len(u_unexp),
        })

    # 6. Synthèses des difficultés et solutions consolidées issues des rapports hebdomadaires
    collected_difficulties = [
        {"user": r.user.full_name, "period": f"{r.period_start.strftime('%d/%m')}..{r.period_end.strftime('%d/%m')}", "text": r.difficulties}
        for r in weekly_reports
        if r.difficulties and r.difficulties.strip()
    ]
    collected_solutions = [
        {"user": r.user.full_name, "period": f"{r.period_start.strftime('%d/%m')}..{r.period_end.strftime('%d/%m')}", "text": r.solutions}
        for r in weekly_reports
        if r.solutions and r.solutions.strip()
    ]

    return {
        "report": monthly_report,
        "period_start": start_date,
        "period_end": end_date,
        "reports_stats": reports_stats,
        "weekly_reports": weekly_reports,
        "tasks_stats": tasks_stats,
        "tasks": tasks_list,
        "unexpected_activities": unexpected_activities,
        "teams_summary": teams_summary,
        "members_summary": members_summary,
        "collected_difficulties": collected_difficulties,
        "collected_solutions": collected_solutions,
    }


def update_monthly_report_content(
    monthly_report: MonthlyReport,
    data: dict[str, str],
    current_user: User,
) -> MonthlyReport:
    """Met à jour les sections rédactionnelles du rapport mensuel (CDC Section 17, RB-027)."""
    old_summary = monthly_report.narrative_summary
    monthly_report.narrative_summary = data.get("narrative_summary", "").strip() or None
    monthly_report.key_achievements = data.get("key_achievements", "").strip() or None
    monthly_report.difficulties_summary = data.get("difficulties_summary", "").strip() or None
    monthly_report.action_plan = data.get("action_plan", "").strip() or None
    monthly_report.observations = data.get("observations", "").strip() or None

    log_action(
        "update",
        "MonthlyReport",
        monthly_report.id,
        old_value=old_summary[:50] if old_summary else "N/A",
        new_value=f"Mise à jour des synthèses mensuelles par {current_user.full_name}",
    )
    db.session.commit()
    return monthly_report


def finalize_monthly_report(
    monthly_report: MonthlyReport,
    current_user: User,
) -> MonthlyReport:
    """Finalise le rapport mensuel départemental (CDC Section 28, RB-027)."""
    if not monthly_report.can_transition_to(MonthlyReportStatus.FINALISE):
        raise ValueError("Le rapport ne peut pas être finalisé dans son état actuel.")

    monthly_report.status = MonthlyReportStatus.FINALISE
    monthly_report.finalized_at = utc_now()
    monthly_report.finalized_by_id = current_user.id

    log_action(
        "validate",
        "MonthlyReport",
        monthly_report.id,
        new_value=f"Rapport mensuel finalisé par le chef de service {current_user.full_name}",
    )
    db.session.commit()
    return monthly_report


def reopen_monthly_report(
    monthly_report: MonthlyReport,
    current_user: User,
) -> MonthlyReport:
    """Réouvre le rapport mensuel en brouillon pour ajustements."""
    if not monthly_report.can_transition_to(MonthlyReportStatus.BROUILLON):
        raise ValueError("Le rapport ne peut pas être réouvert dans son état actuel.")

    monthly_report.status = MonthlyReportStatus.BROUILLON
    monthly_report.finalized_at = None
    monthly_report.finalized_by_id = None

    log_action(
        "update",
        "MonthlyReport",
        monthly_report.id,
        new_value=f"Rapport mensuel réouvert en brouillon par {current_user.full_name}",
    )
    db.session.commit()
    return monthly_report
