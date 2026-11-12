
from datetime import datetime, timezone

from extensions import db


class WebsiteSuspension(db.Model):
    __tablename__ = "website_suspensions"

    id = db.Column(db.Integer, primary_key=True)

    website_id = db.Column(
        db.Integer,
        db.ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL")
    )

    duration_days = db.Column(
        db.Integer,
        nullable=False
    )

    reason = db.Column(
        db.Text,
        nullable=False
    )

    started_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    expires_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False
    )

    restored_at = db.Column(db.DateTime(timezone=True))

    restored_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL")
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    website = db.relationship(
        "Website",
        back_populates="suspensions"
    )

    admin = db.relationship(
        "User",
        foreign_keys=[admin_id]
    )

    restorer = db.relationship(
        "User",
        foreign_keys=[restored_by]
    )

    def __repr__(self):
        return f"<WebsiteSuspension {self.id}>"
