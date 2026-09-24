from datetime import date, datetime, time
from typing import Any

from flask import url_for
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    AuditLog,
    Task,
    TaskStatus,
    TaskUpdate,
    Team,
    UnexpectedActivity,
    User,
    UserRole,
    UserTeam,
    WeeklyReport,
    WeeklyReportStatus,
)


def _safe_url_for(endpoint: str, **kwargs) -> str:
    """Génère une URL de manière sûre, y compris hors contexte de requête HTTP actif."""
    try:
        return url_for(endpoint, **kwargs)
    except RuntimeError:
        params = "&".join(f"{k}={v}" for k, v in kwargs.items())
        return f"/{endpoint.replace('.', '/')}{'?' + params if params else ''}"


def get_accessible_user_ids(user: User) -> set[int] | None:
    """Retourne l'ensemble des IDs utilisateurs consultables par cet utilisateur.
    None signifie accès illimité (Chef de service)."""
    if user.is_chef_service():
        return None
    accessible = {user.id}
    for link in user.team_links:
        if link.is_team_lead:
            subordinates = (
                db.session.query(UserTeam.user_id)
                .filter_by(team_id=link.team_id)
                .all()
            )
            accessible.update(s[0] for s in subordinates)
    return accessible


def search_history(
    current_user: User,
    q: str | None = None,
    user_id: int | None = None,
    team_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    entity_type: str | None = None,
) -> list[dict[str, Any]]:
    """Recherche transversale dans l'historique des activités (CDC Section 21, RB-030)."""
    accessible_ids = get_accessible_user_ids(current_user)

    # Si un user_id spécifique est demandé, vérifier qu'il fait partie du périmètre
    filtered_user_ids: list[int] | None = None
    if user_id:
        if accessible_ids is not None and user_id not in accessible_ids:
            return []
        filtered_user_ids = [user_id]
    elif accessible_ids is not None:
        filtered_user_ids = list(accessible_ids)

    results: list[dict[str, Any]] = []
    term = f"%{q.strip()}%" if q and q.strip() else None

    # 1. Recherche dans les Tâches
    if not entity_type or entity_type in ("all", "task"):
        query = db.session.query(Task)
        if filtered_user_ids is not None:
            query = query.filter(
                or_(
                    Task.responsible_id.in_(filtered_user_ids),
                    Task.co_responsible_id.in_(filtered_user_ids),
                )
            )
        if team_id:
            query = query.filter(Task.team_id == team_id)
        if start_date:
            query = query.filter(Task.due_date >= start_date)
        if end_date:
            query = query.filter(Task.due_date <= end_date)
        if term:
            query = query.filter(
                or_(
                    Task.title.ilike(term),
                    Task.description.ilike(term),
                    Task.comment.ilike(term),
                )
            )

        for t in query.limit(100).all():
            results.append({
                "type": "task",
                "type_label": "Tâche",
                "badge_color": "blue",
                "id": t.id,
                "title": t.title,
                "date": t.due_date or t.created_at.date(),
                "user": t.responsible,
                "team": t.team.name if t.team else None,
                "status": t.status.value.replace("_", " ").upper(),
                "progress": t.progress,
                "snippet": t.description or t.comment or "Aucune description.",
                "url": _safe_url_for("tasks.view_task", task_id=t.id),
            })

    # 2. Recherche dans les Mises à jour quotidiennes
    if not entity_type or entity_type in ("all", "update"):
        query = db.session.query(TaskUpdate).join(Task, TaskUpdate.task_id == Task.id)
        if filtered_user_ids is not None:
            query = query.filter(TaskUpdate.user_id.in_(filtered_user_ids))
        if team_id:
            query = query.filter(Task.team_id == team_id)
        if start_date:
            dt_start = datetime.combine(start_date, time.min)
            query = query.filter(TaskUpdate.created_at >= dt_start)
        if end_date:
            dt_end = datetime.combine(end_date, time.max)
            query = query.filter(TaskUpdate.created_at <= dt_end)
        if term:
            query = query.filter(
                or_(
                    TaskUpdate.work_done.ilike(term),
                    TaskUpdate.difficulties.ilike(term),
                    TaskUpdate.next_step.ilike(term),
                )
            )

        for u in query.limit(100).all():
            results.append({
                "type": "update",
                "type_label": "Mise à jour quotidienne",
                "badge_color": "emerald",
                "id": u.id,
                "title": f"Mise à jour sur : {u.task.title}",
                "date": u.created_at.date(),
                "user": u.user,
                "team": u.task.team.name if u.task and u.task.team else None,
                "status": f"{int(u.progress)} %",
                "progress": u.progress,
                "snippet": f"Travail : {u.work_done}" + (f" | Difficultés : {u.difficulties}" if u.difficulties else ""),
                "url": _safe_url_for("tasks.view_task", task_id=u.task_id),
            })

    # 3. Recherche dans les Activités imprévues
    if not entity_type or entity_type in ("all", "activity"):
        query = db.session.query(UnexpectedActivity)
        if filtered_user_ids is not None:
            query = query.filter(UnexpectedActivity.user_id.in_(filtered_user_ids))
        if start_date:
            query = query.filter(UnexpectedActivity.activity_date >= start_date)
        if end_date:
            query = query.filter(UnexpectedActivity.activity_date <= end_date)
        if term:
            query = query.filter(
                or_(
                    UnexpectedActivity.title.ilike(term),
                    UnexpectedActivity.description.ilike(term),
                    UnexpectedActivity.requester.ilike(term),
                    UnexpectedActivity.result.ilike(term),
                    UnexpectedActivity.responsible_comment.ilike(term),
                )
            )

        for act in query.limit(100).all():
            teams = [link.team.name for link in act.user.team_links if link.team]
            team_str = ", ".join(teams) if teams else None
            if team_id and not any(link.team_id == team_id for link in act.user.team_links):
                continue

            results.append({
                "type": "activity",
                "type_label": "Activité imprévue",
                "badge_color": "purple",
                "id": act.id,
                "title": act.title,
                "date": act.activity_date,
                "user": act.user,
                "team": team_str,
                "status": f"Priorité {act.priority.value.upper()}",
                "progress": None,
                "snippet": act.description or act.result or (f"Demandeur : {act.requester}" if act.requester else "Activité déclarée."),
                "url": _safe_url_for("activities.view_activity", activity_id=act.id),
            })

    # 4. Recherche dans les Rapports hebdomadaires
    if not entity_type or entity_type in ("all", "report"):
        query = db.session.query(WeeklyReport)
        if filtered_user_ids is not None:
            query = query.filter(WeeklyReport.user_id.in_(filtered_user_ids))
        if start_date:
            query = query.filter(WeeklyReport.period_start >= start_date)
        if end_date:
            query = query.filter(WeeklyReport.period_end <= end_date)
        if term:
            query = query.filter(
                or_(
                    WeeklyReport.narrative_summary.ilike(term),
                    WeeklyReport.difficulties.ilike(term),
                    WeeklyReport.solutions.ilike(term),
                    WeeklyReport.observations.ilike(term),
                )
            )

        for rep in query.limit(100).all():
            teams = [link.team.name for link in rep.user.team_links if link.team]
            team_str = ", ".join(teams) if teams else None
            if team_id and not any(link.team_id == team_id for link in rep.user.team_links):
                continue

            results.append({
                "type": "report",
                "type_label": "Rapport hebdomadaire",
                "badge_color": "amber",
                "id": rep.id,
                "title": f"Rapport semaine du {rep.period_start.strftime('%d/%m/%Y')} au {rep.period_end.strftime('%d/%m/%Y')}",
                "date": rep.period_end,
                "user": rep.user,
                "team": team_str,
                "status": rep.status.value.upper(),
                "progress": None,
                "snippet": rep.narrative_summary or rep.difficulties or "Rapport d'activités.",
                "url": _safe_url_for("reports.detail_report", id=rep.id),
            })

    # Tri par date décroissante
    results.sort(key=lambda r: (r["date"] if isinstance(r["date"], date) else date.min), reverse=True)
    return results
