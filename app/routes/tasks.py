from datetime import datetime

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Task, TaskPriority, TaskStatus, TaskType, Team
from ..permissions import can_create_task, can_edit_task, can_update_task_progress, can_view_task
from ..services.task_service import (
    TaskValidationError,
    add_task_update,
    create_task,
    get_assignable_members,
    get_visible_tasks,
    has_updated_today,
    update_task,
)

tasks_blueprint = Blueprint("tasks", __name__, url_prefix="/tasks")


def _get_creatable_teams_for_user(user) -> list[Team]:
    """Retourne la liste des équipes dans lesquelles l'utilisateur peut créer des tâches."""
    if user.is_chef_service():
        return db.session.query(Team).order_by(Team.name).all()
    led_ids = {link.team_id for link in user.team_links if link.is_team_lead}
    return db.session.query(Team).filter(Team.id.in_(led_ids)).order_by(Team.name).all()


@tasks_blueprint.get("")
@login_required
def list_tasks():
    team_id = request.args.get("team_id", type=int)
    status_str = request.args.get("status")
    filter_mode = request.args.get("filter", "all")

    status = None
    if status_str:
        try:
            status = TaskStatus(status_str)
        except ValueError:
            pass

    only_mine = filter_mode == "mine"
    only_late = filter_mode == "late"

    tasks = get_visible_tasks(
        user=current_user,
        team_id=team_id,
        status=status,
        only_mine=only_mine,
        only_late=only_late,
    )

    # Équipes accessibles pour le filtre
    if current_user.is_chef_service():
        filter_teams = db.session.query(Team).order_by(Team.name).all()
    else:
        user_team_ids = current_user.team_ids()
        filter_teams = (
            db.session.query(Team)
            .filter(Team.id.in_(user_team_ids))
            .order_by(Team.name)
            .all()
        )

    can_create = can_create_task(current_user)

    return render_template(
        "tasks/list.html",
        tasks=tasks,
        filter_teams=filter_teams,
        current_team_id=team_id,
        current_status=status_str,
        current_filter=filter_mode,
        can_create=can_create,
        statuses=TaskStatus,
    )


@tasks_blueprint.get("/teams/<int:team_id>/members")
@login_required
def team_members(team_id: int):
    """Retourne les membres éligibles pour affectation d'une tâche."""
    members = get_assignable_members(team_id)
    return jsonify([{"id": m.id, "name": m.full_name} for m in members])


@tasks_blueprint.route("/new", methods=["GET", "POST"])
@login_required
def create_new_task():
    if not can_create_task(current_user):
        abort(403)

    creatable_teams = _get_creatable_teams_for_user(current_user)

    if request.method == "POST":
        team_id = request.form.get("team_id", type=int)
        responsible_id = request.form.get("responsible_id", type=int)
        co_responsible_id = request.form.get("co_responsible_id", type=int)
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", TaskPriority.NORMALE.value)
        task_type = request.form.get("task_type", TaskType.QUALITATIVE.value)
        objective = request.form.get("objective")
        progress = request.form.get("progress")
        realized = request.form.get("realized")
        comment = request.form.get("comment", "").strip()

        start_date_str = request.form.get("start_date", "").strip()
        due_date_str = request.form.get("due_date", "").strip()

        start_date = None
        due_date = None
        date_errors = []
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            except ValueError:
                date_errors.append("Format de date de début invalide (AAAA-MM-JJ attendu).")
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            except ValueError:
                date_errors.append("Format d'échéance invalide (AAAA-MM-JJ attendu).")

        data = {
            "title": title,
            "description": description,
            "team_id": team_id,
            "responsible_id": responsible_id,
            "co_responsible_id": co_responsible_id,
            "start_date": start_date,
            "due_date": due_date,
            "priority": priority,
            "task_type": task_type,
            "objective": objective,
            "progress": progress,
            "realized": realized,
            "status": TaskStatus.A_FAIRE.value,
            "comment": comment,
        }

        try:
            if date_errors:
                raise TaskValidationError(date_errors)
            task = create_task(current_user, data)
            flash(f"Tâche '{task.title}' créée avec succès.", "success")
            return redirect(url_for("tasks.view_task", task_id=task.id))
        except TaskValidationError as e:
            for err in e.errors:
                flash(err, "error")

            assignable_members = get_assignable_members(team_id) if team_id else []
            return render_template(
                "tasks/form.html",
                task=None,
                teams=creatable_teams,
                assignable_members=assignable_members,
                priorities=TaskPriority,
                task_types=TaskType,
                statuses=TaskStatus,
                form=request.form,
            )

    selected_team_id = creatable_teams[0].id if creatable_teams else None
    assignable_members = get_assignable_members(selected_team_id) if selected_team_id else []

    return render_template(
        "tasks/form.html",
        task=None,
        teams=creatable_teams,
        assignable_members=assignable_members,
        priorities=TaskPriority,
        task_types=TaskType,
        statuses=TaskStatus,
        form=None,
    )


@tasks_blueprint.get("/<int:task_id>")
@login_required
def view_task(task_id: int):
    task = db.session.get(Task, task_id)
    if task is None:
        abort(404)

    if not can_view_task(current_user, task):
        abort(403)

    can_edit = can_edit_task(current_user, task)
    can_update = can_update_task_progress(current_user, task)
    updated_today = has_updated_today(task)

    return render_template(
        "tasks/detail.html",
        task=task,
        can_edit=can_edit,
        can_update=can_update,
        updated_today=updated_today,
        statuses=TaskStatus,
    )


@tasks_blueprint.route("/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit_task_route(task_id: int):
    task = db.session.get(Task, task_id)
    if task is None:
        abort(404)

    if not can_edit_task(current_user, task):
        abort(403)

    creatable_teams = _get_creatable_teams_for_user(current_user)
    assignable_members = get_assignable_members(task.team_id)

    if request.method == "POST":
        team_id = request.form.get("team_id", type=int)
        responsible_id = request.form.get("responsible_id", type=int)
        co_responsible_id = request.form.get("co_responsible_id", type=int)
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", task.priority.value)
        task_type = request.form.get("task_type", task.task_type.value)
        objective = request.form.get("objective")
        progress = request.form.get("progress")
        realized = request.form.get("realized")
        status = request.form.get("status", task.status.value)
        comment = request.form.get("comment", "").strip()

        start_date_str = request.form.get("start_date", "").strip()
        due_date_str = request.form.get("due_date", "").strip()

        start_date = None
        due_date = None
        date_errors = []
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            except ValueError:
                date_errors.append("Format de date de début invalide.")
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            except ValueError:
                date_errors.append("Format d'échéance invalide.")

        data = {
            "title": title,
            "description": description,
            "team_id": team_id,
            "responsible_id": responsible_id,
            "co_responsible_id": co_responsible_id,
            "start_date": start_date,
            "due_date": due_date,
            "priority": priority,
            "task_type": task_type,
            "objective": objective,
            "progress": progress,
            "realized": realized,
            "status": status,
            "comment": comment,
        }

        try:
            if date_errors:
                raise TaskValidationError(date_errors)
            update_task(task, current_user, data)
            flash("Tâche mise à jour avec succès.", "success")
            return redirect(url_for("tasks.view_task", task_id=task.id))
        except TaskValidationError as e:
            for err in e.errors:
                flash(err, "error")

    return render_template(
        "tasks/form.html",
        task=task,
        teams=creatable_teams,
        assignable_members=assignable_members,
        priorities=TaskPriority,
        task_types=TaskType,
        statuses=TaskStatus,
        form=None,
    )


@tasks_blueprint.post("/<int:task_id>/updates")
@login_required
def add_update_to_task(task_id: int):
    task = db.session.get(Task, task_id)
    if task is None:
        abort(404)

    if not can_update_task_progress(current_user, task):
        abort(403)

    data = {
        "work_done": request.form.get("work_done", ""),
        "difficulties": request.form.get("difficulties", ""),
        "next_step": request.form.get("next_step", ""),
        "progress": request.form.get("progress"),
        "realized": request.form.get("realized"),
        "status": request.form.get("status"),
    }

    try:
        add_task_update(task, current_user, data)
        flash("Mise à jour quotidienne enregistrée avec succès.", "success")
    except TaskValidationError as e:
        for err in e.errors:
            flash(err, "error")

    return redirect(url_for("tasks.view_task", task_id=task.id))

