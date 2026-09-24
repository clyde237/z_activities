from datetime import datetime

from flask import Blueprint, render_template, request
from flask_login import login_required

from ..extensions import db
from ..models import AuditLog, User
from ..permissions import chef_service_required

audit_blueprint = Blueprint("audit", __name__, url_prefix="/audit")


@audit_blueprint.get("")
@login_required
@chef_service_required
def list_audit_logs():
    user_id = request.args.get("user_id", type=int)
    object_type = request.args.get("object_type", "").strip()
    action = request.args.get("action", "").strip()
    date_str = request.args.get("date", "").strip()

    query = db.session.query(AuditLog)

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if object_type:
        query = query.filter(AuditLog.object_type == object_type)
    if action:
        query = query.filter(AuditLog.action == action)
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            query = query.filter(db.func.date(AuditLog.created_at) == target_date)
        except ValueError:
            pass

    logs = query.order_by(AuditLog.created_at.desc()).limit(200).all()

    users = db.session.query(User).order_by(User.last_name, User.first_name).all()
    distinct_types = [
        r[0] for r in db.session.query(AuditLog.object_type).distinct().all() if r[0]
    ]
    distinct_actions = [
        r[0] for r in db.session.query(AuditLog.action).distinct().all() if r[0]
    ]

    return render_template(
        "audit/index.html",
        logs=logs,
        users=users,
        distinct_types=distinct_types,
        distinct_actions=distinct_actions,
        current_user_id=user_id,
        current_object_type=object_type,
        current_action=action,
        current_date=date_str,
    )
