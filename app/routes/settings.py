from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Team, User

settings_blueprint = Blueprint("settings", __name__, url_prefix="/settings")


@settings_blueprint.route("", methods=["GET", "POST"])
@login_required
def settings_view():
    tab = request.args.get("tab", "general")

    if request.method == "POST":
        flash("Paramètres mis à jour avec succès.", "success")
        return redirect(url_for("settings.settings_view", tab=tab))

    teams_count = db.session.query(Team).count()
    users_count = db.session.query(User).filter_by(is_active_account=True).count()

    return render_template(
        "settings/index.html",
        active_tab=tab,
        teams_count=teams_count,
        users_count=users_count,
    )
