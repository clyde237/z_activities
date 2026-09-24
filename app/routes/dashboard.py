from flask import Blueprint, render_template
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Team, User

dashboard_blueprint = Blueprint("dashboard", __name__)


@dashboard_blueprint.get("/")
@login_required
def index():
    supervised_teams = []
    stats = {}

    if current_user.is_chef_service():
        stats = {
            "users_count": db.session.query(User).count(),
            "teams_count": db.session.query(Team).count(),
        }
    else:
        for link in current_user.team_links:
            if link.is_team_lead:
                supervised_teams.append(link.team)

    return render_template(
        "dashboard/index.html",
        user=current_user,
        supervised_teams=supervised_teams,
        stats=stats,
    )
