from datetime import datetime

from ..extensions import db
from .enums import MonthlyReportStatus, WeeklyReportStatus

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
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
    validated_by = db.relationship("User", foreign_keys=[validated_by_id])
    monthly_report = db.relationship("MonthlyReport", back_populates="weekly_reports")

    def can_transition_to(self, new_status: WeeklyReportStatus) -> bool:
        return new_status in WEEKLY_REPORT_TRANSITIONS.get(self.status, set())

    def __repr__(self) -> str:
        return f"<WeeklyReport user={self.user_id} {self.period_start}..{self.period_end}>"


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
    observations = db.Column(db.Text)
    finalized_at = db.Column(db.DateTime)
    finalized_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    finalized_by = db.relationship("User")
    weekly_reports = db.relationship("WeeklyReport", back_populates="monthly_report")

    def __repr__(self) -> str:
        return f"<MonthlyReport {self.month}/{self.year}>"
