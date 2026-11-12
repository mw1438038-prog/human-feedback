
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from extensions import db
from models import Notification


notifications_bp = Blueprint(
    "notifications",
    __name__,
    url_prefix="/api/notifications"
)


def serialize_notification(notification):
    return {
        "id": notification.id,
        "title": notification.title,
        "message": notification.message,
        "notification_type": notification.notification_type,
        "reference_type": notification.reference_type,
        "reference_id": notification.reference_id,
        "is_read": notification.is_read,
        "read_at": (
            notification.read_at.isoformat()
            if notification.read_at else None
        ),
        "created_at": (
            notification.created_at.isoformat()
            if notification.created_at else None
        )
    }


@notifications_bp.get("/")
@login_required
def notification_list():
    page = request.args.get("page", 1, type=int)
    per_page = min(
        request.args.get("per_page", 20, type=int),
        100
    )

    if page < 1 or per_page < 1:
        return jsonify({
            "success": False,
            "message": "Invalid pagination values."
        }), 400

    pagination = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Notification.created_at.desc()
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()

    return jsonify({
        "success": True,
        "unread_count": unread_count,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "notifications": [
            serialize_notification(item)
            for item in pagination.items
        ]
    })


@notifications_bp.get("/unread-count")
@login_required
def unread_notification_count():
    count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()

    return jsonify({
        "success": True,
        "unread_count": count
    })


@notifications_bp.put("/<int:notification_id>/read")
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first()

    if not notification:
        return jsonify({
            "success": False,
            "message": "Notification not found."
        }), 404

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = db.func.now()
        db.session.commit()

    return jsonify({
        "success": True,
        "message": "Notification marked as read.",
        "notification": serialize_notification(notification)
    })


@notifications_bp.put("/read-all")
@login_required
def mark_all_notifications_read():
    db.session.query(Notification).filter_by(
        user_id=current_user.id,
        is_read=False
    ).update(
        {
            Notification.is_read: True,
            Notification.read_at: db.func.now()
        },
        synchronize_session=False
    )

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "All notifications marked as read."
    })
