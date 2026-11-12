
from decimal import Decimal

from app import app
from extensions import db
from models import Plan


PLANS = [
    {
        "name": "Free",
        "code": "free",
        "description": (
            "30-day free trial. Maximum 1 website. "
            "Website submission requires at least 1,000 available credits."
        ),
        "duration_days": 30,
        "website_limit": 1,
        "monthly_price": Decimal("0.00"),
        "is_trial": True,
        "is_active": True,
    },
    {
        "name": "Pro",
        "code": "pro",
        "description": "Monthly plan with up to 3 websites.",
        "duration_days": 30,
        "website_limit": 3,
        "monthly_price": Decimal("9.00"),
        "is_trial": False,
        "is_active": True,
    },
    {
        "name": "Business",
        "code": "business",
        "description": "Monthly plan with unlimited websites.",
        "duration_days": 30,
        "website_limit": None,
        "monthly_price": Decimal("24.00"),
        "is_trial": False,
        "is_active": True,
    },
]


with app.app_context():
    try:
        for plan_data in PLANS:
            plan = Plan.query.filter_by(
                code=plan_data["code"]
            ).first()

            if plan:
                for key, value in plan_data.items():
                    setattr(plan, key, value)

                print(f"UPDATED: {plan_data['name']}")
            else:
                db.session.add(Plan(**plan_data))
                print(f"CREATED: {plan_data['name']}")

        db.session.commit()

        print("\nSUCCESS: All 3 plans saved.")

        for plan in Plan.query.order_by(Plan.id).all():
            print(
                f"{plan.name} | "
                f"${plan.monthly_price} | "
                f"Website limit: {plan.website_limit}"
            )

    except Exception:
        db.session.rollback()
        raise
