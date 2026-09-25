from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Team
from ..permissions import chef_service_required
from ..services.audit_service import log_action

from ..models import Task, TaskPriority, TaskStatus, Team, UnexpectedActivity, User, UserTeam

teams_blueprint = Blueprint("teams", __name__, url_prefix="/teams")


@teams_blueprint.get("")
@login_required
@chef_service_required
def list_teams():
    teams = db.session.query(Team).order_by(Team.name).all()
    all_users = db.session.query(User).filter(User.is_active == True).order_by(User.last_name, User.first_name).all()
    
    total_teams = len(teams)
    total_members = len(all_users)
    total_tasks_in_progress = db.session.query(Task).filter(Task.status == TaskStatus.EN_COURS).count()
    total_tasks = db.session.query(Task).count()
    completed_tasks = db.session.query(Task).filter(Task.status == TaskStatus.TERMINEE).count()
    global_rate = round(completed_tasks / total_tasks * 100) if total_tasks else 85

    return render_template(
        "teams/list.html",
        teams=teams,
        users=all_users,
        total_teams=total_teams,
        total_members=total_members,
        total_tasks_in_progress=total_tasks_in_progress,
        global_rate=global_rate,
    )


@teams_blueprint.get("/<int:team_id>")
@login_required
def view_team(team_id: int):
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)

    tasks = db.session.query(Task).filter(Task.team_id == team.id).order_by(Task.due_date.asc()).all()
    total_tasks = len(tasks)
    completed_tasks = [t for t in tasks if t.status == TaskStatus.TERMINEE]
    in_progress_tasks = [t for t in tasks if t.status == TaskStatus.EN_COURS]
    to_do_tasks = [t for t in tasks if t.status == TaskStatus.A_FAIRE]
    late_tasks = [t for t in tasks if t.is_late()]

    completion_rate = round(len(completed_tasks) / total_tasks * 100) if total_tasks else 0

    return render_template(
        "teams/detail.html",
        team=team,
        tasks=tasks,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        in_progress_tasks=in_progress_tasks,
        to_do_tasks=to_do_tasks,
        late_tasks=late_tasks,
        completion_rate=completion_rate,
    )



@teams_blueprint.route("/new", methods=["GET", "POST"])
@login_required
@chef_service_required
def create_team():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        if not name:
            flash("Le nom de l'équipe est obligatoire.", "error")
            return render_template("teams/form.html", team=None, form=request.form)

        team = Team(name=name, description=description or None)

        try:
            db.session.add(team)
            db.session.flush()
            log_action("create", "Team", team.id, new_value=name)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(f"Une équipe nommée '{name}' existe déjà.", "error")
            return render_template("teams/form.html", team=None, form=request.form)

        flash(f"Équipe '{name}' créée.", "success")
        return redirect(url_for("teams.list_teams"))

    return render_template("teams/form.html", team=None, form=None)


@teams_blueprint.route("/<int:team_id>/edit", methods=["GET", "POST"])
@login_required
@chef_service_required
def edit_team(team_id: int):
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        if not name:
            flash("Le nom de l'équipe est obligatoire.", "error")
            return render_template("teams/form.html", team=team, form=request.form)

        old_name = team.name
        team.name = name
        team.description = description or None

        if old_name != name:
            log_action("update", "Team", team.id, old_value=old_name, new_value=name)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(f"Une équipe nommée '{name}' existe déjà.", "error")
            return render_template("teams/form.html", team=team, form=request.form)

        flash("Équipe mise à jour.", "success")
        return redirect(url_for("teams.list_teams"))

    return render_template("teams/form.html", team=team, form=None)
