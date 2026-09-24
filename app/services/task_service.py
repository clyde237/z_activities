from datetime import date
from typing import Any

from ..extensions import db
from ..models import Task, TaskPriority, TaskStatus, TaskType, Team, User, UserRole, UserTeam
from ..permissions import can_create_task, can_edit_task
from .audit_service import log_action


class TaskValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def get_assignable_members(team_id: int) -> list[User]:
    """Retourne la liste des utilisateurs actifs membres d'une équipe donnée."""
    return (
        db.session.query(User)
        .join(UserTeam, User.id == UserTeam.user_id)
        .filter(UserTeam.team_id == team_id, User.is_active_account.is_(True))
        .order_by(User.last_name, User.first_name)
        .all()
    )


def validate_and_build_task_data(
    user: User,
    data: dict[str, Any],
    existing_task: Task | None = None,
) -> dict[str, Any]:
    errors = []

    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    team_id = data.get("team_id")
    responsible_id = data.get("responsible_id")
    co_responsible_id = data.get("co_responsible_id")
    start_date = data.get("start_date")
    due_date = data.get("due_date")
    priority_val = data.get("priority", TaskPriority.NORMALE.value)
    task_type_val = data.get("task_type", TaskType.QUALITATIVE.value)
    objective_val = data.get("objective")
    realized_val = data.get("realized", 0.0)
    progress_val = data.get("progress", 0.0)
    status_val = data.get("status", TaskStatus.A_FAIRE.value)
    comment = data.get("comment", "").strip()

    if not title:
        errors.append("Le titre de la tâche est obligatoire.")

    if team_id is None:
        errors.append("L'équipe est obligatoire.")
    else:
        team = db.session.get(Team, team_id)
        if team is None:
            errors.append("L'équipe sélectionnée est invalide.")
        elif not can_create_task(user, team_id):
            errors.append("Vous n'avez pas l'autorisation d'affecter des tâches à cette équipe.")

    # Validation des dates
    if not start_date or not due_date:
        errors.append("Les dates de début et d'échéance sont obligatoires.")
    elif due_date < start_date:
        errors.append("La date d'échéance ne peut pas être antérieure à la date de début.")

    # Validation des responsables (RB-006 : max 2 responsables, distincts et membres de l'équipe)
    if team_id is not None:
        team_member_ids = {
            m.id for m in get_assignable_members(team_id)
        }
        if not responsible_id:
            errors.append("Le responsable principal est obligatoire.")
        elif responsible_id not in team_member_ids:
            errors.append("Le responsable principal doit être un membre actif de l'équipe sélectionnée.")

        if co_responsible_id:
            if co_responsible_id == responsible_id:
                errors.append("Le co-responsable doit être différent du responsable principal.")
            elif co_responsible_id not in team_member_ids:
                errors.append("Le co-responsable doit être un membre actif de l'équipe sélectionnée.")

    # Validation Priorité
    try:
        priority = TaskPriority(priority_val)
    except (ValueError, TypeError):
        errors.append("Priorité invalide.")
        priority = TaskPriority.NORMALE

    # Validation Type et Progression (RB-010, RB-011, RB-012)
    try:
        task_type = TaskType(task_type_val)
    except (ValueError, TypeError):
        errors.append("Type de tâche invalide.")
        task_type = TaskType.QUALITATIVE

    clean_objective = None
    clean_realized = 0.0
    clean_progress = 0.0

    if task_type == TaskType.QUANTITATIVE:
        try:
            clean_objective = float(objective_val) if objective_val is not None else None
            if clean_objective is None or clean_objective <= 0:
                errors.append("Pour une tâche quantitative, l'objectif doit être un nombre strictement positif.")
        except (ValueError, TypeError):
            errors.append("L'objectif quantitatif doit être une valeur numérique valide.")

        try:
            clean_realized = float(realized_val) if realized_val else 0.0
            if clean_realized < 0:
                errors.append("La valeur réalisée ne peut pas être négative.")
        except (ValueError, TypeError):
            errors.append("La valeur réalisée doit être numérique.")

        if clean_objective and clean_objective > 0:
            clean_progress = min(100.0, round((clean_realized / clean_objective) * 100, 2))
    else:
        # Qualitative : saisie manuelle de la progression
        try:
            clean_progress = float(progress_val) if progress_val is not None else 0.0
            if clean_progress < 0 or clean_progress > 100:
                errors.append("La progression doit être comprise entre 0 et 100 %.")
        except (ValueError, TypeError):
            errors.append("La progression doit être une valeur numérique.")

    # Validation Statut & Transitions
    try:
        status = TaskStatus(status_val)
    except (ValueError, TypeError):
        errors.append("Statut de tâche invalide.")
        status = TaskStatus.A_FAIRE

    if existing_task is not None and status != existing_task.status:
        if not existing_task.can_transition_to(status):
            errors.append(
                f"Transition de statut non autorisée depuis '{existing_task.status.value}' vers '{status.value}'."
            )

    if errors:
        raise TaskValidationError(errors)

    return {
        "title": title,
        "description": description or None,
        "team_id": team_id,
        "responsible_id": responsible_id,
        "co_responsible_id": co_responsible_id or None,
        "start_date": start_date,
        "due_date": due_date,
        "priority": priority,
        "task_type": task_type,
        "objective": clean_objective,
        "realized": clean_realized,
        "progress": clean_progress,
        "status": status,
        "comment": comment or None,
    }


def create_task(user: User, data: dict[str, Any]) -> Task:
    clean_data = validate_and_build_task_data(user, data)
    task = Task(**clean_data)
    db.session.add(task)
    db.session.flush()

    log_action("create", "Task", task.id, new_value=f"title={task.title} team_id={task.team_id}")
    db.session.commit()
    return task


def update_task(task: Task, user: User, data: dict[str, Any]) -> Task:
    if not can_edit_task(user, task):
        raise TaskValidationError(["Vous n'avez pas l'autorisation de modifier cette tâche."])

    clean_data = validate_and_build_task_data(user, data, existing_task=task)

    old_status = task.status.value
    old_responsible_id = task.responsible_id

    for key, val in clean_data.items():
        setattr(task, key, val)

    log_action(
        "update",
        "Task",
        task.id,
        old_value=f"status={old_status} resp={old_responsible_id}",
        new_value=f"status={task.status.value} resp={task.responsible_id}",
    )
    db.session.commit()
    return task


def get_visible_tasks(
    user: User,
    team_id: int | None = None,
    status: TaskStatus | None = None,
    only_mine: bool = False,
    only_late: bool = False,
) -> list[Task]:
    query = db.session.query(Task)

    if only_mine or user.role == UserRole.COLLABORATEUR and not any(l.is_team_lead for l in user.team_links):
        query = query.filter((Task.responsible_id == user.id) | (Task.co_responsible_id == user.id))
    elif user.role == UserRole.COLLABORATEUR:
        # Chef d'équipe : ses équipes dirigées + ses propres tâches
        led_team_ids = {link.team_id for link in user.team_links if link.is_team_lead}
        query = query.filter(
            Task.team_id.in_(led_team_ids)
            | (Task.responsible_id == user.id)
            | (Task.co_responsible_id == user.id)
        )

    if team_id is not None:
        query = query.filter(Task.team_id == team_id)

    if status is not None:
        query = query.filter(Task.status == status)

    if only_late:
        today = date.today()
        query = query.filter(
            Task.due_date < today,
            ~Task.status.in_([TaskStatus.TERMINEE, TaskStatus.ANNULEE]),
        )

    return query.order_by(Task.due_date.asc(), Task.priority.desc()).all()
