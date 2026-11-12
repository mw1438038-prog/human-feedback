
from datetime import datetime, timezone

from extensions import db


class Website(db.Model):
    __tablename__ = "websites"

    id = db.Column(db.Integer, primary_key=True)

    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("website_categories.id", ondelete="RESTRICT"),
        nullable=False
    )

    name = db.Column(db.String(150), nullable=False)

    url = db.Column(
        db.String(2048),
        nullable=False,
        index=True
    )

    description = db.Column(db.Text, nullable=False)

    logo_path = db.Column(db.String(500))

    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
        index=True
    )

    rejection_category = db.Column(db.String(100))
    rejection_reason = db.Column(db.Text)

    reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL")
    )

    reviewed_at = db.Column(db.DateTime(timezone=True))

    resubmission_count = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    approved_at = db.Column(db.DateTime(timezone=True))

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

    owner = db.relationship(
        "User",
        foreign_keys=[owner_id]
    )

    reviewer = db.relationship(
        "User",
        foreign_keys=[reviewed_by]
    )

    category = db.relationship(
        "WebsiteCategory",
        back_populates="websites"
    )

    verifications = db.relationship(
        "WebsiteVerification",
        back_populates="website",
        cascade="all, delete-orphan"
    )

    suspensions = db.relationship(
        "WebsiteSuspension",
        back_populates="website",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Website {self.name}: {self.status}>"
