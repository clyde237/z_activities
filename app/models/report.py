from ..extensions import db
from .enums import MonthlyReportStatus, WeeklyReportStatus
from .utils import utc_now

# RB-021/023: brouillon à la génération; seul le chef de service valide.
WEEKLY_REPORT_TRANSITIONS: dict[WeeklyReportStatus, set[WeeklyReportStatus]] = {
    WeeklyReportStatus.BROUILLON: {WeeklyReportStatus.SOUMIS},
    WeeklyReportStatus.SOUMIS: {WeeklyReportStatus.VALIDE, WeeklyReportStatus.BROUILLON},
    WeeklyReportStatus.VALIDE: set(),
}


class WeeklyReport(db.Model):
    __tablename__ = "weekly_reports"
    __table_args__ = (
        db.UniqueConstraint("user_id", "period_start", name="uq_weekly_report_user_period"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    status = db.Column(
        db.Enum(WeeklyReportStatus, native_enum=False, length=16),
        nullable=False,
        default=WeeklyReportStatus.BROUILLON,
    )
    narrative_summary = db.Column(db.Text)
    difficulties = db.Column(db.Text)
    solutions = db.Column(db.Text)
    observations = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime)
    validated_at = db.Column(db.DateTime)
    validated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    monthly_report_id = db.Column(db.Integer, db.ForeignKey("monthly_reports.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    user = db.relationship("User", foreign_keys=[user_id])
    validated_by = db.relationship("User", foreign_keys=[validated_by_id])
    monthly_report = db.relationship("MonthlyReport", back_populates="weekly_reports")

    def can_transition_to(self, new_status: WeeklyReportStatus) -> bool:
        return new_status in WEEKLY_REPORT_TRANSITIONS.get(self.status, set())

    def __repr__(self) -> str:
        return f"<WeeklyReport user={self.user_id} {self.period_start}..{self.period_end}>"


MONTHLY_REPORT_TRANSITIONS: dict[MonthlyReportStatus, set[MonthlyReportStatus]] = {
    MonthlyReportStatus.BROUILLON: {MonthlyReportStatus.FINALISE},
    MonthlyReportStatus.FINALISE: {MonthlyReportStatus.BROUILLON},
}

MONTH_NAMES_FR = {
    1: "Janvier",
    2: "Février",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Août",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Décembre",
}


class MonthlyReport(db.Model):
    __tablename__ = "monthly_reports"
    __table_args__ = (
        db.UniqueConstraint("year", "month", name="uq_monthly_report_period"),
    )

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.Enum(MonthlyReportStatus, native_enum=False, length=16),
        nullable=False,
        default=MonthlyReportStatus.BROUILLON,
    )
    narrative_summary = db.Column(db.Text)
    key_achievements = db.Column(db.Text)
    difficulties_summary = db.Column(db.Text)
    action_plan = db.Column(db.Text)
    observations = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    finalized_at = db.Column(db.DateTime)
    finalized_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    finalized_by = db.relationship("User", foreign_keys=[finalized_by_id])
    weekly_reports = db.relationship("WeeklyReport", back_populates="monthly_report")

    def can_transition_to(self, new_status: MonthlyReportStatus) -> bool:
        return new_status in MONTHLY_REPORT_TRANSITIONS.get(self.status, set())

    @property
    def month_name(self) -> str:
        return MONTH_NAMES_FR.get(self.month, f"Mois {self.month}")

    @property
    def title(self) -> str:
        return f"Rapport mensuel départemental - {self.month_name} {self.year}"

    def __repr__(self) -> str:
        return f"<MonthlyReport {self.month}/{self.year} ({self.status.value})>"
