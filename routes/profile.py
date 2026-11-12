
import os
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request, current_app
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import UserProfile


profile_bp = Blueprint(
    "profile",
    __name__,
    url_prefix="/api/profile"
)

ALLOWED_IMAGE_EXTENSIONS = {
    "jpg", "jpeg", "png", "webp"
}

MAX_PROFILE_IMAGE_SIZE = 5 * 1024 * 1024


def error_response(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def get_upload_root():
    return Path(
        current_app.config["UPLOAD_FOLDER"]
    ).resolve()


def resolve_upload_path(relative_path):
    if not relative_path:
        return None

    upload_root = get_upload_root()
    file_path = (upload_root / relative_path).resolve()

    if upload_root not in file_path.parents:
        current_app.logger.warning(
            "Blocked unsafe upload path."
        )
        return None

    return file_path


def delete_profile_picture(relative_path):
    file_path = resolve_upload_path(relative_path)

    if not file_path:
        return

    try:
        if file_path.is_file():
            file_path.unlink()

    except OSError:
        current_app.logger.exception(
            "Unable to delete profile picture."
        )


def get_user_profile():
    profile = UserProfile.query.filter_by(
        user_id=current_user.id
    ).first()

    if not profile:
        profile = UserProfile(
            user_id=current_user.id
        )
        db.session.add(profile)
        db.session.flush()

    return profile


def serialize_profile(user, profile):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "email_verified": user.is_email_verified,
        "role": user.role,
        "phone": profile.phone,
        "country": profile.country,
        "bio": profile.bio,
        "has_profile_picture": bool(
            profile.profile_picture
        ),
        "created_at": (
            user.created_at.isoformat()
            if user.created_at else None
        )
    }


def get_image_extension(filename):
    filename = secure_filename(filename or "")

    if "." not in filename:
        return None

    extension = filename.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return None

    return extension


def validate_image_signature(file_bytes, extension):
    if extension in {"jpg", "jpeg"}:
        return file_bytes.startswith(b"\xff\xd8\xff")

    if extension == "png":
        return file_bytes.startswith(
            b"\x89PNG\r\n\x1a\n"
        )

    if extension == "webp":
        return (
            len(file_bytes) >= 12
            and file_bytes[:4] == b"RIFF"
            and file_bytes[8:12] == b"WEBP"
        )

    return False


@profile_bp.get("/")
@login_required
def get_profile():
    profile = get_user_profile()

    db.session.commit()

    return jsonify({
        "success": True,
        "profile": serialize_profile(
            current_user,
            profile
        )
    })


@profile_bp.put("/")
@login_required
def update_profile():
    data = request.get_json(silent=True) or {}

    name = data.get("name")
    phone = data.get("phone")
    country = data.get("country")
    bio = data.get("bio")

    if name is not None:
        name = str(name).strip()

        if not name:
            return error_response(
                "Name cannot be empty."
            )

        if len(name) > 150:
            return error_response(
                "Name must not exceed 150 characters."
            )

    if phone is not None:
        phone = str(phone).strip()

        if len(phone) > 30:
            return error_response(
                "Phone must not exceed 30 characters."
            )

    if country is not None:
        country = str(country).strip()

        if len(country) > 100:
            return error_response(
                "Country must not exceed 100 characters."
            )

    if bio is not None:
        bio = str(bio).strip()

        if len(bio) > 1000:
            return error_response(
                "Bio must not exceed 1,000 characters."
            )

    profile = get_user_profile()

    if name is not None:
        current_user.name = name

    if phone is not None:
        profile.phone = phone or None

    if country is not None:
        profile.country = country or None

    if bio is not None:
        profile.bio = bio or None

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Profile updated successfully.",
        "profile": serialize_profile(
            current_user,
            profile
        )
    })


@profile_bp.put("/password")
@login_required
def change_password():
    data = request.get_json(silent=True) or {}

    current_password = data.get(
        "current_password", ""
    )

    new_password = data.get(
        "new_password", ""
    )

    confirm_password = data.get(
        "confirm_password", ""
    )

    if not current_password or not new_password:
        return error_response(
            "Current and new passwords are required."
        )

    if len(new_password) < 8:
        return error_response(
            "New password must contain at least 8 characters."
        )

    if new_password != confirm_password:
        return error_response(
            "New password and confirmation do not match."
        )

    if not current_user.check_password(
        current_password
    ):
        return error_response(
            "Current password is incorrect.",
            401
        )

    if current_user.check_password(new_password):
        return error_response(
            "New password must be different from the current password."
        )

    current_user.set_password(new_password)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Password changed successfully."
    })


@profile_bp.post("/picture")
@login_required
def upload_profile_picture():
    uploaded_file = request.files.get("picture")

    if not uploaded_file:
        return error_response(
            "Please select a profile picture."
        )

    extension = get_image_extension(
        uploaded_file.filename
    )

    if not extension:
        return error_response(
            "Only JPG, JPEG, PNG and WEBP images are allowed."
        )

    file_bytes = uploaded_file.read(
        MAX_PROFILE_IMAGE_SIZE + 1
    )

    if not file_bytes:
        return error_response(
            "The selected image is empty."
        )

    if len(file_bytes) > MAX_PROFILE_IMAGE_SIZE:
        return error_response(
            "Profile picture must be 5 MB or smaller.",
            413
        )

    if not validate_image_signature(
        file_bytes,
        extension
    ):
        return error_response(
            "The uploaded file is not a valid image."
        )

    upload_root = get_upload_root()
    upload_folder = upload_root / "profiles"
    upload_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    filename = (
        f"user_{current_user.id}_"
        f"{uuid.uuid4().hex}.{extension}"
    )

    safe_filename = secure_filename(filename)
    relative_path = str(
        Path("profiles") / safe_filename
    ).replace("\\", "/")

    destination = resolve_upload_path(relative_path)

    if not destination:
        return error_response(
            "Invalid upload destination.",
            500
        )

    profile = get_user_profile()
    old_picture = profile.profile_picture

    try:
        with open(destination, "wb") as image_file:
            image_file.write(file_bytes)

        profile.profile_picture = relative_path

        db.session.commit()

    except Exception:
        db.session.rollback()

        try:
            if destination.is_file():
                destination.unlink()
        except OSError:
            current_app.logger.exception(
                "Unable to remove failed profile upload."
            )

        current_app.logger.exception(
            "Profile picture upload failed."
        )

        return error_response(
            "Unable to upload profile picture.",
            500
        )

    if old_picture:
        delete_profile_picture(old_picture)

    return jsonify({
        "success": True,
        "message": "Profile picture uploaded successfully."
    })


@profile_bp.delete("/picture")
@login_required
def remove_profile_picture():
    profile = UserProfile.query.filter_by(
        user_id=current_user.id
    ).first()

    if not profile or not profile.profile_picture:
        return error_response(
            "No profile picture found.",
            404
        )

    old_picture = profile.profile_picture

    profile.profile_picture = None

    db.session.commit()

    delete_profile_picture(old_picture)

    return jsonify({
        "success": True,
        "message": "Profile picture removed successfully."
    })
