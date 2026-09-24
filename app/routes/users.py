from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Team, User, UserRole, UserTeam
from ..permissions import chef_service_required
from ..services.audit_service import log_action

users_blueprint = Blueprint("users", __name__, url_prefix="/users")

MIN_PASSWORD_LENGTH = 8


@users_blueprint.get("")
@login_required
@chef_service_required
def list_users():
    users = db.session.query(User).order_by(User.last_name, User.first_name).all()
    return render_template("users/list.html", users=users)


@users_blueprint.route("/new", methods=["GET", "POST"])
@login_required
@chef_service_required
def create_user():
    teams = db.session.query(Team).order_by(Team.name).all()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        function = request.form.get("function", "").strip()
        role = request.form.get("role", UserRole.COLLABORATEUR.value)
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        team_id = request.form.get("team_id", type=int)
        is_team_lead = request.form.get("is_team_lead") == "on"

        errors = []
        if not username or not first_name or not last_name:
            errors.append("Identifiant, prénom et nom sont obligatoires.")
        if role not in {r.value for r in UserRole}:
            errors.append("Rôle invalide.")
        if len(password) < MIN_PASSWORD_LENGTH:
            errors.append(
                f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères."
            )
        if password != password_confirm:
            errors.append("Les mots de passe ne correspondent pas.")
        if team_id is not None and db.session.get(Team, team_id) is None:
            errors.append("L'équipe sélectionnée est invalide.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "users/form.html",
                user=None,
                roles=UserRole,
                form=request.form,
                teams=teams,
            )

        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            function=function or None,
            role=UserRole(role),
        )
        user.set_password(password)

        try:
            db.session.add(user)
            db.session.flush()
            if team_id is not None:
                db.session.add(UserTeam(user_id=user.id, team_id=team_id, is_team_lead=is_team_lead))
            log_action("create", "User", user.id, new_value=username)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(f"L'identifiant '{username}' est déjà utilisé.", "error")
            return render_template(
                "users/form.html",
                user=None,
                roles=UserRole,
                form=request.form,
                teams=teams,
            )

        flash(f"Utilisateur '{username}' créé.", "success")
        return redirect(url_for("users.list_users"))

    return render_template("users/form.html", user=None, roles=UserRole, form=None, teams=teams)


@users_blueprint.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@chef_service_required
def edit_user(user_id: int):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        function = request.form.get("function", "").strip()
        role = request.form.get("role", user.role.value)
        is_active_account = request.form.get("is_active_account") == "on"
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        errors = []
        if not first_name or not last_name:
            errors.append("Prénom et nom sont obligatoires.")
        if role not in {r.value for r in UserRole}:
            errors.append("Rôle invalide.")
        if password and len(password) < MIN_PASSWORD_LENGTH:
            errors.append(
                f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères."
            )
        if password and password != password_confirm:
            errors.append("Les mots de passe ne correspondent pas.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "users/form.html", user=user, roles=UserRole, form=request.form
            )

        old_role = user.role.value
        old_active = user.is_active_account

        user.first_name = first_name
        user.last_name = last_name
        user.function = function or None
        user.role = UserRole(role)
        user.is_active_account = is_active_account
        if password:
            user.set_password(password)

        if old_role != user.role.value or old_active != user.is_active_account:
            log_action(
                "update",
                "User",
                user.id,
                old_value=f"role={old_role} active={old_active}",
                new_value=f"role={user.role.value} active={user.is_active_account}",
            )

        db.session.commit()
        flash("Utilisateur mis à jour.", "success")
        return redirect(url_for("users.edit_user", user_id=user.id))

    teams = db.session.query(Team).order_by(Team.name).all()
    return render_template(
        "users/form.html", user=user, roles=UserRole, form=None, teams=teams
    )


@users_blueprint.post("/<int:user_id>/teams")
@login_required
@chef_service_required
def assign_team(user_id: int):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)

    team_id = request.form.get("team_id", type=int)
    is_team_lead = request.form.get("is_team_lead") == "on"
    team = db.session.get(Team, team_id) if team_id else None

    if team is None:
        flash("Équipe invalide.", "error")
        return redirect(url_for("users.edit_user", user_id=user.id))

    existing = (
        db.session.query(UserTeam)
        .filter_by(user_id=user.id, team_id=team.id)
        .one_or_none()
    )
    if existing:
        flash(f"{user.full_name} est déjà dans l'équipe {team.name}.", "error")
        return redirect(url_for("users.edit_user", user_id=user.id))

    link = UserTeam(user_id=user.id, team_id=team.id, is_team_lead=is_team_lead)
    db.session.add(link)
    log_action(
        "assign_team", "User", user.id, new_value=f"team={team.name} lead={is_team_lead}"
    )
    db.session.commit()

    flash(f"{user.full_name} affecté à l'équipe {team.name}.", "success")
    return redirect(url_for("users.edit_user", user_id=user.id))


@users_blueprint.post("/<int:user_id>/teams/<int:team_id>/remove")
@login_required
@chef_service_required
def remove_team(user_id: int, team_id: int):
    link = (
        db.session.query(UserTeam)
        .filter_by(user_id=user_id, team_id=team_id)
        .one_or_none()
    )
    if link is None:
        abort(404)

    team_name = link.team.name
    db.session.delete(link)
    log_action("remove_team", "User", user_id, old_value=f"team={team_name}")
    db.session.commit()

    flash("Affectation retirée.", "success")
    return redirect(url_for("users.edit_user", user_id=user_id))


@users_blueprint.post("/<int:user_id>/teams/<int:team_id>/toggle-lead")
@login_required
@chef_service_required
def toggle_team_lead(user_id: int, team_id: int):
    link = (
        db.session.query(UserTeam)
        .filter_by(user_id=user_id, team_id=team_id)
        .one_or_none()
    )
    if link is None:
        abort(404)

    old_value = link.is_team_lead
    link.is_team_lead = not link.is_team_lead
    log_action(
        "toggle_team_lead",
        "UserTeam",
        link.id,
        old_value=str(old_value),
        new_value=str(link.is_team_lead),
    )
    db.session.commit()

    flash("Statut de chef d'équipe mis à jour.", "success")
    return redirect(url_for("users.edit_user", user_id=user_id))
