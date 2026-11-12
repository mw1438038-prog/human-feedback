
import re

from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from models import WebsiteCategory, Website


categories_bp = Blueprint(
    "categories",
    __name__,
    url_prefix="/api/categories"
)


def error_response(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def admin_required():
    if not current_user.is_authenticated:
        return error_response("Authentication required.", 401)

    if current_user.role != "admin":
        return error_response("Admin access required.", 403)

    if not current_user.is_active:
        return error_response("Your account is inactive.", 403)

    if current_user.is_suspended:
        return error_response("Your account is suspended.", 403)

    return None


def serialize_category(category):
    website_count = Website.query.filter_by(
        category_id=category.id
    ).count()

    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
        "is_active": category.is_active,
        "website_count": website_count,
        "created_at": (
            category.created_at.isoformat()
            if category.created_at else None
        )
    }


def create_slug(name):
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


@categories_bp.get("/")
def list_categories():
    search = request.args.get("search", "").strip()

    query = WebsiteCategory.query.filter_by(
        is_active=True
    )

    if search:
        query = query.filter(
            WebsiteCategory.name.ilike(f"%{search}%")
        )

    categories = query.order_by(
        WebsiteCategory.name.asc()
    ).all()

    return jsonify({
        "success": True,
        "total": len(categories),
        "categories": [
            serialize_category(category)
            for category in categories
        ]
    })


@categories_bp.get("/<int:category_id>")
def get_category(category_id):
    category = WebsiteCategory.query.filter_by(
        id=category_id,
        is_active=True
    ).first()

    if not category:
        return error_response(
            "Category not found.",
            404
        )

    return jsonify({
        "success": True,
        "category": serialize_category(category)
    })


@categories_bp.post("/")
@login_required
def create_category():
    access_error = admin_required()

    if access_error:
        return access_error

    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()

    if not name:
        return error_response("Category name is required.")

    if len(name) > 100:
        return error_response(
            "Category name must not exceed 100 characters."
        )

    if len(description) > 5000:
        return error_response(
            "Description is too long."
        )

    existing = WebsiteCategory.query.filter(
        func.lower(WebsiteCategory.name) == name.lower()
    ).first()

    if existing:
        return error_response(
            "A category with this name already exists.",
            409
        )

    slug = create_slug(name)

    if not slug:
        return error_response(
            "Category name must contain valid characters."
        )

    existing_slug = WebsiteCategory.query.filter_by(
        slug=slug
    ).first()

    if existing_slug:
        return error_response(
            "A category with this slug already exists.",
            409
        )

    category = WebsiteCategory(
        name=name,
        slug=slug,
        description=description or None,
        is_active=True
    )

    try:
        db.session.add(category)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Category created successfully.",
            "category": serialize_category(category)
        }), 201

    except Exception:
        db.session.rollback()
        return error_response(
            "Category could not be created.",
            500
        )


@categories_bp.put("/<int:category_id>")
@login_required
def update_category(category_id):
    access_error = admin_required()

    if access_error:
        return access_error

    category = db.session.get(
        WebsiteCategory,
        category_id
    )

    if not category:
        return error_response(
            "Category not found.",
            404
        )

    data = request.get_json(silent=True) or {}

    name = str(
        data.get("name", category.name)
    ).strip()

    description = str(
        data.get("description", category.description or "")
    ).strip()

    if not name:
        return error_response(
            "Category name is required."
        )

    if len(name) > 100:
        return error_response(
            "Category name must not exceed 100 characters."
        )

    if len(description) > 5000:
        return error_response(
            "Description is too long."
        )

    duplicate = WebsiteCategory.query.filter(
        func.lower(WebsiteCategory.name) == name.lower(),
        WebsiteCategory.id != category.id
    ).first()

    if duplicate:
        return error_response(
            "Another category already uses this name.",
            409
        )

    new_slug = create_slug(name)

    if not new_slug:
        return error_response(
            "Invalid category name."
        )

    duplicate_slug = WebsiteCategory.query.filter(
        WebsiteCategory.slug == new_slug,
        WebsiteCategory.id != category.id
    ).first()

    if duplicate_slug:
        return error_response(
            "Another category already uses this slug.",
            409
        )

    category.name = name
    category.slug = new_slug
    category.description = description or None

    try:
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Category updated successfully.",
            "category": serialize_category(category)
        })

    except Exception:
        db.session.rollback()
        return error_response(
            "Category could not be updated.",
            500
        )


@categories_bp.patch("/<int:category_id>/deactivate")
@login_required
def deactivate_category(category_id):
    access_error = admin_required()

    if access_error:
        return access_error

    category = db.session.get(
        WebsiteCategory,
        category_id
    )

    if not category:
        return error_response(
            "Category not found.",
            404
        )

    category.is_active = False

    try:
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Category deactivated successfully."
        })

    except Exception:
        db.session.rollback()
        return error_response(
            "Category could not be deactivated.",
            500
        )


@categories_bp.patch("/<int:category_id>/activate")
@login_required
def activate_category(category_id):
    access_error = admin_required()

    if access_error:
        return access_error

    category = db.session.get(
        WebsiteCategory,
        category_id
    )

    if not category:
        return error_response(
            "Category not found.",
            404
        )

    category.is_active = True

    try:
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Category activated successfully."
        })

    except Exception:
        db.session.rollback()
        return error_response(
            "Category could not be activated.",
            500
        )
