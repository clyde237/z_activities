from ..extensions import db
from .enums import TaskPriority
from .utils import utc_now


class UnexpectedActivity(db.Model):
    """Activité imprévue (section 13). Intégrée automatiquement au rapport
    hebdomadaire par la couche service — pas de lien stocké ici tant que le
    rapport n'existe pas encore au moment de la déclaration."""

    __tablename__ = "unexpected_activities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    activity_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    requester = db.Column(db.String(120))  # demandeur/origine
    priority = db.Column(
        db.Enum(TaskPriority, native_enum=False, length=16),
        nullable=False,
        default=TaskPriority.NORMALE,
    )
    result = db.Column(db.Text)  # résultat obtenu
    responsible_comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    user = db.relationship("User")

    @property
    def status_label(self) -> str:
        if self.result or self.end_time:
            return "Résolue"
        if self.start_time:
            return "En cours"
        return "En attente"

    @property
    def team_name(self) -> str:
        if self.user and self.user.team_links:
            return self.user.team_links[0].team.name
        return "Générale"

    def __repr__(self) -> str:
        return f"<UnexpectedActivity {self.id} {self.title!r}>"

