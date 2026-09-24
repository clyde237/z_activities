from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import TaskPriority, UnexpectedActivity, User, UserRole, UserTeam
from ..services.activity_service import (
    ActivityValidationError,
    can_manage_activity,
    create_unexpected_activity,
    delete_unexpected_activity,
    get_visible_activities,
    update_unexpected_activity,
)

activities_blueprint = Blueprint("activities", __name__, url_prefix="/activities")


@activities_blueprint.get("")
@login_required
def list_activities():
    user_id_filter = request.args.get("user_id", type=int)
    activities = get_visible_activities(user=current_user, user_id=user_id_filter)

    # Utilisateurs sélectionnables pour le filtre si chef de service ou chef d'équipe
    selectable_users = []
    if current_user.is_chef_service():
        selectable_users = db.session.query(User).order_by(User.last_name, User.first_name).all()
    elif any(link.is_team_lead for link in current_user.team_links):
        led_team_ids = {link.team_id for link in current_user.team_links if link.is_team_lead}
        subordinate_ids = {
            link.user_id
            for link in db.session.query(UserTeam).filter(UserTeam.team_id.in_(led_team_ids)).all()
        }
        subordinate_ids.add(current_user.id)
        selectable_users = (
            db.session.query(User)
            .filter(User.id.in_(subordinate_ids))
            .order_by(User.last_name, User.first_name)
            .all()
        )

    return render_template(
        "activities/list.html",
        activities=activities,
        selectable_users=selectable_users,
        current_user_id=user_id_filter,
    )


@activities_blueprint.route("/new", methods=["GET", "POST"])
@login_required
def create_new_activity():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        activity_date_str = request.form.get("activity_date", "").strip()
        start_time_str = request.form.get("start_time", "").strip()
        end_time_str = request.form.get("end_time", "").strip()
        requester = request.form.get("requester", "").strip()
        priority = request.form.get("priority", TaskPriority.NORMALE.value)
        result = request.form.get("result", "").strip()

        activity_date = None
        start_time = None
        end_time = None
        errors = []

        if activity_date_str:
            try:
                activity_date = datetime.strptime(activity_date_str, "%Y-%m-%d").date()
            except ValueError:
                errors.append("Format de date invalide (AAAA-MM-JJ attendu).")

        if start_time_str:
            try:
                start_time = datetime.strptime(start_time_str, "%H:%M").time()
            except ValueError:
                errors.append("Format d'heure de début invalide (HH:MM attendu).")

        if end_time_str:
            try:
                end_time = datetime.strptime(end_time_str, "%H:%M").time()
            except ValueError:
                errors.append("Format d'heure de fin invalide (HH:MM attendu).")

        data = {
            "title": title,
            "description": description,
            "activity_date": activity_date,
            "start_time": start_time,
            "end_time": end_time,
            "requester": requester,
            "priority": priority,
            "result": result,
        }

        try:
            if errors:
                raise ActivityValidationError(errors)
            activity = create_unexpected_activity(current_user, data)
            flash(f"Activité imprévue '{activity.title}' enregistrée avec succès.", "success")
            return redirect(url_for("activities.list_activities"))
        except ActivityValidationError as e:
            for err in e.errors:
                flash(err, "error")

    return render_template(
        "activities/form.html",
        activity=None,
        priorities=TaskPriority,
        form=request.form if request.method == "POST" else None,
    )


@activities_blueprint.get("/<int:activity_id>")
@login_required
def view_activity(activity_id: int):
    activity = db.session.get(UnexpectedActivity, activity_id)
    if activity is None:
        abort(404)

    can_edit = can_manage_activity(current_user, activity)
    is_manager = current_user.is_chef_service() or any(link.is_team_lead for link in current_user.team_links)

    return render_template(
        "activities/detail.html",
        activity=activity,
        can_edit=can_edit,
        is_manager=is_manager,
    )


@activities_blueprint.route("/<int:activity_id>/edit", methods=["GET", "POST"])
@login_required
def edit_activity_route(activity_id: int):
    activity = db.session.get(UnexpectedActivity, activity_id)
    if activity is None:
        abort(404)

    if not can_manage_activity(current_user, activity):
        abort(403)

    is_manager = current_user.is_chef_service() or any(link.is_team_lead for link in current_user.team_links)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        activity_date_str = request.form.get("activity_date", "").strip()
        start_time_str = request.form.get("start_time", "").strip()
        end_time_str = request.form.get("end_time", "").strip()
        requester = request.form.get("requester", "").strip()
        priority = request.form.get("priority", activity.priority.value)
        result = request.form.get("result", "").strip()
        responsible_comment = request.form.get("responsible_comment", "").strip()

        activity_date = None
        start_time = None
        end_time = None
        errors = []

        if activity_date_str:
            try:
                activity_date = datetime.strptime(activity_date_str, "%Y-%m-%d").date()
            except ValueError:
                errors.append("Format de date invalide.")

        if start_time_str:
            try:
                start_time = datetime.strptime(start_time_str, "%H:%M").time()
            except ValueError:
                errors.append("Format d'heure de début invalide.")

        if end_time_str:
            try:
                end_time = datetime.strptime(end_time_str, "%H:%M").time()
            except ValueError:
                errors.append("Format d'heure de fin invalide.")

        data = {
            "title": title,
            "description": description,
            "activity_date": activity_date,
            "start_time": start_time,
            "end_time": end_time,
            "requester": requester,
            "priority": priority,
            "result": result,
            "responsible_comment": responsible_comment,
        }

        try:
            if errors:
                raise ActivityValidationError(errors)
            update_unexpected_activity(activity, current_user, data)
            flash("Activité imprévue mise à jour.", "success")
            return redirect(url_for("activities.view_activity", activity_id=activity.id))
        except ActivityValidationError as e:
            for err in e.errors:
                flash(err, "error")

    return render_template(
        "activities/form.html",
        activity=activity,
        priorities=TaskPriority,
        is_manager=is_manager,
        form=None,
    )


@activities_blueprint.post("/<int:activity_id>/delete")
@login_required
def delete_activity_route(activity_id: int):
    activity = db.session.get(UnexpectedActivity, activity_id)
    if activity is None:
        abort(404)

    if not can_manage_activity(current_user, activity):
        abort(403)

    delete_unexpected_activity(activity, current_user)
    flash("Activité imprévue supprimée.", "success")
    return redirect(url_for("activities.list_activities"))
