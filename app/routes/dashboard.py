from datetime import date, datetime, timedelta

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from ..extensions import db
from ..models import (
    AuditLog,
    MonthlyReport,
    Task,
    TaskPriority,
    TaskStatus,
    TaskUpdate,
    Team,
    UnexpectedActivity,
    User,
    UserTeam,
    WeeklyReport,
    WeeklyReportStatus,
)
from ..services.report_service import get_week_bounds

dashboard_blueprint = Blueprint("dashboard", __name__)


def _format_relative_time(dt: datetime) -> str:
    if not dt:
        return "Récemment"
    if dt.tzinfo is not None:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    else:
        now = datetime.now()
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "À l'instant"
    minutes = seconds // 60
    if minutes < 60:
        return f"Il y a {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"Il y a {hours} h"
    days = hours // 24
    if days == 1:
        return "Hier"
    if days < 7:
        return f"Il y a {days} jours"
    return dt.strftime("%d/%m")


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
    chart_evolution_data = {}
    recent_activities = []
    upcoming_deadlines = []
    priority_tasks = []
    recent_reports = []

    # Construction des 7 jours de la semaine courante (Lundi à Dimanche)
    week_days = [week_start + timedelta(days=i) for i in range(7)]
    day_labels_fr = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    evolution_labels = [f"{day_labels_fr[i]} {d.day}" for i, d in enumerate(week_days)]

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

        # Tâches récentes et prioritaires
        recent_tasks = (
            db.session.query(Task)
            .filter(~Task.status.in_([TaskStatus.TERMINEE, TaskStatus.ANNULEE]))
            .order_by(Task.due_date.asc())
            .limit(5)
            .all()
        )

        priority_tasks = (
            db.session.query(Task)
            .filter(~Task.status.in_([TaskStatus.TERMINEE, TaskStatus.ANNULEE]))
            .order_by(
                (Task.priority == TaskPriority.URGENTE).desc(),
                Task.due_date.asc()
            )
            .limit(5)
            .all()
        )

        upcoming_deadlines = (
            db.session.query(Task)
            .filter(~Task.status.in_([TaskStatus.TERMINEE, TaskStatus.ANNULEE]))
            .order_by(Task.due_date.asc())
            .limit(4)
            .all()
        )

        # Progression par équipe
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

        # Progression par membre
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
                "initials": u.initials,
                "function": u.function or u.role.value,
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

        # Données graphiques Chart.js
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
            "total": len(all_tasks),
            "completed": sum(1 for t in all_tasks if t.status == TaskStatus.TERMINEE),
            "in_progress": sum(1 for t in all_tasks if t.status == TaskStatus.EN_COURS),
            "late": sum(1 for t in all_tasks if t.is_late(today)),
        }
        chart_teams_data = {
            "labels": [tp["name"] for tp in teams_progress],
            "progress": [tp["avg_progress"] for tp in teams_progress],
            "tasks_count": [tp["total_tasks"] for tp in teams_progress],
        }

        # Évolution sur la semaine (réalisées vs prévues)
        realized_counts = []
        planned_counts = []
        for d in week_days:
            realized_counts.append(sum(1 for t in all_tasks if t.status == TaskStatus.TERMINEE and any(u.created_at.date() == d for u in t.updates)))
            planned_counts.append(sum(1 for t in all_tasks if t.due_date == d))

        chart_evolution_data = {
            "labels": evolution_labels,
            "realized": realized_counts,
            "planned": planned_counts,
        }

        # Activités récentes
        recent_updates = db.session.query(TaskUpdate).order_by(TaskUpdate.created_at.desc()).limit(5).all()
        for up in recent_updates:
            recent_activities.append({
                "text": f"{up.user.full_name} a mis à jour la tâche « {up.task.title} »",
                "time": _format_relative_time(up.created_at),
                "dot_color": "blue",
            })
        recent_unexp = db.session.query(UnexpectedActivity).order_by(UnexpectedActivity.created_at.desc()).limit(3).all()
        for un in recent_unexp:
            recent_activities.append({
                "text": f"{un.user.full_name} a ajouté une activité imprévue « {un.title} »",
                "time": _format_relative_time(un.created_at),
                "dot_color": "rose",
            })
        recent_activities.sort(key=lambda x: x["time"], reverse=False)

        # Rapports
        last_weekly = db.session.query(WeeklyReport).order_by(WeeklyReport.period_start.desc()).first()
        last_monthly = db.session.query(MonthlyReport).order_by(MonthlyReport.created_at.desc()).first()
        if last_weekly:
            recent_reports.append({
                "title": "Rapport hebdomadaire",
                "period": f"Semaine du {last_weekly.period_start.strftime('%d/%m')} au {last_weekly.period_end.strftime('%d/%m/%Y')}",
                "status": last_weekly.status.value,
                "url": f"/reports/{last_weekly.id}",
            })
        if last_monthly:
            recent_reports.append({
                "title": "Rapport mensuel",
                "period": f"Mois de {last_monthly.month_name} {last_monthly.year}",
                "status": last_monthly.status.value,
                "url": f"/monthly-reports/{last_monthly.id}",
            })

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

        priority_tasks = (
            db.session.query(Task)
            .filter(
                ((Task.responsible_id == current_user.id) | (Task.co_responsible_id == current_user.id)),
                ~Task.status.in_([TaskStatus.TERMINEE, TaskStatus.ANNULEE])
            )
            .order_by((Task.priority == TaskPriority.URGENTE).desc(), Task.due_date.asc())
            .limit(5)
            .all()
        )

        upcoming_deadlines = (
            db.session.query(Task)
            .filter(
                ((Task.responsible_id == current_user.id) | (Task.co_responsible_id == current_user.id)),
                ~Task.status.in_([TaskStatus.TERMINEE, TaskStatus.ANNULEE])
            )
            .order_by(Task.due_date.asc())
            .limit(4)
            .all()
        )

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
                    "initials": u.initials,
                    "function": u.function or u.role.value,
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

            # Stats de l'équipe
            stats["team_tasks_total"] = len(team_tasks)
            stats["team_tasks_completed"] = sum(1 for t in team_tasks if t.status == TaskStatus.TERMINEE)
            stats["team_tasks_in_progress"] = sum(1 for t in team_tasks if t.status == TaskStatus.EN_COURS)
            stats["team_tasks_late"] = sum(1 for t in team_tasks if t.is_late(today))
            stats["team_members_count"] = len(subordinates)

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
                "total": len(team_tasks),
                "completed": sum(1 for t in team_tasks if t.status == TaskStatus.TERMINEE),
                "in_progress": sum(1 for t in team_tasks if t.status == TaskStatus.EN_COURS),
                "late": sum(1 for t in team_tasks if t.is_late(today)),
            }
            chart_teams_data = {
                "labels": [tp["name"] for tp in teams_progress],
                "progress": [tp["avg_progress"] for tp in teams_progress],
                "tasks_count": [tp["total_tasks"] for tp in teams_progress],
            }

            # Évolution de l'équipe
            realized_counts = []
            planned_counts = []
            for d in week_days:
                realized_counts.append(sum(1 for t in team_tasks if t.status == TaskStatus.TERMINEE and any(u.created_at.date() == d for u in t.updates)))
                planned_counts.append(sum(1 for t in team_tasks if t.due_date == d))

            chart_evolution_data = {
                "labels": evolution_labels,
                "realized": realized_counts,
                "planned": planned_counts,
            }

            # Activités récentes de l'équipe
            team_task_ids = [t.id for t in team_tasks]
            recent_updates = (
                db.session.query(TaskUpdate)
                .filter(TaskUpdate.task_id.in_(team_task_ids))
                .order_by(TaskUpdate.created_at.desc())
                .limit(5)
                .all()
            )
            for up in recent_updates:
                recent_activities.append({
                    "text": f"{up.user.full_name} a mis à jour la tâche « {up.task.title} »",
                    "time": _format_relative_time(up.created_at),
                    "dot_color": "blue",
                })

            upcoming_deadlines = (
                db.session.query(Task)
                .filter(Task.team_id.in_(led_team_ids), ~Task.status.in_([TaskStatus.TERMINEE, TaskStatus.ANNULEE]))
                .order_by(Task.due_date.asc())
                .limit(4)
                .all()
            )

        else:
            # Collaborateur simple
            user_updates = (
                db.session.query(TaskUpdate)
                .filter_by(user_id=current_user.id)
                .order_by(TaskUpdate.created_at.desc())
                .limit(5)
                .all()
            )
            for up in user_updates:
                recent_activities.append({
                    "text": f"Vous avez mis à jour la tâche « {up.task.title} »",
                    "time": _format_relative_time(up.created_at),
                    "dot_color": "blue",
                })

    # Taux de complétion
    completion_rate = (
        round((stats["tasks_completed"] / stats["tasks_total"]) * 100)
        if stats.get("tasks_total") and stats["tasks_total"] > 0
        else 0
    )

    return render_template(
        "dashboard/index.html",
        user=current_user,
        supervised_teams=supervised_teams,
        stats=stats,
        recent_tasks=recent_tasks,
        priority_tasks=priority_tasks,
        upcoming_deadlines=upcoming_deadlines,
        recent_activities=recent_activities,
        recent_reports=recent_reports,
        my_weekly_report=my_weekly_report,
        week_start=week_start,
        week_end=week_end,
        pending_reports_count=pending_reports_count,
        teams_progress=teams_progress,
        members_progress=members_progress,
        chart_status_data=chart_status_data,
        chart_teams_data=chart_teams_data,
        chart_evolution_data=chart_evolution_data,
        completion_rate=completion_rate,
        today=today,
    )
