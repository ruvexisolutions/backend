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

    # Seed services for OLG Hair Saloon (darshanurs54@gmail.com)
    try:
        from .olg_catalog import OLG_CATALOG
        olg_salon = db.query(SalonModel).filter(
            (SalonModel.email.ilike("darshanurs54@gmail.com")) |
            (SalonModel.id == "sln_1dc700ec03ea") |
            (SalonModel.name.ilike("%olg%"))
        ).first()

        if not olg_salon:
            now_dt = datetime.utcnow()
            olg_salon = SalonModel(
                id="sln_1dc700ec03ea",
                name="OLG Professional Unisex Salon & HairFixing",
                slug="darshan-urs-s-atelier-7b0e",
                branch="Chickmagalur Studio",
                city="Chickmagalur",
                currency="₹",
                chairs=5,
                category="Hair Studio & Aesthetic Spa",
                phone="8296294666",
                email="darshanurs54@gmail.com",
                address="opp jayashree digital, aralimara road, basavanahalli, chikmagalur",
                timing="10:00 AM - 09:00 PM (All Days)",
                rating=4.9,
                review_count=418,
                trial_started_at=now_dt,
                trial_ends_at=None,
                subscription_status="active",
                subscription_plan="pro",
                upi_id="8296294666@ybl",
                upi_payee_name="OLG Professional Unisex Salon",
                cash_enabled=True,
                upi_enabled=True,
            )
            db.add(olg_salon)
            db.commit()
        else:
            olg_salon.subscription_status = "active"
            olg_salon.subscription_plan = "pro"
            olg_salon.trial_ends_at = None
            db.commit()

        # Ensure all salons tied to darshanurs54@gmail.com have active Pro subscription access
        darshan_salons = db.query(SalonModel).filter(
            (SalonModel.email.ilike("darshanurs54@gmail.com")) |
            (SalonModel.id == "sln_1dc700ec03ea") |
            (SalonModel.name.ilike("%olg%"))
        ).all()
        for s in darshan_salons:
            s.subscription_status = "active"
            s.subscription_plan = "pro"
            s.trial_ends_at = None
        db.commit()

        # Ensure darshanurs54@gmail.com user exists and has valid password
        darshan_user = db.query(UserModel).filter(
            (UserModel.email.ilike("darshanurs54@gmail.com")) |
            (UserModel.salon_id == olg_salon.id)
        ).first()
        if darshan_user:
            darshan_user.salon_id = olg_salon.id
            if not darshan_user.phone:
                darshan_user.phone = "8296294666"
            darshan_user.role = "MASTER_ADMIN"
            if not darshan_user.password_hash or len(darshan_user.password_hash) < 10:
                darshan_user.password_hash = hash_password("Ruvexi2026!")
            db.commit()
        else:
            import uuid
            darshan_user = UserModel(
                id=f"usr_{uuid.uuid4().hex[:12]}",
                salon_id=olg_salon.id,
                name="Darshan Urs",
                email="darshanurs54@gmail.com",
                phone="8296294666",
                role="MASTER_ADMIN",
                avatar="D",
                password_hash=hash_password("Ruvexi2026!"),
            )
            db.add(darshan_user)
            db.commit()

        # Seed all 125 services idempotently
        existing_srvs = {
            (s.name.strip().lower(), s.category.strip().lower()): s
            for s in db.query(ServiceModel).filter(ServiceModel.salon_id == olg_salon.id).all()
        }
        for item in OLG_CATALOG:
            key = (item["name"].strip().lower(), item["category"].strip().lower())
            if key in existing_srvs:
                s = existing_srvs[key]
                s.price = item["price"]
                s.duration_minutes = item["duration_minutes"]
                s.buffer_minutes = item.get("buffer_minutes", 5)
                s.description = item.get("description", "")
                s.is_active = True
                s.is_online_bookable = True
                s.popular = item.get("popular", False)
            else:
                s = ServiceModel(
                    id=item["id"],
                    salon_id=olg_salon.id,
                    name=item["name"],
                    category=item["category"],
                    price=item["price"],
                    duration_minutes=item["duration_minutes"],
                    buffer_minutes=item.get("buffer_minutes", 5),
                    description=item.get("description", ""),
                    is_active=True,
                    is_online_bookable=True,
                    popular=item.get("popular", False),
                )
                db.add(s)
        db.commit()
        print(f"[Seed] Successfully ensured {len(OLG_CATALOG)} services for OLG salon ({olg_salon.name})")
    except Exception as e_olg:
        db.rollback()
        print(f"[Seed Notice] OLG services seed notice: {e_olg}")

    # Configure chethanchethu524@gmail.com as MASTER_ADMIN owning "OLG Unisex Salon & HairFixing" with 3 branches & 125 services
    try:
        from .olg_catalog import OLG_CATALOG
        chethan_salon = db.query(SalonModel).filter(
            (SalonModel.email.ilike("chethanchethu524@gmail.com")) |
            (SalonModel.id == "sln_3857fe44e88a")
        ).first()

        now_dt = datetime.utcnow()
        if not chethan_salon:
            chethan_salon = SalonModel(
                id="sln_3857fe44e88a",
                name="OLG Unisex Salon & HairFixing",
                slug="chethan-shyva-s-atelier-604a",
                branch="Chikmagalur",
                city="Chikmagalur",
                currency="₹",
                chairs=6,
                category="Hair Studio & Aesthetic Spa",
                phone="8296294666",
                email="chethanchethu524@gmail.com",
                address="opp jayashree digital, aralimara road, basavanahalli, chikmagalur",
                timing="10:00 AM - 09:00 PM (All Days)",
                rating=4.9,
                review_count=418,
                trial_started_at=now_dt,
                trial_ends_at=None,
                subscription_status="active",
                subscription_plan="pro",
                upi_id="8296294666@ybl",
                upi_payee_name="OLG Unisex Salon & HairFixing",
                cash_enabled=True,
                upi_enabled=True,
            )
            db.add(chethan_salon)
            db.commit()
        else:
            chethan_salon.name = "OLG Unisex Salon & HairFixing"
            chethan_salon.city = "Chikmagalur"
            chethan_salon.branch = "Chikmagalur"
            chethan_salon.subscription_status = "active"
            chethan_salon.subscription_plan = "pro"
            chethan_salon.trial_ends_at = None
            chethan_salon.upi_id = "8296294666@ybl"
            chethan_salon.upi_payee_name = "OLG Unisex Salon & HairFixing"
            chethan_salon.cash_enabled = True
            chethan_salon.upi_enabled = True
            db.commit()

        # Ensure user chethanchethu524@gmail.com has MASTER_ADMIN role
        chethan_user = db.query(UserModel).filter(
            UserModel.email.ilike("chethanchethu524@gmail.com")
        ).first()
        if chethan_user:
            chethan_user.salon_id = chethan_salon.id
            chethan_user.role = "MASTER_ADMIN"
            if not chethan_user.phone:
                chethan_user.phone = "8296294666"
            if not chethan_user.password_hash or len(chethan_user.password_hash) < 10:
                chethan_user.password_hash = hash_password("Ruvexi2026!")
            db.commit()
        else:
            import uuid
            chethan_user = UserModel(
                id=f"usr_{uuid.uuid4().hex[:12]}",
                salon_id=chethan_salon.id,
                name="Chethan Shyva",
                email="chethanchethu524@gmail.com",
                phone="8296294666",
                role="MASTER_ADMIN",
                avatar="C",
                password_hash=hash_password("Ruvexi2026!"),
            )
            db.add(chethan_user)
            db.commit()

        # Ensure 3 branches under this salon: chikmagalur, hassan, belur
        branches_data = [
            {
                "id": f"brn_{chethan_salon.id[-8:]}_chik",
                "name": "Chikmagalur",
                "code": "BR-CHIK",
                "city": "Chikmagalur",
                "address": "opp jayashree digital, aralimara road, basavanahalli, chikmagalur",
                "phone": "8296294666",
                "email": "chethanchethu524@gmail.com",
                "chairs": 6,
            },
            {
                "id": f"brn_{chethan_salon.id[-8:]}_hassan",
                "name": "Hassan",
                "code": "BR-HASSAN",
                "city": "Hassan",
                "address": "Main Road, Near City Bus Stand, Hassan",
                "phone": "8296294666",
                "email": "chethanchethu524@gmail.com",
                "chairs": 6,
            },
            {
                "id": f"brn_{chethan_salon.id[-8:]}_belur",
                "name": "Belur",
                "code": "BR-BELUR",
                "city": "Belur",
                "address": "Temple Road, Belur",
                "phone": "8296294666",
                "email": "chethanchethu524@gmail.com",
                "chairs": 5,
            },
        ]

        existing_branches = {b.name.strip().lower(): b for b in db.query(BranchModel).filter(BranchModel.salon_id == chethan_salon.id).all()}
        for b_data in branches_data:
            key = b_data["name"].strip().lower()
            if key in existing_branches:
                br = existing_branches[key]
                br.code = b_data["code"]
                br.city = b_data["city"]
                br.address = b_data["address"]
                br.phone = b_data["phone"]
                br.email = b_data["email"]
                br.is_active = True
            else:
                br = BranchModel(
                    id=b_data["id"],
                    salon_id=chethan_salon.id,
                    name=b_data["name"],
                    code=b_data["code"],
                    city=b_data["city"],
                    address=b_data["address"],
                    phone=b_data["phone"],
                    email=b_data["email"],
                    chairs=b_data["chairs"],
                    is_active=True,
                )
                db.add(br)
        db.commit()

        # Seed all 125 services into chethan_salon
        existing_srvs = {
            (s.name.strip().lower(), s.category.strip().lower()): s
            for s in db.query(ServiceModel).filter(ServiceModel.salon_id == chethan_salon.id).all()
        }
        for item in OLG_CATALOG:
            key = (item["name"].strip().lower(), item["category"].strip().lower())
            if key in existing_srvs:
                s = existing_srvs[key]
                s.price = item["price"]
                s.duration_minutes = item["duration_minutes"]
                s.buffer_minutes = item.get("buffer_minutes", 5)
                s.description = item.get("description", "")
                s.is_active = True
                s.is_online_bookable = True
                s.popular = item.get("popular", False)
            else:
                s = ServiceModel(
                    id=f"srv_c_{item['id']}",
                    salon_id=chethan_salon.id,
                    name=item["name"],
                    category=item["category"],
                    price=item["price"],
                    duration_minutes=item["duration_minutes"],
                    buffer_minutes=item.get("buffer_minutes", 5),
                    description=item.get("description", ""),
                    is_active=True,
                    is_online_bookable=True,
                    popular=item.get("popular", False),
                )
                db.add(s)
        db.commit()
        print(f"[Seed] Successfully configured Chethan MASTER_ADMIN salon ({chethan_salon.name}) with 3 branches and {len(OLG_CATALOG)} services.")
    except Exception as e_chethan:
        db.rollback()
        print(f"[Seed Notice] Chethan salon setup notice: {e_chethan}")

    # Explicit purge of decommissioned demo / test accounts and salons
    try:
        purge_decommissioned_accounts(db)
    except Exception as e_purge:
        db.rollback()
        print(f"[Seed Notice] Decommissioned accounts purge notice: {e_purge}")

    return


def purge_decommissioned_accounts(db: Session) -> list:
    """Permanently purges decommissioned demo, test, and placeholder accounts and salons."""
    DECOMMISSIONED_EMAILS = [
        "ruvexisolutions@gmail.com",
        "verified.manager.1794256393@ruvexi.com",
        "founder@ruvexisolutions.com",
        "director.test@ruvexi.com",
        "probe_check_1234@ruvexi.com",
        "sunil@billcaresalon.com",
    ]
    DECOMMISSIONED_SLUGS = [
        "ruvexis-salon-&-spa-86a0",
        "ruvexi-luxury-flagship-fd63",
        "ruvexi-atelier-bengaluru-480a",
        "ruvexi-test-atelier-a101",
        "probe-salon-ce49",
        "aura-luxury-salon-&-spa-9f22",
    ]
    DECOMMISSIONED_SALON_IDS = [
        "sln_768aef32ad07",
        "sln_5ba8ec0b93cf",
        "sln_494b36e0007b",
        "sln_82e722804d9b",
        "sln_49029c100894",
        "sln_66c2243a0701",
    ]

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
    )

    # 1. Locate all salons matching criteria
    target_salons = db.query(SalonModel).filter(
        (SalonModel.id.in_(DECOMMISSIONED_SALON_IDS)) |
        (SalonModel.slug.in_(DECOMMISSIONED_SLUGS)) |
        (SalonModel.email.in_(DECOMMISSIONED_EMAILS))
    ).all()

    target_salon_ids = set(s.id for s in target_salons)
    for sid in DECOMMISSIONED_SALON_IDS:
        target_salon_ids.add(sid)

    removed_salons_info = []

    if target_salon_ids:
        # Cascade delete child entities
        db.query(StaffModel).filter(StaffModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(ServiceModel).filter(ServiceModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(CustomerModel).filter(CustomerModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(AppointmentModel).filter(AppointmentModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(InvoiceModel).filter(InvoiceModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(PaymentModel).filter(PaymentModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(FollowUpModel).filter(FollowUpModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(FeedbackModel).filter(FeedbackModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(InventoryModel).filter(InventoryModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(InventoryLedgerModel).filter(InventoryLedgerModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(ExpenseModel).filter(ExpenseModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(BranchModel).filter(BranchModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(CashRegisterShiftModel).filter(CashRegisterShiftModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(WhatsAppMessageModel).filter(WhatsAppMessageModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)
        db.query(InvitationModel).filter(InvitationModel.salon_id.in_(target_salon_ids)).delete(synchronize_session=False)

        for s in target_salons:
            removed_salons_info.append({"id": s.id, "name": s.name, "email": s.email})
            db.delete(s)

    # 2. Locate and delete matching users
    db.query(UserModel).filter(
        (UserModel.salon_id.in_(target_salon_ids)) |
        (UserModel.email.in_(DECOMMISSIONED_EMAILS))
    ).delete(synchronize_session=False)

    db.commit()
    if removed_salons_info:
        print(f"[Decommission Purge] Successfully removed {len(removed_salons_info)} decommissioned salons: {removed_salons_info}")
    return removed_salons_info
