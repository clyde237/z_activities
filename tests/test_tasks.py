from datetime import date, timedelta

from app.models import AuditLog, Task, TaskPriority, TaskStatus, TaskType, Team, User, UserRole, UserTeam


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


def test_chef_service_can_create_qualitative_task(client, db):
    chef = _create_user(db, "chef_tasks", UserRole.CHEF_SERVICE)
    member = _create_user(db, "member_tasks", UserRole.COLLABORATEUR)
    team = Team(name="Comptabilité")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))
    db.session.commit()

    _login(client, "chef_tasks")

    today = date.today()
    due = today + timedelta(days=5)

    response = client.post(
        "/tasks/new",
        data={
            "title": "Rapprochement bancaire",
            "description": "Contrôler les relevés de compte",
            "team_id": team.id,
            "responsible_id": member.id,
            "start_date": today.strftime("%Y-%m-%d"),
            "due_date": due.strftime("%Y-%m-%d"),
            "priority": TaskPriority.HAUTE.value,
            "task_type": TaskType.QUALITATIVE.value,
            "progress": "25",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    task = db.session.query(Task).filter_by(title="Rapprochement bancaire").one_or_none()
    assert task is not None
    assert task.team_id == team.id
    assert task.responsible_id == member.id
    assert task.co_responsible_id is None
    assert task.priority == TaskPriority.HAUTE
    assert task.task_type == TaskType.QUALITATIVE
    assert task.progress == 25.0
    assert task.status == TaskStatus.A_FAIRE

    # Piste d'audit
    audit = db.session.query(AuditLog).filter_by(action="create", object_type="Task", object_id=task.id).one_or_none()
    assert audit is not None


def test_quantitative_task_progress_auto_computed(client, db):
    chef = _create_user(db, "chef_quant", UserRole.CHEF_SERVICE)
    member = _create_user(db, "member_quant", UserRole.COLLABORATEUR)
    team = Team(name="Achat")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))
    db.session.commit()

    _login(client, "chef_quant")

    today = date.today()
    response = client.post(
        "/tasks/new",
        data={
            "title": "Saisie factures fournisseurs",
            "team_id": team.id,
            "responsible_id": member.id,
            "start_date": today.strftime("%Y-%m-%d"),
            "due_date": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
            "priority": TaskPriority.NORMALE.value,
            "task_type": TaskType.QUANTITATIVE.value,
            "objective": "200",
            "realized": "50",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    task = db.session.query(Task).filter_by(title="Saisie factures fournisseurs").one()
    assert task.task_type == TaskType.QUANTITATIVE
    assert task.objective == 200.0
    assert task.realized == 50.0
    assert task.progress == 25.0  # (50 / 200) * 100


def test_team_lead_can_create_task_for_own_team(client, db):
    lead = _create_user(db, "lead_user_t", UserRole.COLLABORATEUR)
    member = _create_user(db, "member_t", UserRole.COLLABORATEUR)
    team = Team(name="Trésorerie")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=lead.id, team_id=team.id, is_team_lead=True))
    db.session.add(UserTeam(user_id=member.id, team_id=team.id, is_team_lead=False))
    db.session.commit()

    _login(client, "lead_user_t")

    today = date.today()
    response = client.post(
        "/tasks/new",
        data={
            "title": "Établissement du prévisionnel",
            "team_id": team.id,
            "responsible_id": member.id,
            "start_date": today.strftime("%Y-%m-%d"),
            "due_date": (today + timedelta(days=3)).strftime("%Y-%m-%d"),
            "priority": TaskPriority.NORMALE.value,
            "task_type": TaskType.QUALITATIVE.value,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert db.session.query(Task).filter_by(title="Établissement du prévisionnel").one_or_none() is not None


def test_collaborateur_cannot_create_task(client, db):
    simple_member = _create_user(db, "simple_coll", UserRole.COLLABORATEUR)
    team = Team(name="Stock")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=simple_member.id, team_id=team.id, is_team_lead=False))
    db.session.commit()

    _login(client, "simple_coll")

    # Accès direct formulaire de création interdit (403)
    response = client.get("/tasks/new")
    assert response.status_code == 403


def test_team_lead_cannot_create_task_for_other_team(client, db):
    lead = _create_user(db, "lead_other", UserRole.COLLABORATEUR)
    other_member = _create_user(db, "other_member", UserRole.COLLABORATEUR)
    team_a = Team(name="Équipe A")
    team_b = Team(name="Équipe B")
    db.session.add_all([team_a, team_b])
    db.session.flush()

    db.session.add(UserTeam(user_id=lead.id, team_id=team_a.id, is_team_lead=True))
    db.session.add(UserTeam(user_id=other_member.id, team_id=team_b.id, is_team_lead=False))
    db.session.commit()

    _login(client, "lead_other")

    today = date.today()
    response = client.post(
        "/tasks/new",
        data={
            "title": "Tâche illégale",
            "team_id": team_b.id,
            "responsible_id": other_member.id,
            "start_date": today.strftime("%Y-%m-%d"),
            "due_date": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
            "priority": TaskPriority.NORMALE.value,
            "task_type": TaskType.QUALITATIVE.value,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert db.session.query(Task).filter_by(title="Tâche illégale").one_or_none() is None


def test_co_responsible_must_be_distinct_from_responsible(client, db):
    chef = _create_user(db, "chef_distinct", UserRole.CHEF_SERVICE)
    member = _create_user(db, "member_same", UserRole.COLLABORATEUR)
    team = Team(name="Magasin")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))
    db.session.commit()

    _login(client, "chef_distinct")

    today = date.today()
    response = client.post(
        "/tasks/new",
        data={
            "title": "Tâche même responsable",
            "team_id": team.id,
            "responsible_id": member.id,
            "co_responsible_id": member.id,  # Même personne !
            "start_date": today.strftime("%Y-%m-%d"),
            "due_date": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
            "priority": TaskPriority.NORMALE.value,
            "task_type": TaskType.QUALITATIVE.value,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert db.session.query(Task).filter_by(title="Tâche même responsable").one_or_none() is None


def test_due_date_before_start_date_rejected(client, db):
    chef = _create_user(db, "chef_dates", UserRole.CHEF_SERVICE)
    member = _create_user(db, "member_d", UserRole.COLLABORATEUR)
    team = Team(name="Contrôle")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))
    db.session.commit()

    _login(client, "chef_dates")

    today = date.today()
    yesterday = today - timedelta(days=1)

    response = client.post(
        "/tasks/new",
        data={
            "title": "Tâche dates erronées",
            "team_id": team.id,
            "responsible_id": member.id,
            "start_date": today.strftime("%Y-%m-%d"),
            "due_date": yesterday.strftime("%Y-%m-%d"),  # Échéance avant début
            "priority": TaskPriority.NORMALE.value,
            "task_type": TaskType.QUALITATIVE.value,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert db.session.query(Task).filter_by(title="Tâche dates erronées").one_or_none() is None


def test_member_cannot_edit_task_structure(client, db):
    chef = _create_user(db, "chef_edit", UserRole.CHEF_SERVICE)
    member = _create_user(db, "member_assigned", UserRole.COLLABORATEUR)
    team = Team(name="Comptabilité B")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))

    today = date.today()
    task = Task(
        title="Tâche protégée",
        team_id=team.id,
        responsible_id=member.id,
        start_date=today,
        due_date=today + timedelta(days=5),
        priority=TaskPriority.NORMALE,
        task_type=TaskType.QUALITATIVE,
        status=TaskStatus.A_FAIRE,
    )
    db.session.add(task)
    db.session.commit()

    # Le membre assigné tente d'accéder à l'édition de la tâche (RB-013)
    _login(client, "member_assigned")
    response = client.get(f"/tasks/{task.id}/edit")
    assert response.status_code == 403


def test_task_status_transitions_enforced(client, db):
    chef = _create_user(db, "chef_trans", UserRole.CHEF_SERVICE)
    member = _create_user(db, "member_trans", UserRole.COLLABORATEUR)
    team = Team(name="Audit")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))

    today = date.today()
    task = Task(
        title="Tâche terminée",
        team_id=team.id,
        responsible_id=member.id,
        start_date=today,
        due_date=today + timedelta(days=2),
        priority=TaskPriority.NORMALE,
        task_type=TaskType.QUALITATIVE,
        status=TaskStatus.TERMINEE,
    )
    db.session.add(task)
    db.session.commit()

    _login(client, "chef_trans")

    # Tentative d'amener une tâche TERMINEE vers A_FAIRE (interdit par ALLOWED_STATUS_TRANSITIONS)
    response = client.post(
        f"/tasks/{task.id}/edit",
        data={
            "title": "Tâche terminée",
            "team_id": team.id,
            "responsible_id": member.id,
            "start_date": today.strftime("%Y-%m-%d"),
            "due_date": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
            "priority": TaskPriority.NORMALE.value,
            "task_type": TaskType.QUALITATIVE.value,
            "status": TaskStatus.A_FAIRE.value,
        },
        follow_redirects=True,
    )

    db.session.refresh(task)
    assert task.status == TaskStatus.TERMINEE


def test_late_task_indicator(client, db):
    member = _create_user(db, "member_late", UserRole.COLLABORATEUR)
    team = Team(name="Fiscalité")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=member.id, team_id=team.id))

    yesterday = date.today() - timedelta(days=1)
    task_late = Task(
        title="Déclaration fiscale urgente",
        team_id=team.id,
        responsible_id=member.id,
        start_date=yesterday - timedelta(days=5),
        due_date=yesterday,
        priority=TaskPriority.URGENTE,
        task_type=TaskType.QUALITATIVE,
        status=TaskStatus.EN_COURS,
    )
    task_done = Task(
        title="Déclaration terminée",
        team_id=team.id,
        responsible_id=member.id,
        start_date=yesterday - timedelta(days=5),
        due_date=yesterday,
        priority=TaskPriority.NORMALE,
        task_type=TaskType.QUALITATIVE,
        status=TaskStatus.TERMINEE,
    )
    db.session.add_all([task_late, task_done])
    db.session.commit()

    assert task_late.is_late() is True
    assert task_done.is_late() is False  # Si terminée, non considérée en retard


def test_team_members_api_endpoint(client, db):
    user = _create_user(db, "api_user", UserRole.COLLABORATEUR)
    team = Team(name="API Team")
    db.session.add(team)
    db.session.flush()
    db.session.add(UserTeam(user_id=user.id, team_id=team.id))
    db.session.commit()

    _login(client, "api_user")
    response = client.get(f"/tasks/teams/{team.id}/members")
    assert response.status_code == 200
    data = response.json
    assert len(data) == 1
    assert data[0]["id"] == user.id
    assert data[0]["name"] == user.full_name
