
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user, login_required
from flask_mail import Message

from extensions import db, mail
from models import (
    Feedback,
    FeedbackReply,
    Notification,
    Subscription,
)


feedback_replies_bp = Blueprint(
    "feedback_replies",
    __name__,
    url_prefix="/api/feedback"
)


def utc_now():
    return datetime.now(timezone.utc)


def normalize_datetime(value):
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def error_response(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def has_active_plan(user):
    if (
        not user
        or not user.is_active
        or user.is_suspended
        or not user.is_email_verified
    ):
        return False

    now = utc_now()

    # Free trial
    trial_expiry = normalize_datetime(
        user.free_trial_expires_at
    )

    if (
        user.free_trial_used
        and trial_expiry
        and trial_expiry > now
    ):
        return True

    # Paid subscription
    subscription = Subscription.query.filter(
        Subscription.user_id == user.id,
        Subscription.status == "active",
        Subscription.expires_at.isnot(None)
    ).order_by(
        Subscription.expires_at.desc()
    ).first()

    if not subscription:
        return False

    expiry = normalize_datetime(
        subscription.expires_at
    )

    return bool(expiry and expiry > now)


def get_participant(feedback):
    is_provider = (
        feedback.user_id == current_user.id
    )

    is_owner = (
        feedback.website is not None
        and feedback.website.owner_id == current_user.id
    )

    return is_provider or is_owner


def serialize_reply(reply):
    return {
        "id": reply.id,
        "feedback_id": reply.feedback_id,
        "user_id": reply.user_id,
        "user_name": (
            reply.user.name if reply.user else None
        ),
        "message": reply.message,
        "created_at": (
            reply.created_at.isoformat()
            if reply.created_at else None
        )
    }


def send_reply_email(
    recipient,
    sender_name,
    message,
    feedback_id
):
    try:
        base_url = current_app.config.get(
            "APP_BASE_URL",
            "http://127.0.0.1:5000"
        )

        email = Message(
            subject="New reply on HUMAN FEEDBACK",
            recipients=[recipient.email],
            body=(
                f"Hi {recipient.name},\n\n"
                f"{sender_name} has replied to your feedback.\n\n"
                f"Reply:\n{message}\n\n"
                f"View conversation:\n"
                f"{base_url}/feedback/{feedback_id}\n\n"
                "Regards,\n"
                "HUMAN FEEDBACK"
            )
        )

        mail.send(email)

    except Exception:
        current_app.logger.exception(
            "Could not send feedback reply email."
        )


def create_notification(recipient, sender, feedback_id):
    notification = Notification(
        user_id=recipient.id,
        title="New feedback reply",
        message=(
            f"{sender.name} replied to your feedback."
        ),
        notification_type="feedback_reply",
        reference_type="feedback",
        reference_id=feedback_id,
        is_read=False
    )

    db.session.add(notification)


@feedback_replies_bp.get("/<int:feedback_id>/replies")
@login_required
def list_replies(feedback_id):
    feedback = db.session.get(
        Feedback,
        feedback_id
    )

    if not feedback:
        return error_response(
            "Feedback not found.",
            404
        )

    if feedback.status != "approved":
        return error_response(
            "Replies are available only for approved feedback.",
            403
        )

    if not get_participant(feedback):
        return error_response(
            "Only the feedback provider and website owner can view this conversation.",
            403
        )

    # Conversation history remains accessible even if a plan expires.
    # Only sending new replies requires both plans to be active.
    replies = FeedbackReply.query.filter_by(
        feedback_id=feedback.id
    ).order_by(
        FeedbackReply.created_at.asc()
    ).all()

    return jsonify({
        "success": True,
        "feedback_id": feedback.id,
        "total": len(replies),
        "replies": [
            serialize_reply(reply)
            for reply in replies
        ]
    })


@feedback_replies_bp.post("/<int:feedback_id>/replies")
@login_required
def create_reply(feedback_id):
    feedback = db.session.get(
        Feedback,
        feedback_id
    )

    if not feedback:
        return error_response(
            "Feedback not found.",
            404
        )

    if feedback.status != "approved":
        return error_response(
            "You can reply only to approved feedback.",
            403
        )

    if not get_participant(feedback):
        return error_response(
            "Only the feedback provider and website owner can reply.",
            403
        )

    provider = feedback.user
    owner = feedback.website.owner if feedback.website else None

    if not provider or not owner:
        return error_response(
            "Feedback participants could not be found.",
            404
        )

    if not has_active_plan(current_user):
        return error_response(
            "Your active plan is required to send replies.",
            403
        )

    # Both participants must have an active plan.
    if not has_active_plan(provider):
        return error_response(
            "The feedback provider's plan is inactive. Replies are currently disabled.",
            403
        )

    if not has_active_plan(owner):
        return error_response(
            "The website owner's plan is inactive. Replies are currently disabled.",
            403
        )

    data = request.get_json(silent=True) or {}

    message = str(
        data.get("message", "")
    ).strip()

    if not message:
        return error_response(
            "Reply message is required."
        )

    if len(message) > 5000:
        return error_response(
            "Reply must not exceed 5,000 characters."
        )

    reply = FeedbackReply(
        feedback_id=feedback.id,
        user_id=current_user.id,
        message=message
    )

    recipient = (
        owner if current_user.id == provider.id
        else provider
    )

    try:
        db.session.add(reply)

        if recipient.id != current_user.id:
            create_notification(
                recipient,
                current_user,
                feedback.id
            )

        db.session.commit()

        if recipient.id != current_user.id:
            send_reply_email(
                recipient,
                current_user.name,
                message,
                feedback.id
            )

        return jsonify({
            "success": True,
            "message": "Reply sent successfully.",
            "reply": serialize_reply(reply)
        }), 201

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Feedback reply creation failed."
        )

        return error_response(
            "Reply could not be sent. Please try again.",
            500
        )
