from datetime import date

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Task, TaskStatus, Team, UnexpectedActivity, User

dashboard_blueprint = Blueprint("dashboard", __name__)


@dashboard_blueprint.get("/")
@login_required
def index():
    today = date.today()
    supervised_teams = []
    stats = {}

    if current_user.is_chef_service():
        all_tasks = db.session.query(Task).all()
        activities_count = db.session.query(UnexpectedActivity).count()
        tasks_needing_update = sum(
            1 for t in all_tasks
            if t.status == TaskStatus.EN_COURS and not any(u.created_at.date() == today for u in t.updates)
        )
        stats = {
            "users_count": db.session.query(User).count(),
            "teams_count": db.session.query(Team).count(),
            "tasks_total": len(all_tasks),
            "tasks_in_progress": sum(1 for t in all_tasks if t.status == TaskStatus.EN_COURS),
            "tasks_completed": sum(1 for t in all_tasks if t.status == TaskStatus.TERMINEE),
            "tasks_late": sum(1 for t in all_tasks if t.is_late(today)),
            "activities_count": activities_count,
            "tasks_needing_update": tasks_needing_update,
        }
        recent_tasks = (
            db.session.query(Task)
            .filter(~Task.status.in_([TaskStatus.TERMINEE, TaskStatus.ANNULEE]))
            .order_by(Task.due_date.asc())
            .limit(5)
            .all()
        )
    else:
        for link in current_user.team_links:
            if link.is_team_lead:
                supervised_teams.append(link.team)

        my_tasks = (
            db.session.query(Task)
            .filter((Task.responsible_id == current_user.id) | (Task.co_responsible_id == current_user.id))
            .all()
        )
        activities_count = (
            db.session.query(UnexpectedActivity)
            .filter_by(user_id=current_user.id)
            .count()
        )
        tasks_needing_update = sum(
            1 for t in my_tasks
            if t.status == TaskStatus.EN_COURS and not any(u.created_at.date() == today for u in t.updates)
        )
        stats = {
            "tasks_total": len(my_tasks),
            "tasks_in_progress": sum(1 for t in my_tasks if t.status == TaskStatus.EN_COURS),
            "tasks_completed": sum(1 for t in my_tasks if t.status == TaskStatus.TERMINEE),
            "tasks_late": sum(1 for t in my_tasks if t.is_late(today)),
            "activities_count": activities_count,
            "tasks_needing_update": tasks_needing_update,
        }
        recent_tasks = [
            t for t in my_tasks if t.status not in (TaskStatus.TERMINEE, TaskStatus.ANNULEE)
        ][:5]

    return render_template(
        "dashboard/index.html",
        user=current_user,
        supervised_teams=supervised_teams,
        stats=stats,
        recent_tasks=recent_tasks,
    )
