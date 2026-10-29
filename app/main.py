import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from app.core.database import engine, Base, SessionLocal
from app.core.seed import seed_database
from app.api.v1.router import router as api_v1_router

def ensure_schema_compatibility():
    """Idempotently ensures all recently added columns exist across SQLite/PostgreSQL tables."""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        is_postgres = "postgres" in engine.dialect.name.lower()

        # Users role check constraint & branch_id compatibility
        if "users" in tables:
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check"))
                    conn.execute(text("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('SALON_MANAGER', 'SALON_RECEPTIONIST', 'owner', 'manager', 'receptionist', 'admin', 'MASTER_ADMIN'))"))
            except Exception as ex:
                print(f"[Users Check Constraint Migration] {ex}")
            
            user_cols = [c["name"] for c in inspector.get_columns("users")]
            if "branch_id" not in user_cols:
                with engine.begin() as conn:
                    if is_postgres:
                        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS branch_id VARCHAR(64)"))
                    else:
                        conn.execute(text("ALTER TABLE users ADD COLUMN branch_id VARCHAR(64)"))

        # Invitations branch_id
        if "invitations" in tables:
            inv_t_cols = [c["name"] for c in inspector.get_columns("invitations")]
            if "branch_id" not in inv_t_cols:
                with engine.begin() as conn:
                    if is_postgres:
                        conn.execute(text("ALTER TABLE invitations ADD COLUMN IF NOT EXISTS branch_id VARCHAR(64)"))
                    else:
                        conn.execute(text("ALTER TABLE invitations ADD COLUMN branch_id VARCHAR(64)"))

        # Staff branch_id
        if "staff" in tables:
            staff_cols = [c["name"] for c in inspector.get_columns("staff")]
            if "branch_id" not in staff_cols:
                with engine.begin() as conn:
                    if is_postgres:
                        conn.execute(text("ALTER TABLE staff ADD COLUMN IF NOT EXISTS branch_id VARCHAR(64)"))
                    else:
                        conn.execute(text("ALTER TABLE staff ADD COLUMN branch_id VARCHAR(64)"))

        # Branches code column
        if "branches" in tables:
            brn_cols = [c["name"] for c in inspector.get_columns("branches")]
            if "code" not in brn_cols:
                with engine.begin() as conn:
                    if is_postgres:
                        conn.execute(text("ALTER TABLE branches ADD COLUMN IF NOT EXISTS code VARCHAR(32)"))
                    else:
                        conn.execute(text("ALTER TABLE branches ADD COLUMN code VARCHAR(32)"))

        # Cash register shifts branch_id
        if "cash_register_shifts" in tables:
            crs_cols = [c["name"] for c in inspector.get_columns("cash_register_shifts")]
            if "branch_id" not in crs_cols:
                with engine.begin() as conn:
                    if is_postgres:
                        conn.execute(text("ALTER TABLE cash_register_shifts ADD COLUMN IF NOT EXISTS branch_id VARCHAR(64)"))
                    else:
                        conn.execute(text("ALTER TABLE cash_register_shifts ADD COLUMN branch_id VARCHAR(64)"))

        # Salons table columns upgrade
        if "salons" in tables:
            salons_cols = [c["name"] for c in inspector.get_columns("salons")]
            bool_type = "BOOLEAN"
            false_val = "FALSE" if is_postgres else "0"
            true_val = "TRUE" if is_postgres else "1"
            dt_type = "TIMESTAMPTZ" if is_postgres else "DATETIME"
            
            salon_columns_to_add = [
                ("logo", "VARCHAR(512) DEFAULT '/logo.png'"),
                ("logo_url", "VARCHAR(512) DEFAULT '/logo.png'"),
                ("upi_id", "VARCHAR(128)"),
                ("upi_payee_name", "VARCHAR(128)"),
                ("upi_enabled", f"{bool_type} DEFAULT {false_val}"),
                ("cash_enabled", f"{bool_type} DEFAULT {true_val}"),
                ("payment_instructions", "TEXT"),
                ("bank_account_name", "VARCHAR(128)"),
                ("bank_account_number", "VARCHAR(64)"),
                ("bank_ifsc", "VARCHAR(32)"),
                ("bank_name", "VARCHAR(128)"),
                ("trial_started_at", dt_type),
                ("trial_ends_at", dt_type),
                ("subscription_status", "VARCHAR(32) DEFAULT 'trial'"),
                ("subscription_plan", "VARCHAR(64) DEFAULT 'free_trial'"),
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
            ]
            with engine.begin() as conn:
                for col_name, col_def in salon_columns_to_add:
                    if col_name not in salons_cols:
                        try:
                            if is_postgres:
                                conn.execute(text(f"ALTER TABLE salons ADD COLUMN IF NOT EXISTS {col_name} {col_def}"))
                            else:
                                conn.execute(text(f"ALTER TABLE salons ADD COLUMN {col_name} {col_def}"))
                        except Exception as e_col:
                            print(f"[Salons Column {col_name} Migration Notice] {e_col}")

        # Invoices columns upgrade
        if "invoices" in tables:
            inv_cols = [c["name"] for c in inspector.get_columns("invoices")]
            dt_type = "TIMESTAMPTZ" if is_postgres else "DATETIME"
            invoice_columns = [
                ("upi_vpa_snapshot", "VARCHAR(128)"),
                ("upi_payee_name_snapshot", "VARCHAR(128)"),
                ("upi_uri_snapshot", "TEXT"),
                ("cash_tendered", "FLOAT DEFAULT 0.0"),
                ("change_returned", "FLOAT DEFAULT 0.0"),
                ("amount_received", "FLOAT DEFAULT 0.0"),
                ("change_given", "FLOAT DEFAULT 0.0"),
                ("verified_by_name", "VARCHAR(128)"),
                ("verified_by_user_id", "VARCHAR(64)"),
                ("payment_reference", "VARCHAR(128)"),
                ("paid_at", dt_type),
                ("refund_amount", "FLOAT DEFAULT 0.0"),
                ("refund_reason", "TEXT"),
                ("refunded_at", dt_type),
                ("points_redeemed", "INTEGER DEFAULT 0"),
                ("points_discount", "FLOAT DEFAULT 0.0"),
            ]
            with engine.begin() as conn:
                for col_name, col_def in invoice_columns:
                    if col_name not in inv_cols:
                        try:
                            if is_postgres:
                                conn.execute(text(f"ALTER TABLE invoices ADD COLUMN IF NOT EXISTS {col_name} {col_def}"))
                            else:
                                conn.execute(text(f"ALTER TABLE invoices ADD COLUMN {col_name} {col_def}"))
                        except Exception as e_col:
                            print(f"[Invoices Column {col_name} Migration Notice] {e_col}")

        # Appointments chair_number
        if "appointments" in tables:
            apt_cols = [c["name"] for c in inspector.get_columns("appointments")]
            if "chair_number" not in apt_cols:
                with engine.begin() as conn:
                    if is_postgres:
                        conn.execute(text("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS chair_number INTEGER DEFAULT 1"))
                    else:
                        conn.execute(text("ALTER TABLE appointments ADD COLUMN chair_number INTEGER DEFAULT 1"))

        # Customers wallet_balance
        if "customers" in tables:
            cust_cols = [c["name"] for c in inspector.get_columns("customers")]
            if "wallet_balance" not in cust_cols:
                with engine.begin() as conn:
                    if is_postgres:
                        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS wallet_balance FLOAT DEFAULT 0.0"))
                    else:
                        conn.execute(text("ALTER TABLE customers ADD COLUMN wallet_balance FLOAT DEFAULT 0.0"))

        # Services consumable materials
        if "services" in tables:
            srv_cols = [c["name"] for c in inspector.get_columns("services")]
            cols_to_add = [
                ("material_used", "VARCHAR(256)"),
                ("material_item_id", "VARCHAR(64)"),
                ("material_quantity", "FLOAT DEFAULT 0.0"),
                ("material_unit", "VARCHAR(32) DEFAULT 'ml'"),
            ]
            with engine.begin() as conn:
                for col_name, col_type in cols_to_add:
                    if col_name not in srv_cols:
                        if is_postgres:
                            conn.execute(text(f"ALTER TABLE services ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                        else:
                            conn.execute(text(f"ALTER TABLE services ADD COLUMN {col_name} {col_type}"))
    except Exception as e:
        print(f"[Schema Migration Notice] {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure tables exist & seed default data
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    db = SessionLocal()
    try:
        seed_database(db)
    except Exception as e:
        print(f"[Seed Graceful Catch] {e}")
    finally:
        db.close()
    yield
    # Shutdown logic if any

app = FastAPI(
    title="BillCare Solution Platform API",
    description="Multi-tenant Salon & Spa Management SaaS Backend API (FastAPI Modular Monolith)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
if not allowed_origins:
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://billcareweb.vercel.app",
        "https://billcaresolution.com",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*(railway\.app|vercel\.app|billcaresolution\.com)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 endpoints
app.include_router(api_v1_router)

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint used by uptime monitors and container orchestration."""
    return {"status": "healthy", "service": "billcare-api", "version": "1.0.0"}

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to BillCare Solution API - The Operating System for Modern Salons & Spas",
        "docs_url": "/docs",
        "version": "1.0.0",
        "endpoints": {
            "bootstrap": "/api/v1/bootstrap",
            "customers": "/api/v1/customers",
            "appointments": "/api/v1/appointments",
            "pos_invoices": "/api/v1/invoices",
            "staff": "/api/v1/staff",
            "inventory": "/api/v1/inventory",
            "services": "/api/v1/services",
            "retention": "/api/v1/followups",
        }
    }
