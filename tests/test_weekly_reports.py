import io
import zipfile
from datetime import date, timedelta

import pytest

from app.models import (
    AuditLog,
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
from app.services.docx_generator import generate_weekly_report_docx
from app.services.report_service import (
    ReportValidationError,
    generate_weekly_reports_for_all,
    get_or_create_weekly_report,
    get_report_data,
    get_week_bounds,
    reject_weekly_report_to_draft,
    submit_weekly_report,
    update_weekly_report,
    validate_weekly_report,
)


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
# 1. Calcul des bornes de semaine et création automatique
# ---------------------------------------------------------

def test_get_week_bounds():
    # 2026-09-24 est un jeudi (weekday=3)
    target = date(2026, 9, 24)
    start, end = get_week_bounds(target)
    # Lundi = 2026-09-21
    assert start == date(2026, 9, 21)
    # Dimanche = 2026-09-27
    assert end == date(2026, 9, 27)


def test_get_or_create_weekly_report_creates_draft_and_audits(db):
    """RB-020, RB-021: Le rapport hebdomadaire est créé en brouillon avec audit."""
    user = _create_user(db, "collab_rep1")
    target = date(2026, 9, 25)  # Vendredi

    report, created = get_or_create_weekly_report(user, target_date=target)
    assert created is True
    assert report.status == WeeklyReportStatus.BROUILLON
    assert report.user_id == user.id
    assert report.period_start == date(2026, 9, 21)
    assert report.period_end == date(2026, 9, 27)

    # Idempotence : appel répété retourne le même rapport
    report2, created2 = get_or_create_weekly_report(user, target_date=target)
    assert created2 is False
    assert report2.id == report.id

    # Journal d'audit
    audit = (
        db.session.query(AuditLog)
        .filter_by(object_type="WeeklyReport", object_id=report.id, action="create")
        .first()
    )
    assert audit is not None


def test_generate_weekly_reports_for_all(db):
    """RB-020: Génère les rapports du vendredi pour tous les membres actifs."""
    u1 = _create_user(db, "u1_active")
    u2 = _create_user(db, "u2_active")
    _create_user(db, "u3_inactive", is_active=False)

    reports = generate_weekly_reports_for_all(date(2026, 9, 25))
    user_ids = [r.user_id for r in reports]
    assert u1.id in user_ids
    assert u2.id in user_ids
    assert len(reports) == 2


def test_flask_cli_generate_weekly_reports(app, db):
    """Vérifie la commande CLI flask generate-weekly-reports."""
    _create_user(db, "cli_user")
    runner = app.test_cli_runner()
    result = runner.invoke(args=["generate-weekly-reports", "--date", "2026-09-25"])
    assert result.exit_code == 0
    assert "Génération terminée" in result.output


# ---------------------------------------------------------
# 2. Agrégation des données du rapport (Section 16 CDC)
# ---------------------------------------------------------

def test_get_report_data_aggregates_tasks_and_unexpected(db):
    user = _create_user(db, "rep_data_user")
    team = Team(name="Comptabilité Rep")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=user.id, team_id=team.id))

    report, _ = get_or_create_weekly_report(user, date(2026, 9, 25))

    # Tâche dans la semaine
    t1 = Task(
        title="Rapprochement banque",
        team_id=team.id,
        responsible_id=user.id,
        start_date=report.period_start,
        due_date=report.period_start + timedelta(days=2),
        priority=TaskPriority.NORMALE,
        task_type=TaskType.QUALITATIVE,
        progress=100.0,
        status=TaskStatus.TERMINEE,
    )
    # Activité imprévue dans la semaine
    act1 = UnexpectedActivity(
        title="Facture client d'urgence",
        user_id=user.id,
        activity_date=report.period_start + timedelta(days=1),
        priority=TaskPriority.HAUTE,
        requester="Direction Générale",
        result="Facture émise et envoyée",
    )
    db.session.add_all([t1, act1])
    db.session.commit()

    data = get_report_data(report)
    assert len(data["tasks"]) == 1
    assert data["tasks"][0].id == t1.id
    assert len(data["completed_tasks"]) == 1
    assert len(data["unexpected_activities"]) == 1
    assert data["stats"]["total_tasks"] == 1
    assert data["stats"]["completed_count"] == 1
    assert data["stats"]["average_progress"] == 100
    assert data["stats"]["unexpected_count"] == 1


# ---------------------------------------------------------
# 3. Workflow : Édition, Soumission, Validation (RB-021..023)
# ---------------------------------------------------------

def test_collaborator_can_edit_draft_report(db):
    """RB-022: Le membre peut modifier son rapport avant soumission."""
    user = _create_user(db, "author_edit")
    report, _ = get_or_create_weekly_report(user, date(2026, 9, 25))

    data = {
        "narrative_summary": "Synthèse de la semaine : objectifs atteints.",
        "difficulties": "Lenteur internet lundi.",
        "solutions": "Bascule sur le réseau de secours.",
        "observations": "Prévoir inventaire.",
    }
    updated = update_weekly_report(report, user, data)
    assert updated.narrative_summary == "Synthèse de la semaine : objectifs atteints."
    assert updated.difficulties == "Lenteur internet lundi."
    assert updated.solutions == "Bascule sur le réseau de secours."


def test_submit_weekly_report_workflow(db):
    user = _create_user(db, "submitter_user")
    report, _ = get_or_create_weekly_report(user, date(2026, 9, 25))

    # Soumission
    submitted = submit_weekly_report(report, user)
    assert submitted.status == WeeklyReportStatus.SOUMIS
    assert submitted.submitted_at is not None

    # Ne peut plus être édité une fois soumis par le collaborateur
    with pytest.raises(ReportValidationError):
        update_weekly_report(report, user, {"narrative_summary": "Modification refusée"})


def test_validate_weekly_report_by_chef_service(db):
    """RB-023: Seul le chef de service valide le rapport hebdomadaire."""
    author = _create_user(db, "author_val")
    chef = _create_user(db, "chef_val", role=UserRole.CHEF_SERVICE)
    other = _create_user(db, "other_val", role=UserRole.COLLABORATEUR)

    report, _ = get_or_create_weekly_report(author, date(2026, 9, 25))
    submit_weekly_report(report, author)

    # Un collaborateur normal ne peut pas valider
    with pytest.raises(ReportValidationError):
        validate_weekly_report(report, other)

    # Le chef de service valide
    validated = validate_weekly_report(report, chef, observations="Excellent travail.")
    assert validated.status == WeeklyReportStatus.VALIDE
    assert validated.validated_by_id == chef.id
    assert validated.validated_at is not None
    assert validated.observations == "Excellent travail."


def test_reject_weekly_report_to_draft(db):
    author = _create_user(db, "author_rej")
    chef = _create_user(db, "chef_rej", role=UserRole.CHEF_SERVICE)

    report, _ = get_or_create_weekly_report(author, date(2026, 9, 25))
    submit_weekly_report(report, author)

    rejected = reject_weekly_report_to_draft(report, chef, reason="Préciser les écarts de caisse")
    assert rejected.status == WeeklyReportStatus.BROUILLON
    assert "Préciser les écarts de caisse" in rejected.observations


# ---------------------------------------------------------
# 4. Permissions et Visibilité (RB-024)
# ---------------------------------------------------------

def test_permissions_team_lead_can_view_member_report(client, db):
    """RB-024: Le chef d'équipe peut consulter les rapports des membres de son équipe."""
    lead = _create_user(db, "team_lead_rep")
    member = _create_user(db, "member_rep")
    other = _create_user(db, "stranger_rep")

    team = Team(name="Trésorerie Rep")
    db.session.add(team)
    db.session.flush()

    db.session.add(UserTeam(user_id=lead.id, team_id=team.id, is_team_lead=True))
    db.session.add(UserTeam(user_id=member.id, team_id=team.id, is_team_lead=False))
    db.session.commit()

    report, _ = get_or_create_weekly_report(member, date(2026, 9, 25))

    # 1. Un utilisateur étranger à l'équipe ne peut pas voir le rapport (403)
    _login(client, "stranger_rep")
    resp = client.get(f"/reports/{report.id}")
    assert resp.status_code == 403

    # 2. Le chef d'équipe peut consulter le rapport (200)
    _login(client, "team_lead_rep")
    resp_lead = client.get(f"/reports/{report.id}")
    assert resp_lead.status_code == 200
    assert "Rapport d'activités hebdomadaire" in resp_lead.get_data(as_text=True)

    # 3. Le membre peut consulter son propre rapport (200)
    _login(client, "member_rep")
    resp_member = client.get(f"/reports/{report.id}")
    assert resp_member.status_code == 200


# ---------------------------------------------------------
# 5. Export Word (.docx)
# ---------------------------------------------------------

def test_generate_weekly_report_docx_structure(db):
    user = _create_user(db, "docx_user")
    report, _ = get_or_create_weekly_report(user, date(2026, 9, 25))
    report.narrative_summary = "Synthèse narrative de test Word."
    db.session.commit()

    data = get_report_data(report)
    stream = generate_weekly_report_docx(report, data)
    content = stream.getvalue()

    # Le fichier doit débuter par la signature PKZIP (standard OpenXML .docx)
    assert content[:4] == b"PK\x03\x04"

    # Vérification que c'est une archive ZIP valide avec word/document.xml
    with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
        namelist = zf.namelist()
        assert "[Content_Types].xml" in namelist
        assert "_rels/.rels" in namelist
        assert "word/document.xml" in namelist

        doc_xml = zf.read("word/document.xml").decode("utf-8")
        assert "HÔTEL LE ZINGANA" in doc_xml
        assert "DÉPARTEMENT COMPTABILITÉ &amp; FINANCE" in doc_xml
        assert "RAPPORT D'ACTIVITÉS HEBDOMADAIRE" in doc_xml
        assert "Synthèse narrative de test Word." in doc_xml


def test_export_docx_route(client, db):
    user = _create_user(db, "route_docx_user")
    report, _ = get_or_create_weekly_report(user, date(2026, 9, 25))

    _login(client, "route_docx_user")
    resp = client.get(f"/reports/{report.id}/export-docx")
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in resp.headers["Content-Type"]
    assert "attachment;" in resp.headers.get("Content-Disposition", "")
    assert resp.data[:4] == b"PK\x03\x04"
