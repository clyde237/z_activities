import zipfile
from datetime import date, datetime, timedelta
import io

from app.models import (
    AuditLog,
    MonthlyReport,
    MonthlyReportStatus,
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
from app.services.history_service import search_history
from app.services.monthly_report_service import (
    finalize_monthly_report,
    get_monthly_report_data,
    get_or_create_monthly_report,
    reopen_monthly_report,
    update_monthly_report_content,
)


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


def test_create_and_consolidate_monthly_report(client, db):
    """Test de création et consolidation automatique du rapport mensuel départemental (CDC 17, RB-025, RB-026)."""
    chef = _create_user(db, "chef_monthly", role=UserRole.CHEF_SERVICE)
    collab = _create_user(db, "collab_monthly", role=UserRole.COLLABORATEUR)

    team_compta = Team(name="Comptabilité")
    team_treso = Team(name="Trésorerie")
    db.session.add_all([team_compta, team_treso])
    db.session.flush()

    db.session.add(UserTeam(user_id=collab.id, team_id=team_compta.id))
    db.session.commit()

    # Mois cible : Mars 2026
    start_march = date(2026, 3, 1)
    end_march = date(2026, 3, 31)

    # 1. Tâche terminée dans le mois
    t1 = Task(
        title="Clôture TVA Mars",
        team_id=team_compta.id,
        responsible_id=collab.id,
        start_date=start_march,
        due_date=date(2026, 3, 20),
        status=TaskStatus.TERMINEE,
        progress=100.0,
    )
    # 2. Tâche en cours dans le mois
    t2 = Task(
        title="Rapprochement bancaire",
        team_id=team_treso.id,
        responsible_id=collab.id,
        start_date=start_march,
        due_date=date(2026, 3, 28),
        status=TaskStatus.EN_COURS,
        progress=60.0,
    )
    # 3. Activité imprévue dans le mois
    act = UnexpectedActivity(
        title="Contrôle fiscal inopiné",
        user_id=collab.id,
        activity_date=date(2026, 3, 15),
        priority=TaskPriority.URGENTE,
        result="Dossier transmis",
    )
    # 4. Rapport hebdomadaire dans le mois
    rep_hebdo = WeeklyReport(
        user_id=collab.id,
        period_start=date(2026, 3, 9),
        period_end=date(2026, 3, 15),
        status=WeeklyReportStatus.VALIDE,
        narrative_summary="Bonne semaine",
        difficulties="Lenteur réseau",
        solutions="Utilisation du mode hors ligne",
    )
    db.session.add_all([t1, t2, act, rep_hebdo])
    db.session.commit()

    # Création du rapport mensuel
    monthly_rep, created = get_or_create_monthly_report(2026, 3, chef)
    assert created is True
    assert monthly_rep.year == 2026
    assert monthly_rep.month == 3
    assert monthly_rep.status == MonthlyReportStatus.BROUILLON
    assert monthly_rep.month_name == "Mars"

    # Vérification du rattachement du rapport hebdomadaire
    db.session.refresh(rep_hebdo)
    assert rep_hebdo.monthly_report_id == monthly_rep.id

    # Agrégation des données
    data = get_monthly_report_data(monthly_rep)
    assert data["period_start"] == start_march
    assert data["period_end"] == end_march
    assert data["tasks_stats"]["total"] >= 2
    assert data["tasks_stats"]["completed"] >= 1
    assert data["tasks_stats"]["in_progress"] >= 1
    assert data["reports_stats"]["valides"] >= 1
    assert len(data["unexpected_activities"]) >= 1
    assert len(data["teams_summary"]) >= 2
    assert any(ts["team"].name == "Comptabilité" for ts in data["teams_summary"])
    assert any(d["text"] == "Lenteur réseau" for d in data["collected_difficulties"])


def test_monthly_report_permissions(client, db):
    """Vérification des droits d'accès : seul le Chef de service peut générer, éditer et finaliser (RB-027)."""
    chef = _create_user(db, "chef_perm", role=UserRole.CHEF_SERVICE)
    collab = _create_user(db, "collab_perm", role=UserRole.COLLABORATEUR)

    monthly_rep, _ = get_or_create_monthly_report(2026, 2, chef)

    # 1. Le collaborateur normal ne peut pas générer un rapport mensuel (403)
    _login(client, "collab_perm")
    resp_gen = client.post("/monthly-reports/generate", data={"year": 2026, "month": 1})
    assert resp_gen.status_code == 403

    # 2. Le collaborateur ne peut pas accéder à l'édition (403)
    resp_edit = client.get(f"/monthly-reports/{monthly_rep.id}/edit")
    assert resp_edit.status_code == 403

    # 3. Le collaborateur ne peut pas finaliser (403)
    resp_fin = client.post(f"/monthly-reports/{monthly_rep.id}/finalize")
    assert resp_fin.status_code == 403

    # 4. Le collaborateur peut consulter la liste et le détail (200)
    resp_list = client.get("/monthly-reports")
    assert resp_list.status_code == 200
    assert "Février 2026" in resp_list.get_data(as_text=True)

    resp_detail = client.get(f"/monthly-reports/{monthly_rep.id}")
    assert resp_detail.status_code == 200
    assert "Février 2026" in resp_detail.get_data(as_text=True)

    # 5. Le Chef de service peut accéder à l'édition et générer
    _login(client, "chef_perm")
    resp_chef_edit = client.get(f"/monthly-reports/{monthly_rep.id}/edit")
    assert resp_chef_edit.status_code == 200
    assert "Ajustement du rapport mensuel" in resp_chef_edit.get_data(as_text=True)


def test_monthly_report_adjustment_and_finalization_workflow(client, db):
    """Test du cycle d'ajustement rédactionnel, finalisation et réouverture (RB-027)."""
    chef = _create_user(db, "chef_flow", role=UserRole.CHEF_SERVICE)
    monthly_rep, _ = get_or_create_monthly_report(2026, 4, chef)

    _login(client, "chef_flow")

    # Ajustement des textes
    resp_save = client.post(
        f"/monthly-reports/{monthly_rep.id}/edit",
        data={
            "narrative_summary": "Synthèse du mois d'Avril satisfaisante.",
            "key_achievements": "Audit interne validé sans réserve.",
            "difficulties_summary": "Absences pour congés.",
            "action_plan": "Recrutement d'un stagiaire.",
            "observations": "Félicitations aux équipes.",
        },
        follow_redirects=True,
    )
    assert resp_save.status_code == 200

    db.session.refresh(monthly_rep)
    assert monthly_rep.narrative_summary == "Synthèse du mois d'Avril satisfaisante."
    assert monthly_rep.key_achievements == "Audit interne validé sans réserve."
    assert monthly_rep.status == MonthlyReportStatus.BROUILLON

    # Finalisation officielle
    resp_fin = client.post(f"/monthly-reports/{monthly_rep.id}/finalize", follow_redirects=True)
    assert resp_fin.status_code == 200

    db.session.refresh(monthly_rep)
    assert monthly_rep.status == MonthlyReportStatus.FINALISE
    assert monthly_rep.finalized_at is not None
    assert monthly_rep.finalized_by_id == chef.id

    # Modification impossible tant que finalisé
    resp_cant_edit = client.get(f"/monthly-reports/{monthly_rep.id}/edit", follow_redirects=True)
    assert "Ce rapport mensuel est déjà finalisé" in resp_cant_edit.get_data(as_text=True)

    # Réouverture en brouillon
    resp_reopen = client.post(f"/monthly-reports/{monthly_rep.id}/reopen", follow_redirects=True)
    assert resp_reopen.status_code == 200

    db.session.refresh(monthly_rep)
    assert monthly_rep.status == MonthlyReportStatus.BROUILLON
    assert monthly_rep.finalized_at is None


def test_monthly_report_docx_export(client, db):
    """Test de génération du fichier Word (.docx) pour le rapport mensuel (CDC 29)."""
    chef = _create_user(db, "chef_docx", role=UserRole.CHEF_SERVICE)
    monthly_rep, _ = get_or_create_monthly_report(2026, 5, chef)
    update_monthly_report_content(
        monthly_rep,
        {
            "narrative_summary": "Excellente performance départementale pour Mai 2026.",
            "key_achievements": "Clôture anticipée de 2 jours.",
        },
        chef,
    )

    _login(client, "chef_docx")
    resp = client.get(f"/monthly-reports/{monthly_rep.id}/export-docx")
    assert resp.status_code == 200
    assert resp.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert "attachment" in resp.headers.get("Content-Disposition", "")
    assert "rapport_mensuel_05_2026.docx" in resp.headers.get("Content-Disposition", "")

    # Vérification que le buffer est un zip docx valide
    docx_zip = zipfile.ZipFile(io.BytesIO(resp.data))
    assert "word/document.xml" in docx_zip.namelist()
    assert "[Content_Types].xml" in docx_zip.namelist()

    doc_xml = docx_zip.read("word/document.xml").decode("utf-8")
    assert "HÔTEL LE ZINGANA" in doc_xml
    assert "RAPPORT MENSUEL D&#39;ACTIVITÉS DÉPARTEMENTAL" in doc_xml or "RAPPORT MENSUEL" in doc_xml
    assert "Mai 2026" in doc_xml
    assert "Excellente performance" in doc_xml


def test_monthly_report_search_and_audit(client, db):
    """Test de la recherche dans l'historique et des entrées dans le journal d'audit (RB-028, RB-030)."""
    chef = _create_user(db, "chef_audit_mr", role=UserRole.CHEF_SERVICE)
    monthly_rep, _ = get_or_create_monthly_report(2026, 6, chef)
    update_monthly_report_content(
        monthly_rep,
        {"narrative_summary": "Projet de migration comptable achevé"},
        chef,
    )

    # 1. Recherche transversale par mot-clé
    results = search_history(current_user=chef, q="migration comptable")
    found_types = [r["type"] for r in results]
    assert "monthly_report" in found_types
    mr_res = next(r for r in results if r["type"] == "monthly_report")
    assert "Juin 2026" in mr_res["title"]

    # 2. Vérification dans le journal d'audit
    audit_entries = (
        db.session.query(AuditLog)
        .filter_by(object_type="MonthlyReport", object_id=monthly_rep.id)
        .all()
    )
    assert len(audit_entries) >= 2  # create et update
    actions = [e.action for e in audit_entries]
    assert "create" in actions
    assert "update" in actions
