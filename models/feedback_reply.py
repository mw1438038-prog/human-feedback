
from datetime import datetime, timezone

from extensions import db


class FeedbackReply(db.Model):
    __tablename__ = "feedback_replies"

    id = db.Column(db.Integer, primary_key=True)

    feedback_id = db.Column(
        db.Integer,
        db.ForeignKey("feedback.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )

    message = db.Column(db.Text, nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    feedback = db.relationship(
        "Feedback",
        back_populates="replies"
    )

    user = db.relationship("User")

    def __repr__(self):
        return f"<FeedbackReply {self.id}>"
