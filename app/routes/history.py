from datetime import datetime

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Team, User, UserTeam
from ..services.history_service import (
    get_accessible_user_ids,
    search_history as search_history_service,
)

history_blueprint = Blueprint("history", __name__, url_prefix="/history")


@history_blueprint.get("", endpoint="search_history")
@login_required
def search_history_view():
    q = request.args.get("q", "").strip()
    user_id_arg = request.args.get("user_id", type=int)
    team_id_arg = request.args.get("team_id", type=int)
    entity_type = request.args.get("type", "all")
    start_str = request.args.get("start_date", "").strip()
    end_str = request.args.get("end_date", "").strip()

    start_date = None
    if start_str:
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    end_date = None
    if end_str:
        try:
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    results = search_history_service(
        current_user=current_user,
        q=q or None,
        user_id=user_id_arg,
        team_id=team_id_arg,
        start_date=start_date,
        end_date=end_date,
        entity_type=entity_type,
    )

    # Récupération des filtres accessibles
    accessible_ids = get_accessible_user_ids(current_user)
    selectable_users = []
    selectable_teams = []

    if current_user.is_chef_service():
        selectable_users = db.session.query(User).order_by(User.last_name, User.first_name).all()
        selectable_teams = db.session.query(Team).order_by(Team.name).all()
    elif accessible_ids is not None:
        selectable_users = (
            db.session.query(User)
            .filter(User.id.in_(accessible_ids))
            .order_by(User.last_name, User.first_name)
            .all()
        )
        led_team_ids = {link.team_id for link in current_user.team_links if link.is_team_lead}
        selectable_teams = db.session.query(Team).filter(Team.id.in_(led_team_ids)).all()

    return render_template(
        "history/index.html",
        results=results,
        q=q,
        current_user_id=user_id_arg,
        current_team_id=team_id_arg,
        current_type=entity_type,
        current_start_date=start_str,
        current_end_date=end_str,
        selectable_users=selectable_users,
        selectable_teams=selectable_teams,
    )
