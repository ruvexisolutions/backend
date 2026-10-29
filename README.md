# BillCare Backend — FastAPI · SQLAlchemy · Railway

Multi-tenant Salon & Spa Management SaaS backend built with **FastAPI**, deployable to **Railway** in one click.

## 🚀 Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

1. Click **Deploy on Railway** above  
2. Add a **PostgreSQL** plugin (Railway auto-injects `DATABASE_URL`)  
3. Set the required environment variables (see `.env.example`)  
4. Railway auto-detects `railway.toml` and starts the service

## 🏗 Project Structure

```
backend/
├── app/
│   ├── main.py               # FastAPI app entry point
│   ├── api/v1/               # Versioned API routes
│   ├── core/
│   │   ├── database.py       # SQLAlchemy engine & session
│   │   ├── models.py         # ORM models
│   │   ├── security.py       # JWT auth
│   │   └── seed.py           # Default data seeder
│   ├── modules/              # Feature modules (appointments, POS, staff…)
│   └── services/             # External integrations (Razorpay, WhatsApp)
├── tests/                    # Pytest test suite
├── .env.example              # Environment variable template
├── railway.toml              # Railway deployment config
├── Procfile                  # Process declaration (fallback)
├── runtime.txt               # Python version pin
└── requirements.txt          # Python dependencies
```

## ⚙️ Environment Variables

Copy `.env.example` → `.env` and fill in your values.  
In Railway, set variables under **Service → Variables**.

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection URI (auto-set by Railway PostgreSQL plugin) |
| `JWT_SECRET` | ✅ | Long random string for signing JWTs |
| `RAZORPAY_KEY_ID` | Optional | Razorpay API key |
| `RAZORPAY_KEY_SECRET` | Optional | Razorpay API secret |
| `WHATSAPP_ACCESS_TOKEN` | Optional | Meta WhatsApp Cloud API token |

## 🏃 Local Development

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

## 🧪 Running Tests

```bash
pytest tests/ -v
```

## 📡 API Endpoints

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
