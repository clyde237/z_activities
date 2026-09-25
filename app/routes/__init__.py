from .activities import activities_blueprint
from .audit import audit_blueprint
from .auth import auth_blueprint
from .dashboard import dashboard_blueprint
from .health import health_blueprint
from .history import history_blueprint
from .monthly_reports import monthly_reports_blueprint
from .reports import reports_blueprint
from .tasks import tasks_blueprint
from .teams import teams_blueprint
from .users import users_blueprint


def register_routes(app: Flask) -> None:
    app.register_blueprint(health_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(dashboard_blueprint)
    app.register_blueprint(users_blueprint)
    app.register_blueprint(teams_blueprint)
    app.register_blueprint(tasks_blueprint)
    app.register_blueprint(activities_blueprint)
    app.register_blueprint(reports_blueprint)
    app.register_blueprint(monthly_reports_blueprint)
    app.register_blueprint(history_blueprint)
    app.register_blueprint(audit_blueprint)


