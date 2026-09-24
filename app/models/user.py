from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, login_manager
from .enums import UserRole
from .utils import utc_now


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    function = db.Column(db.String(120))
    role = db.Column(
        db.Enum(UserRole, native_enum=False, length=32),
        nullable=False,
        default=UserRole.COLLABORATEUR,
    )
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    team_links = db.relationship(
        "UserTeam", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_active(self) -> bool:
        # UserMixin attend `is_active` comme indicateur de connexion possible.
        # On le fait pointer vers notre propre champ métier "compte actif/inactif"
        # (section 6) plutôt que de dupliquer un second flag.
        return self.is_active_account

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def is_chef_service(self) -> bool:
        return self.role == UserRole.CHEF_SERVICE

    def is_team_lead_of(self, team_id: int) -> bool:
        return any(
            link.team_id == team_id and link.is_team_lead for link in self.team_links
        )

    def team_ids(self) -> set[int]:
        return {link.team_id for link in self.team_links}

    def __repr__(self) -> str:
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.session.get(User, int(user_id))
