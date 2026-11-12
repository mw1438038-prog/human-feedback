
from datetime import datetime, timezone

from extensions import db


class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)

    website_id = db.Column(
        db.Integer,
        db.ForeignKey("websites.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    overall_rating = db.Column(db.Integer, nullable=False)
    design_rating = db.Column(db.Integer, nullable=False)
    speed_rating = db.Column(db.Integer, nullable=False)
    ux_rating = db.Column(db.Integer, nullable=False)
    content_rating = db.Column(db.Integer, nullable=False)

    comment = db.Column(db.Text, nullable=False)

    screenshot_path = db.Column(db.String(500))

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

    reward_credited = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    visit_recorded_at = db.Column(
        db.DateTime(timezone=True)
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

    website = db.relationship("Website")

    user = db.relationship(
        "User",
        foreign_keys=[user_id]
    )

    reviewer = db.relationship(
        "User",
        foreign_keys=[reviewed_by]
    )

    replies = db.relationship(
        "FeedbackReply",
        back_populates="feedback",
        cascade="all, delete-orphan",
        order_by="FeedbackReply.created_at"
    )

    def __repr__(self):
        return f"<Feedback {self.id}: {self.status}>"
