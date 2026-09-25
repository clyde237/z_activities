from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Notification
from ..services.notification_service import (
    get_unread_notifications_count,
    get_user_notifications,
    mark_all_notifications_as_read,
    mark_notification_as_read,
)

notifications_blueprint = Blueprint(
    "notifications",
    __name__,
    url_prefix="/notifications",
)


@notifications_blueprint.get("")
@login_required
def list_notifications():
    """Centre de notifications in-app (CDC Section 23)."""
    filter_unread = request.args.get("unread", "0") == "1"
    notifications = get_user_notifications(
        user=current_user,
        unread_only=filter_unread,
        limit=100,
    )
    unread_count = get_unread_notifications_count(current_user)

    return render_template(
        "notifications/index.html",
        notifications=notifications,
        unread_count=unread_count,
        filter_unread=filter_unread,
    )


@notifications_blueprint.post("/<int:id>/read")
@login_required
def mark_read(id: int):
    """Marque une notification comme lue et redirige vers la ressource ciblée."""
    notif = db.session.get(Notification, id)
    if notif and notif.user_id == current_user.id:
        notif.is_read = True
        db.session.commit()
        target = request.args.get("next") or notif.target_url
        return redirect(target)

    return redirect(url_for("notifications.list_notifications"))


@notifications_blueprint.post("/read-all")
@login_required
def mark_all_read():
    """Marque toutes les notifications de l'utilisateur comme lues."""
    count = mark_all_notifications_as_read(current_user)
    if count > 0:
        flash(f"{count} notification{'s ont été marquées' if count > 1 else ' a été marquée'} comme lue.", "success")
    return redirect(url_for("notifications.list_notifications"))


@notifications_blueprint.get("/unread-count")
@login_required
def unread_count_api():
    """Endpoint API JSON retournant le nombre de notifications non lues."""
    count = get_unread_notifications_count(current_user)
    return jsonify({"unread_count": count})
