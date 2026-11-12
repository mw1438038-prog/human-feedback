
from app import app
from extensions import db
from models import WebsiteCategory, ReportCategory


WEBSITE_CATEGORIES = [
    ("Business", "business", "Business and company websites."),
    ("E-commerce", "e-commerce", "Online stores and shopping websites."),
    ("Education", "education", "Educational institutions and learning platforms."),
    ("Entertainment", "entertainment", "Entertainment, media and gaming websites."),
    ("Finance", "finance", "Banking, financial and investment websites."),
    ("Health", "health", "Healthcare and medical information websites."),
    ("News & Media", "news-media", "News publishers and media websites."),
    ("Portfolio", "portfolio", "Personal portfolios and professional profiles."),
    ("Technology", "technology", "Technology, software and IT websites."),
    ("Other", "other", "Websites that do not fit another category."),
]


REPORT_CATEGORIES = [
    ("Fake Information", "fake-information", "False or fabricated information."),
    ("Spam", "spam", "Spam, unwanted or repetitive content."),
    ("Abusive Content", "abusive-content", "Harassment, threats or abusive material."),
    ("Misleading Feedback", "misleading-feedback", "False or deceptive feedback."),
    ("Fraud/Scam", "fraud-scam", "Fraudulent activity or scam attempts."),
    ("Copyright Violation", "copyright-violation", "Unauthorized use of copyrighted material."),
    ("Other", "other", "Any other reportable issue."),
]


def seed_categories(model, categories, category_type):
    for name, slug, description in categories:
        category = model.query.filter_by(slug=slug).first()

        if not category:
            category = model.query.filter_by(name=name).first()

        if category:
            category.name = name
            category.slug = slug
            category.description = description
            category.is_active = True
            print(f"UPDATED {category_type}: {name}")
        else:
            db.session.add(
                model(
                    name=name,
                    slug=slug,
                    description=description,
                    is_active=True
                )
            )
            print(f"CREATED {category_type}: {name}")


with app.app_context():
    try:
        seed_categories(
            WebsiteCategory,
            WEBSITE_CATEGORIES,
            "WEBSITE CATEGORY"
        )

        seed_categories(
            ReportCategory,
            REPORT_CATEGORIES,
            "REPORT CATEGORY"
        )

        db.session.commit()

        print("\nSUCCESS: All categories saved.")

        print(
            "\nWebsite categories:",
            WebsiteCategory.query.filter_by(is_active=True).count()
        )

        print(
            "Report categories:",
            ReportCategory.query.filter_by(is_active=True).count()
        )

    except Exception:
        db.session.rollback()
        raise
