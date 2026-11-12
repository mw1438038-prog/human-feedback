
from datetime import datetime, timezone
from math import ceil

from flask import Blueprint, jsonify
from flask_login import current_user, login_required
from sqlalchemy import func, desc

from extensions import db
from models import (
    Website,
    Feedback,
    CreditTransaction,
    Subscription,
    Notification,
)


dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/api/dashboard"
)


def utc_now():
    return datetime.now(timezone.utc)


def normalize_datetime(value):
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def serialize_datetime(value):
    value = normalize_datetime(value)
    return value.isoformat() if value else None


def get_active_subscription(user_id, now):
    subscriptions = Subscription.query.filter_by(
        user_id=user_id,
        status="active"
    ).order_by(
        desc(Subscription.expires_at),
        desc(Subscription.id)
    ).all()

    for subscription in subscriptions:
        expiry = normalize_datetime(
            subscription.expires_at
        )

        if expiry and expiry > now:
            return subscription

    return None


def get_trial_data(user, now):
    started_at = normalize_datetime(
        user.free_trial_started_at
    )

    expires_at = normalize_datetime(
        user.free_trial_expires_at
    )

    trial_active = bool(
        user.free_trial_used
        and started_at
        and expires_at
        and expires_at > now
    )

    if not user.free_trial_used:
        status = "not_started"
    elif trial_active:
        status = "active"
    else:
        status = "expired"

    remaining_days = (
        ceil((expires_at - now).total_seconds() / 86400)
        if trial_active else 0
    )

    return {
        "used": user.free_trial_used,
        "status": status,
        "active": trial_active,
        "started_at": serialize_datetime(started_at),
        "expires_at": serialize_datetime(expires_at),
        "remaining_days": remaining_days,
    }


def get_access_data(user, trial_active, subscription):
    if not user.is_active:
        status = "inactive"
    elif user.is_suspended:
        status = "suspended"
    elif not user.is_email_verified:
        status = "email_not_verified"
    elif not trial_active and not subscription:
        status = "plan_expired"
    else:
        status = "active"

    return {
        "platform_access": status == "active",
        "status": status,
        "is_active": user.is_active,
        "is_suspended": user.is_suspended,
        "suspension_reason": user.suspension_reason,
        "is_email_verified": user.is_email_verified,
    }


@dashboard_bp.get("/")
@login_required
def overview():
    user_id = current_user.id
    now = utc_now()

    # Website statistics
    website_stats = db.session.query(
        func.count(Website.id).label("total"),
        func.count(Website.id).filter(
            Website.status == "active"
        ).label("active"),
        func.count(Website.id).filter(
            Website.status == "pending"
        ).label("pending"),
        func.count(Website.id).filter(
            Website.status == "rejected"
        ).label("rejected"),
    ).filter(
        Website.owner_id == user_id
    ).one()

    # Feedback submitted by user
    submitted_stats = db.session.query(
        func.count(Feedback.id).label("total"),
        func.count(Feedback.id).filter(
            Feedback.status == "approved"
        ).label("approved"),
        func.count(Feedback.id).filter(
            Feedback.status == "pending"
        ).label("pending"),
        func.count(Feedback.id).filter(
            Feedback.status == "rejected"
        ).label("rejected"),
    ).filter(
        Feedback.user_id == user_id
    ).one()

    # Approved feedback received by user's websites
    received_feedback_count = db.session.query(
        func.count(Feedback.id)
    ).join(
        Website,
        Feedback.website_id == Website.id
    ).filter(
        Website.owner_id == user_id,
        Feedback.status == "approved"
    ).scalar() or 0

    # Latest credit balance
    latest_transaction = CreditTransaction.query.filter_by(
        user_id=user_id
    ).order_by(
        desc(CreditTransaction.created_at),
        desc(CreditTransaction.id)
    ).first()

    available_credits = (
        latest_transaction.balance_after
        if latest_transaction else 0
    )

    # Subscription and Free Trial
    active_subscription = get_active_subscription(
        user_id,
        now
    )

    trial_data = get_trial_data(
        current_user,
        now
    )

    access_data = get_access_data(
        current_user,
        trial_data["active"],
        active_subscription
    )

    subscription_data = None

    if active_subscription:
        plan = active_subscription.plan

        subscription_data = {
            "id": active_subscription.id,
            "status": active_subscription.status,
            "payment_provider": active_subscription.payment_provider,
            "plan": {
                "id": plan.id,
                "name": plan.name,
                "code": plan.code,
                "website_limit": plan.website_limit,
                "is_trial": plan.is_trial,
            },
            "started_at": serialize_datetime(
                active_subscription.started_at
            ),
            "expires_at": serialize_datetime(
                active_subscription.expires_at
            ),
        }

    # Recent notifications
    recent_notifications = Notification.query.filter_by(
        user_id=user_id
    ).order_by(
        desc(Notification.created_at),
        desc(Notification.id)
    ).limit(5).all()

    unread_notifications = Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).count()

    notifications_data = [
        {
            "id": item.id,
            "title": item.title,
            "message": item.message,
            "type": item.notification_type,
            "is_read": item.is_read,
            "created_at": serialize_datetime(
                item.created_at
            ),
        }
        for item in recent_notifications
    ]

    return jsonify({
        "success": True,
        "dashboard": {
            "user": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
                "role": current_user.role,
            },
            "account": access_data,
            "websites": {
                "total": website_stats.total,
                "active": website_stats.active,
                "pending": website_stats.pending,
                "rejected": website_stats.rejected,
            },
            "submitted_feedback": {
                "total": submitted_stats.total,
                "approved": submitted_stats.approved,
                "pending": submitted_stats.pending,
                "rejected": submitted_stats.rejected,
            },
            "received_approved_feedback": received_feedback_count,
            "credits": {
                "available": available_credits,
            },
            "subscription": subscription_data,
            "free_trial": trial_data,
            "notifications": {
                "unread": unread_notifications,
                "recent": notifications_data,
            },
        },
    })


@dashboard_bp.get("/summary")
@login_required
def summary():
    user_id = current_user.id
    now = utc_now()

    total_websites = Website.query.filter_by(
        owner_id=user_id
    ).count()

    total_feedback = Feedback.query.filter_by(
        user_id=user_id
    ).count()

    approved_feedback = Feedback.query.filter_by(
        user_id=user_id,
        status="approved"
    ).count()

    unread_notifications = Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).count()

    active_subscription = get_active_subscription(
        user_id,
        now
    )

    trial_data = get_trial_data(
        current_user,
        now
    )

    access_data = get_access_data(
        current_user,
        trial_data["active"],
        active_subscription
    )

    return jsonify({
        "success": True,
        "summary": {
            "total_websites": total_websites,
            "total_feedback_submitted": total_feedback,
            "approved_feedback": approved_feedback,
            "unread_notifications": unread_notifications,
            "free_trial": trial_data,
            "account": access_data,
        },
    })
