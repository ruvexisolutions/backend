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

DEFAULT_SALON_ID = "sln_Ruvexi_flagship"

def _seed_password_hash() -> str:
    import os, secrets
    pw = os.getenv("SEED_DEFAULT_PASSWORD", "").strip()
    return hash_password(pw or secrets.token_urlsafe(24))

def seed_database(db: Session):
    # Idempotent database seeding for development and demo environments
    try:
        from sqlalchemy import text
        bind = db.get_bind()
        is_postgres = "postgres" in (bind.dialect.name.lower() if bind else "")
        dt_type = "TIMESTAMPTZ" if is_postgres else "DATETIME"
        bool_type = "BOOLEAN"
        false_val = "FALSE" if is_postgres else "0"
        true_val = "TRUE" if is_postgres else "1"

        # Check existing columns on salons before altering
        for col, col_type in [
            ("upi_id", "VARCHAR(128)"),
            ("logo", "VARCHAR(512) DEFAULT '/logo.png'"),
            ("bank_account_name", "VARCHAR(128)"),
            ("bank_account_number", "VARCHAR(64)"),
            ("bank_ifsc", "VARCHAR(32)"),
            ("bank_name", "VARCHAR(128)"),
            ("trial_started_at", dt_type),
            ("trial_ends_at", dt_type),
            ("subscription_status", "VARCHAR(32) DEFAULT 'trial'"),
            ("subscription_plan", "VARCHAR(32) DEFAULT 'trial'"),
            ("whatsapp_phone_number_id", "VARCHAR(128)"),
            ("whatsapp_waba_id", "VARCHAR(128)"),
            ("whatsapp_access_token", "TEXT"),
            ("whatsapp_display_number", "VARCHAR(32)"),
            ("whatsapp_verified_name", "VARCHAR(128)"),
            ("whatsapp_quality_rating", "VARCHAR(32) DEFAULT 'GREEN'"),
            ("whatsapp_status", "VARCHAR(32) DEFAULT 'not_connected'"),
            ("whatsapp_webhook_verified", f"{bool_type} DEFAULT {false_val}"),
            ("whatsapp_last_tested_at", dt_type),
            ("whatsapp_error_message", "TEXT"),
            ("whatsapp_templates_status", "VARCHAR(64) DEFAULT 'APPROVED (3 Active)'"),
            ("upi_payee_name", "VARCHAR(128)"),
            ("upi_enabled", f"{bool_type} DEFAULT {false_val}"),
            ("cash_enabled", f"{bool_type} DEFAULT {true_val}"),
            ("payment_instructions", "TEXT"),
        ]:
            try:
                if is_postgres:
                    db.execute(text(f"ALTER TABLE salons ADD COLUMN IF NOT EXISTS {col} {col_type}"))
                else:
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
                    template_name VARCHAR(64) DEFAULT 'Ruvexi_service_receipt',
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

    # Clean architecture: pure schema checks only. No mock accounts, no hardcoded demo data.
    return


def wipe_all_data(db: Session) -> dict:
    """
    Permanently erases ALL accounts, salons, branches, appointments, services,
    customers, staff, invoices, payments, and operational data.
    Zero hardcoded values, zero stale accounts.
    """
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
        BranchModel,
        CashRegisterShiftModel,
        ExpenseModel,
        InventoryLedgerModel,
        WhatsAppMessageModel,
        InvitationModel,
        BlockedTimeSlotModel,
    )
    counts = {}
    models_in_order = [
        ("appointments", AppointmentModel),
        ("invoices", InvoiceModel),
        ("payments", PaymentModel),
        ("feedbacks", FeedbackModel),
        ("follow_ups", FollowUpModel),
        ("customers", CustomerModel),
        ("staff", StaffModel),
        ("inventory_ledger", InventoryLedgerModel),
        ("inventory", InventoryModel),
        ("expenses", ExpenseModel),
        ("cash_register_shifts", CashRegisterShiftModel),
        ("whatsapp_messages", WhatsAppMessageModel),
        ("invitations", InvitationModel),
        ("blocked_time_slots", BlockedTimeSlotModel),
        ("branches", BranchModel),
        ("services", ServiceModel),
        ("users", UserModel),
        ("salons", SalonModel),
    ]
    for name, model_cls in models_in_order:
        try:
            cnt = db.query(model_cls).delete(synchronize_session=False)
            counts[name] = cnt
        except Exception as e:
            counts[name] = f"error: {e}"
    db.commit()
    print(f"[Clean Slate Wipe] Database completely wiped: {counts}")
    return counts


def purge_decommissioned_accounts(db: Session) -> list:
    """Delegates to wipe_all_data to maintain a completely clean database."""
    res = wipe_all_data(db)
    return [res]
