
from datetime import datetime, timezone

from extensions import db


class CreditTransaction(db.Model):
    __tablename__ = "credit_transactions"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    amount = db.Column(db.Integer, nullable=False)

    transaction_type = db.Column(
        db.String(30),
        nullable=False
    )

    description = db.Column(db.Text, nullable=False)

    reference_type = db.Column(db.String(50))
    reference_id = db.Column(db.Integer)

    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL")
    )

    balance_after = db.Column(db.Integer, nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id]
    )

    admin = db.relationship(
        "User",
        foreign_keys=[admin_id]
    )

    def __repr__(self):
        return f"<CreditTransaction {self.id}: {self.amount}>"
