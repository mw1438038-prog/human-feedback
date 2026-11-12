
from datetime import datetime, timezone

from extensions import db


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)

    reporter_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("report_categories.id", ondelete="RESTRICT"),
        nullable=False
    )

    target_type = db.Column(
        db.String(30),
        nullable=False
    )

    target_id = db.Column(
        db.Integer,
        nullable=False
    )

    reason = db.Column(db.Text, nullable=False)

    evidence_path = db.Column(db.String(500))

    status = db.Column(
        db.String(30),
        nullable=False,
        default="submitted",
        index=True
    )

    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL")
    )

    admin_action = db.Column(db.String(50))
    admin_reason = db.Column(db.Text)

    reviewed_at = db.Column(db.DateTime(timezone=True))

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    reporter = db.relationship(
        "User",
        foreign_keys=[reporter_id]
    )

    admin = db.relationship(
        "User",
        foreign_keys=[admin_id]
    )

    category = db.relationship(
        "ReportCategory",
        back_populates="reports"
    )

    def __repr__(self):
        return f"<Report {self.id}: {self.status}>"
