from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from models import CreditTransaction, User, AuditLog


credits_bp = Blueprint(
    "credits",
    __name__,
    url_prefix="/api/credits"
)


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


def get_balance(user_id):
    latest_transaction = CreditTransaction.query.filter_by(
        user_id=user_id
    ).order_by(
        CreditTransaction.id.desc()
    ).first()

    return latest_transaction.balance_after if latest_transaction else 0


def serialize_transaction(transaction):
    return {
        "id": transaction.id,
        "amount": transaction.amount,
        "transaction_type": transaction.transaction_type,
        "description": transaction.description,
        "reference_type": transaction.reference_type,
        "reference_id": transaction.reference_id,
        "balance_after": transaction.balance_after,
        "created_at": (
            transaction.created_at.isoformat()
            if transaction.created_at else None
        )
    }


@credits_bp.get("/")
@login_required
def credit_overview():
    balance = get_balance(current_user.id)

    total_earned = db.session.query(
        func.coalesce(func.sum(CreditTransaction.amount), 0)
    ).filter(
        CreditTransaction.user_id == current_user.id,
        CreditTransaction.amount > 0
    ).scalar()

    total_spent = db.session.query(
        func.coalesce(func.sum(CreditTransaction.amount), 0)
    ).filter(
        CreditTransaction.user_id == current_user.id,
        CreditTransaction.amount < 0
    ).scalar()

    return jsonify({
        "success": True,
        "balance": balance,
        "total_earned": int(total_earned or 0),
        "total_spent": abs(int(total_spent or 0))
    })


@credits_bp.get("/history")
@login_required
def credit_history():
    page = request.args.get("page", 1, type=int)
    per_page = min(
        request.args.get("per_page", 20, type=int),
        100
    )

    if page < 1 or per_page < 1:
        return error_response("Invalid pagination values.")

    pagination = CreditTransaction.query.filter_by(
        user_id=current_user.id
    ).order_by(
        CreditTransaction.created_at.desc(),
        CreditTransaction.id.desc()
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    return jsonify({
        "success": True,
        "balance": get_balance(current_user.id),
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "transactions": [
            serialize_transaction(item)
            for item in pagination.items
        ]
    })


@credits_bp.get("/user/<int:user_id>")
@login_required
def admin_user_credit_history(user_id):
    access_error = admin_required()

    if access_error:
        return access_error

    user = db.session.get(User, user_id)

    if not user:
        return error_response("User not found.", 404)

    transactions = CreditTransaction.query.filter_by(
        user_id=user_id
    ).order_by(
        CreditTransaction.created_at.desc(),
        CreditTransaction.id.desc()
    ).limit(100).all()

    return jsonify({
        "success": True,
        "user_id": user.id,
        "user_name": user.name,
        "balance": get_balance(user.id),
        "transactions": [
            serialize_transaction(item)
            for item in transactions
        ]
    })


@credits_bp.post("/adjust")
@login_required
def admin_adjust_credits():
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
            "A reason is mandatory for manual adjustments."
        )

    if len(reason) > 1000:
        return error_response(
            "Reason must not exceed 1,000 characters."
        )

    try:
        # Lock the user row to serialize concurrent credit adjustments.
        user = db.session.query(User).filter_by(
            id=user_id
        ).with_for_update().first()

        if not user:
            db.session.rollback()
            return error_response("User not found.", 404)

        if user.role == "admin":
            db.session.rollback()
            return error_response(
                "Manual credit adjustment is only available for regular users.",
                403
            )

        current_balance = get_balance(user.id)
        new_balance = current_balance + amount

        if new_balance < 0:
            db.session.rollback()
            return error_response(
                "Credit adjustment would make the balance negative."
            )

        transaction = CreditTransaction(
            user_id=user.id,
            amount=amount,
            transaction_type="admin_adjustment",
            description=reason,
            reference_type="admin_adjustment",
            reference_id=None,
            admin_id=current_user.id,
            balance_after=new_balance
        )

        db.session.add(transaction)
        db.session.flush()

        audit_log = AuditLog(
            actor_id=current_user.id,
            action="credit_adjustment",
            entity_type="user",
            entity_id=user.id,
            description=(
                f"Adjusted credits by {amount}. "
                f"New balance: {new_balance}."
            ),
            reason=reason,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:500]
        )

        db.session.add(audit_log)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Credits adjusted successfully.",
            "user_id": user.id,
            "adjustment": amount,
            "balance": new_balance,
            "transaction": serialize_transaction(transaction)
        })

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Admin credit adjustment failed."
        )

        return error_response(
            "Credit adjustment failed.",
            500
        )
