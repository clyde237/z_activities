from app.models import Team, User, UserRole


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
