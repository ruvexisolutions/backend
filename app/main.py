from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="RUVEXI Platform API",
    description="Multi-tenant Salon Management SaaS Backend API (FastAPI Modular Monolith)",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint used by Railway / Netlify / uptime monitors."""
    return {"status": "healthy", "service": "ruvexi-api", "version": "1.0.0"}

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to RUVEXI API - The operating system for modern salons",
        "docs_url": "/docs",
    }
