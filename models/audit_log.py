
from datetime import datetime, timezone

from extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    actor_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    action = db.Column(
        db.String(100),
        nullable=False
    )

    entity_type = db.Column(db.String(100))
    entity_id = db.Column(db.Integer)

    description = db.Column(db.Text, nullable=False)

    reason = db.Column(db.Text)

    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))

    extra_data = db.Column(db.JSON)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    actor = db.relationship("User")

    def __repr__(self):
        return f"<AuditLog {self.id}: {self.action}>"
