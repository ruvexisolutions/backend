import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import (
    SalonModel,
    UserModel,
    CustomerModel,
    ServiceModel,
    StaffModel,
    InventoryModel,
    AppointmentModel,
    InvoiceModel,
    FollowUpModel,
    FeedbackModel,
)

from .security import hash_password

DEFAULT_SALON_ID = "sln_billcare_flagship"

def seed_database(db: Session):
    # Ensure salon table has upi_id and bank details (Safe idempotent schema upgrade)
    try:
        from sqlalchemy import text
        for col, col_type in [
            ("upi_id", "VARCHAR(128) DEFAULT 'billcare.pos@icici'"),
            ("bank_account_name", "VARCHAR(128)"),
            ("bank_account_number", "VARCHAR(64)"),
            ("bank_ifsc", "VARCHAR(32)"),
            ("bank_name", "VARCHAR(128)"),
        ]:
            try:
                db.execute(text(f"ALTER TABLE salons ADD COLUMN {col} {col_type}"))
                db.commit()
            except Exception:
                db.rollback()
    except Exception:
        pass

    # Ensure flagship owner account has valid bcrypt hash for login
    owner_user = db.query(UserModel).filter(UserModel.email == "owner@billcare.io").first()
    if owner_user and (not owner_user.password_hash or not owner_user.password_hash.startswith("$2b$")):
        owner_user.password_hash = hash_password("billcare2026")
        db.commit()

    # Ensure manager account exists for role testing
    manager_user = db.query(UserModel).filter(UserModel.email == "manager@billcare.io").first()
    if not manager_user:
        manager_user = UserModel(
            id="usr_billcare_manager",
            salon_id=DEFAULT_SALON_ID,
            name="Kavita Rao",
            email="manager@billcare.io",
            phone="+91 98450 33445",
            role="manager",
            avatar="K",
            password_hash=hash_password("billcare2026"),
        )
        db.add(manager_user)
        db.commit()
    elif not manager_user.password_hash or not manager_user.password_hash.startswith("$2b$"):
        manager_user.password_hash = hash_password("billcare2026")
        db.commit()

    # Ensure receptionist account exists for role testing
    reception_user = db.query(UserModel).filter(UserModel.email == "reception@billcare.io").first()
    if not reception_user:
        reception_user = UserModel(
            id="usr_billcare_receptionist",
            salon_id=DEFAULT_SALON_ID,
            name="Ananya Sen",
            email="reception@billcare.io",
            phone="+91 98450 55667",
            role="receptionist",
            avatar="A",
            password_hash=hash_password("billcare2026"),
        )
        db.add(reception_user)
        db.commit()
    elif not reception_user.password_hash or not reception_user.password_hash.startswith("$2b$"):
        reception_user.password_hash = hash_password("billcare2026")
        db.commit()

    existing_salon = db.query(SalonModel).filter(SalonModel.id == DEFAULT_SALON_ID).first()
    if existing_salon:
        return

    print("Seeding initial BillCare flagship salon and operational data...")

    # 1. Salon
    salon = SalonModel(
        id=DEFAULT_SALON_ID,
        name="BillCare Premier Atelier & Spa",
        slug="billcare-atelier",
        branch="Flagship Studio",
        city="Mumbai & Bengaluru",
        currency="₹",
        chairs=8,
        category="Luxury Hair Studio & Aesthetic Spa",
        logo_url="/logo.png",
        logo="/logo.png",
        gstin="27AABCB1234F1Z8",
        auto_gst=True,
        phone="+91 98450 11223",
        email="hello@billcare.io",
        address="Suite 401, Crescent Galleria, Indiranagar",
        timing="10:00 AM - 09:00 PM (All Days)",
        rating=4.9,
        review_count=418,
    )
    db.add(salon)

    # 2. User (Owner)
    owner = UserModel(
        id="usr_billcare_owner",
        salon_id=DEFAULT_SALON_ID,
        name="Sunil Kumar",
        email="owner@billcare.io",
        phone="+91 98450 11223",
        role="owner",
        avatar="S",
        password_hash=hash_password("billcare2026"),
    )
    db.add(owner)

    db.commit()
    print("Database seeding completed with clean slate (0 services, 0 customers, 0 staff, 0 inventory).")
