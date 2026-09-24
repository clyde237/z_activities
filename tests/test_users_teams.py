from app.models import AuditLog, Team, User, UserRole, UserTeam


def _create_user(db, username, role, password="secret123"):
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


def test_unauthenticated_redirected_to_login(client):
    response = client.get("/users")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_collaborateur_cannot_manage_teams(client, db):
    _create_user(db, "membre", UserRole.COLLABORATEUR)
    _login(client, "membre")

    response = client.get("/teams")

    assert response.status_code == 403


def test_chef_service_can_create_team(client, db):
    _create_user(db, "chef", UserRole.CHEF_SERVICE)
    _login(client, "chef")

    response = client.post(
        "/teams/new",
        data={"name": "Trésorerie", "description": ""},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert db.session.query(Team).filter_by(name="Trésorerie").one_or_none() is not None


def test_duplicate_team_name_rejected(client, db):
    _create_user(db, "chef", UserRole.CHEF_SERVICE)
    db.session.add(Team(name="Achat"))
    db.session.commit()
    _login(client, "chef")

    response = client.post(
        "/teams/new",
        data={"name": "Achat", "description": ""},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert db.session.query(Team).filter_by(name="Achat").count() == 1


def test_chef_service_can_create_user_and_assign_team(client, db):
    _create_user(db, "chef", UserRole.CHEF_SERVICE)
    team = Team(name="Comptabilité")
    db.session.add(team)
    db.session.commit()

    _login(client, "chef")

    response = client.post(
        "/users/new",
        data={
            "username": "jdupont",
            "first_name": "Jean",
            "last_name": "Dupont",
            "function": "Comptable",
            "role": UserRole.COLLABORATEUR.value,
            "password": "secret123",
            "password_confirm": "secret123",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    new_user = db.session.query(User).filter_by(username="jdupont").one()

    response = client.post(
        f"/users/{new_user.id}/teams",
        data={"team_id": team.id, "is_team_lead": "on"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    db.session.refresh(new_user)
    assert new_user.is_team_lead_of(team.id)


def test_chef_service_can_create_user_with_team_and_team_lead(client, db):
    _create_user(db, "chef", UserRole.CHEF_SERVICE)
    team = Team(name="Achat")
    db.session.add(team)
    db.session.commit()
    _login(client, "chef")

    response = client.post(
        "/users/new",
        data={
            "username": "amartin",
            "first_name": "Alice",
            "last_name": "Martin",
            "function": "Analyste",
            "role": UserRole.COLLABORATEUR.value,
            "password": "secret123",
            "password_confirm": "secret123",
            "team_id": team.id,
            "is_team_lead": "on",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    new_user = db.session.query(User).filter_by(username="amartin").one()
    assert new_user.is_team_lead_of(team.id)


def test_password_mismatch_rejected_on_create(client, db):
    _create_user(db, "chef", UserRole.CHEF_SERVICE)
    _login(client, "chef")

    response = client.post(
        "/users/new",
        data={
            "username": "amartin",
            "first_name": "Alice",
            "last_name": "Martin",
            "role": UserRole.COLLABORATEUR.value,
            "password": "secret123",
            "password_confirm": "different",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert db.session.query(User).filter_by(username="amartin").one_or_none() is None


def test_inactive_user_cannot_login(client, db):
    user = _create_user(db, "inactif", UserRole.COLLABORATEUR)
    user.is_active_account = False
    db.session.commit()

    response = _login(client, "inactif")
    assert response.status_code == 401


def test_logout_invalidates_session(client, db):
    _create_user(db, "membre", UserRole.COLLABORATEUR)
    _login(client, "membre")

    response = client.post("/logout", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    protected = client.get("/")
    assert protected.status_code == 302
    assert "/login" in protected.headers["Location"]


def test_collaborateur_cannot_access_users_management(client, db):
    _create_user(db, "membre", UserRole.COLLABORATEUR)
    _login(client, "membre")

    assert client.get("/users").status_code == 403
    assert client.get("/users/new").status_code == 403


def test_chef_service_can_edit_user_profile_and_status(client, db):
    _create_user(db, "chef", UserRole.CHEF_SERVICE)
    target = _create_user(db, "cible", UserRole.COLLABORATEUR)
    _login(client, "chef")

    response = client.post(
        f"/users/{target.id}/edit",
        data={
            "first_name": "Nouveau",
            "last_name": "Nom",
            "function": "Superviseur",
            "role": UserRole.COLLABORATEUR.value,
            "password": "",
            "password_confirm": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(target)
    assert target.first_name == "Nouveau"
    assert target.function == "Superviseur"
    assert target.is_active_account is False


def test_toggle_team_lead(client, db):
    _create_user(db, "chef", UserRole.CHEF_SERVICE)
    membre = _create_user(db, "membre", UserRole.COLLABORATEUR)
    team = Team(name="Trésorerie")
    db.session.add(team)
    db.session.flush()
    link = UserTeam(user_id=membre.id, team_id=team.id, is_team_lead=False)
    db.session.add(link)
    db.session.commit()

    _login(client, "chef")

    response = client.post(
        f"/users/{membre.id}/teams/{team.id}/toggle-lead",
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(link)
    assert link.is_team_lead is True

    response = client.post(
        f"/users/{membre.id}/teams/{team.id}/toggle-lead",
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(link)
    assert link.is_team_lead is False


def test_remove_team_assignment(client, db):
    _create_user(db, "chef", UserRole.CHEF_SERVICE)
    membre = _create_user(db, "membre", UserRole.COLLABORATEUR)
    team = Team(name="Achat")
    db.session.add(team)
    db.session.flush()
    link = UserTeam(user_id=membre.id, team_id=team.id, is_team_lead=False)
    db.session.add(link)
    db.session.commit()

    _login(client, "chef")

    response = client.post(
        f"/users/{membre.id}/teams/{team.id}/remove",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert db.session.query(UserTeam).filter_by(user_id=membre.id, team_id=team.id).one_or_none() is None

    audit = db.session.query(AuditLog).filter_by(action="remove_team", object_type="User", object_id=membre.id).one_or_none()
    assert audit is not None


def test_dashboard_displays_teams_and_supervision(client, db):
    team_compta = Team(name="Comptabilité")
    team_treso = Team(name="Trésorerie")
    db.session.add_all([team_compta, team_treso])
    db.session.flush()

    lead = _create_user(db, "lead_user", UserRole.COLLABORATEUR)
    member = _create_user(db, "simple_member", UserRole.COLLABORATEUR)

    db.session.add(UserTeam(user_id=lead.id, team_id=team_compta.id, is_team_lead=True))
    db.session.add(UserTeam(user_id=lead.id, team_id=team_treso.id, is_team_lead=False))
    db.session.add(UserTeam(user_id=member.id, team_id=team_compta.id, is_team_lead=False))
    db.session.commit()

    _login(client, "lead_user")
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Équipes sous votre supervision" in html
    assert "Comptabilité" in html
    assert "simple_member" in html or "Prénom Nom" in html
    assert "Mes équipes" in html

    client.post("/logout")
    _login(client, "simple_member")
    resp_member = client.get("/")
    assert resp_member.status_code == 200
    html_member = resp_member.data.decode("utf-8")
    assert "Équipes sous votre supervision" not in html_member
    assert "Mes équipes" in html_member
    assert "Comptabilité" in html_member


def test_team_detail_in_edit_page(client, db):
    _create_user(db, "chef", UserRole.CHEF_SERVICE)
    team = Team(name="Contrôle de gestion")
    db.session.add(team)
    db.session.flush()

    membre = _create_user(db, "cg_membre", UserRole.COLLABORATEUR)
    db.session.add(UserTeam(user_id=membre.id, team_id=team.id, is_team_lead=True))
    db.session.commit()

    _login(client, "chef")
    resp = client.get(f"/teams/{team.id}/edit")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Membres de l'équipe" in html
    assert "cg_membre" in html
    assert "Chef d'équipe" in html
