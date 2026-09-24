from flask import Blueprint, jsonify
from sqlalchemy import text

from ..extensions import db

health_blueprint = Blueprint("health", __name__)


@health_blueprint.get("/health")
def health_check():
    db.session.execute(text("SELECT 1"))
    return jsonify({"status": "ok", "service": "flask-sqlalchemy"})
