from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base, SessionLocal
from app.core.seed import seed_database
from app.api.v1.router import router as api_v1_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure tables exist & seed default data
    Base.metadata.create_all(bind=engine)
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
