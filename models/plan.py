
from datetime import datetime, timezone

from extensions import db


class Plan(db.Model):
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    code = db.Column(
        db.String(30),
        unique=True,
        nullable=False
    )

    description = db.Column(db.Text)

    duration_days = db.Column(
        db.Integer,
        nullable=False,
        default=30
    )

    website_limit = db.Column(db.Integer)

    monthly_price = db.Column(
        db.Numeric(10, 2),
        nullable=False,
        default=0
    )

    is_trial = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

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

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    subscriptions = db.relationship(
        "Subscription",
        back_populates="plan"
    )

    def __repr__(self):
        return f"<Plan {self.code}>"
