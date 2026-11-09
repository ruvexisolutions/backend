# Ruvexi Backend â€” FastAPI Â· SQLAlchemy Â· Railway

Multi-tenant Salon & Spa Management SaaS backend built with **FastAPI**, deployable to **Railway** in one click.

## ðŸš€ Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

1. Click **Deploy on Railway** above  
2. Add a **PostgreSQL** plugin (Railway auto-injects `DATABASE_URL`)  
3. Set the required environment variables (see `.env.example`)  
4. Railway auto-detects `railway.toml` and starts the service

## ðŸ— Project Structure

```
backend/
â”œâ”€â”€ app/
â”‚   â”œâ”€â”€ main.py               # FastAPI app entry point
â”‚   â”œâ”€â”€ api/v1/               # Versioned API routes
â”‚   â”œâ”€â”€ core/
â”‚   â”‚   â”œâ”€â”€ database.py       # SQLAlchemy engine & session
â”‚   â”‚   â”œâ”€â”€ models.py         # ORM models
â”‚   â”‚   â”œâ”€â”€ security.py       # JWT auth
â”‚   â”‚   â””â”€â”€ seed.py           # Default data seeder
â”‚   â”œâ”€â”€ modules/              # Feature modules (appointments, POS, staffâ€¦)
â”‚   â””â”€â”€ services/             # External integrations (Razorpay, WhatsApp)
â”œâ”€â”€ tests/                    # Pytest test suite
â”œâ”€â”€ .env.example              # Environment variable template
â”œâ”€â”€ railway.toml              # Railway deployment config
â”œâ”€â”€ Procfile                  # Process declaration (fallback)
â”œâ”€â”€ runtime.txt               # Python version pin
â””â”€â”€ requirements.txt          # Python dependencies
```

## âš™ï¸ Environment Variables

Copy `.env.example` â†’ `.env` and fill in your values.  
In Railway, set variables under **Service â†’ Variables**.

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | âœ… | PostgreSQL connection URI (auto-set by Railway PostgreSQL plugin) |
| `JWT_SECRET` | âœ… | Long random string for signing JWTs |
| `RAZORPAY_KEY_ID` | Optional | Razorpay API key |
| `RAZORPAY_KEY_SECRET` | Optional | Razorpay API secret |
| `WHATSAPP_ACCESS_TOKEN` | Optional | Meta WhatsApp Cloud API token |

## ðŸƒ Local Development

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # fill in your DATABASE_URL etc.
uvicorn app.main:app --reload
```

API docs available at: `http://localhost:8000/docs`

## ðŸ§ª Running Tests

```bash
pytest tests/ -v
```

## ðŸ“¡ API Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /docs` | Swagger UI |
| `POST /api/v1/bootstrap` | Tenant setup |
| `GET /api/v1/customers` | Customer management |
| `GET /api/v1/appointments` | Appointment management |
| `GET /api/v1/invoices` | POS & billing |
| `GET /api/v1/staff` | Staff management |
| `GET /api/v1/inventory` | Inventory management |
| `GET /api/v1/services` | Services catalog |
| `GET /api/v1/followups` | Retention & follow-ups |
