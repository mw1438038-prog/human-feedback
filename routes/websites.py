
import uuid

from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user, login_required
from sqlalchemy import desc
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    Website,
    WebsiteCategory,
    WebsiteVerification,
    WebsiteSuspension,
    Feedback,
    CreditTransaction,
    Subscription,
)


websites_bp = Blueprint(
    "websites",
    __name__,
    url_prefix="/api/websites"
)

FREE_WEBSITE_LIMIT = 1
PRO_WEBSITE_LIMIT = 3
FREE_WEBSITE_CREDIT_COST = 1000

MAX_UPLOAD_SIZE = 5 * 1024 * 1024

IMAGE_SIGNATURES = {
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "webp": (b"RIFF",),
}


def utc_now():
    return datetime.now(timezone.utc)


def error_response(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def serialize_datetime(value):
    return value.isoformat() if value else None


def get_latest_credit_balance(user_id):
    transaction = CreditTransaction.query.filter_by(
        user_id=user_id
    ).order_by(
        desc(CreditTransaction.created_at),
        desc(CreditTransaction.id)
    ).first()

    return transaction.balance_after if transaction else 0


def get_current_plan(user):
    now = utc_now()

    subscription = Subscription.query.filter(
        Subscription.user_id == user.id,
        Subscription.status == "active",
        Subscription.expires_at > now
    ).order_by(
        desc(Subscription.expires_at)
    ).first()

    if subscription:
        plan = subscription.plan
        code = plan.code.lower()

        if code == "pro":
            return {
                "type": "pro",
                "website_limit": PRO_WEBSITE_LIMIT,
                "subscription": subscription
            }

        if code == "business":
            return {
                "type": "business",
                "website_limit": None,
                "subscription": subscription
            }

        if code == "free" or plan.is_trial:
            return {
                "type": "free",
                "website_limit": FREE_WEBSITE_LIMIT,
                "subscription": subscription
            }

    trial_expiry = user.free_trial_expires_at

    if trial_expiry:
        if trial_expiry.tzinfo is None:
            trial_expiry = trial_expiry.replace(
                tzinfo=timezone.utc
            )

        if trial_expiry > now:
            return {
                "type": "free",
                "website_limit": FREE_WEBSITE_LIMIT,
                "subscription": None
            }

    return None


def validate_file_size(file):
    if not file or not file.filename:
        return False

    try:
        file.stream.seek(0, 2)
        file_size = file.stream.tell()
        file.stream.seek(0)

        return 0 < file_size <= MAX_UPLOAD_SIZE

    except (OSError, ValueError):
        return False


def validate_image(file):
    if not file or not file.filename:
        return False

    if not validate_file_size(file):
        return False

    filename = secure_filename(file.filename)
    extension = Path(filename).suffix.lower().lstrip(".")

    if extension not in {"jpg", "jpeg", "png", "webp"}:
        return False

    header = file.stream.read(12)
    file.stream.seek(0)

    if extension == "webp":
        return (
            len(header) >= 12
            and header[:4] == b"RIFF"
            and header[8:12] == b"WEBP"
        )

    return any(
        header.startswith(signature)
        for signature in IMAGE_SIGNATURES[extension]
    )


def validate_proof(file):
    if not file or not file.filename:
        return False

    if not validate_file_size(file):
        return False

    filename = secure_filename(file.filename)
    extension = Path(filename).suffix.lower().lstrip(".")

    if extension == "pdf":
        header = file.stream.read(5)
        file.stream.seek(0)

        return header == b"%PDF-"

    return validate_image(file)


def save_upload(file, folder):
    filename = secure_filename(file.filename)

    extension = Path(filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{extension}"

    upload_folder = (
        Path(current_app.config["UPLOAD_FOLDER"])
        / "websites"
        / str(current_user.id)
        / folder
    )

    upload_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    file_path = upload_folder / unique_name
    file.save(file_path)

    return str(
        file_path.relative_to(
            Path(current_app.config["UPLOAD_FOLDER"])
        )
    ).replace("\\", "/")


def delete_upload(relative_path):
    if not relative_path:
        return

    upload_root = Path(
        current_app.config["UPLOAD_FOLDER"]
    ).resolve()

    file_path = (
        upload_root / relative_path
    ).resolve()

    if upload_root not in file_path.parents:
        current_app.logger.warning(
            "Blocked unsafe upload deletion path."
        )
        return

    if file_path.is_file():
        file_path.unlink()


def serialize_website(website):
    return {
        "id": website.id,
        "name": website.name,
        "url": website.url,
        "description": website.description,
        "logo_path": website.logo_path,
        "status": website.status,
        "category": {
            "id": website.category.id,
            "name": website.category.name
        },
        "rejection_category": website.rejection_category,
        "rejection_reason": website.rejection_reason,
        "resubmission_count": website.resubmission_count,
        "approved_at": serialize_datetime(
            website.approved_at
        ),
        "created_at": serialize_datetime(
            website.created_at
        ),
        "updated_at": serialize_datetime(
            website.updated_at
        )
    }


def check_user_access():
    if current_user.is_suspended:
        return error_response(
            "Your account is suspended. Website activities are disabled.",
            403
        )

    return None


def validate_website_fields(data):
    name = str(data.get("name", "")).strip()
    url = str(data.get("url", "")).strip()
    description = str(data.get("description", "")).strip()
    category_id = data.get("category_id")

    if not name or not url or not description or not category_id:
        return None, error_response(
            "Website name, URL, description and category are required."
        )

    if len(name) > 150:
        return None, error_response(
            "Website name must not exceed 150 characters."
        )

    if len(url) > 2048:
        return None, error_response(
            "Website URL is too long."
        )

    parsed_url = urlparse(url)

    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or not parsed_url.hostname
    ):
        return None, error_response(
            "Please provide a valid HTTP or HTTPS website URL."
        )

    if len(description) > 10000:
        return None, error_response(
            "Website description is too long."
        )

    try:
        category_id = int(category_id)

    except (TypeError, ValueError):
        return None, error_response(
            "Invalid website category."
        )

    category = WebsiteCategory.query.filter_by(
        id=category_id,
        is_active=True
    ).first()

    if not category:
        return None, error_response(
            "Selected website category is unavailable."
        )

    return {
        "name": name,
        "url": url,
        "description": description,
        "category": category
    }, None


@websites_bp.get("/")
@login_required
def list_websites():
    access_error = check_user_access()

    if access_error:
        return access_error

    websites = Website.query.filter_by(
        owner_id=current_user.id
    ).order_by(
        desc(Website.created_at)
    ).all()

    return jsonify({
        "success": True,
        "total": len(websites),
        "websites": [
            serialize_website(website)
            for website in websites
        ]
    })


@websites_bp.post("/")
@login_required
def create_website():
    access_error = check_user_access()

    if access_error:
        return access_error

    data = request.form

    fields, validation_error = validate_website_fields(data)

    if validation_error:
        return validation_error

    proof = request.files.get("proof")
    logo = request.files.get("logo")

    if not proof or not proof.filename:
        return error_response(
            "Website ownership proof is required."
        )

    if not validate_file_size(proof):
        return error_response(
            "Website proof must not exceed 5 MB and cannot be empty."
        )

    if not validate_proof(proof):
        return error_response(
            "Proof must be a valid JPG, JPEG, PNG, WEBP or PDF file."
        )

    if logo and logo.filename:
        if not validate_file_size(logo):
            return error_response(
                "Website logo must not exceed 5 MB and cannot be empty."
            )

        if not validate_image(logo):
            return error_response(
                "Logo must be a valid JPG, JPEG, PNG or WEBP image."
            )

    plan = get_current_plan(current_user)

    if not plan:
        return error_response(
            "Your Free trial or paid subscription has expired. Please activate a plan.",
            403
        )

    existing_count = Website.query.filter_by(
        owner_id=current_user.id
    ).count()

    limit = plan["website_limit"]

    if limit is not None and existing_count >= limit:
        return error_response(
            f"Your {plan['type'].capitalize()} plan allows a maximum of {limit} website(s).",
            403
        )

    current_balance = get_latest_credit_balance(
        current_user.id
    )

    if (
        plan["type"] == "free"
        and current_balance < FREE_WEBSITE_CREDIT_COST
    ):
        return error_response(
            "You need at least 1,000 available credits to submit a website.",
            403
        )

    saved_files = []

    try:
        proof_path = save_upload(proof, "proof")
        saved_files.append(proof_path)

        logo_path = None

        if logo and logo.filename:
            logo_path = save_upload(logo, "logos")
            saved_files.append(logo_path)

        website = Website(
            owner_id=current_user.id,
            category_id=fields["category"].id,
            name=fields["name"],
            url=fields["url"],
            description=fields["description"],
            logo_path=logo_path,
            status="pending"
        )

        db.session.add(website)
        db.session.flush()

        verification = WebsiteVerification(
            website_id=website.id,
            proof_path=proof_path,
            proof_type=Path(
                secure_filename(proof.filename)
            ).suffix.lower().lstrip("."),
            status="pending"
        )

        db.session.add(verification)

        if plan["type"] == "free":
            new_balance = (
                current_balance - FREE_WEBSITE_CREDIT_COST
            )

            transaction = CreditTransaction(
                user_id=current_user.id,
                amount=-FREE_WEBSITE_CREDIT_COST,
                transaction_type="website_submission",
                description=(
                    f"1,000 credits deducted for submitting "
                    f"website: {website.name}"
                ),
                reference_type="website",
                reference_id=website.id,
                balance_after=new_balance
            )

            db.session.add(transaction)

        db.session.commit()

        return jsonify({
            "success": True,
            "message": (
                "Website submitted successfully. "
                "It is pending Admin review."
            ),
            "website": serialize_website(website),
            "credits_deducted": (
                FREE_WEBSITE_CREDIT_COST
                if plan["type"] == "free" else 0
            ),
            "available_credits": (
                current_balance - FREE_WEBSITE_CREDIT_COST
                if plan["type"] == "free"
                else current_balance
            )
        }), 201

    except Exception:
        db.session.rollback()

        for saved_file in saved_files:
            try:
                delete_upload(saved_file)

            except OSError:
                current_app.logger.exception(
                    "Failed to clean up uploaded file."
                )

        current_app.logger.exception(
            "Website submission failed."
        )

        return error_response(
            "Website submission could not be completed.",
            500
        )


@websites_bp.get("/<int:website_id>")
@login_required
def get_website(website_id):
    access_error = check_user_access()

    if access_error:
        return access_error

    website = Website.query.filter_by(
        id=website_id,
        owner_id=current_user.id
    ).first()

    if not website:
        return error_response(
            "Website not found.",
            404
        )

    verifications = WebsiteVerification.query.filter_by(
        website_id=website.id
    ).order_by(
        desc(WebsiteVerification.created_at)
    ).all()

    result = serialize_website(website)

    result["verifications"] = [
        {
            "id": item.id,
            "proof_type": item.proof_type,
            "status": item.status,
            "admin_reason": item.admin_reason,
            "reviewed_at": serialize_datetime(
                item.reviewed_at
            ),
            "created_at": serialize_datetime(
                item.created_at
            )
        }
        for item in verifications
    ]

    return jsonify({
        "success": True,
        "website": result
    })


@websites_bp.put("/<int:website_id>/resubmit")
@login_required
def resubmit_website(website_id):
    access_error = check_user_access()

    if access_error:
        return access_error

    website = Website.query.filter_by(
        id=website_id,
        owner_id=current_user.id
    ).first()

    if not website:
        return error_response(
            "Website not found.",
            404
        )

    if website.status != "rejected":
        return error_response(
            "Only rejected websites can be edited and resubmitted.",
            409
        )

    data = request.form

    fields, validation_error = validate_website_fields(data)

    if validation_error:
        return validation_error

    proof = request.files.get("proof")
    logo = request.files.get("logo")

    if not proof or not proof.filename:
        return error_response(
            "New ownership proof is required for resubmission."
        )

    if not validate_file_size(proof):
        return error_response(
            "Website proof must not exceed 5 MB and cannot be empty."
        )

    if not validate_proof(proof):
        return error_response(
            "Proof must be a valid JPG, JPEG, PNG, WEBP or PDF file."
        )

    if logo and logo.filename:
        if not validate_file_size(logo):
            return error_response(
                "Website logo must not exceed 5 MB and cannot be empty."
            )

        if not validate_image(logo):
            return error_response(
                "Logo must be a valid JPG, JPEG, PNG or WEBP image."
            )

    saved_files = []

    try:
        proof_path = save_upload(proof, "proof")
        saved_files.append(proof_path)

        old_logo_path = website.logo_path
        new_logo_path = old_logo_path

        if logo and logo.filename:
            new_logo_path = save_upload(logo, "logos")
            saved_files.append(new_logo_path)

        website.name = fields["name"]
        website.url = fields["url"]
        website.description = fields["description"]
        website.category_id = fields["category"].id

        website.status = "pending"
        website.rejection_category = None
        website.rejection_reason = None
        website.reviewed_by = None
        website.reviewed_at = None
        website.approved_at = None
        website.resubmission_count += 1

        website.logo_path = new_logo_path
        website.updated_at = utc_now()

        verification = WebsiteVerification(
            website_id=website.id,
            proof_path=proof_path,
            proof_type=Path(
                secure_filename(proof.filename)
            ).suffix.lower().lstrip("."),
            status="pending"
        )

        db.session.add(verification)
        db.session.commit()

        if new_logo_path != old_logo_path:
            try:
                delete_upload(old_logo_path)

            except OSError:
                current_app.logger.exception(
                    "Could not delete previous website logo."
                )

        return jsonify({
            "success": True,
            "message": (
                "Website resubmitted successfully. "
                "It is pending Admin review."
            ),
            "website": serialize_website(website)
        })

    except Exception:
        db.session.rollback()

        for saved_file in saved_files:
            try:
                delete_upload(saved_file)

            except OSError:
                current_app.logger.exception(
                    "Failed to clean up resubmission file."
                )

        current_app.logger.exception(
            "Website resubmission failed."
        )

        return error_response(
            "Website could not be resubmitted.",
            500
        )


@websites_bp.delete("/<int:website_id>")
@login_required
def delete_website(website_id):
    access_error = check_user_access()

    if access_error:
        return access_error

    website = Website.query.filter_by(
        id=website_id,
        owner_id=current_user.id
    ).first()

    if not website:
        return error_response(
            "Website not found.",
            404
        )

    data = request.get_json(silent=True) or {}

    if data.get("confirm") is not True:
        return error_response(
            "Permanent deletion requires confirm: true."
        )

    try:
        files_to_delete = []

        if website.logo_path:
            files_to_delete.append(website.logo_path)

        verifications = WebsiteVerification.query.filter_by(
            website_id=website.id
        ).all()

        for verification in verifications:
            files_to_delete.append(
                verification.proof_path
            )

        feedback_entries = Feedback.query.filter_by(
            website_id=website.id
        ).all()

        for feedback in feedback_entries:
            if feedback.screenshot_path:
                files_to_delete.append(
                    feedback.screenshot_path
                )

        for feedback in feedback_entries:
            db.session.delete(feedback)

        WebsiteVerification.query.filter_by(
            website_id=website.id
        ).delete(synchronize_session=False)

        WebsiteSuspension.query.filter_by(
            website_id=website.id
        ).delete(synchronize_session=False)

        db.session.delete(website)
        db.session.commit()

        for file_path in files_to_delete:
            try:
                delete_upload(file_path)

            except OSError:
                current_app.logger.exception(
                    "Could not delete website-related upload."
                )

        return jsonify({
            "success": True,
            "message": (
                "Website and its related feedback have been "
                "permanently deleted. Financial and credit "
                "transaction history has been retained."
            )
        })

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Website deletion failed."
        )

        return error_response(
            "Website could not be deleted.",
            500
        )
