
from datetime import datetime, timezone

from extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    title = db.Column(db.String(200), nullable=False)

    message = db.Column(db.Text, nullable=False)

    notification_type = db.Column(
        db.String(50),
        nullable=False
    )

    reference_type = db.Column(db.String(50))
    reference_id = db.Column(db.Integer)

    is_read = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    read_at = db.Column(db.DateTime(timezone=True))

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship("User")

    def __repr__(self):
        return f"<Notification {self.id}>"
