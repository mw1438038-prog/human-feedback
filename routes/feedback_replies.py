
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user, login_required
from flask_mail import Message
from sqlalchemy import or_

from extensions import db, mail
from models import (
    Feedback,
    FeedbackReply,
    Notification,
    Subscription,
    Website,
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

    trial_expiry = normalize_datetime(
        user.free_trial_expires_at
    )

    if (
        user.free_trial_used
        and trial_expiry
        and trial_expiry > now
    ):
        return True

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


def serialize_conversation(feedback):
    provider = feedback.user
    website = feedback.website
    owner = website.owner if website else None

    replies = feedback.replies or []

    latest_reply = (
        replies[-1] if replies else None
    )

    is_provider = (
        feedback.user_id == current_user.id
    )

    is_owner = (
        owner is not None
        and owner.id == current_user.id
    )

    if is_provider:
        conversation_type = "sent"
        other_user = owner
    elif is_owner:
        conversation_type = "received"
        other_user = provider
    else:
        conversation_type = None
        other_user = None

    if latest_reply:
        last_message = latest_reply.message
        last_message_by = (
            latest_reply.user.name
            if latest_reply.user else None
        )
        last_message_at = latest_reply.created_at
    else:
        last_message = feedback.comment
        last_message_by = (
            provider.name if provider else None
        )
        last_message_at = feedback.created_at

    return {
        "id": feedback.id,
        "feedback_id": feedback.id,

        "conversation_type": conversation_type,

        "website": {
            "id": website.id if website else None,
            "name": website.name if website else None,
            "url": website.url if website else None,
        },

        "feedback": {
            "comment": feedback.comment,
            "overall_rating": feedback.overall_rating,
            "design_rating": feedback.design_rating,
            "speed_rating": feedback.speed_rating,
            "ux_rating": feedback.ux_rating,
            "content_rating": feedback.content_rating,
            "created_at": (
                feedback.created_at.isoformat()
                if feedback.created_at else None
            )
        },

        "provider": {
            "id": provider.id if provider else None,
            "name": provider.name if provider else None,
        },

        "owner": {
            "id": owner.id if owner else None,
            "name": owner.name if owner else None,
        },

        "other_user": {
            "id": other_user.id if other_user else None,
            "name": other_user.name if other_user else None,
        },

        "reply_count": len(replies),

        "last_message": last_message,
        "last_message_by": last_message_by,
        "last_message_at": (
            last_message_at.isoformat()
            if last_message_at else None
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


# --------------------------------------------------
# CONVERSATION INBOX
# --------------------------------------------------

@feedback_replies_bp.get("/conversations")
@login_required
def list_conversations():
    """
    Returns approved feedback conversations involving
    the current user.

    Sent:
        Feedback submitted by current user.

    Received:
        Feedback submitted by other users on websites
        owned by current user.

    Conversation history remains accessible even if
    the user's subscription or trial expires.
    """

    try:
        conversations = Feedback.query.join(
            Website,
            Feedback.website_id == Website.id
        ).filter(
            Feedback.status == "approved",
            or_(
                Feedback.user_id == current_user.id,
                Website.owner_id == current_user.id
            )
        ).order_by(
            Feedback.updated_at.desc(),
            Feedback.created_at.desc()
        ).all()

        results = [
            serialize_conversation(feedback)
            for feedback in conversations
        ]

        sent_count = sum(
            1 for item in results
            if item["conversation_type"] == "sent"
        )

        received_count = sum(
            1 for item in results
            if item["conversation_type"] == "received"
        )

        return jsonify({
            "success": True,
            "current_user_id": current_user.id,
            "total": len(results),
            "sent_count": sent_count,
            "received_count": received_count,
            "conversations": results
        })

    except Exception:
        current_app.logger.exception(
            "Could not load feedback conversations."
        )

        return error_response(
            "Conversations could not be loaded.",
            500
        )


# --------------------------------------------------
# LIST REPLIES
# --------------------------------------------------

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


# --------------------------------------------------
# CREATE REPLY
# --------------------------------------------------

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
