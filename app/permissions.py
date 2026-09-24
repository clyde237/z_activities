from functools import wraps

from flask import abort
from flask_login import current_user

from .models import User, UserRole


def roles_required(*roles: UserRole):
    """Vérifie l'autorisation (le rôle), pas l'authentification.

    S'utilise après @login_required : Flask-Login répond déjà "qui est
    l'utilisateur ?" avant que ce décorateur ne réponde "a-t-il le droit ?"
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def chef_service_required(view):
    return roles_required(UserRole.CHEF_SERVICE)(view)


def can_access_team(user: User, team_id: int) -> bool:
    """Section 32 : un membre/chef d'équipe n'a pas de vue hors de son périmètre.
    Le chef de service a une vision globale (section 5.1)."""
    if user.role == UserRole.CHEF_SERVICE:
        return True
    return team_id in user.team_ids()


def can_lead_team(user: User, team_id: int) -> bool:
    """Droits de chef d'équipe sur CETTE équipe précise (section 5.2)."""
    if user.role == UserRole.CHEF_SERVICE:
        return True
    return user.is_team_lead_of(team_id)


def can_create_task(user: User, team_id: int | None = None) -> bool:
    """RB-004 : Le chef de service et les chefs d'équipe peuvent planifier des tâches."""
    if user.role == UserRole.CHEF_SERVICE:
        return True
    if team_id is not None:
        return user.is_team_lead_of(team_id)
    return any(link.is_team_lead for link in user.team_links)


def can_view_task(user: User, task) -> bool:
    """Vérifie si l'utilisateur a le droit de consulter la tâche."""
    if user.role == UserRole.CHEF_SERVICE:
        return True
    if user.is_team_lead_of(task.team_id):
        return True
    if user.id in {task.responsible_id, task.co_responsible_id}:
        return True
    return task.team_id in user.team_ids()


def can_edit_task(user: User, task) -> bool:
    """RB-013 : un membre ne modifie pas les infos structurantes d'une tâche
    qui lui est affectée. Seuls le chef de service et le chef d'équipe de
    l'équipe concernée peuvent modifier une tâche."""
    if user.role == UserRole.CHEF_SERVICE:
        return True
    return user.is_team_lead_of(task.team_id)


def can_update_task_progress(user: User, task) -> bool:
    """Le responsable ou le co-responsable peut renseigner l'avancement
    (RB-008, RB-009), en plus des rôles d'encadrement."""
    if can_edit_task(user, task):
        return True
    return user.id in {task.responsible_id, task.co_responsible_id}

