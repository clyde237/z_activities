from datetime import date, timedelta

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
    WeeklyReport,
    WeeklyReportStatus,
)
from app.services.history_service import search_history
from app.services.report_service import get_or_create_weekly_report


def _create_user(db, username, role=UserRole.COLLABORATEUR, password="secret123", is_active=True):
    user = User(
        username=username,
        first_name="Prénom",
        last_name="Nom",
        role=role,
        is_active_account=is_active,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username, password="secret123"):
    client.post("/logout")
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


# ---------------------------------------------------------
# 1. Tests Dashboard Chef de Service (Section 18 CDC)
# ---------------------------------------------------------

def test_chef_service_supervision_dashboard(client, db):
    chef = _create_user(db, "cds_sup", role=UserRole.CHEF_SERVICE)
    member = _create_user(db, "member_sup", role=UserRole.COLLABORATEUR)

    team = Team(name="Comptabilité Générale")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))

    today = date.today()
    t1 = Task(
        title="Audit TVA",
        team_id=team.id,
        responsible_id=member.id,
        start_date=today,
        due_date=today + timedelta(days=2),
        priority=TaskPriority.HAUTE,
        task_type=TaskType.QUALITATIVE,
        progress=50.0,
        status=TaskStatus.EN_COURS,
    )
    act1 = UnexpectedActivity(
        title="Contrôle inopiné caisse",
        user_id=member.id,
        activity_date=today,
        priority=TaskPriority.URGENTE,
        result="Caisse conforme",
    )
    db.session.add_all([t1, act1])
    db.session.commit()

    # Création et soumission d'un rapport hebdomadaire
    report, _ = get_or_create_weekly_report(member)
    report.status = WeeklyReportStatus.SOUMIS
    db.session.commit()

    _login(client, "cds_sup")
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Vérification des indicateurs et graphiques
    assert "Supervision individuelle des collaborateurs" in html
    assert "Progression par équipe" in html
    assert "Comptabilité Générale" in html
    assert "statusChart" in html
    assert "teamsChart" in html
    assert "Audit TVA" in html
    assert "Rapports hebdomadaires à valider" in html


# ---------------------------------------------------------
# 2. Tests Dashboard Chef d'Équipe (Section 19 CDC)
# ---------------------------------------------------------

def test_team_lead_supervision_dashboard(client, db):
    lead = _create_user(db, "lead_sup")
    member = _create_user(db, "member_team")
    other_member = _create_user(db, "other_member")

    team1 = Team(name="Trésorerie")
    team2 = Team(name="Achats")
    db.session.add_all([team1, team2])
    db.session.flush()

    db.session.add(UserTeam(user_id=lead.id, team_id=team1.id, is_team_lead=True))
    db.session.add(UserTeam(user_id=member.id, team_id=team1.id, is_team_lead=False))
    db.session.add(UserTeam(user_id=other_member.id, team_id=team2.id, is_team_lead=False))
    db.session.commit()

    _login(client, "lead_sup")
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Doit voir l'équipe qu'il supervise
    assert "Trésorerie" in html
    assert "Supervision individuelle" in html
    # Ne doit pas superviser les membres de l'équipe Achats
    assert "other_member" not in html


# ---------------------------------------------------------
# 3. Tests Recherche et Historique Transversal (Section 21, RB-030)
# ---------------------------------------------------------

def test_history_search_by_keyword(db):
    user = _create_user(db, "jean_history")
    team = Team(name="Contrôle")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=user.id, team_id=team.id))

    today = date.today()
    t = Task(
        title="Rapprochement bancaire BICEC",
        description="Vérification des relevés de comptes bancaires",
        team_id=team.id,
        responsible_id=user.id,
        start_date=today,
        due_date=today + timedelta(days=1),
        priority=TaskPriority.NORMALE,
        status=TaskStatus.EN_COURS,
    )
    act = UnexpectedActivity(
        title="Paiement fournisseur urgent",
        user_id=user.id,
        activity_date=today,
        description="Règlement fournisseur sous menace d'interruption",
        priority=TaskPriority.URGENTE,
    )
    db.session.add_all([t, act])
    db.session.commit()

    # Recherche par mot-clé "rapprochement"
    res1 = search_history(user, q="rapprochement")
    assert len(res1) == 1
    assert res1[0]["title"] == "Rapprochement bancaire BICEC"
    assert res1[0]["type"] == "task"

    # Recherche par mot-clé "fournisseur"
    res2 = search_history(user, q="fournisseur")
    assert len(res2) == 1
    assert res2[0]["title"] == "Paiement fournisseur urgent"
    assert res2[0]["type"] == "activity"


def test_history_search_by_user_and_scope(db):
    """Exemple du CDC : 'Toutes les activités de Jean depuis janvier 2026'."""
    jean = _create_user(db, "jean_2026")
    paul = _create_user(db, "paul_2026")
    chef = _create_user(db, "chef_history", role=UserRole.CHEF_SERVICE)

    team = Team(name="Audit interne")
    db.session.add(team)
    db.session.flush()
    db.session.add_all([
        UserTeam(user_id=jean.id, team_id=team.id),
        UserTeam(user_id=paul.id, team_id=team.id),
    ])

    d1 = date(2026, 1, 15)
    d2 = date(2026, 2, 20)
    t_jean = Task(
        title="Inventaire stock janvier",
        team_id=team.id,
        responsible_id=jean.id,
        start_date=d1,
        due_date=d1,
        status=TaskStatus.TERMINEE,
    )
    t_paul = Task(
        title="Inventaire stock février",
        team_id=team.id,
        responsible_id=paul.id,
        start_date=d2,
        due_date=d2,
        status=TaskStatus.TERMINEE,
    )
    db.session.add_all([t_jean, t_paul])
    db.session.commit()

    # Le Chef de service filtre les activités de Jean depuis janvier 2026
    res_jean = search_history(chef, user_id=jean.id, start_date=date(2026, 1, 1))
    titles = [r["title"] for r in res_jean]
    assert "Inventaire stock janvier" in titles
    assert "Inventaire stock février" not in titles


def test_history_view_route(client, db):
    user = _create_user(db, "history_route_user")
    _login(client, "history_route_user")

    resp = client.get("/history?q=test")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Recherche" in html and "Historique" in html


# ---------------------------------------------------------
# 4. Tests Journal d'Audit (Section 22, RB-028)
# ---------------------------------------------------------

def test_audit_logs_permissions_and_listing(client, db):
    chef = _create_user(db, "chef_audit", role=UserRole.CHEF_SERVICE)
    member = _create_user(db, "member_audit", role=UserRole.COLLABORATEUR)

    entry = AuditLog(
        user_id=member.id,
        action="update",
        object_type="Task",
        object_id=42,
        old_value="40%",
        new_value="60%",
    )
    db.session.add(entry)
    db.session.commit()

    # 1. Collaborateur normal n'a pas accès à la page d'audit (403)
    _login(client, "member_audit")
    resp_member = client.get("/audit")
    assert resp_member.status_code == 403

    # 2. Chef de service accède au journal d'audit (200)
    _login(client, "chef_audit")
    resp_chef = client.get("/audit")
    assert resp_chef.status_code == 200
    html = resp_chef.get_data(as_text=True)
    assert "Journal d" in html and "audit" in html and "Traçabilité" in html
    assert "Task" in html
    assert "60%" in html
