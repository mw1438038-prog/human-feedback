
import uuid

from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import (
    Blueprint,
    request,
    jsonify,
    current_app,
    session,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    Feedback,
    Website,
    WebsiteSuspension,
    Subscription,
)


feedback_bp = Blueprint(
    "feedback",
    __name__,
    url_prefix="/api/feedback"
)

FEEDBACK_REWARD = 10
FEEDBACK_COOLDOWN_HOURS = 24
MAX_SCREENSHOT_SIZE = 5 * 1024 * 1024
MAX_COMMENT_LENGTH = 10000

ALLOWED_SCREENSHOT_EXTENSIONS = {
    "jpg", "jpeg", "png", "webp"
}


def error_response(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def utc_now():
    return datetime.now(timezone.utc)


def normalize_datetime(value):
    if value and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def account_can_use_platform(user):
    if not user.is_active or user.is_suspended:
        return False

    if not user.is_email_verified:
        return False

    now = utc_now()

    # Active Free trial
    trial_expiry = normalize_datetime(
        user.free_trial_expires_at
    )

    if (
        user.free_trial_used
        and trial_expiry
        and trial_expiry > now
    ):
        return True

    # Active paid subscription
    subscription = Subscription.query.filter(
        Subscription.user_id == user.id,
        Subscription.status == "active",
        Subscription.expires_at > now
    ).order_by(
        Subscription.expires_at.desc()
    ).first()

    return subscription is not None


def get_active_website(website_id):
    website = db.session.get(Website, website_id)

    if not website:
        return None, "Website not found."

    if website.status != "active" or not website.approved_at:
        return None, "This website is not approved and active."

    active_suspension = WebsiteSuspension.query.filter(
        WebsiteSuspension.website_id == website.id,
        WebsiteSuspension.is_active.is_(True),
        WebsiteSuspension.expires_at > utc_now()
    ).first()

    if active_suspension:
        return None, "This website is temporarily suspended."

    return website, None


def validate_ratings(data):
    rating_fields = [
        "overall_rating",
        "design_rating",
        "speed_rating",
        "ux_rating",
        "content_rating",
    ]

    ratings = {}

    for field in rating_fields:
        value = data.get(field)

        try:
            value = int(value)
        except (TypeError, ValueError):
            return None, f"{field} must be a number from 1 to 5."

        if value < 1 or value > 5:
            return None, f"{field} must be between 1 and 5."

        ratings[field] = value

    return ratings, None


def validate_comment(value):
    comment = str(value or "").strip()

    if not comment:
        return None, "Feedback comment is required."

    if len(comment) > MAX_COMMENT_LENGTH:
        return None, "Feedback comment must not exceed 10,000 characters."

    return comment, None


def validate_screenshot(file):
    if not file or not file.filename:
        return None, None

    filename = secure_filename(file.filename)

    extension = (
        filename.rsplit(".", 1)[-1].lower()
        if "." in filename else ""
    )

    if extension not in ALLOWED_SCREENSHOT_EXTENSIONS:
        return None, "Only JPG, JPEG, PNG and WEBP screenshots are allowed."

    content = file.read(MAX_SCREENSHOT_SIZE + 1)
    file.seek(0)

    if not content:
        return None, "Screenshot file is empty."

    if len(content) > MAX_SCREENSHOT_SIZE:
        return None, "Screenshot must not exceed 5 MB."

    is_jpeg = content.startswith(b"\xff\xd8\xff")
    is_png = content.startswith(b"\x89PNG\r\n\x1a\n")
    is_webp = (
        len(content) >= 12
        and content[:4] == b"RIFF"
        and content[8:12] == b"WEBP"
    )

    valid_signature = (
        (extension in {"jpg", "jpeg"} and is_jpeg)
        or (extension == "png" and is_png)
        or (extension == "webp" and is_webp)
    )

    if not valid_signature:
        return None, "Screenshot content does not match its file extension."

    return content, None


def save_screenshot(content, filename):
    upload_root = Path(
        current_app.config["UPLOAD_FOLDER"]
    ).resolve()

    feedback_folder = upload_root / "feedback"
    feedback_folder.mkdir(parents=True, exist_ok=True)

    safe_filename = secure_filename(filename)
    extension = Path(safe_filename).suffix.lower()

    stored_name = f"{uuid.uuid4().hex}{extension}"
    file_path = feedback_folder / stored_name

    file_path.write_bytes(content)

    return str(
        Path("feedback") / stored_name
    ).replace("\\", "/")


def delete_screenshot(path):
    if not path:
        return

    upload_root = Path(
        current_app.config["UPLOAD_FOLDER"]
    ).resolve()

    file_path = (upload_root / path).resolve()

    # Prevent deleting files outside the uploads directory.
    if upload_root not in file_path.parents:
        current_app.logger.warning(
            "Blocked unsafe screenshot deletion path."
        )
        return

    try:
        if file_path.is_file():
            file_path.unlink()
    except OSError:
        current_app.logger.exception(
            "Could not delete feedback screenshot."
        )


def check_feedback_cooldown(user_id, website_id):
    last_approved = Feedback.query.filter(
        Feedback.user_id == user_id,
        Feedback.website_id == website_id,
        Feedback.status == "approved"
    ).order_by(
        Feedback.reviewed_at.desc()
    ).first()

    if not last_approved or not last_approved.reviewed_at:
        return None

    approved_at = normalize_datetime(
        last_approved.reviewed_at
    )

    next_allowed_at = approved_at + timedelta(
        hours=FEEDBACK_COOLDOWN_HOURS
    )

    if utc_now() < next_allowed_at:
        return jsonify({
            "success": False,
            "message": (
                "You can submit feedback again 24 hours "
                "after your previous feedback was approved."
            ),
            "next_allowed_at": next_allowed_at.isoformat()
        }), 429

    return None


def serialize_feedback(feedback):
    return {
        "id": feedback.id,
        "website_id": feedback.website_id,
        "website_name": (
            feedback.website.name
            if feedback.website else None
        ),
        "user_id": feedback.user_id,
        "user_name": (
            feedback.user.name
            if feedback.user else None
        ),
        "overall_rating": feedback.overall_rating,
        "design_rating": feedback.design_rating,
        "speed_rating": feedback.speed_rating,
        "ux_rating": feedback.ux_rating,
        "content_rating": feedback.content_rating,
        "comment": feedback.comment,
        "has_screenshot": bool(feedback.screenshot_path),
        "status": feedback.status,
        "rejection_category": feedback.rejection_category,
        "rejection_reason": feedback.rejection_reason,
        "reward_credited": feedback.reward_credited,
        "visit_recorded_at": (
            feedback.visit_recorded_at.isoformat()
            if feedback.visit_recorded_at else None
        ),
        "created_at": (
            feedback.created_at.isoformat()
            if feedback.created_at else None
        ),
        "reviewed_at": (
            feedback.reviewed_at.isoformat()
            if feedback.reviewed_at else None
        )
    }


def get_feedback_access(feedback):
    is_admin = current_user.role == "admin"
    is_provider = feedback.user_id == current_user.id
    is_owner = (
        feedback.website
        and feedback.website.owner_id == current_user.id
    )

    if is_admin or is_provider:
        return True

    if is_owner and feedback.status == "approved":
        return True

    return feedback.status == "approved"


def get_request_data():
    if request.is_json:
        return request.get_json(silent=True) or {}

    return request.form


@feedback_bp.post("/visit/<int:website_id>")
@login_required
def record_website_visit(website_id):
    if not account_can_use_platform(current_user):
        return error_response(
            "An active plan is required to use this feature.",
            403
        )

    website, error = get_active_website(website_id)

    if error:
        return error_response(error, 403)

    visited_websites = session.get("visited_websites", {})
    visited_websites[str(website.id)] = utc_now().isoformat()

    session["visited_websites"] = visited_websites
    session.modified = True

    return jsonify({
        "success": True,
        "message": "Website visit recorded.",
        "website_id": website.id,
        "visited_at": visited_websites[str(website.id)]
    })


@feedback_bp.post("/")
@login_required
def submit_feedback():
    if not account_can_use_platform(current_user):
        return error_response(
            "An active plan is required to submit feedback.",
            403
        )

    data = get_request_data()

    try:
        website_id = int(data.get("website_id"))
    except (TypeError, ValueError):
        return error_response("A valid website_id is required.")

    website, error = get_active_website(website_id)

    if error:
        return error_response(error, 403)

    visited_websites = session.get("visited_websites", {})
    visit_time = visited_websites.get(str(website_id))

    if not visit_time:
        return error_response(
            "Please visit the website before submitting feedback."
        )

    try:
        visit_recorded_at = datetime.fromisoformat(visit_time)
        visit_recorded_at = normalize_datetime(visit_recorded_at)
    except (TypeError, ValueError):
        return error_response(
            "Your website visit session is invalid. Please visit the website again."
        )

    ratings, rating_error = validate_ratings(data)

    if rating_error:
        return error_response(rating_error)

    comment, comment_error = validate_comment(
        data.get("comment")
    )

    if comment_error:
        return error_response(comment_error)

    screenshot = request.files.get("screenshot")
    screenshot_content = None
    screenshot_path = None

    if screenshot and screenshot.filename:
        screenshot_content, screenshot_error = validate_screenshot(
            screenshot
        )

        if screenshot_error:
            return error_response(screenshot_error)

    pending_feedback = Feedback.query.filter_by(
        user_id=current_user.id,
        website_id=website_id,
        status="pending"
    ).first()

    if pending_feedback:
        return error_response(
            "You already have pending feedback for this website.",
            409
        )

    cooldown_error = check_feedback_cooldown(
        current_user.id,
        website_id
    )

    if cooldown_error:
        return cooldown_error

    try:
        if screenshot_content:
            screenshot_path = save_screenshot(
                screenshot_content,
                screenshot.filename
            )

        feedback = Feedback(
            website_id=website_id,
            user_id=current_user.id,
            overall_rating=ratings["overall_rating"],
            design_rating=ratings["design_rating"],
            speed_rating=ratings["speed_rating"],
            ux_rating=ratings["ux_rating"],
            content_rating=ratings["content_rating"],
            comment=comment,
            screenshot_path=screenshot_path,
            status="pending",
            visit_recorded_at=visit_recorded_at
        )

        db.session.add(feedback)
        db.session.commit()

        visited_websites.pop(str(website_id), None)
        session["visited_websites"] = visited_websites
        session.modified = True

        return jsonify({
            "success": True,
            "message": "Feedback submitted successfully. It is pending admin approval.",
            "feedback": serialize_feedback(feedback)
        }), 201

    except Exception:
        db.session.rollback()

        if screenshot_path:
            delete_screenshot(screenshot_path)

        current_app.logger.exception(
            "Feedback submission failed."
        )

        return error_response(
            "Feedback could not be submitted. Please try again.",
            500
        )


@feedback_bp.get("/mine")
@login_required
def my_feedback():
    if not account_can_use_platform(current_user):
        return error_response(
            "An active plan is required to use this feature.",
            403
        )

    feedback_list = Feedback.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Feedback.created_at.desc()
    ).all()

    return jsonify({
        "success": True,
        "total": len(feedback_list),
        "feedback": [
            serialize_feedback(item)
            for item in feedback_list
        ]
    })


@feedback_bp.get("/website/<int:website_id>")
@login_required
def website_feedback(website_id):
    if not account_can_use_platform(current_user):
        return error_response(
            "An active plan is required to use this feature.",
            403
        )

    website = db.session.get(Website, website_id)

    if not website:
        return error_response("Website not found.", 404)

    feedback_list = Feedback.query.filter_by(
        website_id=website_id,
        status="approved"
    ).order_by(
        Feedback.reviewed_at.desc()
    ).all()

    return jsonify({
        "success": True,
        "website_id": website.id,
        "total": len(feedback_list),
        "feedback": [
            serialize_feedback(item)
            for item in feedback_list
        ]
    })


@feedback_bp.get("/<int:feedback_id>")
@login_required
def get_feedback(feedback_id):
    feedback = db.session.get(Feedback, feedback_id)

    if not feedback:
        return error_response("Feedback not found.", 404)

    if not get_feedback_access(feedback):
        return error_response(
            "You are not allowed to view this feedback.",
            403
        )

    return jsonify({
        "success": True,
        "feedback": serialize_feedback(feedback)
    })


@feedback_bp.put("/<int:feedback_id>/resubmit")
@login_required
def resubmit_feedback(feedback_id):
    if not account_can_use_platform(current_user):
        return error_response(
            "An active plan is required to resubmit feedback.",
            403
        )

    feedback = db.session.get(Feedback, feedback_id)

    if not feedback:
        return error_response("Feedback not found.", 404)

    if feedback.user_id != current_user.id:
        return error_response(
            "You can only edit your own feedback.",
            403
        )

    if feedback.status != "rejected":
        return error_response(
            "Only rejected feedback can be edited and resubmitted."
        )

    website, error = get_active_website(feedback.website_id)

    if error:
        return error_response(error, 403)

    cooldown_error = check_feedback_cooldown(
        current_user.id,
        feedback.website_id
    )

    if cooldown_error:
        return cooldown_error

    data = get_request_data()

    ratings, rating_error = validate_ratings(data)

    if rating_error:
        return error_response(rating_error)

    comment, comment_error = validate_comment(
        data.get("comment", feedback.comment)
    )

    if comment_error:
        return error_response(comment_error)

    screenshot = request.files.get("screenshot")
    new_screenshot_path = None
    screenshot_content = None

    if screenshot and screenshot.filename:
        screenshot_content, screenshot_error = validate_screenshot(
            screenshot
        )

        if screenshot_error:
            return error_response(screenshot_error)

    old_screenshot_path = feedback.screenshot_path

    try:
        if screenshot_content:
            new_screenshot_path = save_screenshot(
                screenshot_content,
                screenshot.filename
            )

        feedback.overall_rating = ratings["overall_rating"]
        feedback.design_rating = ratings["design_rating"]
        feedback.speed_rating = ratings["speed_rating"]
        feedback.ux_rating = ratings["ux_rating"]
        feedback.content_rating = ratings["content_rating"]
        feedback.comment = comment

        if new_screenshot_path:
            feedback.screenshot_path = new_screenshot_path

        feedback.status = "pending"
        feedback.rejection_category = None
        feedback.rejection_reason = None
        feedback.reviewed_by = None
        feedback.reviewed_at = None

        db.session.commit()

        if new_screenshot_path and old_screenshot_path:
            delete_screenshot(old_screenshot_path)

        return jsonify({
            "success": True,
            "message": "Feedback resubmitted successfully. It is pending admin approval.",
            "feedback": serialize_feedback(feedback)
        })

    except Exception:
        db.session.rollback()

        if new_screenshot_path:
            delete_screenshot(new_screenshot_path)

        current_app.logger.exception(
            "Feedback resubmission failed."
        )

        return error_response(
            "Feedback could not be resubmitted.",
            500
        )
