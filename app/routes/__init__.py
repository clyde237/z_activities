from flask import Flask

from .auth import auth_blueprint
from .dashboard import dashboard_blueprint
from .health import health_blueprint


def register_routes(app: Flask) -> None:
    app.register_blueprint(health_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(dashboard_blueprint)
