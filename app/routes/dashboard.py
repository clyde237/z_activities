from flask import Blueprint, render_template
from flask_login import current_user, login_required

dashboard_blueprint = Blueprint("dashboard", __name__)


@dashboard_blueprint.get("/")
@login_required
def index():
    return render_template("dashboard/index.html", user=current_user)
