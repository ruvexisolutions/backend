# RUVEXI Backend API (`backend`)

Multi-tenant backend engine built with **FastAPI** following the **Modular Monolith** architecture pattern recommended in the RUVEXI PRD (Section 6).

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
├── tests/
│   ├── functional/              # End-to-end booking, checkout, and inventory tests
│   └── tenant_isolation/       # Critical tests ensuring Salon A cannot access Salon B
├── Dockerfile                   # Production deployment for Railway
└── requirements.txt
```

---

## 🔒 Multi-Tenant Security Principle (PRD Section 5.1 - 5.3)
> **"Never trust a salon_id supplied by the frontend as proof of access."**
- Every authenticated request extracts the user's verified `user_id` from Supabase Auth JWT.
- The user's active `salon_id` and role permissions are resolved strictly server-side.
- All database queries enforce tenant scoping (`WHERE salon_id = :salon_id`).
