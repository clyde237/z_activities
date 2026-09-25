from datetime import date, datetime, timedelta
import calendar as pycalendar

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Task, TaskPriority, TaskStatus, Team, UnexpectedActivity, User

calendar_blueprint = Blueprint("calendar", __name__, url_prefix="/calendar")


@calendar_blueprint.get("")
@login_required
def calendar_view():
    today = date.today()
    
    # Paramètres de filtre et de navigation
    year = request.args.get("year", default=today.year, type=int)
    month = request.args.get("month", default=today.month, type=int)
    team_id_filter = request.args.get("team_id", type=int)
    only_mine = request.args.get("mine") == "1"

    # Calcul du mois précédent et suivant
    first_day_of_month = date(year, month, 1)
    if month == 1:
        prev_month_date = date(year - 1, 12, 1)
    else:
        prev_month_date = date(year, month - 1, 1)

    if month == 12:
        next_month_date = date(year + 1, 1, 1)
    else:
        next_month_date = date(year, month + 1, 1)

    # Récupération des équipes disponibles
    if current_user.is_chef_service():
        teams = db.session.query(Team).order_by(Team.name).all()
    else:
        teams = db.session.query(Team).filter(Team.id.in_(current_user.team_ids())).order_by(Team.name).all()

    # Requête des tâches
    task_query = db.session.query(Task)
    if team_id_filter:
        task_query = task_query.filter(Task.team_id == team_id_filter)
    elif not current_user.is_chef_service():
        task_query = task_query.filter(Task.team_id.in_(current_user.team_ids()))

    if only_mine:
        task_query = task_query.filter(
            (Task.responsible_id == current_user.id) | (Task.co_responsible_id == current_user.id)
        )

    all_tasks = task_query.all()

    # Requête des activités imprévues
    activity_query = db.session.query(UnexpectedActivity)
    if only_mine or not current_user.is_chef_service():
        activity_query = activity_query.filter(UnexpectedActivity.user_id == current_user.id)
    all_activities = activity_query.all()

    # Construction des semaines du calendrier (lundi au dimanche)
    cal = pycalendar.Calendar(firstweekday=0) # 0 = Lundi
    month_days = cal.monthdatescalendar(year, month)

    # Dictionnaire d'événements indexé par date ISO (YYYY-MM-DD)
    events_by_date = {}
    for t in all_tasks:
        if t.due_date:
            d_str = t.due_date.isoformat()
            if d_str not in events_by_date:
                events_by_date[d_str] = []
            events_by_date[d_str].append({
                "type": "task",
                "title": t.title,
                "time": "17:00",
                "color": "blue" if t.status != TaskStatus.TERMINEE else "green",
                "status": t.status.value,
                "responsible": t.responsible.full_name if t.responsible else "Non assigné",
            })

    for a in all_activities:
        if a.activity_date:
            d_str = a.activity_date.isoformat()
            if d_str not in events_by_date:
                events_by_date[d_str] = []
            events_by_date[d_str].append({
                "type": "unexpected",
                "title": a.title,
                "time": a.start_time.strftime("%H:%M") if a.start_time else "09:00",
                "color": "rose",
                "status": "Imprévue",
                "responsible": a.user.full_name if a.user else "",
            })

    # Prochains événements à venir
    upcoming_events = []
    for t in sorted([t for t in all_tasks if t.due_date and t.due_date >= today], key=lambda x: x.due_date)[:6]:
        upcoming_events.append({
            "date": t.due_date,
            "title": t.title,
            "team_name": t.team.name if t.team else "Général",
            "time": "09:00 - 17:00",
            "responsible": t.responsible.full_name if t.responsible else "Tous",
            "type": "Tâche",
            "color": "blue",
        })

    month_names_fr = [
        "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
    ]
    current_month_name = f"{month_names_fr[month]} {year}"

    return render_template(
        "calendar/index.html",
        month_days=month_days,
        events_by_date=events_by_date,
        upcoming_events=upcoming_events,
        current_year=year,
        current_month=month,
        current_month_name=current_month_name,
        prev_month_date=prev_month_date,
        next_month_date=next_month_date,
        today=today,
        teams=teams,
        current_team_id=team_id_filter,
        only_mine=only_mine,
    )
