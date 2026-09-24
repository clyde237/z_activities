from datetime import date

from ..extensions import db
from .enums import TaskPriority, TaskStatus, TaskType
from .utils import utc_now

# Transitions de statut autorisées (RB-014, section 10). Centralisé ici pour
# qu'aucune route ne puisse faire sauter une tâche d'un état à un autre
# arbitrairement (ex: TERMINEE -> A_FAIRE).
ALLOWED_STATUS_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.A_FAIRE: {TaskStatus.EN_COURS, TaskStatus.ANNULEE, TaskStatus.REPORTEE},
    TaskStatus.EN_COURS: {
        TaskStatus.A_VALIDER,
        TaskStatus.BLOQUEE,
        TaskStatus.REPORTEE,
        TaskStatus.ANNULEE,
        TaskStatus.TERMINEE,
    },
    TaskStatus.A_VALIDER: {TaskStatus.TERMINEE, TaskStatus.EN_COURS},
    TaskStatus.BLOQUEE: {TaskStatus.EN_COURS, TaskStatus.ANNULEE},
    TaskStatus.REPORTEE: {TaskStatus.A_FAIRE, TaskStatus.EN_COURS, TaskStatus.ANNULEE},
    TaskStatus.TERMINEE: set(),
    TaskStatus.ANNULEE: set(),
}


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    responsible_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    co_responsible_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    start_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    priority = db.Column(
        db.Enum(TaskPriority, native_enum=False, length=16),
        nullable=False,
        default=TaskPriority.NORMALE,
    )
    task_type = db.Column(
        db.Enum(TaskType, native_enum=False, length=16),
        nullable=False,
        default=TaskType.QUALITATIVE,
    )
    objective = db.Column(db.Float)  # requis si task_type == QUANTITATIVE (RB-010)
    realized = db.Column(db.Float, nullable=False, default=0)
    progress = db.Column(db.Float, nullable=False, default=0)  # 0-100
    status = db.Column(
        db.Enum(TaskStatus, native_enum=False, length=16),
        nullable=False,
        default=TaskStatus.A_FAIRE,
    )
    comment = db.Column(db.Text)
    accounting_period_id = db.Column(
        db.Integer, db.ForeignKey("accounting_periods.id")
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    team = db.relationship("Team")
    responsible = db.relationship("User", foreign_keys=[responsible_id])
    co_responsible = db.relationship("User", foreign_keys=[co_responsible_id])
    accounting_period = db.relationship("AccountingPeriod")
    updates = db.relationship(
        "TaskUpdate",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskUpdate.created_at",
    )

    def recompute_progress(self) -> None:
        """RB-011: progression automatique = réalisé / objectif, plafonnée à 100%."""
        if self.task_type != TaskType.QUANTITATIVE:
            return
        if not self.objective or self.objective <= 0:
            self.progress = 0
            return
        self.progress = min(100.0, round((self.realized / self.objective) * 100, 2))

    def is_late(self, as_of: date | None = None) -> bool:
        """Indicateur calculé (section 10) : jamais stocké comme statut."""
        as_of = as_of or date.today()
        return self.status not in (TaskStatus.TERMINEE, TaskStatus.ANNULEE) and self.due_date < as_of

    def can_transition_to(self, new_status: TaskStatus) -> bool:
        return new_status in ALLOWED_STATUS_TRANSITIONS.get(self.status, set())

    def apply_first_update_transition(self) -> None:
        """RB-014: passage auto À faire -> En cours à la première mise à jour."""
        if self.status == TaskStatus.A_FAIRE:
            self.status = TaskStatus.EN_COURS

    def __repr__(self) -> str:
        return f"<Task {self.id} {self.title!r}>"


class TaskUpdate(db.Model):
    """Mise à jour quotidienne (section 11). Table d'historique : une ligne par
    mise à jour, jamais modifiée ni écrasée — la couche service ne doit exposer
    que la création, pas l'édition d'une ligne existante."""

    __tablename__ = "task_updates"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    progress = db.Column(db.Float, nullable=False)
    work_done = db.Column(db.Text, nullable=False)
    difficulties = db.Column(db.Text)
    next_step = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    task = db.relationship("Task", back_populates="updates")
    user = db.relationship("User")

    def __repr__(self) -> str:
        return f"<TaskUpdate task={self.task_id} at={self.created_at}>"
