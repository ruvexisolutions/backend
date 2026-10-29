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

        # Customers wallet_balance
        if "customers" in tables:
            cust_cols = [c["name"] for c in inspector.get_columns("customers")]
            if "wallet_balance" not in cust_cols:
                with engine.begin() as conn:
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
