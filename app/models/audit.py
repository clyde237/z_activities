from datetime import datetime

from ..extensions import db


class AuditLog(db.Model):
    """Journal d'audit (section 22, RB-028).

    Écriture seule par convention applicative : aucune route ne doit exposer
    de modification ou suppression d'une entrée existante.
    """

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(80), nullable=False)
    object_type = db.Column(db.String(50), nullable=False)
    object_id = db.Column(db.Integer)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    user = db.relationship("User")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.object_type}:{self.object_id}>"
