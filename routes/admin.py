
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import (
    Blueprint,
    jsonify,
    request,
    current_app,
    send_file,
)
from flask_login import current_user, login_required
from flask_mail import Message
from sqlalchemy import func, or_

from extensions import db, mail
from models import (
    User,
    Website,
    WebsiteVerification,
    WebsiteSuspension,
    Feedback,
    CreditTransaction,
    Subscription,
    Notification,
    Report,
    AuditLog,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

FEEDBACK_REWARD = 10
WEBSITE_CREDIT_COST = 1000
SUSPENSION_DURATIONS = {7, 15, 30}


# --------------------------------------------------
# General helpers
# --------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc)


def error_response(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def admin_required():
    if current_user.role != "admin":
        return error_response("Admin access required.", 403)

    if not current_user.is_active or current_user.is_suspended:
        return error_response(
            "Your account is inactive or suspended.",
            403
        )

    return None


def resolve_upload_path(relative_path):
    """
    Resolve an upload path safely inside UPLOAD_FOLDER.
    Supports both relative and absolute paths from older records.
    """
    if not relative_path:
        return None

    upload_root = Path(
        current_app.config["UPLOAD_FOLDER"]
    ).resolve()

    supplied_path = Path(relative_path)

    if supplied_path.is_absolute():
        file_path = supplied_path.resolve()
    else:
        file_path = (upload_root / supplied_path).resolve()

    try:
        file_path.relative_to(upload_root)
    except ValueError:
        current_app.logger.error(
            "Blocked file path outside upload directory."
        )
        return None

    return file_path


def send_admin_email(recipient, subject, body):
    """Email failure must never undo a committed admin action."""
    if not recipient or not recipient.email:
        return False

    try:
        message = Message(
            subject=subject,
            recipients=[recipient.email],
            body=body
        )
        mail.send(message)
        return True

    except Exception:
        current_app.logger.exception(
            "Admin notification email delivery failed."
        )
        return False


def create_notification(
    user_id,
    title,
    message,
    notification_type,
    reference_type=None,
    reference_id=None
):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        reference_type=reference_type,
        reference_id=reference_id
    )

    db.session.add(notification)
    return notification


def create_audit_log(
    action,
    entity_type,
    entity_id,
    description,
    reason=None,
    extra_data=None
):
    log = AuditLog(
        actor_id=current_user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        reason=reason,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:500],
        extra_data=extra_data
    )

    db.session.add(log)
    return log


def get_credit_balance(user_id):
    balance = db.session.query(
        func.coalesce(func.sum(CreditTransaction.amount), 0)
    ).filter(
        CreditTransaction.user_id == user_id
    ).scalar()

    return int(balance or 0)


def serialize_user(user):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_email_verified": user.is_email_verified,
        "is_active": user.is_active,
        "is_suspended": user.is_suspended,
        "suspension_reason": user.suspension_reason,
        "free_trial_used": user.free_trial_used,
        "free_trial_expires_at": (
            user.free_trial_expires_at.isoformat()
            if user.free_trial_expires_at else None
        ),
        "created_at": (
            user.created_at.isoformat()
            if user.created_at else None
        )
    }


def serialize_website(website):
    return {
        "id": website.id,
        "owner_id": website.owner_id,
        "owner_name": website.owner.name if website.owner else None,
        "owner_email": website.owner.email if website.owner else None,
        "name": website.name,
        "url": website.url,
        "description": website.description,
        "category": (
            website.category.name if website.category else None
        ),
        "status": website.status,
        "rejection_category": website.rejection_category,
        "rejection_reason": website.rejection_reason,
        "resubmission_count": website.resubmission_count,
        "approved_at": (
            website.approved_at.isoformat()
            if website.approved_at else None
        ),
        "created_at": (
            website.created_at.isoformat()
            if website.created_at else None
        )
    }


def serialize_feedback(feedback):
    return {
        "id": feedback.id,
        "website_id": feedback.website_id,
        "website_name": (
            feedback.website.name if feedback.website else None
        ),
        "user_id": feedback.user_id,
        "user_name": feedback.user.name if feedback.user else None,
        "overall_rating": feedback.overall_rating,
        "design_rating": feedback.design_rating,
        "speed_rating": feedback.speed_rating,
        "ux_rating": feedback.ux_rating,
        "content_rating": feedback.content_rating,
        "comment": feedback.comment,
        "status": feedback.status,
        "rejection_category": feedback.rejection_category,
        "rejection_reason": feedback.rejection_reason,
        "reward_credited": feedback.reward_credited,
        "created_at": (
            feedback.created_at.isoformat()
            if feedback.created_at else None
        )
    }


def serialize_report(report):
    return {
        "id": report.id,
        "reporter_id": report.reporter_id,
        "reporter_name": (
            report.reporter.name if report.reporter else None
        ),
        "category": (
            report.category.name if report.category else None
        ),
        "target_type": report.target_type,
        "target_id": report.target_id,
        "reason": report.reason,
        "has_evidence": bool(report.evidence_path),
        "status": report.status,
        "admin_action": report.admin_action,
        "admin_reason": report.admin_reason,
        "reviewed_at": (
            report.reviewed_at.isoformat()
            if report.reviewed_at else None
        ),
        "created_at": (
            report.created_at.isoformat()
            if report.created_at else None
        )
    }


def get_report_target(report):
    if report.target_type == "website":
        return db.session.get(Website, report.target_id)

    if report.target_type == "feedback":
        return db.session.get(Feedback, report.target_id)

    return None


def create_website_suspension(website, reason, duration, admin_id):
    now = utc_now()

    suspension = WebsiteSuspension(
        website_id=website.id,
        admin_id=admin_id,
        duration_days=duration,
        reason=reason,
        started_at=now,
        expires_at=now + timedelta(days=duration),
        is_active=True
    )

    db.session.add(suspension)
    return suspension


def send_user_notification_email(user, subject, message):
    if not user:
        return

    base_url = current_app.config.get(
        "APP_BASE_URL",
        "http://127.0.0.1:5000"
    )

    send_admin_email(
        user,
        subject,
        (
            f"Hi {user.name},\n\n"
            f"{message}\n\n"
            f"Visit HUMAN FEEDBACK:\n{base_url}\n\n"
            "Regards,\n"
            "HUMAN FEEDBACK"
        )
    )


# --------------------------------------------------
# Admin dashboard
# --------------------------------------------------

@admin_bp.get("/dashboard")
@login_required
def dashboard():
    access_error = admin_required()
    if access_error:
        return access_error

    stats = {
        "total_users": User.query.filter_by(role="user").count(),

        "active_users": User.query.filter_by(
            role="user",
            is_active=True,
            is_suspended=False
        ).count(),

        "suspended_users": User.query.filter_by(
            is_suspended=True
        ).count(),

        "total_websites": Website.query.count(),

        "pending_websites": Website.query.filter_by(
            status="pending"
        ).count(),

        "active_websites": Website.query.filter_by(
            status="active"
        ).count(),

        "pending_feedback": Feedback.query.filter_by(
            status="pending"
        ).count(),

        "approved_feedback": Feedback.query.filter_by(
            status="approved"
        ).count(),

        "pending_reports": Report.query.filter(
            Report.status.in_(["submitted", "under_review"])
        ).count(),

        "total_subscriptions": Subscription.query.count(),

        # Only positive transactions count as credits issued.
        "total_credits_issued": db.session.query(
            func.coalesce(
                func.sum(CreditTransaction.amount), 0
            )
        ).filter(
            CreditTransaction.amount > 0
        ).scalar()
    }

    return jsonify({
        "success": True,
        "statistics": stats
    })


# --------------------------------------------------
# User management
# --------------------------------------------------

@admin_bp.get("/users")
@login_required
def users_list():
    access_error = admin_required()
    if access_error:
        return access_error

    page = request.args.get("page", 1, type=int)
    per_page = min(
        request.args.get("per_page", 20, type=int),
        100
    )

    if page < 1 or per_page < 1:
        return error_response("Invalid pagination values.")

    query = User.query.filter_by(role="user")
    search = request.args.get("search", "").strip()

    if search:
        query = query.filter(
            or_(
                User.name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )

    pagination = query.order_by(
        User.created_at.desc()
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    return jsonify({
        "success": True,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "users": [
            serialize_user(user)
            for user in pagination.items
        ]
    })


@admin_bp.get("/users/<int:user_id>")
@login_required
def user_detail(user_id):
    access_error = admin_required()
    if access_error:
        return access_error

    user = db.session.get(User, user_id)

    if not user:
        return error_response("User not found.", 404)

    return jsonify({
        "success": True,
        "user": serialize_user(user),
        "credit_balance": get_credit_balance(user.id),
        "website_count": Website.query.filter_by(
            owner_id=user.id
        ).count(),
        "feedback_count": Feedback.query.filter_by(
            user_id=user.id
        ).count()
    })


@admin_bp.put("/users/<int:user_id>/suspend")
@login_required
def suspend_user(user_id):
    access_error = admin_required()
    if access_error:
        return access_error

    user = db.session.query(User).filter_by(
        id=user_id
    ).with_for_update().first()

    if not user:
        return error_response("User not found.", 404)

    if user.role == "admin" or user.id == current_user.id:
        return error_response(
            "This admin account cannot be suspended here.",
            403
        )

    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip()

    if not reason:
        return error_response("Suspension reason is mandatory.")

    if len(reason) > 2000:
        return error_response(
            "Reason must not exceed 2,000 characters."
        )

    if user.is_suspended:
        return error_response("User is already suspended.")

    user.is_suspended = True
    user.suspension_reason = reason

    create_notification(
        user.id,
        "Account suspended",
        f"Your account has been suspended. Reason: {reason}",
        "account_suspension",
        "user",
        user.id
    )

    create_audit_log(
        "user_suspended",
        "user",
        user.id,
        f"User {user.email} was suspended.",
        reason
    )

    db.session.commit()

    send_user_notification_email(
        user,
        "Your HUMAN FEEDBACK account has been suspended",
        f"Your account has been suspended.\nReason: {reason}"
    )

    return jsonify({
        "success": True,
        "message": "User suspended successfully."
    })


@admin_bp.put("/users/<int:user_id>/reactivate")
@login_required
def reactivate_user(user_id):
    access_error = admin_required()
    if access_error:
        return access_error

    user = db.session.query(User).filter_by(
        id=user_id
    ).with_for_update().first()

    if not user:
        return error_response("User not found.", 404)

    if user.role == "admin":
        return error_response(
            "This endpoint is for regular users only.",
            403
        )

    if not user.is_suspended:
        return error_response("User is not suspended.")

    user.is_suspended = False
    user.suspension_reason = None

    create_notification(
        user.id,
        "Account reactivated",
        "Your account suspension has been lifted.",
        "account_reactivation",
        "user",
        user.id
    )

    create_audit_log(
        "user_reactivated",
        "user",
        user.id,
        f"User {user.email} was reactivated."
    )

    db.session.commit()

    send_user_notification_email(
        user,
        "Your HUMAN FEEDBACK account has been reactivated",
        "Your account suspension has been lifted. You can now use the platform."
    )

    return jsonify({
        "success": True,
        "message": "User reactivated successfully."
    })


# --------------------------------------------------
# Website management
# --------------------------------------------------

@admin_bp.get("/websites")
@login_required
def websites_list():
    access_error = admin_required()
    if access_error:
        return access_error

    status = request.args.get("status")
    query = Website.query

    if status:
        allowed_statuses = {"pending", "active", "rejected"}

        if status not in allowed_statuses:
            return error_response("Invalid website status.")

        query = query.filter_by(status=status)

    websites = query.order_by(
        Website.created_at.desc()
    ).limit(200).all()

    return jsonify({
        "success": True,
        "total": len(websites),
        "websites": [
            serialize_website(website)
            for website in websites
        ]
    })


@admin_bp.get("/websites/<int:website_id>")
@login_required
def website_detail(website_id):
    access_error = admin_required()
    if access_error:
        return access_error

    website = db.session.get(Website, website_id)

    if not website:
        return error_response("Website not found.", 404)

    verifications = [
        {
            "id": item.id,
            "proof_type": item.proof_type,
            "status": item.status,
            "admin_reason": item.admin_reason,
            "created_at": (
                item.created_at.isoformat()
                if item.created_at else None
            ),
            "reviewed_at": (
                item.reviewed_at.isoformat()
                if item.reviewed_at else None
            )
        }
        for item in website.verifications
    ]

    active_suspension = WebsiteSuspension.query.filter_by(
        website_id=website.id,
        is_active=True
    ).order_by(
        WebsiteSuspension.started_at.desc()
    ).first()

    # Expired suspensions are no longer treated as active.
    if (
        active_suspension
        and active_suspension.expires_at <= utc_now()
    ):
        active_suspension.is_active = False
        active_suspension.restored_at = active_suspension.expires_at
        active_suspension.restored_by = None
        db.session.commit()
        active_suspension = None

    return jsonify({
        "success": True,
        "website": serialize_website(website),
        "verifications": verifications,
        "active_suspension": (
            {
                "id": active_suspension.id,
                "reason": active_suspension.reason,
                "duration_days": active_suspension.duration_days,
                "expires_at": active_suspension.expires_at.isoformat()
            }
            if active_suspension else None
        )
    })


@admin_bp.get("/websites/<int:website_id>/proof/<int:verification_id>")
@login_required
def website_proof(website_id, verification_id):
    access_error = admin_required()
    if access_error:
        return access_error

    verification = WebsiteVerification.query.filter_by(
        id=verification_id,
        website_id=website_id
    ).first()

    if not verification:
        return error_response("Verification proof not found.", 404)

    if not verification.proof_path:
        return error_response("No proof file is attached.", 404)

    proof_path = resolve_upload_path(
        verification.proof_path
    )

    if not proof_path:
        return error_response("Invalid proof file location.", 403)

    if not proof_path.is_file():
        return error_response(
            "Proof file not found on server.",
            404
        )

    return send_file(
        proof_path,
        as_attachment=True,
        download_name=proof_path.name
    )


@admin_bp.put("/websites/<int:website_id>/review")
@login_required
def review_website(website_id):
    access_error = admin_required()
    if access_error:
        return access_error

    website = db.session.query(Website).filter_by(
        id=website_id
    ).with_for_update().first()

    if not website:
        return error_response("Website not found.", 404)

    if website.status != "pending":
        return error_response(
            "Only pending websites can be reviewed. Resubmission is required for another review."
        )

    data = request.get_json(silent=True) or {}
    decision = str(data.get("decision", "")).strip().lower()
    now = utc_now()

    if decision == "approve":
        website.status = "active"
        website.rejection_category = None
        website.rejection_reason = None
        website.approved_at = now

        create_notification(
            website.owner_id,
            "Website approved",
            f"Your website {website.name} has been approved.",
            "website_approval",
            "website",
            website.id
        )

        action = "website_approved"
        description = f"Website {website.name} was approved."
        audit_reason = None
        email_subject = "Your website has been approved"
        email_body = (
            f"Your website {website.name} has been approved "
            "and is now active."
        )

    elif decision == "reject":
        category = str(
            data.get("rejection_category", "")
        ).strip()

        reason = str(data.get("reason", "")).strip()

        if not category or not reason:
            return error_response(
                "Rejection category and reason are mandatory."
            )

        if len(category) > 100 or len(reason) > 2000:
            return error_response(
                "Rejection details are too long."
            )

        website.status = "rejected"
        website.rejection_category = category
        website.rejection_reason = reason
        website.approved_at = None

        owner = db.session.query(User).filter_by(
            id=website.owner_id
        ).with_for_update().first()

        debit = CreditTransaction.query.filter(
            CreditTransaction.user_id == website.owner_id,
            CreditTransaction.reference_type == "website",
            CreditTransaction.reference_id == website.id,
            CreditTransaction.transaction_type == "website_submission",
            CreditTransaction.amount == -WEBSITE_CREDIT_COST
        ).first()

        existing_refund = CreditTransaction.query.filter_by(
            user_id=website.owner_id,
            transaction_type="website_refund",
            reference_type="website",
            reference_id=website.id
        ).first()

        refund_issued = False

        if owner and debit and not existing_refund:
            balance = get_credit_balance(owner.id)
            new_balance = balance + WEBSITE_CREDIT_COST

            db.session.add(
                CreditTransaction(
                    user_id=owner.id,
                    amount=WEBSITE_CREDIT_COST,
                    transaction_type="website_refund",
                    description=(
                        f"Refund for rejected website: {website.name}"
                    ),
                    reference_type="website",
                    reference_id=website.id,
                    admin_id=current_user.id,
                    balance_after=new_balance
                )
            )

            create_notification(
                owner.id,
                "Website credits refunded",
                "1,000 credits have been refunded for your rejected website.",
                "website_credit_refund",
                "website",
                website.id
            )

            refund_issued = True

        create_notification(
            website.owner_id,
            "Website rejected",
            (
                f"Your website was rejected. "
                f"Category: {category}. Reason: {reason}"
            ),
            "website_rejection",
            "website",
            website.id
        )

        action = "website_rejected"
        description = f"Website {website.name} was rejected."
        audit_reason = reason
        email_subject = "Your website submission was rejected"
        email_body = (
            f"Your website {website.name} was rejected.\n"
            f"Category: {category}\n"
            f"Reason: {reason}\n"
            + (
                "\nYour 1,000 website submission credits have been refunded."
                if refund_issued else ""
            )
        )

    else:
        return error_response(
            "Decision must be approve or reject."
        )

    website.reviewed_by = current_user.id
    website.reviewed_at = now

    verification = WebsiteVerification.query.filter_by(
        website_id=website.id,
        status="pending"
    ).order_by(
        WebsiteVerification.created_at.desc()
    ).with_for_update().first()

    if verification:
        verification.status = (
            "approved" if decision == "approve" else "rejected"
        )
        verification.admin_id = current_user.id
        verification.admin_reason = (
            None if decision == "approve"
            else website.rejection_reason
        )
        verification.reviewed_at = now

    create_audit_log(
        action,
        "website",
        website.id,
        description,
        audit_reason,
        {"decision": decision}
    )

    owner = website.owner
    db.session.commit()

    send_user_notification_email(
        owner,
        email_subject,
        email_body
    )

    return jsonify({
        "success": True,
        "message": (
            "Website approved successfully."
            if decision == "approve"
            else "Website rejected successfully."
        ),
        "website": serialize_website(website)
    })


@admin_bp.put("/websites/<int:website_id>/suspend")
@login_required
def suspend_website(website_id):
    access_error = admin_required()
    if access_error:
        return access_error

    website = db.session.query(Website).filter_by(
        id=website_id
    ).with_for_update().first()

    if not website:
        return error_response("Website not found.", 404)

    data = request.get_json(silent=True) or {}

    try:
        duration = int(data.get("duration_days"))
    except (TypeError, ValueError):
        return error_response(
            "Valid suspension duration is required."
        )

    reason = str(data.get("reason", "")).strip()

    if duration not in SUSPENSION_DURATIONS:
        return error_response(
            "Suspension must be 7, 15 or 30 days."
        )

    if not reason:
        return error_response(
            "Suspension reason is mandatory."
        )

    if len(reason) > 2000:
        return error_response(
            "Reason must not exceed 2,000 characters."
        )

    if website.status != "active":
        return error_response(
            "Only active websites can be suspended."
        )

    existing = WebsiteSuspension.query.filter_by(
        website_id=website.id,
        is_active=True
    ).with_for_update().first()

    if existing and existing.expires_at <= utc_now():
        existing.is_active = False
        existing.restored_at = existing.expires_at
        existing.restored_by = None
        db.session.flush()
        existing = None

    if existing:
        return error_response(
            "Website already has an active suspension."
        )

    suspension = create_website_suspension(
        website,
        reason,
        duration,
        current_user.id
    )

    create_notification(
        website.owner_id,
        "Website suspended",
        (
            f"Your website has been suspended for {duration} days. "
            f"Reason: {reason}"
        ),
        "website_suspension",
        "website",
        website.id
    )

    create_audit_log(
        "website_suspended",
        "website",
        website.id,
        f"Website suspended for {duration} days.",
        reason,
        {"duration_days": duration}
    )

    owner = website.owner
    expires_at = suspension.expires_at

    db.session.commit()

    send_user_notification_email(
        owner,
        "Your website has been suspended",
        (
            f"Your website {website.name} has been suspended for "
            f"{duration} days.\nReason: {reason}\n"
            f"Expected expiry: {expires_at.isoformat()}"
        )
    )

    return jsonify({
        "success": True,
        "message": "Website suspended successfully.",
        "expires_at": expires_at.isoformat()
    })


@admin_bp.put("/websites/<int:website_id>/restore")
@login_required
def restore_website(website_id):
    access_error = admin_required()
    if access_error:
        return access_error

    website = db.session.query(Website).filter_by(
        id=website_id
    ).with_for_update().first()

    if not website:
        return error_response("Website not found.", 404)

    suspension = WebsiteSuspension.query.filter_by(
        website_id=website.id,
        is_active=True
    ).order_by(
        WebsiteSuspension.started_at.desc()
    ).with_for_update().first()

    if not suspension:
        return error_response(
            "No active suspension found.",
            404
        )

    suspension.is_active = False
    suspension.restored_at = utc_now()
    suspension.restored_by = current_user.id

    create_notification(
        website.owner_id,
        "Website restored",
        f"Your website {website.name} has been restored.",
        "website_restoration",
        "website",
        website.id
    )

    create_audit_log(
        "website_restored",
        "website",
        website.id,
        f"Website {website.name} suspension was lifted."
    )

    owner = website.owner
    db.session.commit()

    send_user_notification_email(
        owner,
        "Your website suspension has been lifted",
        f"Your website {website.name} has been restored."
    )

    return jsonify({
        "success": True,
        "message": "Website restored successfully."
    })


# --------------------------------------------------
# Feedback management
# --------------------------------------------------

@admin_bp.get("/feedback")
@login_required
def feedback_list():
    access_error = admin_required()
    if access_error:
        return access_error

    status = request.args.get("status")
    query = Feedback.query

    if status:
        allowed_statuses = {
            "pending", "approved", "rejected", "removed"
        }

        if status not in allowed_statuses:
            return error_response("Invalid feedback status.")

        query = query.filter_by(status=status)

    feedback_items = query.order_by(
        Feedback.created_at.desc()
    ).limit(200).all()

    return jsonify({
        "success": True,
        "total": len(feedback_items),
        "feedback": [
            serialize_feedback(item)
            for item in feedback_items
        ]
    })


@admin_bp.put("/feedback/<int:feedback_id>/review")
@login_required
def review_feedback(feedback_id):
    access_error = admin_required()
    if access_error:
        return access_error

    feedback = db.session.query(Feedback).filter_by(
        id=feedback_id
    ).with_for_update().first()

    if not feedback:
        return error_response("Feedback not found.", 404)

    if feedback.status != "pending":
        return error_response(
            "Only pending feedback can be reviewed. "
            "Rejected feedback must be resubmitted first."
        )

    data = request.get_json(silent=True) or {}
    decision = str(data.get("decision", "")).strip().lower()
    now = utc_now()

    if decision == "approve":
        feedback.status = "approved"
        feedback.rejection_category = None
        feedback.rejection_reason = None

        user = db.session.query(User).filter_by(
            id=feedback.user_id
        ).with_for_update().first()

        if not user:
            return error_response(
                "Feedback author not found.",
                404
            )

        existing_reward = CreditTransaction.query.filter_by(
            user_id=feedback.user_id,
            transaction_type="feedback_reward",
            reference_type="feedback",
            reference_id=feedback.id
        ).first()

        if existing_reward:
            feedback.reward_credited = True

        elif not feedback.reward_credited:
            balance = get_credit_balance(user.id)
            new_balance = balance + FEEDBACK_REWARD

            db.session.add(
                CreditTransaction(
                    user_id=user.id,
                    amount=FEEDBACK_REWARD,
                    transaction_type="feedback_reward",
                    description=(
                        f"Reward for approved feedback #{feedback.id}"
                    ),
                    reference_type="feedback",
                    reference_id=feedback.id,
                    admin_id=current_user.id,
                    balance_after=new_balance
                )
            )

            feedback.reward_credited = True

            create_notification(
                user.id,
                "Feedback approved",
                "Your feedback was approved. 10 credits have been added.",
                "feedback_approval",
                "feedback",
                feedback.id
            )

        action = "feedback_approved"
        description = f"Feedback #{feedback.id} was approved."
        audit_reason = None
        email_subject = "Your feedback has been approved"
        email_body = (
            "Your feedback has been approved. "
            "10 credits have been awarded if they had not already been credited."
        )

    elif decision == "reject":
        category = str(
            data.get("rejection_category", "")
        ).strip()

        reason = str(data.get("reason", "")).strip()

        if not category or not reason:
            return error_response(
                "Rejection category and reason are mandatory."
            )

        if len(category) > 100 or len(reason) > 2000:
            return error_response(
                "Rejection details are too long."
            )

        feedback.status = "rejected"
        feedback.rejection_category = category
        feedback.rejection_reason = reason

        create_notification(
            feedback.user_id,
            "Feedback rejected",
            (
                f"Your feedback was rejected. "
                f"Category: {category}. Reason: {reason}"
            ),
            "feedback_rejection",
            "feedback",
            feedback.id
        )

        action = "feedback_rejected"
        description = f"Feedback #{feedback.id} was rejected."
        audit_reason = reason
        email_subject = "Your feedback was rejected"
        email_body = (
            f"Your feedback was rejected.\n"
            f"Category: {category}\nReason: {reason}"
        )

    else:
        return error_response(
            "Decision must be approve or reject."
        )

    feedback.reviewed_by = current_user.id
    feedback.reviewed_at = now

    create_audit_log(
        action,
        "feedback",
        feedback.id,
        description,
        audit_reason,
        {"decision": decision}
    )

    author = feedback.user
    db.session.commit()

    send_user_notification_email(
        author,
        email_subject,
        email_body
    )

    return jsonify({
        "success": True,
        "message": (
            "Feedback approved successfully."
            if decision == "approve"
            else "Feedback rejected successfully."
        ),
        "feedback": serialize_feedback(feedback)
    })


# --------------------------------------------------
# Report management
# --------------------------------------------------

@admin_bp.get("/reports")
@login_required
def reports_list():
    access_error = admin_required()
    if access_error:
        return access_error

    status = request.args.get("status")
    query = Report.query

    if status:
        allowed_statuses = {
            "submitted", "under_review", "resolved", "rejected"
        }

        if status not in allowed_statuses:
            return error_response("Invalid report status.")

        query = query.filter_by(status=status)

    reports = query.order_by(
        Report.created_at.desc()
    ).limit(200).all()

    return jsonify({
        "success": True,
        "total": len(reports),
        "reports": [
            serialize_report(report)
            for report in reports
        ]
    })


@admin_bp.get("/reports/<int:report_id>")
@login_required
def report_detail(report_id):
    access_error = admin_required()
    if access_error:
        return access_error

    report = db.session.get(Report, report_id)

    if not report:
        return error_response("Report not found.", 404)

    return jsonify({
        "success": True,
        "report": serialize_report(report)
    })


@admin_bp.get("/reports/<int:report_id>/evidence")
@login_required
def report_evidence(report_id):
    access_error = admin_required()
    if access_error:
        return access_error

    report = db.session.get(Report, report_id)

    if not report or not report.evidence_path:
        return error_response(
            "Report evidence not found.",
            404
        )

    evidence_path = resolve_upload_path(
        report.evidence_path
    )

    if not evidence_path:
        return error_response(
            "Invalid evidence file location.",
            403
        )

    if not evidence_path.is_file():
        return error_response(
            "Evidence file not found on server.",
            404
        )

    return send_file(
        evidence_path,
        as_attachment=True,
        download_name=evidence_path.name
    )


@admin_bp.put("/reports/<int:report_id>/review")
@login_required
def review_report(report_id):
    access_error = admin_required()
    if access_error:
        return access_error

    report = db.session.query(Report).filter_by(
        id=report_id
    ).with_for_update().first()

    if not report:
        return error_response("Report not found.", 404)

    data = request.get_json(silent=True) or {}

    action = str(data.get("action", "")).strip().lower()
    reason = str(data.get("reason", "")).strip()

    allowed_actions = {
        "under_review",
        "dismiss",
        "remove_feedback",
        "suspend_website",
        "warn",
        "keep_pending",
        "resolve",
        "reject"
    }

    if action not in allowed_actions:
        return error_response("Invalid report action.")

    if not reason:
        return error_response(
            "Admin action reason is mandatory."
        )

    if len(reason) > 2000:
        return error_response(
            "Reason must not exceed 2,000 characters."
        )

    target = get_report_target(report)

    if not target:
        return error_response(
            "The reported website or feedback no longer exists.",
            404
        )

    now = utc_now()
    duration = None
    send_to = None
    email_subject = None
    email_body = None

    if action == "under_review":
        report.status = "under_review"
        report.admin_action = "under_review"

    elif action == "keep_pending":
        report.status = "under_review"
        report.admin_action = "keep_pending"

    elif action in {"dismiss", "reject"}:
        report.status = "rejected"
        report.admin_action = "dismiss"

    elif action in {
        "resolve",
        "remove_feedback",
        "suspend_website",
        "warn"
    }:
        report.status = "resolved"
        report.admin_action = action

        if action == "remove_feedback":
            if report.target_type != "feedback":
                return error_response(
                    "remove_feedback can only be used for feedback reports."
                )

            target = db.session.query(Feedback).filter_by(
                id=report.target_id
            ).with_for_update().first()

            if not target:
                return error_response(
                    "Reported feedback not found.",
                    404
                )

            target.status = "removed"
            target.rejection_reason = reason
            target.reviewed_by = current_user.id
            target.reviewed_at = now

            send_to = target.user

            create_notification(
                target.user_id,
                "Feedback removed",
                (
                    "Your feedback was removed by an administrator. "
                    f"Reason: {reason}"
                ),
                "feedback_removed",
                "feedback",
                target.id
            )

            email_subject = "Your feedback was removed"
            email_body = (
                f"Your feedback #{target.id} was removed.\n"
                f"Reason: {reason}"
            )

        elif action == "suspend_website":
            if report.target_type != "website":
                return error_response(
                    "suspend_website can only be used for website reports."
                )

            try:
                duration = int(data.get("duration_days"))
            except (TypeError, ValueError):
                return error_response(
                    "A valid suspension duration is required."
                )

            if duration not in SUSPENSION_DURATIONS:
                return error_response(
                    "Suspension must be 7, 15 or 30 days."
                )

            target = db.session.query(Website).filter_by(
                id=report.target_id
            ).with_for_update().first()

            if not target or target.status != "active":
                return error_response(
                    "Only active websites can be suspended."
                )

            active_suspension = WebsiteSuspension.query.filter_by(
                website_id=target.id,
                is_active=True
            ).with_for_update().first()

            if (
                active_suspension
                and active_suspension.expires_at <= now
            ):
                active_suspension.is_active = False
                active_suspension.restored_at = (
                    active_suspension.expires_at
                )
                active_suspension.restored_by = None
                db.session.flush()
                active_suspension = None

            if active_suspension:
                return error_response(
                    "Website already has an active suspension."
                )

            create_website_suspension(
                target,
                reason,
                duration,
                current_user.id
            )

            send_to = target.owner

            create_notification(
                target.owner_id,
                "Website suspended",
                (
                    f"Your website has been suspended for "
                    f"{duration} days. Reason: {reason}"
                ),
                "website_suspension",
                "website",
                target.id
            )

            email_subject = "Your website has been suspended"
            email_body = (
                f"Your website {target.name} has been suspended "
                f"for {duration} days.\nReason: {reason}"
            )

        elif action == "warn":
            if report.target_type == "website":
                send_to = target.owner
                reference_type = "website"
                reference_id = target.id
                target_description = f"website {target.name}"

            else:
                send_to = target.user
                reference_type = "feedback"
                reference_id = target.id
                target_description = f"feedback #{target.id}"

            if not send_to:
                return error_response(
                    "Warning recipient not found.",
                    404
                )

            create_notification(
                send_to.id,
                "Platform warning",
                (
                    f"An administrator issued a warning regarding "
                    f"your {target_description}. Reason: {reason}"
                ),
                "admin_warning",
                reference_type,
                reference_id
            )

            email_subject = "HUMAN FEEDBACK platform warning"
            email_body = (
                f"An administrator issued a warning regarding your "
                f"{target_description}.\nReason: {reason}"
            )

    report.admin_id = current_user.id
    report.admin_reason = reason
    report.reviewed_at = now

    if action in {"under_review", "keep_pending"}:
        create_notification(
            report.reporter_id,
            "Report is under review",
            "Your report is still under review by an administrator.",
            "report_review",
            "report",
            report.id
        )

    else:
        create_notification(
            report.reporter_id,
            "Report reviewed",
            (
                f"Your report has been reviewed. "
                f"Action: {report.admin_action}."
            ),
            "report_review",
            "report",
            report.id
        )

    create_audit_log(
        "report_action",
        "report",
        report.id,
        f"Report #{report.id} action: {action}.",
        reason,
        {
            "action": action,
            "target_type": report.target_type,
            "target_id": report.target_id,
            "duration_days": duration
        }
    )

    reporter = report.reporter

    db.session.commit()

    if send_to and email_subject:
        send_user_notification_email(
            send_to,
            email_subject,
            email_body
        )

    if action not in {"under_review", "keep_pending"}:
        send_user_notification_email(
            reporter,
            "Your HUMAN FEEDBACK report has been reviewed",
            (
                f"Your report #{report.id} has been reviewed.\n"
                f"Action: {report.admin_action}\n"
                f"Reason: {reason}"
            )
        )

    return jsonify({
        "success": True,
        "message": "Report action completed successfully.",
        "report": serialize_report(report)
    })


# --------------------------------------------------
# Manual credit adjustment
# --------------------------------------------------

@admin_bp.post("/credits/adjust")
@login_required
def adjust_user_credits():
    access_error = admin_required()
    if access_error:
        return access_error

    data = request.get_json(silent=True) or {}

    try:
        user_id = int(data.get("user_id"))
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        return error_response(
            "Valid user_id and amount are required."
        )

    reason = str(data.get("reason", "")).strip()

    if amount == 0:
        return error_response(
            "Adjustment amount cannot be zero."
        )

    if abs(amount) > 1000000:
        return error_response(
            "Adjustment amount is too large."
        )

    if not reason:
        return error_response(
            "Adjustment reason is mandatory."
        )

    if len(reason) > 2000:
        return error_response(
            "Reason must not exceed 2,000 characters."
        )

    user = db.session.query(User).filter_by(
        id=user_id
    ).with_for_update().first()

    if not user:
        return error_response("User not found.", 404)

    if user.role == "admin":
        return error_response(
            "Manual credit adjustments are for regular users only."
        )

    balance = get_credit_balance(user.id)
    new_balance = balance + amount

    if new_balance < 0:
        return error_response(
            "Credit balance cannot become negative."
        )

    db.session.add(
        CreditTransaction(
            user_id=user.id,
            amount=amount,
            transaction_type="admin_adjustment",
            description=reason,
            reference_type="admin_adjustment",
            reference_id=None,
            admin_id=current_user.id,
            balance_after=new_balance
        )
    )

    create_audit_log(
        "credit_adjustment",
        "user",
        user.id,
        (
            f"Credits adjusted by {amount}. "
            f"New balance: {new_balance}."
        ),
        reason,
        {
            "amount": amount,
            "balance_after": new_balance
        }
    )

    create_notification(
        user.id,
        "Credit balance adjusted",
        (
            f"Your credit balance was adjusted by {amount}. "
            f"Reason: {reason}"
        ),
        "credit_adjustment",
        "user",
        user.id
    )

    db.session.commit()

    send_user_notification_email(
        user,
        "Your HUMAN FEEDBACK credit balance was adjusted",
        (
            f"Your credit balance was adjusted by {amount}.\n"
            f"New balance: {new_balance}\n"
            f"Reason: {reason}"
        )
    )

    return jsonify({
        "success": True,
        "message": "Credits adjusted successfully.",
        "user_id": user.id,
        "adjustment": amount,
        "balance": new_balance
    })


# --------------------------------------------------
# Audit logs
# --------------------------------------------------

@admin_bp.get("/audit-logs")
@login_required
def audit_logs():
    access_error = admin_required()
    if access_error:
        return access_error

    page = request.args.get("page", 1, type=int)
    per_page = min(
        request.args.get("per_page", 30, type=int),
        100
    )

    if page < 1 or per_page < 1:
        return error_response(
            "Invalid pagination values."
        )

    pagination = AuditLog.query.order_by(
        AuditLog.created_at.desc()
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    logs = [
        {
            "id": item.id,
            "actor_id": item.actor_id,
            "action": item.action,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "description": item.description,
            "reason": item.reason,
            "ip_address": item.ip_address,
            "user_agent": item.user_agent,
            "extra_data": item.extra_data,
            "created_at": (
                item.created_at.isoformat()
                if item.created_at else None
            )
        }
        for item in pagination.items
    ]

    return jsonify({
        "success": True,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "logs": logs
    })
