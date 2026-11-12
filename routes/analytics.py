
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from models import (
    Website,
    Feedback,
    CreditTransaction,
)


analytics_bp = Blueprint(
    "analytics",
    __name__,
    url_prefix="/api/analytics"
)


def error_response(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def get_owned_website(website_id):
    return Website.query.filter_by(
        id=website_id,
        owner_id=current_user.id
    ).first()


def get_credit_balance(user_id):
    balance = db.session.query(
        func.coalesce(
            func.sum(CreditTransaction.amount),
            0
        )
    ).filter(
        CreditTransaction.user_id == user_id
    ).scalar()

    return int(balance or 0)


def get_date_range():
    days = request.args.get("days", 30, type=int)

    if days not in {7, 30, 90, 180, 365}:
        return None

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    return start_date, end_date


# --------------------------------------------------
# User analytics overview
# --------------------------------------------------

@analytics_bp.get("/overview")
@login_required
def analytics_overview():
    date_range = get_date_range()

    if not date_range:
        return error_response(
            "Days must be 7, 30, 90, 180 or 365."
        )

    start_date, end_date = date_range

    websites = Website.query.filter_by(
        owner_id=current_user.id
    ).all()

    website_ids = [website.id for website in websites]

    approved_query = Feedback.query.filter(
        Feedback.website_id.in_(website_ids),
        Feedback.status == "approved",
        Feedback.created_at >= start_date,
        Feedback.created_at <= end_date
    )

    total_feedback = approved_query.count()

    average_rating = approved_query.with_entities(
        func.avg(Feedback.overall_rating)
    ).scalar()

    received_feedback = Feedback.query.filter(
        Feedback.website_id.in_(website_ids),
        Feedback.status == "approved"
    ).count()

    submitted_feedback = Feedback.query.filter_by(
        user_id=current_user.id
    ).filter(
        Feedback.created_at >= start_date,
        Feedback.created_at <= end_date
    ).count()

    approved_submitted_feedback = Feedback.query.filter_by(
        user_id=current_user.id,
        status="approved"
    ).filter(
        Feedback.created_at >= start_date,
        Feedback.created_at <= end_date
    ).count()

    pending_submitted_feedback = Feedback.query.filter_by(
        user_id=current_user.id,
        status="pending"
    ).count()

    rejected_submitted_feedback = Feedback.query.filter_by(
        user_id=current_user.id,
        status="rejected"
    ).count()

    credits_earned = db.session.query(
        func.coalesce(
            func.sum(CreditTransaction.amount),
            0
        )
    ).filter(
        CreditTransaction.user_id == current_user.id,
        CreditTransaction.amount > 0,
        CreditTransaction.created_at >= start_date,
        CreditTransaction.created_at <= end_date
    ).scalar()

    credits_spent = db.session.query(
        func.coalesce(
            func.sum(CreditTransaction.amount * -1),
            0
        )
    ).filter(
        CreditTransaction.user_id == current_user.id,
        CreditTransaction.amount < 0,
        CreditTransaction.created_at >= start_date,
        CreditTransaction.created_at <= end_date
    ).scalar()

    return jsonify({
        "success": True,
        "period_days": request.args.get(
            "days",
            30,
            type=int
        ),
        "overview": {
            "total_websites": len(websites),
            "active_websites": sum(
                1 for website in websites
                if website.status == "active"
            ),
            "pending_websites": sum(
                1 for website in websites
                if website.status == "pending"
            ),
            "rejected_websites": sum(
                1 for website in websites
                if website.status == "rejected"
            ),
            "received_approved_feedback": received_feedback,
            "received_feedback_in_period": total_feedback,
            "average_received_rating": (
                round(float(average_rating), 2)
                if average_rating is not None else 0
            ),
            "submitted_feedback": submitted_feedback,
            "approved_submitted_feedback": approved_submitted_feedback,
            "pending_submitted_feedback": pending_submitted_feedback,
            "rejected_submitted_feedback": rejected_submitted_feedback,
            "credits_balance": get_credit_balance(
                current_user.id
            ),
            "credits_earned_in_period": int(
                credits_earned or 0
            ),
            "credits_spent_in_period": int(
                credits_spent or 0
            )
        }
    })


# --------------------------------------------------
# Individual website analytics
# --------------------------------------------------

@analytics_bp.get("/website/<int:website_id>")
@login_required
def website_analytics(website_id):
    website = get_owned_website(website_id)

    if not website:
        return error_response(
            "Website not found or access denied.",
            404
        )

    date_range = get_date_range()

    if not date_range:
        return error_response(
            "Days must be 7, 30, 90, 180 or 365."
        )

    start_date, end_date = date_range

    query = Feedback.query.filter_by(
        website_id=website.id,
        status="approved"
    )

    period_query = query.filter(
        Feedback.created_at >= start_date,
        Feedback.created_at <= end_date
    )

    total_feedback = query.count()
    period_feedback = period_query.count()

    def average_rating(column):
        value = period_query.with_entities(
            func.avg(column)
        ).scalar()

        return (
            round(float(value), 2)
            if value is not None else 0
        )

    ratings = {
        "overall": average_rating(
            Feedback.overall_rating
        ),
        "design": average_rating(
            Feedback.design_rating
        ),
        "speed": average_rating(
            Feedback.speed_rating
        ),
        "ux": average_rating(
            Feedback.ux_rating
        ),
        "content": average_rating(
            Feedback.content_rating
        )
    }

    rating_distribution = {}

    for rating in range(1, 6):
        rating_distribution[str(rating)] = period_query.filter(
            Feedback.overall_rating == rating
        ).count()

    return jsonify({
        "success": True,
        "website": {
            "id": website.id,
            "name": website.name,
            "url": website.url,
            "status": website.status
        },
        "period_days": request.args.get(
            "days",
            30,
            type=int
        ),
        "analytics": {
            "total_approved_feedback": total_feedback,
            "approved_feedback_in_period": period_feedback,
            "ratings": ratings,
            "rating_distribution": rating_distribution
        }
    })


# --------------------------------------------------
# Feedback trend by date
# --------------------------------------------------

@analytics_bp.get("/website/<int:website_id>/trends")
@login_required
def website_feedback_trends(website_id):
    website = get_owned_website(website_id)

    if not website:
        return error_response(
            "Website not found or access denied.",
            404
        )

    date_range = get_date_range()

    if not date_range:
        return error_response(
            "Days must be 7, 30, 90, 180 or 365."
        )

    start_date, end_date = date_range

    feedback_items = Feedback.query.filter(
        Feedback.website_id == website.id,
        Feedback.status == "approved",
        Feedback.created_at >= start_date,
        Feedback.created_at <= end_date
    ).order_by(
        Feedback.created_at.asc()
    ).all()

    daily_data = {}

    current_date = start_date.date()
    final_date = end_date.date()

    while current_date <= final_date:
        daily_data[current_date.isoformat()] = {
            "date": current_date.isoformat(),
            "feedback_count": 0,
            "total_rating": 0,
            "average_rating": 0
        }

        current_date += timedelta(days=1)

    for feedback in feedback_items:
        date_key = feedback.created_at.date().isoformat()

        if date_key not in daily_data:
            continue

        daily_data[date_key]["feedback_count"] += 1
        daily_data[date_key]["total_rating"] += (
            feedback.overall_rating
        )

    for item in daily_data.values():
        count = item["feedback_count"]

        if count:
            item["average_rating"] = round(
                item["total_rating"] / count,
                2
            )

        del item["total_rating"]

    return jsonify({
        "success": True,
        "website_id": website.id,
        "website_name": website.name,
        "period_days": request.args.get(
            "days",
            30,
            type=int
        ),
        "trends": list(daily_data.values())
    })


# --------------------------------------------------
# User feedback performance
# --------------------------------------------------

@analytics_bp.get("/my-feedback")
@login_required
def my_feedback_analytics():
    date_range = get_date_range()

    if not date_range:
        return error_response(
            "Days must be 7, 30, 90, 180 or 365."
        )

    start_date, end_date = date_range

    feedback_items = Feedback.query.filter(
        Feedback.user_id == current_user.id,
        Feedback.created_at >= start_date,
        Feedback.created_at <= end_date
    )

    total = feedback_items.count()

    approved = feedback_items.filter_by(
        status="approved"
    ).count()

    pending = feedback_items.filter_by(
        status="pending"
    ).count()

    rejected = feedback_items.filter_by(
        status="rejected"
    ).count()

    return jsonify({
        "success": True,
        "period_days": request.args.get(
            "days",
            30,
            type=int
        ),
        "feedback_statistics": {
            "total": total,
            "approved": approved,
            "pending": pending,
            "rejected": rejected
        }
    })
