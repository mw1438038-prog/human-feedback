
from datetime import datetime, timezone

from extensions import db


class WebsiteVerification(db.Model):
    __tablename__ = "website_verifications"

    id = db.Column(db.Integer, primary_key=True)

    website_id = db.Column(
        db.Integer,
        db.ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    proof_path = db.Column(
        db.String(500),
        nullable=False
    )

    proof_type = db.Column(db.String(100))

    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )

    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL")
    )

    admin_reason = db.Column(db.Text)

    reviewed_at = db.Column(db.DateTime(timezone=True))

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    website = db.relationship(
        "Website",
        back_populates="verifications"
    )

    admin = db.relationship(
        "User",
        foreign_keys=[admin_id]
    )

    def __repr__(self):
        return f"<WebsiteVerification {self.id}: {self.status}>"
