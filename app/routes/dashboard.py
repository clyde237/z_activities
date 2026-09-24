from datetime import date

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from ..extensions import db
from ..models import (
    Task,
    TaskStatus,
    Team,
    UnexpectedActivity,
    User,
    UserTeam,
    WeeklyReport,
    WeeklyReportStatus,
)
from ..services.report_service import get_week_bounds

dashboard_blueprint = Blueprint("dashboard", __name__)


@dashboard_blueprint.get("/")
@login_required
def index():
    today = date.today()
    week_start, week_end = get_week_bounds(today)
    supervised_teams = []
    stats = {}

    # Rapport hebdomadaire personnel pour la semaine courante
    my_weekly_report = (
        db.session.query(WeeklyReport)
        .filter_by(user_id=current_user.id, period_start=week_start)
        .one_or_none()
    )

    pending_reports_count = 0
    teams_progress = []
    members_progress = []
    chart_status_data = {}
    chart_teams_data = {}

    if current_user.is_chef_service():
        all_tasks = db.session.query(Task).all()
        activities_count = db.session.query(UnexpectedActivity).count()
        pending_reports_count = (
            db.session.query(WeeklyReport)
            .filter_by(status=WeeklyReportStatus.SOUMIS)
            .count()
        )
        tasks_needing_update = sum(
            1 for t in all_tasks
            if t.status == TaskStatus.EN_COURS and not any(u.created_at.date() == today for u in t.updates)
        )
        stats = {
            "users_count": db.session.query(User).filter_by(is_active_account=True).count(),
            "teams_count": db.session.query(Team).count(),
            "tasks_total": len(all_tasks),
            "tasks_in_progress": sum(1 for t in all_tasks if t.status == TaskStatus.EN_COURS),
            "tasks_completed": sum(1 for t in all_tasks if t.status == TaskStatus.TERMINEE),
            "tasks_late": sum(1 for t in all_tasks if t.is_late(today)),
            "activities_count": activities_count,
            "tasks_needing_update": tasks_needing_update,
            "pending_reports_count": pending_reports_count,
        }
        recent_tasks = (
            db.session.query(Task)
            .filter(~Task.status.in_([TaskStatus.TERMINEE, TaskStatus.ANNULEE]))
            .order_by(Task.due_date.asc())
            .limit(5)
            .all()
        )

        # Progression par équipe (CDC Section 18)
        all_teams = db.session.query(Team).all()
        for tm in all_teams:
            t_tasks = [t for t in all_tasks if t.team_id == tm.id]
            completed = sum(1 for t in t_tasks if t.status == TaskStatus.TERMINEE)
            in_prog = sum(1 for t in t_tasks if t.status == TaskStatus.EN_COURS)
            late = sum(1 for t in t_tasks if t.is_late(today))
            avg_p = round(sum(t.progress for t in t_tasks) / len(t_tasks)) if t_tasks else 0
            teams_progress.append({
                "id": tm.id,
                "name": tm.name,
                "total_tasks": len(t_tasks),
                "completed": completed,
                "in_progress": in_prog,
                "late": late,
                "avg_progress": avg_p,
            })

        # Progression par membre (CDC Section 18)
        active_users = db.session.query(User).filter_by(is_active_account=True).order_by(User.last_name, User.first_name).all()
        user_reports = {
            r.user_id: r
            for r in db.session.query(WeeklyReport).filter_by(period_start=week_start).all()
        }
        for u in active_users:
            u_tasks = [t for t in all_tasks if t.responsible_id == u.id or t.co_responsible_id == u.id]
            u_completed = sum(1 for t in u_tasks if t.status == TaskStatus.TERMINEE)
            u_in_prog = sum(1 for t in u_tasks if t.status == TaskStatus.EN_COURS)
            u_late = sum(1 for t in u_tasks if t.is_late(today))
            u_avg_p = round(sum(t.progress for t in u_tasks) / len(u_tasks)) if u_tasks else 0
            u_has_updated = any(
                any(up.created_at.date() == today and up.user_id == u.id for up in t.updates)
                for t in u_tasks
            )
            rep = user_reports.get(u.id)
            members_progress.append({
                "id": u.id,
                "full_name": u.full_name,
                "username": u.username,
                "role": u.role.value,
                "teams": [link.team.name for link in u.team_links if link.team],
                "total_tasks": len(u_tasks),
                "completed": u_completed,
                "in_progress": u_in_prog,
                "late": u_late,
                "avg_progress": u_avg_p,
                "has_updated_today": u_has_updated,
                "report_status": rep.status.value if rep else "non initialisé",
            })

        # Données graphiques Chart.js (CDC Section 18 & 30)
        chart_status_data = {
            "labels": ["À faire", "En cours", "À valider", "Terminée", "Bloquée", "Reportée", "Annulée"],
            "counts": [
                sum(1 for t in all_tasks if t.status == TaskStatus.A_FAIRE),
                sum(1 for t in all_tasks if t.status == TaskStatus.EN_COURS),
                sum(1 for t in all_tasks if t.status == TaskStatus.A_VALIDER),
                sum(1 for t in all_tasks if t.status == TaskStatus.TERMINEE),
                sum(1 for t in all_tasks if t.status == TaskStatus.BLOQUEE),
                sum(1 for t in all_tasks if t.status == TaskStatus.REPORTEE),
                sum(1 for t in all_tasks if t.status == TaskStatus.ANNULEE),
            ],
        }
        chart_teams_data = {
            "labels": [tp["name"] for tp in teams_progress],
            "progress": [tp["avg_progress"] for tp in teams_progress],
            "tasks_count": [tp["total_tasks"] for tp in teams_progress],
        }

    else:
        # Chef d'équipe ou collaborateur
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

        # Si chef d'équipe : suivi opérationnel de son équipe (CDC Section 19)
        if supervised_teams:
            led_team_ids = [tm.id for tm in supervised_teams]
            team_tasks = db.session.query(Task).filter(Task.team_id.in_(led_team_ids)).all()
            for tm in supervised_teams:
                t_tasks = [t for t in team_tasks if t.team_id == tm.id]
                completed = sum(1 for t in t_tasks if t.status == TaskStatus.TERMINEE)
                in_prog = sum(1 for t in t_tasks if t.status == TaskStatus.EN_COURS)
                late = sum(1 for t in t_tasks if t.is_late(today))
                avg_p = round(sum(t.progress for t in t_tasks) / len(t_tasks)) if t_tasks else 0
                teams_progress.append({
                    "id": tm.id,
                    "name": tm.name,
                    "total_tasks": len(t_tasks),
                    "completed": completed,
                    "in_progress": in_prog,
                    "late": late,
                    "avg_progress": avg_p,
                })

            subordinate_links = (
                db.session.query(UserTeam)
                .filter(UserTeam.team_id.in_(led_team_ids))
                .all()
            )
            subordinate_user_ids = {link.user_id for link in subordinate_links}
            subordinates = db.session.query(User).filter(User.id.in_(subordinate_user_ids)).all()
            user_reports = {
                r.user_id: r
                for r in db.session.query(WeeklyReport).filter_by(period_start=week_start).all()
            }
            for u in subordinates:
                u_tasks = [t for t in team_tasks if t.responsible_id == u.id or t.co_responsible_id == u.id]
                u_completed = sum(1 for t in u_tasks if t.status == TaskStatus.TERMINEE)
                u_in_prog = sum(1 for t in u_tasks if t.status == TaskStatus.EN_COURS)
                u_late = sum(1 for t in u_tasks if t.is_late(today))
                u_avg_p = round(sum(t.progress for t in u_tasks) / len(u_tasks)) if u_tasks else 0
                u_has_updated = any(
                    any(up.created_at.date() == today and up.user_id == u.id for up in t.updates)
                    for t in u_tasks
                )
                rep = user_reports.get(u.id)
                members_progress.append({
                    "id": u.id,
                    "full_name": u.full_name,
                    "username": u.username,
                    "role": u.role.value,
                    "teams": [link.team.name for link in u.team_links if link.team],
                    "total_tasks": len(u_tasks),
                    "completed": u_completed,
                    "in_progress": u_in_prog,
                    "late": u_late,
                    "avg_progress": u_avg_p,
                    "has_updated_today": u_has_updated,
                    "report_status": rep.status.value if rep else "non initialisé",
                })

            chart_status_data = {
                "labels": ["À faire", "En cours", "À valider", "Terminée", "Bloquée", "Reportée", "Annulée"],
                "counts": [
                    sum(1 for t in team_tasks if t.status == TaskStatus.A_FAIRE),
                    sum(1 for t in team_tasks if t.status == TaskStatus.EN_COURS),
                    sum(1 for t in team_tasks if t.status == TaskStatus.A_VALIDER),
                    sum(1 for t in team_tasks if t.status == TaskStatus.TERMINEE),
                    sum(1 for t in team_tasks if t.status == TaskStatus.BLOQUEE),
                    sum(1 for t in team_tasks if t.status == TaskStatus.REPORTEE),
                    sum(1 for t in team_tasks if t.status == TaskStatus.ANNULEE),
                ],
            }
            chart_teams_data = {
                "labels": [tp["name"] for tp in teams_progress],
                "progress": [tp["avg_progress"] for tp in teams_progress],
                "tasks_count": [tp["total_tasks"] for tp in teams_progress],
            }

    return render_template(
        "dashboard/index.html",
        user=current_user,
        supervised_teams=supervised_teams,
        stats=stats,
        recent_tasks=recent_tasks,
        my_weekly_report=my_weekly_report,
        week_start=week_start,
        week_end=week_end,
        pending_reports_count=pending_reports_count,
        teams_progress=teams_progress,
        members_progress=members_progress,
        chart_status_data=chart_status_data,
        chart_teams_data=chart_teams_data,
    )
