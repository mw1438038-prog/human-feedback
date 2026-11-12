
import os
from functools import wraps

from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    redirect,
    url_for,
    abort,
)
from flask_login import current_user, login_required
from flask_wtf.csrf import generate_csrf

from config import Config
from extensions import (
    db,
    migrate,
    login_manager,
    csrf,
    mail,
    limiter,
)

# Load all models
import models

# Import all 13 route blueprints
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.websites import websites_bp
from routes.categories import categories_bp
from routes.feedback import feedback_bp
from routes.feedback_replies import feedback_replies_bp
from routes.credits import credits_bp
from routes.subscriptions import subscriptions_bp
from routes.notifications import notifications_bp
from routes.reports import reports_bp
from routes.admin import admin_bp
from routes.analytics import analytics_bp
from routes.profile import profile_bp


def create_app():
    app = Flask(__name__)

    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

    # Authentication handling
    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "message": "Authentication required. Please log in."
            }), 401

        return redirect(url_for("login_page"))

    # Admin-only page protection
    def admin_required(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if getattr(current_user, "role", None) != "admin":
                abort(403)

            return view(*args, **kwargs)

        return wrapped

    # Create upload directory
    os.makedirs(
        app.config["UPLOAD_FOLDER"],
        exist_ok=True
    )

    # Register all API blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(websites_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(feedback_replies_bp)
    app.register_blueprint(credits_bp)
    app.register_blueprint(subscriptions_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(profile_bp)

    # ==========================================
    # PUBLIC HTML PAGES
    # ==========================================

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/about")
    def about_page():
        return render_template("about.html")

    @app.get("/contact")
    def contact_page():
        return render_template("contact.html")

    @app.get("/pricing")
    def pricing_page():
        return render_template("pricing.html")

    @app.get("/faq")
    def faq_page():
        return render_template("faq.html")

    @app.get("/login")
    def login_page():
        return render_template("login.html")

    @app.get("/register")
    def register_page():
        return render_template("register.html")

    @app.get("/forgot-password")
    def forgot_password_page():
        return render_template("forgot_password.html")

    @app.get("/reset-password")
    def reset_password_page():
        return render_template("reset_password.html")

    @app.get("/verify-email")
    def verify_email_page():
        return render_template("verify_email.html")

    @app.get("/terms")
    def terms_page():
        return render_template("terms.html")

    @app.get("/privacy-policy")
    def privacy_policy_page():
        return render_template("privacy_policy.html")

    @app.get("/cookie-policy")
    def cookie_policy_page():
        return render_template("cookie_policy.html")

    # ==========================================
    # AUTHENTICATED USER PAGES
    # ==========================================

    @app.get("/dashboard")
    @login_required
    def dashboard_page():
        return render_template("dashboard.html")

    @app.get("/websites")
    @login_required
    def my_websites_page():
        return render_template("my_websites.html")

    @app.get("/websites/add")
    @login_required
    def add_website_page():
        return render_template("add_website.html")

    @app.get("/websites/<int:website_id>")
    @login_required
    def website_details_page(website_id):
        return render_template(
            "website_details.html",
            website_id=website_id
        )

    @app.get("/feedback")
    @login_required
    def feedback_page():
        return render_template("feedback.html")

    @app.get("/feedback/<int:feedback_id>")
    @login_required
    def feedback_details_page(feedback_id):
        return render_template(
            "feedback_details.html",
            feedback_id=feedback_id
        )

    @app.get("/replies")
    @login_required
    def replies_page():
        return render_template("replies.html")

    @app.get("/credits")
    @login_required
    def credits_page():
        return render_template("credits.html")

    @app.get("/credits/history")
    @login_required
    def credit_history_page():
        return render_template("credit_history.html")

    @app.get("/analytics")
    @login_required
    def analytics_page():
        return render_template("analytics.html")

    @app.get("/notifications")
    @login_required
    def notifications_page():
        return render_template("notifications.html")

    @app.get("/reports")
    @login_required
    def reports_page():
        return render_template("reports.html")

    @app.get("/profile")
    @login_required
    def profile_page():
        return render_template("profile.html")

    @app.get("/settings")
    @login_required
    def settings_page():
        return render_template("settings.html")

    @app.get("/subscription")
    @login_required
    def subscription_page():
        return render_template("subscription.html")

    # ==========================================
    # ADMIN-ONLY HTML PAGES
    # ==========================================

    @app.get("/admin")
    @admin_required
    def admin_dashboard_page():
        return render_template("admin_dashboard.html")

    @app.get("/admin/users")
    @admin_required
    def admin_users_page():
        return render_template("admin_users.html")

    @app.get("/admin/users/<int:user_id>")
    @admin_required
    def admin_user_details_page(user_id):
        return render_template(
            "admin_user_details.html",
            user_id=user_id
        )

    @app.get("/admin/website-approvals")
    @admin_required
    def admin_website_approvals_page():
        return render_template("admin_website_approvals.html")

    @app.get("/admin/websites/<int:website_id>")
    @admin_required
    def admin_website_details_page(website_id):
        return render_template(
            "admin_website_details.html",
            website_id=website_id
        )

    @app.get("/admin/website-suspensions")
    @admin_required
    def admin_website_suspensions_page():
        return render_template("admin_website_suspensions.html")

    @app.get("/admin/feedback-moderation")
    @admin_required
    def admin_feedback_moderation_page():
        return render_template("admin_feedback_moderation.html")

    @app.get("/admin/reports")
    @admin_required
    def admin_reports_page():
        return render_template("admin_reports.html")

    @app.get("/admin/reports/<int:report_id>")
    @admin_required
    def admin_report_details_page(report_id):
        return render_template(
            "admin_report_details.html",
            report_id=report_id
        )

    @app.get("/admin/credit-management")
    @admin_required
    def admin_credit_management_page():
        return render_template("admin_credit_management.html")

    @app.get("/admin/audit-logs")
    @admin_required
    def admin_audit_logs_page():
        return render_template("admin_audit_logs.html")

    @app.get("/admin/profile")
    @admin_required
    def admin_profile_page():
        return render_template("admin_profile.html")

    # ==========================================
    # API ENDPOINTS
    # ==========================================

    # CSRF token endpoint
    @app.get("/api/csrf-token")
    def csrf_token():
        return jsonify({
            "success": True,
            "csrf_token": generate_csrf()
        })

    # API health check
    @app.get("/api/health")
    def health():
        return jsonify({
            "success": True,
            "application": "HUMAN FEEDBACK",
            "backend": "Flask",
            "status": "running"
        })

    # Return initialized Flask application
    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
