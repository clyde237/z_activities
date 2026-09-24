from ..extensions import db
from .enums import PeriodType


class AccountingPeriod(db.Model):
    """Période comptable (section 24), pour préparer les tâches récurrentes
    (section 25) sans les implémenter dans cette version."""

    __tablename__ = "accounting_periods"
    __table_args__ = (
        db.CheckConstraint("end_date >= start_date", name="ck_accounting_period_dates"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    period_type = db.Column(
        db.Enum(PeriodType, native_enum=False, length=24), nullable=False
    )
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    def __repr__(self) -> str:
        return f"<AccountingPeriod {self.name}>"
