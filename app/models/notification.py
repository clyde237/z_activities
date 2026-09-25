from ..extensions import db
from .utils import utc_now


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    notif_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    related_object_type = db.Column(db.String(50))
    related_object_id = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    user = db.relationship("User")

    @property
    def target_url(self) -> str:
        """Retourne l'URL vers laquelle naviguer lors du clic sur la notification."""
        if self.related_object_type == "Task" and self.related_object_id:
            return f"/tasks/{self.related_object_id}"
        elif self.related_object_type == "WeeklyReport" and self.related_object_id:
            return f"/reports/{self.related_object_id}"
        elif self.related_object_type == "MonthlyReport" and self.related_object_id:
            return f"/monthly-reports/{self.related_object_id}"
        elif self.related_object_type == "UnexpectedActivity" and self.related_object_id:
            return f"/activities/{self.related_object_id}"
        return "/"

    @property
    def icon(self) -> str:
        """Icône visuelle adaptée selon le type d'événement (CDC Section 23)."""
        icons = {
            "task_assigned": "📌",
            "task_due_soon": "⏳",
            "task_late": "🚨",
            "task_update_reminder": "⏰",
            "report_submitted": "📬",
            "report_validated": "✅",
            "report_revision_requested": "↩️",
            "unexpected_activity_created": "⚡",
            "monthly_report_finalized": "🗓️",
        }
        return icons.get(self.notif_type, "🔔")

    def __repr__(self) -> str:
        return f"<Notification {self.notif_type} -> user={self.user_id} (read={self.is_read})>"
