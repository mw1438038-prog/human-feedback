
from datetime import datetime, timezone

from extensions import db


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    plan_id = db.Column(
        db.Integer,
        db.ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )

    payment_provider = db.Column(
        db.String(30),
        default="internal"
    )

    external_subscription_id = db.Column(
        db.String(255),
        unique=True
    )

    started_at = db.Column(db.DateTime(timezone=True))
    expires_at = db.Column(db.DateTime(timezone=True))

    canceled_at = db.Column(db.DateTime(timezone=True))

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

    user = db.relationship("User")

    plan = db.relationship(
        "Plan",
        back_populates="subscriptions"
    )

    def __repr__(self):
        return f"<Subscription {self.id}: {self.status}>"
