from ..extensions import db
from .utils import utc_now


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))

    member_links = db.relationship(
        "UserTeam", back_populates="team", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Team {self.name}>"


class UserTeam(db.Model):
    """Affectation d'un utilisateur à une équipe (RB-002).

    is_team_lead porte le statut de "chef d'équipe" (section 4) : il est
    défini par équipe, pas globalement sur l'utilisateur.
    """

    __tablename__ = "user_teams"
    __table_args__ = (
        db.UniqueConstraint("user_id", "team_id", name="uq_user_team"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    is_team_lead = db.Column(db.Boolean, nullable=False, default=False)
    joined_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    user = db.relationship("User", back_populates="team_links")
    team = db.relationship("Team", back_populates="member_links")

    def __repr__(self) -> str:
        return f"<UserTeam user={self.user_id} team={self.team_id}>"
