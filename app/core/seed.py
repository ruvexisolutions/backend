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
    PaymentModel,
)

from .security import hash_password

DEFAULT_SALON_ID = "sln_billcare_flagship"

def seed_database(db: Session):
    # Ensure salon table has upi_id, bank details, and trial columns
    try:
        from sqlalchemy import text
        for col, col_type in [
            ("upi_id", "VARCHAR(128) DEFAULT 'billcare.pos@icici'"),
            ("bank_account_name", "VARCHAR(128)"),
            ("bank_account_number", "VARCHAR(64)"),
            ("bank_ifsc", "VARCHAR(32)"),
            ("bank_name", "VARCHAR(128)"),
            ("trial_started_at", "DATETIME"),
            ("trial_ends_at", "DATETIME"),
            ("subscription_status", "VARCHAR(32) DEFAULT 'trial'"),
            ("subscription_plan", "VARCHAR(32) DEFAULT 'trial'"),
            ("whatsapp_phone_number_id", "VARCHAR(128)"),
            ("whatsapp_waba_id", "VARCHAR(128)"),
            ("whatsapp_access_token", "TEXT"),
            ("whatsapp_display_number", "VARCHAR(32)"),
            ("whatsapp_verified_name", "VARCHAR(128)"),
            ("whatsapp_quality_rating", "VARCHAR(32) DEFAULT 'GREEN'"),
            ("whatsapp_status", "VARCHAR(32) DEFAULT 'not_connected'"),
            ("whatsapp_webhook_verified", "BOOLEAN DEFAULT 0"),
            ("whatsapp_last_tested_at", "DATETIME"),
            ("whatsapp_error_message", "TEXT"),
            ("whatsapp_templates_status", "VARCHAR(64) DEFAULT 'APPROVED (3 Active)'"),
            ("upi_payee_name", "VARCHAR(128)"),
            ("upi_enabled", "BOOLEAN DEFAULT 0"),
            ("cash_enabled", "BOOLEAN DEFAULT 1"),
            ("payment_instructions", "TEXT"),
        ]:
            try:
                db.execute(text(f"ALTER TABLE salons ADD COLUMN {col} {col_type}"))
                db.commit()
            except Exception:
                db.rollback()
        
        # Ensure appointments table has chair_number
        try:
            db.execute(text("ALTER TABLE appointments ADD COLUMN chair_number INTEGER DEFAULT 1"))
            db.commit()
        except Exception:
            db.rollback()

        # Ensure invoices table has payment audit, refund, and points redemption columns
        for col, col_type in [
            ("amount_received", "FLOAT DEFAULT 0.0"),
            ("change_given", "FLOAT DEFAULT 0.0"),
            ("verified_by_name", "VARCHAR(128)"),
            ("verified_by_user_id", "VARCHAR(64)"),
            ("payment_reference", "VARCHAR(128)"),
            ("paid_at", "DATETIME"),
            ("refund_amount", "FLOAT DEFAULT 0.0"),
            ("refund_reason", "TEXT"),
            ("refunded_at", "DATETIME"),
            ("points_redeemed", "INTEGER DEFAULT 0"),
            ("points_discount", "FLOAT DEFAULT 0.0"),
        ]:
            try:
                db.execute(text(f"ALTER TABLE invoices ADD COLUMN {col} {col_type}"))
                db.commit()
            except Exception:
                db.rollback()

        # Ensure payments table exists
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS payments (
                    id VARCHAR(64) PRIMARY KEY,
                    salon_id VARCHAR(64) NOT NULL,
                    invoice_id VARCHAR(64) NOT NULL,
                    amount FLOAT NOT NULL DEFAULT 0.0,
                    currency VARCHAR(10) DEFAULT 'INR',
                    method VARCHAR(32) NOT NULL DEFAULT 'CASH',
                    status VARCHAR(32) DEFAULT 'pending',
                    provider_ref_id VARCHAR(255),
                    verification_method VARCHAR(64) DEFAULT 'manual_receptionist_verification',
                    verified_by_user_id VARCHAR(64),
                    verified_by_name VARCHAR(128),
                    amount_received FLOAT DEFAULT 0.0,
                    change_given FLOAT DEFAULT 0.0,
                    upi_vpa_snapshot VARCHAR(128),
                    upi_payee_name_snapshot VARCHAR(128),
                    upi_uri_snapshot TEXT,
                    notes TEXT,
                    audit_metadata_json TEXT DEFAULT '{}',
                    created_at DATETIME,
                    confirmed_at DATETIME
                )
            """))
            db.commit()
        except Exception:
            db.rollback()

        # Ensure whatsapp_messages table exists
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS whatsapp_messages (
                    id VARCHAR(64) PRIMARY KEY,
                    salon_id VARCHAR(64) NOT NULL,
                    recipient_phone VARCHAR(32) NOT NULL,
                    customer_name VARCHAR(128) DEFAULT 'Valued Client',
                    message_type VARCHAR(64) NOT NULL,
                    template_name VARCHAR(64) DEFAULT 'billcare_service_receipt',
                    meta_message_id VARCHAR(128),
                    status VARCHAR(32) DEFAULT 'sent',
                    idempotency_key VARCHAR(128),
                    error_details TEXT,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
            db.commit()
        except Exception:
            db.rollback()

        # Ensure cash_register_shifts table exists
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS cash_register_shifts (
                    id VARCHAR(64) PRIMARY KEY,
                    salon_id VARCHAR(64) NOT NULL,
                    opened_by_user_id VARCHAR(64),
                    opened_by_name VARCHAR(128) DEFAULT 'Front Desk Cashier',
                    closed_by_user_id VARCHAR(64),
                    closed_by_name VARCHAR(128),
                    opening_float FLOAT DEFAULT 2000.0,
                    cash_sales FLOAT DEFAULT 0.0,
                    upi_sales FLOAT DEFAULT 0.0,
                    card_sales FLOAT DEFAULT 0.0,
                    total_sales FLOAT DEFAULT 0.0,
                    expected_cash FLOAT DEFAULT 2000.0,
                    counted_cash FLOAT,
                    cash_variance FLOAT DEFAULT 0.0,
                    status VARCHAR(32) DEFAULT 'open',
                    notes TEXT DEFAULT '',
                    opened_at DATETIME,
                    closed_at DATETIME
                )
            """))
            db.commit()
        except Exception:
            db.rollback()

        # Ensure expenses table exists
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id VARCHAR(64) PRIMARY KEY,
                    salon_id VARCHAR(64) NOT NULL,
                    title VARCHAR(128) NOT NULL,
                    category VARCHAR(64) DEFAULT 'Supplies',
                    amount FLOAT NOT NULL,
                    payment_method VARCHAR(32) DEFAULT 'Cash',
                    date VARCHAR(32),
                    recorded_by_name VARCHAR(128) DEFAULT 'Salon Manager',
                    notes TEXT DEFAULT '',
                    created_at DATETIME
                )
            """))
            db.commit()
        except Exception:
            db.rollback()

        # Ensure inventory_ledger table exists
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS inventory_ledger (
                    id VARCHAR(64) PRIMARY KEY,
                    salon_id VARCHAR(64) NOT NULL,
                    item_id VARCHAR(64) NOT NULL,
                    item_name VARCHAR(128) NOT NULL,
                    change_qty INTEGER NOT NULL,
                    previous_stock INTEGER DEFAULT 0,
                    new_stock INTEGER DEFAULT 0,
                    reason VARCHAR(128) DEFAULT 'sale',
                    performed_by VARCHAR(128) DEFAULT 'POS System',
                    created_at DATETIME
                )
            """))
            db.commit()
        except Exception:
            db.rollback()
    except Exception:
        pass

    # Ensure flagship owner account has normalized role and valid bcrypt hash
    owner_user = db.query(UserModel).filter(UserModel.email == "owner@billcare.io").first()
    if owner_user:
        owner_user.role = "SALON_MANAGER"
        owner_user.phone = "+919845011223"
        if not owner_user.password_hash or not owner_user.password_hash.startswith("$2b$"):
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
            phone="+919845033445",
            role="SALON_MANAGER",
            avatar="K",
            password_hash=hash_password("billcare2026"),
        )
        db.add(manager_user)
        db.commit()
    else:
        manager_user.role = "SALON_MANAGER"
        manager_user.phone = "+919845033445"
        if not manager_user.password_hash or not manager_user.password_hash.startswith("$2b$"):
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
            phone="+919845055667",
            role="SALON_RECEPTIONIST",
            avatar="A",
            password_hash=hash_password("billcare2026"),
        )
        db.add(reception_user)
        db.commit()
    else:
        reception_user.role = "SALON_RECEPTIONIST"
        reception_user.phone = "+919845055667"
        if not reception_user.password_hash or not reception_user.password_hash.startswith("$2b$"):
            reception_user.password_hash = hash_password("billcare2026")
        db.commit()

    now = datetime.utcnow()
    trial_end = now + timedelta(days=7)

    existing_salon = db.query(SalonModel).filter(SalonModel.id == DEFAULT_SALON_ID).first()
    if existing_salon:
        if not existing_salon.trial_started_at:
            existing_salon.trial_started_at = now
        if not existing_salon.trial_ends_at:
            existing_salon.trial_ends_at = trial_end
        if not existing_salon.subscription_status:
            existing_salon.subscription_status = "trial"
        if not existing_salon.subscription_plan:
            existing_salon.subscription_plan = "trial"
        if existing_salon.cash_enabled is None:
            existing_salon.cash_enabled = True
        if existing_salon.upi_enabled is None:
            existing_salon.upi_enabled = True
        if not existing_salon.upi_id:
            existing_salon.upi_id = "flagship@icici"
        if not existing_salon.upi_payee_name:
            existing_salon.upi_payee_name = "BillCare Flagship Atelier"
        db.commit()
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
        phone="+919845011223",
        email="hello@billcare.io",
        address="Suite 401, Crescent Galleria, Indiranagar",
        timing="10:00 AM - 09:00 PM (All Days)",
        rating=4.9,
        review_count=418,
        trial_started_at=now,
        trial_ends_at=trial_end,
        subscription_status="trial",
        subscription_plan="trial",
    )
    db.add(salon)

    # 2. User (Default Salon Manager)
    owner = UserModel(
        id="usr_billcare_owner",
        salon_id=DEFAULT_SALON_ID,
        name="Sunil Kumar",
        email="owner@billcare.io",
        phone="+919845011223",
        role="SALON_MANAGER",
        avatar="S",
        password_hash=hash_password("billcare2026"),
    )
    db.add(owner)

    db.commit()
    print("Database seeding completed with normalized roles and 7-day trial active.")
