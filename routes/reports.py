
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    Report,
    ReportCategory,
    Website,
    Feedback
)


reports_bp = Blueprint(
    "reports",
    __name__,
    url_prefix="/api/reports"
)

MAX_EVIDENCE_SIZE = 5 * 1024 * 1024
MAX_REASON_LENGTH = 5000

ALLOWED_EVIDENCE_EXTENSIONS = {
    "jpg", "jpeg", "png", "webp"
}

REPORT_TARGET_TYPES = {"website", "feedback"}


def error_response(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def validate_evidence(file):
    if not file or not file.filename:
        return None, None

    filename = secure_filename(file.filename)

    if not filename or "." not in filename:
        return None, "Evidence file must have a valid extension."

    extension = filename.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED_EVIDENCE_EXTENSIONS:
        return None, "Only JPG, JPEG, PNG and WEBP files are allowed."

    file.seek(0)
    content = file.read(MAX_EVIDENCE_SIZE + 1)
    file.seek(0)

    if not content:
        return None, "Evidence file is empty."

    if len(content) > MAX_EVIDENCE_SIZE:
        return None, "Evidence file must not exceed 5 MB."

    is_jpeg = content.startswith(b"\xff\xd8\xff")

    is_png = content.startswith(
        b"\x89PNG\r\n\x1a\n"
    )

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
        return None, "Evidence file content does not match its extension."

    return extension, None


def save_evidence(file, extension):
    upload_root = Path(
        current_app.config["UPLOAD_FOLDER"]
    ).resolve()

    reports_folder = upload_root / "reports"
    reports_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    filename = f"{uuid.uuid4().hex}.{extension}"
    file_path = reports_folder / filename

    file.save(file_path)

    return str(
        Path("reports") / filename
    ).replace("\\", "/")


def delete_evidence(path):
    if not path:
        return

    upload_root = Path(
        current_app.config["UPLOAD_FOLDER"]
    ).resolve()

    file_path = (upload_root / path).resolve()

    if upload_root not in file_path.parents:
        current_app.logger.warning(
            "Blocked unsafe report evidence deletion path."
        )
        return

    try:
        if file_path.is_file():
            file_path.unlink()

    except OSError:
        current_app.logger.exception(
            "Could not delete report evidence."
        )


def serialize_report(report):
    return {
        "id": report.id,
        "category": {
            "id": report.category.id,
            "name": report.category.name
        },
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


@reports_bp.get("/categories")

def report_categories():
    categories = ReportCategory.query.filter_by(
        is_active=True
    ).order_by(
        ReportCategory.name.asc()
    ).all()

    return jsonify({
        "success": True,
        "categories": [
            {
                "id": category.id,
                "name": category.name,
                "slug": category.slug
            }
            for category in categories
        ]
    })


@reports_bp.post("/")
@login_required
def create_report():
    if not current_user.is_active:
        return error_response(
            "Your account is inactive.",
            403
        )

    if current_user.is_suspended:
        return error_response(
            "Your account is suspended. You cannot submit reports.",
            403
        )

    data = request.form

    try:
        category_id = int(data.get("category_id", ""))
        target_id = int(data.get("target_id", ""))
    except (TypeError, ValueError):
        return error_response(
            "Valid category_id and target_id are required."
        )

    target_type = str(
        data.get("target_type", "")
    ).strip().lower()

    reason = str(
        data.get("reason", "")
    ).strip()

    if target_type not in REPORT_TARGET_TYPES:
        return error_response(
            "Target type must be website or feedback."
        )

    if target_id < 1:
        return error_response(
            "Invalid target ID."
        )

    if not reason:
        return error_response(
            "Report reason is required."
        )

    if len(reason) > MAX_REASON_LENGTH:
        return error_response(
            "Report reason must not exceed 5,000 characters."
        )

    category = db.session.get(
        ReportCategory,
        category_id
    )

    if not category or not category.is_active:
        return error_response(
            "Invalid or inactive report category."
        )

    if target_type == "website":
        target = db.session.get(
            Website,
            target_id
        )
    else:
        target = db.session.get(
            Feedback,
            target_id
        )

    if not target:
        return error_response(
            "Report target not found.",
            404
        )

    evidence = request.files.get("evidence")
    extension = None

    if evidence and evidence.filename:
        extension, validation_error = validate_evidence(
            evidence
        )

        if validation_error:
            return error_response(validation_error)

    evidence_path = None

    try:
        if extension:
            evidence_path = save_evidence(
                evidence,
                extension
            )

        report = Report(
            reporter_id=current_user.id,
            category_id=category.id,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            evidence_path=evidence_path,
            status="submitted"
        )

        db.session.add(report)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Report submitted successfully.",
            "report": serialize_report(report)
        }), 201

    except Exception:
        db.session.rollback()

        if evidence_path:
            delete_evidence(evidence_path)

        current_app.logger.exception(
            "Report submission failed."
        )

        return error_response(
            "Unable to submit report. Please try again.",
            500
        )


@reports_bp.get("/mine")
@login_required
def my_reports():
    page = request.args.get(
        "page", 1, type=int
    )

    per_page = min(
        request.args.get("per_page", 20, type=int),
        100
    )

    if page < 1 or per_page < 1:
        return error_response(
            "Invalid pagination values."
        )

    pagination = Report.query.filter_by(
        reporter_id=current_user.id
    ).order_by(
        Report.created_at.desc()
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
        "reports": [
            serialize_report(report)
            for report in pagination.items
        ]
    })


@reports_bp.get("/<int:report_id>")
@login_required
def report_detail(report_id):
    report = db.session.get(
        Report,
        report_id
    )

    if not report:
        return error_response(
            "Report not found.",
            404
        )

    is_admin = current_user.role == "admin"

    if (
        report.reporter_id != current_user.id
        and not is_admin
    ):
        return error_response(
            "You cannot access this report.",
            403
        )

    return jsonify({
        "success": True,
        "report": serialize_report(report)
    })
