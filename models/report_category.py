
from datetime import datetime, timezone

from extensions import db


class ReportCategory(db.Model):
    __tablename__ = "report_categories"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    slug = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    description = db.Column(db.Text)

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    reports = db.relationship(
        "Report",
        back_populates="category"
    )

    def __repr__(self):
        return f"<ReportCategory {self.name}>"
