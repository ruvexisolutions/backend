# BillCare Solution Backend API (`backend`)

Multi-tenant backend engine built with **FastAPI** following the **Modular Monolith** architecture pattern.

---

## 🏗️ Architecture & Modules

The backend is structured into distinct, isolated domain modules:

```
backend/
├── app/
│   ├── api/v1/endpoints/        # REST route definitions
│   ├── core/                    # Core infrastructure
│   │   ├── config.py            # Environment configurations (Supabase, Redis, Razorpay)
│   │   ├── database.py          # SQLAlchemy async session manager
│   │   └── security.py          # JWT validation & tenant context resolution
│   ├── modules/                 # Modular monolith business domains
│   │   ├── tenants/             # Tenant lifecycle, onboarding, subdomains & branding
│   │   ├── appointments/        # Booking lifecycle & double-booking prevention engine
│   │   ├── customers/           # CRM, loyalty points, visit histories, consent
│   │   ├── staff/               # Staff rosters, attendance & commission calculation
│   │   ├── pos/                 # Invoicing, payments, tax/GST calculation, split tender
│   │   ├── inventory/           # Stock movements, alerts, product ledger
│   │   ├── notifications/       # WhatsApp Cloud API, reminder triggers, templates
│   │   ├── ai_insights/         # Pattern detection, underbooked alerts, forecasting
│   │   └── subscriptions/       # Razorpay subscriptions, plan tiers & quotas
│   ├── workers/                 # Celery / ARQ worker for reminders & async jobs
│   └── main.py                  # FastAPI application entrypoint
```
