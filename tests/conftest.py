from pathlib import Path

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture
def app(tmp_path: Path):
    class TestConfig:
        TESTING = True
        SECRET_KEY = "test-secret"
        DATABASE_PATH = str(tmp_path / "test.sqlite3")
        WTF_CSRF_ENABLED = False

    flask_app = create_app(TestConfig)

    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db
