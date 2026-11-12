
import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


class Config:

    # Application security
    SECRET_KEY = os.getenv("SECRET_KEY")

    # Database connection
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    # Session security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = (
        os.getenv("COOKIE_SECURE", "false").lower() == "true"
    )

    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    # CSRF protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    # File upload security
    MAX_CONTENT_LENGTH = 11 * 1024 * 1024

    ALLOWED_IMAGE_EXTENSIONS = {
        "jpg",
        "jpeg",
        "png",
        "webp",
    }

    UPLOAD_FOLDER = BASE_DIR / "uploads"

    # Application settings
    MAX_LOGIN_ATTEMPTS = 5

    # Application URL
    APP_BASE_URL = os.getenv(
        "APP_BASE_URL",
        "http://127.0.0.1:5000"
    ).rstrip("/")

    # Resend SMTP configuration
    MAIL_SERVER = os.getenv(
        "MAIL_SERVER",
        "smtp.resend.com"
    )

    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))

    MAIL_USE_TLS = True
    MAIL_USE_SSL = False

    MAIL_USERNAME = os.getenv(
        "MAIL_USERNAME",
        "resend"
    )

    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

    MAIL_DEFAULT_SENDER = os.getenv(
        "MAIL_DEFAULT_SENDER",
        "onboarding@resend.dev"
    )
