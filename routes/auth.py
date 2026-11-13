
from datetime import datetime, timedelta, timezone
import hashlib
import hmac

from itsdangerous import (
    URLSafeTimedSerializer,
    BadSignature,
    SignatureExpired
)

from flask import Blueprint, request, jsonify, current_app
from flask_login import (
    login_user,
    logout_user,
    current_user,
    login_required
)
from sqlalchemy import func
from flask_mail import Message

from extensions import db, login_manager, limiter, mail
from models import User


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth"
)


def utc_now():
    return datetime.now(timezone.utc)


def password_fingerprint(user):
    return hashlib.sha256(
        user.password_hash.encode("utf-8")
    ).hexdigest()


def generate_token(user, purpose):
    serializer = URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"]
    )

    payload = {
        "user_id": user.id,
        "purpose": purpose
    }

    if purpose == "password_reset":
        payload["password_fingerprint"] = (
            password_fingerprint(user)
        )

    return serializer.dumps(
        payload,
        salt="human-feedback-auth"
    )


def verify_token(token, purpose, max_age):
    serializer = URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"]
    )

    try:
        data = serializer.loads(
            token,
            salt="human-feedback-auth",
            max_age=max_age
        )

    except (BadSignature, SignatureExpired):
        return None

    if not isinstance(data, dict):
        return None

    if data.get("purpose") != purpose:
        return None

    user_id = data.get("user_id")

    if not isinstance(user_id, int):
        return None

    user = db.session.get(User, user_id)

    if not user:
        return None

    if purpose == "password_reset":
        token_fingerprint = data.get(
            "password_fingerprint",
            ""
        )

        current_fingerprint = password_fingerprint(user)

        if not isinstance(token_fingerprint, str):
            return None

        if not hmac.compare_digest(
            token_fingerprint,
            current_fingerprint
        ):
            return None

    return user


def send_auth_email(subject, recipient, body):
    try:
        message = Message(
            subject=subject,
            recipients=[recipient],
            body=body
        )

        mail.send(message)
        return True

    except Exception:
        current_app.logger.exception(
            "Authentication email delivery failed"
        )
        return False


@login_manager.user_loader
def load_user(user_id):
    """
    Session ID format:
        user_id:auth_version
    """

    try:
        user_id, session_version = user_id.split(":", 1)

        user_id = int(user_id)
        session_version = int(session_version)

    except (AttributeError, TypeError, ValueError):
        return None

    user = db.session.get(User, user_id)

    if not user:
        return None

    if user.auth_version != session_version:
        return None

    return user


def error_response(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


# --------------------------------------------------
# REGISTER
# No email confirmation required
# Public registration always creates a normal user
# --------------------------------------------------

@auth_bp.post("/register")
@limiter.limit("5 per hour")
def register():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    if not name or not email or not password:
        return error_response(
            "Name, email and password are required."
        )

    if len(name) > 120:
        return error_response(
            "Name must not exceed 120 characters."
        )

    if len(email) > 255 or "@" not in email:
        return error_response(
            "Please provide a valid email address."
        )

    if not isinstance(password, str) or len(password) < 8:
        return error_response(
            "Password must contain at least 8 characters."
        )

    if password != confirm_password:
        return error_response(
            "Passwords do not match."
        )

    existing_user = db.session.query(User.id).filter(
        func.lower(User.email) == email
    ).first()

    if existing_user:
        return error_response(
            "Unable to register with these details. Please try logging in.",
            409
        )

    user = User(
        name=name,
        email=email,

        # Never accept a role from public signup.
        role="user",

        # No email verification required.
        is_email_verified=True,

        is_active=True,
        is_suspended=False,
        free_trial_used=False
    )

    user.set_password(password)

    try:
        db.session.add(user)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Registration successful. You can now log in."
        }), 201

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Registration failed"
        )

        return error_response(
            "Registration could not be completed.",
            500
        )


# --------------------------------------------------
# LOGIN
# No email confirmation required
# --------------------------------------------------

@auth_bp.post("/login")
@limiter.limit("10 per hour")
def login():
    if current_user.is_authenticated:
        return jsonify({
            "success": True,
            "message": "Already logged in."
        })

    data = request.get_json(silent=True) or {}

    email = str(
        data.get("email", "")
    ).strip().lower()

    password = data.get("password", "")

    if not email or not password:
        return error_response(
            "Email and password are required."
        )

    user = User.query.filter(
        func.lower(User.email) == email
    ).first()

    if not user or not user.check_password(password):
        return error_response(
            "Invalid email or password.",
            401
        )

    if not user.is_active:
        return error_response(
            "This account is inactive.",
            403
        )

    login_user(
        user,
        remember=False
    )

    if not user.free_trial_used:
        now = utc_now()

        user.free_trial_started_at = now
        user.free_trial_expires_at = (
            now + timedelta(days=30)
        )
        user.free_trial_used = True

    user.updated_at = utc_now()

    try:
        db.session.commit()

    except Exception:
        db.session.rollback()
        logout_user()

        current_app.logger.exception(
            "Login session initialization failed"
        )

        return error_response(
            "Login could not be completed. Please try again.",
            500
        )

    return jsonify({
        "success": True,
        "message": "Login successful.",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "is_suspended": user.is_suspended,
            "suspension_reason": user.suspension_reason,
            "free_trial_started_at": (
                user.free_trial_started_at.isoformat()
                if user.free_trial_started_at else None
            ),
            "free_trial_expires_at": (
                user.free_trial_expires_at.isoformat()
                if user.free_trial_expires_at else None
            )
        }
    })


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()

    return jsonify({
        "success": True,
        "message": "Logout successful."
    })


# --------------------------------------------------
# CURRENT USER
# --------------------------------------------------

@auth_bp.get("/me")
@login_required
def me():
    return jsonify({
        "success": True,
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
            "role": current_user.role,
            "is_email_verified": current_user.is_email_verified,
            "is_active": current_user.is_active,
            "is_suspended": current_user.is_suspended,
            "suspension_reason": current_user.suspension_reason,
            "free_trial_started_at": (
                current_user.free_trial_started_at.isoformat()
                if current_user.free_trial_started_at else None
            ),
            "free_trial_expires_at": (
                current_user.free_trial_expires_at.isoformat()
                if current_user.free_trial_expires_at else None
            )
        }
    })


# --------------------------------------------------
# FORGOT PASSWORD
# Password reset email remains enabled
# --------------------------------------------------

@auth_bp.post("/forgot-password")
@limiter.limit("3 per hour")
def forgot_password():
    data = request.get_json(silent=True) or {}

    email = str(
        data.get("email", "")
    ).strip().lower()

    if email:
        user = User.query.filter(
            func.lower(User.email) == email
        ).first()

        if user and user.is_active:
            token = generate_token(
                user,
                "password_reset"
            )

            frontend_url = current_app.config.get(
                "FRONTEND_URL",
                current_app.config["APP_BASE_URL"]
            ).rstrip("/")

            reset_url = (
                f"{frontend_url}/reset-password?token={token}"
            )

            send_auth_email(
                "Reset your HUMAN FEEDBACK password",
                user.email,
                (
                    "Use this link to reset your password:\n"
                    f"{reset_url}\n\n"
                    "This link expires in 30 minutes."
                )
            )

    return jsonify({
        "success": True,
        "message": (
            "If an eligible account exists, "
            "password reset instructions will be sent."
        )
    })


# --------------------------------------------------
# RESET PASSWORD
# --------------------------------------------------

@auth_bp.post("/reset-password")
@limiter.limit("5 per hour")
def reset_password():
    data = request.get_json(silent=True) or {}

    token = data.get("token", "")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    if not token or not password:
        return error_response(
            "Token and new password are required."
        )

    if not isinstance(password, str) or len(password) < 8:
        return error_response(
            "Password must contain at least 8 characters."
        )

    if password != confirm_password:
        return error_response(
            "Passwords do not match."
        )

    user = verify_token(
        token,
        "password_reset",
        1800
    )

    if not user or not user.is_active:
        return error_response(
            "Password reset link is invalid or expired."
        )

    try:
        user.set_password(password)

        # Invalidate all existing login sessions.
        user.auth_version += 1
        user.updated_at = utc_now()

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Password reset failed"
        )

        return error_response(
            "Password could not be reset. Please try again.",
            500
        )

    return jsonify({
        "success": True,
        "message": "Password has been reset successfully."
    })
