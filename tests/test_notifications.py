from datetime import date, timedelta

from app.models import (
    Notification,
    Task,
    TaskPriority,
    TaskStatus,
    TaskType,
    Team,
    UnexpectedActivity,
    User,
    UserRole,
    UserTeam,
    WeeklyReport,
    WeeklyReportStatus,
)
from app.services.activity_service import create_unexpected_activity
from app.services.notification_service import (
    check_deadlines_and_send_reminders,
    create_notification,
    get_unread_notifications_count,
    get_user_notifications,
    mark_all_notifications_as_read,
    mark_notification_as_read,
)
from app.services.report_service import (
    get_or_create_weekly_report,
    reject_weekly_report_to_draft,
    submit_weekly_report,
    validate_weekly_report,
)
from app.services.task_service import create_task


def _create_user(db, username, role=UserRole.COLLABORATEUR):
    u = User(
        username=username,
        first_name="Prénom",
        last_name=username.capitalize(),
        role=role,
    )
    u.set_password("secret123")
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username, password="secret123"):
    client.post("/logout")
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def test_notification_creation_and_reading(client, db):
    """Test du modèle et des opérations de lecture/comptage de notifications."""
    user = _create_user(db, "notif_user")

    assert get_unread_notifications_count(user) == 0

    n1 = create_notification(user.id, "task_assigned", "Tâche assignée", "Task", 1)
    n2 = create_notification(user.id, "task_due_soon", "Échéance proche", "Task", 2)

    assert get_unread_notifications_count(user) == 2
    assert len(get_user_notifications(user)) == 2

    # Marquer une notification comme lue
    success = mark_notification_as_read(n1.id, user)
    assert success is True
    assert get_unread_notifications_count(user) == 1
    assert len(get_user_notifications(user, unread_only=True)) == 1

    # Marquer toutes comme lues
    count = mark_all_notifications_as_read(user)
    assert count == 1
    assert get_unread_notifications_count(user) == 0


def test_task_assignment_triggers_notification(client, db):
    """Vérifie qu'assigner une tâche déclenche des notifications pour les responsables (CDC 23)."""
    chef = _create_user(db, "chef_notif_task", role=UserRole.CHEF_SERVICE)
    resp = _create_user(db, "resp_notif_task")
    co_resp = _create_user(db, "co_resp_notif_task")

    team = Team(name="Comptabilité Notif")
    db.session.add(team)
    db.session.flush()
    db.session.add_all([
        UserTeam(user_id=resp.id, team_id=team.id),
        UserTeam(user_id=co_resp.id, team_id=team.id),
    ])
    db.session.commit()

    task = create_task(
        user=chef,
        data={
            "title": "Vérification Facturation",
            "team_id": team.id,
            "responsible_id": resp.id,
            "co_responsible_id": co_resp.id,
            "start_date": date.today(),
            "due_date": date.today() + timedelta(days=3),
            "priority": TaskPriority.NORMALE.value,
            "task_type": TaskType.QUALITATIVE.value,
            "progress": 0.0,
            "status": "a_faire",
        },
    )

    # Responsable reçoit une notification
    resp_notifs = get_user_notifications(resp)
    assert len(resp_notifs) >= 1
    assert resp_notifs[0].notif_type == "task_assigned"
    assert "Vérification Facturation" in resp_notifs[0].message
    assert resp_notifs[0].target_url == f"/tasks/{task.id}"

    # Co-responsable reçoit aussi une notification
    co_resp_notifs = get_user_notifications(co_resp)
    assert len(co_resp_notifs) >= 1
    assert co_resp_notifs[0].notif_type == "task_assigned"
    assert "co-responsable" in co_resp_notifs[0].message


def test_weekly_report_workflow_notifications(client, db):
    """Vérifie que la soumission, validation et rejet de rapport génèrent des notifications (CDC 23)."""
    chef = _create_user(db, "chef_notif_rep", role=UserRole.CHEF_SERVICE)
    collab = _create_user(db, "collab_notif_rep")

    report, _ = get_or_create_weekly_report(collab)

    # 1. Soumission -> Notification au Chef de service
    submit_weekly_report(report, collab)
    chef_notifs = get_user_notifications(chef)
    assert len(chef_notifs) >= 1
    assert any(n.notif_type == "report_submitted" for n in chef_notifs)

    # 2. Validation -> Notification au Collaborateur
    validate_weekly_report(report, chef, observations="Excellent travail")
    collab_notifs = get_user_notifications(collab)
    assert len(collab_notifs) >= 1
    assert any(n.notif_type == "report_validated" for n in collab_notifs)

    # 3. Demande de révision (retour en brouillon) -> Notification au Collaborateur
    # Pour simuler une réouverture ou renvoi
    report.status = WeeklyReportStatus.SOUMIS
    db.session.commit()
    reject_weekly_report_to_draft(report, chef, reason="Préciser les points bloquants")

    collab_notifs_after = get_user_notifications(collab)
    assert any(n.notif_type == "report_revision_requested" for n in collab_notifs_after)


def test_unexpected_activity_triggers_notification(client, db):
    """Vérifie que la déclaration d'une activité imprévue notifie le Chef de service et le Chef d'équipe."""
    chef = _create_user(db, "chef_unexp_notif", role=UserRole.CHEF_SERVICE)
    lead = _create_user(db, "lead_unexp_notif")
    member = _create_user(db, "member_unexp_notif")

    team = Team(name="Trésorerie Notif")
    db.session.add(team)
    db.session.flush()
    db.session.add_all([
        UserTeam(user_id=lead.id, team_id=team.id, is_team_lead=True),
        UserTeam(user_id=member.id, team_id=team.id, is_team_lead=False),
    ])
    db.session.commit()

    activity = create_unexpected_activity(
        member,
        {
            "title": "Panne système caisse",
            "activity_date": date.today(),
            "priority": TaskPriority.URGENTE.value,
            "result": "Serveur redémarré",
        },
    )

    chef_notifs = get_user_notifications(chef)
    assert any(n.notif_type == "unexpected_activity_created" for n in chef_notifs)

    lead_notifs = get_user_notifications(lead)
    assert any(n.notif_type == "unexpected_activity_created" for n in lead_notifs)


def test_check_deadlines_and_reminders(client, db):
    """Test du mécanisme de détection automatique d'échéances et de rappels quotidiens."""
    user = _create_user(db, "user_reminders")
    team = Team(name="Contrôle Notif")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=user.id, team_id=team.id))

    today = date.today()

    # Tâche arrivant à échéance demain
    t_soon = Task(
        title="Échéance demain",
        team_id=team.id,
        responsible_id=user.id,
        start_date=today - timedelta(days=5),
        due_date=today + timedelta(days=1),
        status=TaskStatus.EN_COURS,
        progress=40.0,
    )
    # Tâche en retard
    t_late = Task(
        title="Tâche déjà en retard",
        team_id=team.id,
        responsible_id=user.id,
        start_date=today - timedelta(days=10),
        due_date=today - timedelta(days=2),
        status=TaskStatus.EN_COURS,
        progress=20.0,
    )
    db.session.add_all([t_soon, t_late])
    db.session.commit()

    counts = check_deadlines_and_send_reminders(today)
    assert counts["due_soon"] >= 1
    assert counts["late"] >= 1
    assert counts["update_reminders"] >= 2  # les deux tâches sont EN_COURS sans mise à jour aujourd'hui

    user_notifs = get_user_notifications(user)
    types = [n.notif_type for n in user_notifs]
    assert "task_due_soon" in types
    assert "task_late" in types
    assert "task_update_reminder" in types


def test_notifications_web_interface(client, db):
    """Test des routes de l'interface utilisateur pour les notifications."""
    user = _create_user(db, "web_notif_user")
    n = create_notification(user.id, "task_assigned", "Nouvelle tâche assignée", "Task", 99)

    _login(client, "web_notif_user")

    # 1. Consultation de la page des notifications
    resp = client.get("/notifications")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Centre de notifications" in html
    assert "Nouvelle tâche assignée" in html

    # 2. API unread count
    resp_api = client.get("/notifications/unread-count")
    assert resp_api.status_code == 200
    assert resp_api.json["unread_count"] >= 1

    # 3. Marquer comme lue
    resp_read = client.post(f"/notifications/{n.id}/read?next=/notifications", follow_redirects=True)
    assert resp_read.status_code == 200
    db.session.refresh(n)
    assert n.is_read is True

    # 4. Tout marquer comme lu
    n2 = create_notification(user.id, "task_late", "Autre retard", "Task", 100)
    resp_read_all = client.post("/notifications/read-all", follow_redirects=True)
    assert resp_read_all.status_code == 200
    db.session.refresh(n2)
    assert n2.is_read is True
