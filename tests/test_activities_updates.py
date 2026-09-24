from datetime import date, time, timedelta

from app.models import (
    AuditLog,
    Task,
    TaskPriority,
    TaskStatus,
    TaskType,
    TaskUpdate,
    Team,
    UnexpectedActivity,
    User,
    UserRole,
    UserTeam,
)
from app.services.task_service import has_updated_today


def _create_user(db, username, role=UserRole.COLLABORATEUR, password="secret123"):
    user = User(
        username=username,
        first_name="Prénom",
        last_name="Nom",
        role=role,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username, password="secret123"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


# ---------------------------------------------------------
# Tests Mises à jour quotidiennes (TaskUpdate & RB-014)
# ---------------------------------------------------------

def test_member_can_add_task_update_and_triggers_auto_transition(client, db):
    """RB-014: Une tâche à l'état À faire passe automatiquement à En cours à la 1ère mise à jour."""
    member = _create_user(db, "member_up1", UserRole.COLLABORATEUR)
    team = Team(name="Comptabilité U")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))

    today = date.today()
    task = Task(
        title="Tâche quotidienne",
        team_id=team.id,
        responsible_id=member.id,
        start_date=today,
        due_date=today + timedelta(days=3),
        priority=TaskPriority.NORMALE,
        task_type=TaskType.QUALITATIVE,
        progress=0.0,
        status=TaskStatus.A_FAIRE,
    )
    db.session.add(task)
    db.session.commit()

    assert task.status == TaskStatus.A_FAIRE
    assert has_updated_today(task) is False

    _login(client, "member_up1")

    response = client.post(
        f"/tasks/{task.id}/updates",
        data={
            "work_done": "Contrôle des 30 premières lignes effectué sans anomalie.",
            "difficulties": "Accès au serveur un peu lent le matin.",
            "next_step": "Finaliser les 50 lignes restantes demain.",
            "progress": "30",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    db.session.refresh(task)

    # RB-014 vérifié
    assert task.status == TaskStatus.EN_COURS
    assert task.progress == 30.0
    assert len(task.updates) == 1
    assert has_updated_today(task) is True

    update = task.updates[0]
    assert update.user_id == member.id
    assert update.progress == 30.0
    assert "30 premières lignes" in update.work_done
    assert "Accès au serveur" in update.difficulties
    assert "Finaliser les 50 lignes" in update.next_step

    # Audit vérifié
    audit = db.session.query(AuditLog).filter_by(action="update_progress", object_type="Task", object_id=task.id).one_or_none()
    assert audit is not None


def test_quantitative_update_recomputes_progress(client, db):
    """Pour une tâche quantitative, le cumul réalisé recalcule la progression."""
    member = _create_user(db, "member_quant_up", UserRole.COLLABORATEUR)
    team = Team(name="Achat U")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))

    today = date.today()
    task = Task(
        title="Traitement de 200 bons de commande",
        team_id=team.id,
        responsible_id=member.id,
        start_date=today,
        due_date=today + timedelta(days=4),
        priority=TaskPriority.NORMALE,
        task_type=TaskType.QUANTITATIVE,
        objective=200.0,
        realized=0.0,
        progress=0.0,
        status=TaskStatus.EN_COURS,
    )
    db.session.add(task)
    db.session.commit()

    _login(client, "member_quant_up")

    response = client.post(
        f"/tasks/{task.id}/updates",
        data={
            "work_done": "Saisie de 80 bons de commande.",
            "realized": "80",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    db.session.refresh(task)
    assert task.realized == 80.0
    assert task.progress == 40.0  # (80 / 200) * 100


def test_unauthorized_user_cannot_update_task_progress(client, db):
    """Un utilisateur non assigné et non superviseur ne peut pas ajouter de mise à jour."""
    member_owner = _create_user(db, "member_owner", UserRole.COLLABORATEUR)
    intruder = _create_user(db, "member_intruder", UserRole.COLLABORATEUR)
    team = Team(name="Stock U")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member_owner.id, team_id=team.id))
    db.session.add(UserTeam(user_id=intruder.id, team_id=team.id))

    today = date.today()
    task = Task(
        title="Inventaire magasin",
        team_id=team.id,
        responsible_id=member_owner.id,
        start_date=today,
        due_date=today + timedelta(days=2),
        priority=TaskPriority.NORMALE,
        task_type=TaskType.QUALITATIVE,
        status=TaskStatus.EN_COURS,
    )
    db.session.add(task)
    db.session.commit()

    _login(client, "member_intruder")
    response = client.post(
        f"/tasks/{task.id}/updates",
        data={"work_done": "Tentative illégale", "progress": "50"},
    )
    assert response.status_code == 403


def test_cannot_update_completed_task(client, db):
    """Impossible de poster une mise à jour sur une tâche terminée."""
    member = _create_user(db, "member_done", UserRole.COLLABORATEUR)
    team = Team(name="Treso U")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))

    today = date.today()
    task = Task(
        title="Tâche finie",
        team_id=team.id,
        responsible_id=member.id,
        start_date=today,
        due_date=today,
        priority=TaskPriority.NORMALE,
        task_type=TaskType.QUALITATIVE,
        progress=100.0,
        status=TaskStatus.TERMINEE,
    )
    db.session.add(task)
    db.session.commit()

    _login(client, "member_done")
    response = client.post(
        f"/tasks/{task.id}/updates",
        data={"work_done": "Modification post-clôture", "progress": "100"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(task)
    assert len(task.updates) == 0


# ---------------------------------------------------------
# Tests Activités imprévues (UnexpectedActivity, RB-005, RB-028)
# ---------------------------------------------------------

def test_member_can_declare_unexpected_activity(client, db):
    """RB-005: Un membre peut déclarer une activité imprévue."""
    member = _create_user(db, "member_act", UserRole.COLLABORATEUR)
    _login(client, "member_act")

    today = date.today()
    response = client.post(
        "/activities/new",
        data={
            "title": "Dépannage caisse restaurant",
            "description": "Appel d'urgence du maître d'hôtel pour blocage du logiciel de caisse.",
            "activity_date": today.strftime("%Y-%m-%d"),
            "start_time": "14:30",
            "end_time": "15:45",
            "requester": "Maître d'hôtel",
            "priority": TaskPriority.URGENTE.value,
            "result": "Problème d'imprimante thermique résolu et caisse débloquée.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    activity = db.session.query(UnexpectedActivity).filter_by(title="Dépannage caisse restaurant").one_or_none()
    assert activity is not None
    assert activity.user_id == member.id
    assert activity.requester == "Maître d'hôtel"
    assert activity.priority == TaskPriority.URGENTE
    assert activity.start_time == time(14, 30)
    assert activity.end_time == time(15, 45)
    assert "résolu" in activity.result

    # Audit vérifié
    audit = db.session.query(AuditLog).filter_by(action="create", object_type="UnexpectedActivity", object_id=activity.id).one_or_none()
    assert audit is not None


def test_invalid_times_rejected_in_unexpected_activity(client, db):
    """L'heure de fin ne peut pas être antérieure à l'heure de début."""
    member = _create_user(db, "member_time_err", UserRole.COLLABORATEUR)
    _login(client, "member_time_err")

    today = date.today()
    response = client.post(
        "/activities/new",
        data={
            "title": "Activité horaire erroné",
            "activity_date": today.strftime("%Y-%m-%d"),
            "start_time": "16:00",
            "end_time": "14:00",  # Fin avant début
            "priority": TaskPriority.NORMALE.value,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert db.session.query(UnexpectedActivity).filter_by(title="Activité horaire erroné").one_or_none() is None


def test_manager_can_add_comment_to_unexpected_activity(client, db):
    """Le chef de service ou chef d'équipe peut commenter une activité imprévue."""
    chef = _create_user(db, "chef_supervise", UserRole.CHEF_SERVICE)
    member = _create_user(db, "member_declared", UserRole.COLLABORATEUR)

    activity = UnexpectedActivity(
        user_id=member.id,
        title="Recherche justificatif bancaire 2025",
        activity_date=date.today(),
        priority=TaskPriority.NORMALE,
        result="Document retrouvé et scanné.",
    )
    db.session.add(activity)
    db.session.commit()

    _login(client, "chef_supervise")

    response = client.post(
        f"/activities/{activity.id}/edit",
        data={
            "title": activity.title,
            "activity_date": activity.activity_date.strftime("%Y-%m-%d"),
            "priority": activity.priority.value,
            "result": activity.result,
            "responsible_comment": "Bien pris en compte. Transmis au commissaire aux comptes.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    db.session.refresh(activity)
    assert activity.responsible_comment == "Bien pris en compte. Transmis au commissaire aux comptes."


def test_member_can_delete_own_activity(client, db):
    """Un collaborateur peut supprimer sa propre activité imprévue."""
    member = _create_user(db, "member_del", UserRole.COLLABORATEUR)
    activity = UnexpectedActivity(
        user_id=member.id,
        title="Activité en doublon",
        activity_date=date.today(),
    )
    db.session.add(activity)
    db.session.commit()

    _login(client, "member_del")
    response = client.post(f"/activities/{activity.id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert db.session.get(UnexpectedActivity, activity.id) is None


def test_intruder_cannot_delete_other_user_activity(client, db):
    """Un collaborateur ne peut pas supprimer l'activité d'un collègue."""
    owner = _create_user(db, "owner_act", UserRole.COLLABORATEUR)
    intruder = _create_user(db, "intruder_act", UserRole.COLLABORATEUR)
    activity = UnexpectedActivity(
        user_id=owner.id,
        title="Activité protégée",
        activity_date=date.today(),
    )
    db.session.add(activity)
    db.session.commit()

    _login(client, "intruder_act")
    response = client.post(f"/activities/{activity.id}/delete")
    assert response.status_code == 403
    assert db.session.get(UnexpectedActivity, activity.id) is not None
