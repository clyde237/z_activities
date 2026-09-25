from datetime import date, datetime, time, timedelta
from typing import Any

from ..extensions import db
from ..models import (
    Notification,
    MonthlyReport,
    Task,
    TaskStatus,
    UnexpectedActivity,
    User,
    UserRole,
    WeeklyReport,
)
from ..models.utils import utc_now


def create_notification(
    user_id: int,
    notif_type: str,
    message: str,
    related_object_type: str | None = None,
    related_object_id: int | None = None,
) -> Notification:
    """Crée une notification pour un utilisateur, en évitant les doublons non lus récents."""
    # Éviter de dupliquer un rappel non lu identique émis dans les dernières 24 heures
    recent_dup = (
        db.session.query(Notification)
        .filter_by(
            user_id=user_id,
            notif_type=notif_type,
            related_object_type=related_object_type,
            related_object_id=related_object_id,
            is_read=False,
        )
        .first()
    )
    if recent_dup:
        return recent_dup

    notif = Notification(
        user_id=user_id,
        notif_type=notif_type,
        message=message,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
        is_read=False,
    )
    db.session.add(notif)
    db.session.commit()
    return notif


def get_user_notifications(
    user: User,
    unread_only: bool = False,
    limit: int = 50,
) -> list[Notification]:
    """Récupère les notifications d'un utilisateur par ordre chronologique décroissant."""
    query = (
        db.session.query(Notification)
        .filter_by(user_id=user.id)
    )
    if unread_only:
        query = query.filter_by(is_read=False)
    return query.order_by(Notification.created_at.desc()).limit(limit).all()


def get_unread_notifications_count(user: User) -> int:
    """Retourne le nombre de notifications non lues pour l'affichage du badge."""
    if not user.is_authenticated:
        return 0
    return (
        db.session.query(Notification)
        .filter_by(user_id=user.id, is_read=False)
        .count()
    )


def mark_notification_as_read(notification_id: int, user: User) -> bool:
    """Marque une notification précise comme lue."""
    notif = db.session.get(Notification, notification_id)
    if notif and notif.user_id == user.id:
        notif.is_read = True
        db.session.commit()
        return True
    return False


def mark_all_notifications_as_read(user: User) -> int:
    """Marque toutes les notifications non lues de l'utilisateur comme lues."""
    count = (
        db.session.query(Notification)
        .filter_by(user_id=user.id, is_read=False)
        .update({"is_read": True})
    )
    db.session.commit()
    return count


# -------------------------------------------------------------
# Déclencheurs / Hooks métiers (CDC Section 23)
# -------------------------------------------------------------

def notify_task_assigned(task: Task) -> None:
    """Notifie le responsable et le co-responsable d'une tâche lors de son attribution."""
    if task.responsible_id:
        create_notification(
            user_id=task.responsible_id,
            notif_type="task_assigned",
            message=f"La tâche « {task.title} » vous a été attribuée (Échéance : {task.due_date.strftime('%d/%m/%Y') if task.due_date else 'non définie'}).",
            related_object_type="Task",
            related_object_id=task.id,
        )
    if task.co_responsible_id and task.co_responsible_id != task.responsible_id:
        create_notification(
            user_id=task.co_responsible_id,
            notif_type="task_assigned",
            message=f"Vous avez été désigné(e) co-responsable de la tâche « {task.title} ».",
            related_object_type="Task",
            related_object_id=task.id,
        )


def notify_report_submitted(report: WeeklyReport) -> None:
    """Notifie les Chefs de service qu'un rapport hebdomadaire a été soumis et attend validation."""
    chefs = db.session.query(User).filter_by(role=UserRole.CHEF_SERVICE, is_active_account=True).all()
    author_name = report.user.full_name
    for chef in chefs:
        create_notification(
            user_id=chef.id,
            notif_type="report_submitted",
            message=f"{author_name} a soumis son rapport hebdomadaire ({report.period_start.strftime('%d/%m')}..{report.period_end.strftime('%d/%m')}) pour validation.",
            related_object_type="WeeklyReport",
            related_object_id=report.id,
        )


def notify_report_validated(report: WeeklyReport) -> None:
    """Notifie le collaborateur que son rapport hebdomadaire a été validé."""
    create_notification(
        user_id=report.user_id,
        notif_type="report_validated",
        message=f"Votre rapport hebdomadaire du {report.period_start.strftime('%d/%m/%Y')} au {report.period_end.strftime('%d/%m/%Y')} a été validé par le Chef de service.",
        related_object_type="WeeklyReport",
        related_object_id=report.id,
    )


def notify_report_revision_requested(report: WeeklyReport, observation: str | None = None) -> None:
    """Notifie le collaborateur qu'une révision de son rapport hebdomadaire est demandée."""
    obs_text = f" Remarque : {observation}" if observation else ""
    create_notification(
        user_id=report.user_id,
        notif_type="report_revision_requested",
        message=f"Votre rapport hebdomadaire du {report.period_start.strftime('%d/%m')} a été renvoyé en brouillon pour révision.{obs_text}",
        related_object_type="WeeklyReport",
        related_object_id=report.id,
    )


def notify_unexpected_activity_created(activity: UnexpectedActivity) -> None:
    """Notifie les Chefs de service et les Chefs d'équipe concernés de la déclaration d'une activité imprévue."""
    # Chefs de service
    chefs = db.session.query(User).filter_by(role=UserRole.CHEF_SERVICE, is_active_account=True).all()
    user_name = activity.user.full_name
    recipients = {c.id for c in chefs if c.id != activity.user_id}

    # Chefs des équipes de l'utilisateur
    for link in activity.user.team_links:
        for team_link in link.team.member_links:
            if team_link.is_team_lead and team_link.user_id != activity.user_id:
                recipients.add(team_link.user_id)

    for uid in recipients:
        create_notification(
            user_id=uid,
            notif_type="unexpected_activity_created",
            message=f"{user_name} a déclaré une activité imprévue : « {activity.title} » (Priorité : {activity.priority.value.upper()}).",
            related_object_type="UnexpectedActivity",
            related_object_id=activity.id,
        )


def notify_monthly_report_finalized(monthly_report: MonthlyReport) -> None:
    """Notifie l'ensemble des encadrants lors de la finalisation du rapport mensuel."""
    leaders = (
        db.session.query(User)
        .filter(
            User.is_active_account == True,
            User.role.in_([UserRole.CHEF_SERVICE, UserRole.COLLABORATEUR]),
        )
        .all()
    )
    for u in leaders:
        # Notifier les chefs de service et chefs d'équipe
        if u.is_chef_service() or any(link.is_team_lead for link in u.team_links):
            create_notification(
                user_id=u.id,
                notif_type="monthly_report_finalized",
                message=f"Le rapport mensuel départemental de {monthly_report.month_name} {monthly_report.year} a été finalisé et est disponible au téléchargement.",
                related_object_type="MonthlyReport",
                related_object_id=monthly_report.id,
            )


# -------------------------------------------------------------
# Vérifications périodiques (Échéances, Retards, Rappels de mise à jour)
# -------------------------------------------------------------

def check_deadlines_and_send_reminders(today: date | None = None) -> dict[str, int]:
    """Exécute les vérifications automatiques d'échéances et de rappels quotidiens."""
    if today is None:
        today = date.today()

    tomorrow = today + timedelta(days=1)
    counts = {
        "due_soon": 0,
        "late": 0,
        "update_reminders": 0,
    }

    active_tasks = (
        db.session.query(Task)
        .filter(~Task.status.in_([TaskStatus.TERMINEE, TaskStatus.ANNULEE]))
        .all()
    )

    for t in active_tasks:
        if not t.responsible_id:
            continue

        # 1. Échéance imminente (demain ou aujourd'hui)
        if t.due_date and (t.due_date == today or t.due_date == tomorrow):
            delay_str = "aujourd'hui" if t.due_date == today else "demain"
            create_notification(
                user_id=t.responsible_id,
                notif_type="task_due_soon",
                message=f"Échéance imminente : la tâche « {t.title} » arrive à échéance {delay_str} ({t.due_date.strftime('%d/%m/%Y')}).",
                related_object_type="Task",
                related_object_id=t.id,
            )
            counts["due_soon"] += 1

        # 2. Tâche en retard
        if t.is_late(today):
            create_notification(
                user_id=t.responsible_id,
                notif_type="task_late",
                message=f"Alerte retard : la tâche « {t.title} » est en retard (échéance dépassée le {t.due_date.strftime('%d/%m/%Y')}).",
                related_object_type="Task",
                related_object_id=t.id,
            )
            counts["late"] += 1

        # 3. Rappel de mise à jour quotidienne (si en cours et aucune mise à jour aujourd'hui)
        if t.status == TaskStatus.EN_COURS:
            has_update_today = any(u.created_at.date() == today for u in t.updates)
            if not has_update_today:
                create_notification(
                    user_id=t.responsible_id,
                    notif_type="task_update_reminder",
                    message=f"Rappel quotidien : veuillez documenter l'avancement du jour pour « {t.title} ».",
                    related_object_type="Task",
                    related_object_id=t.id,
                )
                counts["update_reminders"] += 1

    return counts
