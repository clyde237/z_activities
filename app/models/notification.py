from datetime import datetime

from ..extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    notif_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    related_object_type = db.Column(db.String(50))
    related_object_id = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    user = db.relationship("User")

    def __repr__(self) -> str:
        return f"<Notification {self.notif_type} -> user={self.user_id}>"
