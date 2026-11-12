
from datetime import datetime, timezone

from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from extensions import db
from models import Plan, Subscription


subscriptions_bp = Blueprint(
    "subscriptions",
    __name__,
    url_prefix="/api/subscriptions"
)


def utc_now():
    return datetime.now(timezone.utc)


def normalize_datetime(value):
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def get_current_subscription(user_id):
    now = utc_now()

    subscriptions = Subscription.query.filter_by(
        user_id=user_id,
        status="active"
    ).order_by(
        Subscription.expires_at.desc()
    ).all()

    for subscription in subscriptions:
        expires_at = normalize_datetime(
            subscription.expires_at
        )

        if expires_at and expires_at > now:
            return subscription

    return None


def serialize_plan(plan):
    return {
        "id": plan.id,
        "name": plan.name,
        "code": plan.code,
        "description": plan.description,
        "duration_days": plan.duration_days,
        "website_limit": plan.website_limit,
        "monthly_price": (
            float(plan.monthly_price)
            if plan.monthly_price is not None else None
        ),
        "is_trial": plan.is_trial
    }


def serialize_subscription(subscription):
    return {
        "id": subscription.id,
        "status": subscription.status,
        "payment_provider": subscription.payment_provider,
        "external_subscription_id": (
            subscription.external_subscription_id
        ),
        "started_at": (
            subscription.started_at.isoformat()
            if subscription.started_at else None
        ),
        "expires_at": (
            subscription.expires_at.isoformat()
            if subscription.expires_at else None
        ),
        "canceled_at": (
            subscription.canceled_at.isoformat()
            if subscription.canceled_at else None
        ),
        "plan": serialize_plan(subscription.plan)
    }


@subscriptions_bp.get("/plans")
def available_plans():
    plans = Plan.query.filter_by(
        is_active=True
    ).order_by(
        Plan.monthly_price.asc()
    ).all()

    return jsonify({
        "success": True,
        "plans": [
            serialize_plan(plan)
            for plan in plans
        ]
    })


@subscriptions_bp.get("/current")
@login_required
def current_subscription():
    subscription = get_current_subscription(
        current_user.id
    )

    trial_started = normalize_datetime(
        current_user.free_trial_started_at
    )

    trial_expires = normalize_datetime(
        current_user.free_trial_expires_at
    )

    now = utc_now()

    trial_active = bool(
        current_user.free_trial_used
        and trial_started
        and trial_expires
        and trial_expires > now
    )

    trial = {
        "used": current_user.free_trial_used,
        "active": trial_active,
        "started_at": (
            trial_started.isoformat()
            if trial_started else None
        ),
        "expires_at": (
            trial_expires.isoformat()
            if trial_expires else None
        )
    }

    return jsonify({
        "success": True,
        "has_active_subscription": subscription is not None,
        "subscription": (
            serialize_subscription(subscription)
            if subscription else None
        ),
        "free_trial": trial,
        "platform_access": (
            subscription is not None or trial_active
        )
    })


@subscriptions_bp.get("/history")
@login_required
def subscription_history():
    subscriptions = Subscription.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Subscription.created_at.desc()
    ).all()

    return jsonify({
        "success": True,
        "total": len(subscriptions),
        "subscriptions": [
            serialize_subscription(item)
            for item in subscriptions
        ]
    })


@subscriptions_bp.get("/<int:subscription_id>")
@login_required
def subscription_detail(subscription_id):
    subscription = db.session.get(
        Subscription,
        subscription_id
    )

    if not subscription:
        return jsonify({
            "success": False,
            "message": "Subscription not found."
        }), 404

    if subscription.user_id != current_user.id:
        return jsonify({
            "success": False,
            "message": "You cannot access this subscription."
        }), 403

    return jsonify({
        "success": True,
        "subscription": serialize_subscription(
            subscription
        )
    })
