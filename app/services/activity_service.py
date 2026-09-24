from datetime import date, time
from typing import Any

from ..extensions import db
from ..models import TaskPriority, UnexpectedActivity, User, UserRole, UserTeam
from .audit_service import log_action


class ActivityValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def can_manage_activity(user: User, activity: UnexpectedActivity) -> bool:
    """Vérifie si l'utilisateur peut modifier ou supprimer l'activité."""
    if user.role == UserRole.CHEF_SERVICE:
        return True
    if activity.user_id == user.id:
        return True
    # Un chef d'équipe peut commenter/consulter les activités des membres de ses équipes
    user_team_ids = {link.team_id for link in user.team_links if link.is_team_lead}
    author_team_ids = {link.team_id for link in activity.user.team_links}
    return bool(user_team_ids.intersection(author_team_ids))


def validate_and_build_activity_data(
    user: User,
    data: dict[str, Any],
    existing_activity: UnexpectedActivity | None = None,
) -> dict[str, Any]:
    errors = []

    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    activity_date = data.get("activity_date")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    requester = data.get("requester", "").strip()
    priority_val = data.get("priority", TaskPriority.NORMALE.value)
    result = data.get("result", "").strip()
    responsible_comment = data.get("responsible_comment", "").strip()

    if not title:
        errors.append("Le titre de l'activité imprévue est obligatoire.")

    if not activity_date:
        errors.append("La date de l'activité est obligatoire.")

    if start_time and end_time and end_time < start_time:
        errors.append("L'heure de fin ne peut pas précéder l'heure de début.")

    try:
        priority = TaskPriority(priority_val)
    except (ValueError, TypeError):
        errors.append("Priorité invalide.")
        priority = TaskPriority.NORMALE

    if errors:
        raise ActivityValidationError(errors)

    clean_data: dict[str, Any] = {
        "title": title,
        "description": description or None,
        "activity_date": activity_date,
        "start_time": start_time,
        "end_time": end_time,
        "requester": requester or None,
        "priority": priority,
        "result": result or None,
    }

    # Le commentaire du responsable ne peut être renseigné que par un encadrant (chef de service ou chef d'équipe)
    is_manager = user.is_chef_service() or any(link.is_team_lead for link in user.team_links)
    if is_manager and responsible_comment:
        clean_data["responsible_comment"] = responsible_comment
    elif existing_activity is not None and not is_manager:
        # Conserver le commentaire existant si l'auteur le modifie sans être manager
        clean_data["responsible_comment"] = existing_activity.responsible_comment
    else:
        clean_data["responsible_comment"] = responsible_comment or None

    return clean_data


def create_unexpected_activity(user: User, data: dict[str, Any]) -> UnexpectedActivity:
    clean_data = validate_and_build_activity_data(user, data)
    activity = UnexpectedActivity(user_id=user.id, **clean_data)
    db.session.add(activity)
    db.session.flush()

    log_action("create", "UnexpectedActivity", activity.id, new_value=activity.title)
    db.session.commit()
    return activity


def update_unexpected_activity(
    activity: UnexpectedActivity,
    user: User,
    data: dict[str, Any],
) -> UnexpectedActivity:
    if not can_manage_activity(user, activity):
        raise ActivityValidationError(["Vous n'avez pas l'autorisation de modifier cette activité."])

    clean_data = validate_and_build_activity_data(user, data, existing_activity=activity)

    for key, val in clean_data.items():
        setattr(activity, key, val)

    log_action("update", "UnexpectedActivity", activity.id, new_value=activity.title)
    db.session.commit()
    return activity


def delete_unexpected_activity(activity: UnexpectedActivity, user: User) -> None:
    if not can_manage_activity(user, activity):
        raise ActivityValidationError(["Vous n'avez pas l'autorisation de supprimer cette activité."])

    activity_id = activity.id
    title = activity.title
    db.session.delete(activity)
    log_action("delete", "UnexpectedActivity", activity_id, old_value=title)
    db.session.commit()


def get_visible_activities(
    user: User,
    user_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[UnexpectedActivity]:
    query = db.session.query(UnexpectedActivity)

    if user.is_chef_service():
        if user_id:
            query = query.filter(UnexpectedActivity.user_id == user_id)
    elif any(link.is_team_lead for link in user.team_links):
        # Chef d'équipe : ses équipes + les siennes
        led_team_ids = {link.team_id for link in user.team_links if link.is_team_lead}
        subordinate_ids = {
            link.user_id
            for link in db.session.query(UserTeam).filter(UserTeam.team_id.in_(led_team_ids)).all()
        }
        subordinate_ids.add(user.id)
        if user_id and user_id in subordinate_ids:
            query = query.filter(UnexpectedActivity.user_id == user_id)
        else:
            query = query.filter(UnexpectedActivity.user_id.in_(subordinate_ids))
    else:
        # Collaborateur : uniquement ses propres activités
        query = query.filter(UnexpectedActivity.user_id == user.id)

    if start_date:
        query = query.filter(UnexpectedActivity.activity_date >= start_date)
    if end_date:
        query = query.filter(UnexpectedActivity.activity_date <= end_date)

    return query.order_by(UnexpectedActivity.activity_date.desc(), UnexpectedActivity.created_at.desc()).all()
