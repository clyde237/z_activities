from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Team
from ..permissions import chef_service_required
from ..services.audit_service import log_action

teams_blueprint = Blueprint("teams", __name__, url_prefix="/teams")


@teams_blueprint.get("")
@login_required
@chef_service_required
def list_teams():
    teams = db.session.query(Team).order_by(Team.name).all()
    return render_template("teams/list.html", teams=teams)


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
