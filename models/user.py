
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = db.Column(db.String(255), nullable=False)

    # Increment this value to invalidate all existing login sessions.
    auth_version = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0"
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="user"
    )

    is_email_verified = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    is_suspended = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    suspension_reason = db.Column(db.Text)

    free_trial_started_at = db.Column(db.DateTime(timezone=True))
    free_trial_expires_at = db.Column(db.DateTime(timezone=True))

    free_trial_used = db.Column(
        db.Boolean,
        nullable=False,
        default=False
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

    profile = db.relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    def get_id(self):
        return f"{self.id}:{self.auth_version}"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"
