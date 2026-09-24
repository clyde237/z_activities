from pathlib import Path

from flask import Flask

from .cli import register_cli
from .config import Config
from .extensions import db, login_manager, migrate
from .routes import register_routes


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        database_path = (
            Path(app.config["DATABASE_PATH"])
            if Path(app.config["DATABASE_PATH"]).is_absolute()
            else Path(app.instance_path).parent / app.config["DATABASE_PATH"]
        )
        database_path.parent.mkdir(parents=True, exist_ok=True)
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_path.resolve()}"

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from . import models  # noqa: F401  (enregistre les modèles auprès de SQLAlchemy)

    register_routes(app)
    register_cli(app)

    return app
