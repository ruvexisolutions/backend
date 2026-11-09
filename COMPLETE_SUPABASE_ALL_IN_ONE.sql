-- ============================================================================
-- BILLCARE COMPLETE SAAS DATABASE SETUP (ALL-IN-ONE CONSOLIDATED SCRIPT)
-- Architecture: PostgreSQL 14+ / Supabase
-- Multi-Tenancy: Shared database with strict Row Level Security (RLS)
-- Includes: Extensions, All Tables, Schema Compatibility, Performance Indexes,
--           Security Policies (RLS), and Default Seed Data.
-- Safe to re-run multiple times (Fully Idempotent).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. EXTENSIONS
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ----------------------------------------------------------------------------
-- 2. TENANTS & MULTI-LOCATION BRANCHES
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS salons (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(128) UNIQUE NOT NULL,
    branch VARCHAR(128) DEFAULT 'Flagship Studio',
    city VARCHAR(100) NOT NULL,
    currency VARCHAR(10) DEFAULT '₹',
    chairs INT DEFAULT 6,
    category VARCHAR(128) DEFAULT 'Luxury Hair Studio & Aesthetic Spa',
    logo_url TEXT DEFAULT '/logo.png',
    gstin VARCHAR(32) DEFAULT '27AABCB1234F1Z8',
    auto_gst BOOLEAN DEFAULT TRUE,
    phone VARCHAR(32) NOT NULL,
    email VARCHAR(255) NOT NULL,
    address TEXT NOT NULL,
    timing VARCHAR(128) DEFAULT '10:00 AM - 09:00 PM (All Days)',
    rating NUMERIC(3, 2) DEFAULT 4.90,
    review_count INT DEFAULT 0,
    is_published BOOLEAN DEFAULT TRUE,
    upi_id VARCHAR(128),
    upi_payee_name VARCHAR(128),
    upi_enabled BOOLEAN DEFAULT FALSE,
    cash_enabled BOOLEAN DEFAULT TRUE,
    payment_instructions TEXT,
    bank_account_name VARCHAR(128),
    bank_account_number VARCHAR(64),
    bank_ifsc VARCHAR(32),
    bank_name VARCHAR(128),
    whatsapp_phone_number_id VARCHAR(128),
    whatsapp_waba_id VARCHAR(128),
    whatsapp_access_token TEXT,
    whatsapp_display_number VARCHAR(32),
    whatsapp_verified_name VARCHAR(255),
    whatsapp_quality_rating VARCHAR(32) DEFAULT 'GREEN',
    whatsapp_status VARCHAR(32) DEFAULT 'not_connected',
    whatsapp_webhook_verified BOOLEAN DEFAULT FALSE,
    whatsapp_last_tested_at TIMESTAMPTZ,
    whatsapp_error_message TEXT,
    whatsapp_templates_status VARCHAR(64) DEFAULT 'unverified',
    trial_started_at TIMESTAMPTZ DEFAULT NOW(),
    trial_ends_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days',
    subscription_status VARCHAR(32) DEFAULT 'trial',
    subscription_plan VARCHAR(32) DEFAULT 'free_trial',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS branches (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(32) NOT NULL,
    city VARCHAR(100) NOT NULL,
    address TEXT NOT NULL,
    phone VARCHAR(32),
    chairs_capacity INT DEFAULT 6,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(salon_id, code)
);

-- ----------------------------------------------------------------------------
-- 3. USERS, ROLES & ACCESS CONTROL (RBAC)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(32),
    role VARCHAR(32) NOT NULL CHECK (role IN ('SALON_MANAGER', 'SALON_RECEPTIONIST', 'owner', 'manager', 'receptionist', 'admin')),
    avatar TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invitations (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'SALON_RECEPTIONIST',
    token VARCHAR(128) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    is_accepted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS otps (
    id VARCHAR(64) PRIMARY KEY,
    phone VARCHAR(32) NOT NULL,
    otp_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INT DEFAULT 0,
    is_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 4. CRM & CLIENT INTELLIGENCE
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(32) NOT NULL,
    email VARCHAR(255),
    gender VARCHAR(16) DEFAULT 'female' CHECK (gender IN ('female', 'male', 'other', 'unspecified')),
    birthday DATE,
    anniversary DATE,
    vip_tier VARCHAR(32) DEFAULT 'Standard' CHECK (vip_tier IN ('Standard', 'Silver', 'Gold', 'Atelier Club', 'VIP Elite')),
    total_visits INT DEFAULT 0,
    visits_count INT DEFAULT 0,
    total_spend NUMERIC(12, 2) DEFAULT 0.00,
    total_spent NUMERIC(12, 2) DEFAULT 0.00,
    wallet_balance NUMERIC(12, 2) DEFAULT 0.00,
    loyalty_points INT DEFAULT 50,
    last_visit_date DATE,
    rebooking_cadence_days INT DEFAULT 28,
    tags JSONB DEFAULT '[]'::jsonb,
    notes TEXT,
    patch_test_status VARCHAR(32) DEFAULT 'verified' CHECK (patch_test_status IN ('verified', 'pending', 'expired', 'exempt')),
    patch_test_date DATE,
    allergies TEXT,
    preferred_staff_id VARCHAR(64),
    formula_notes TEXT,
    marketing_consent BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(salon_id, phone)
);

CREATE TABLE IF NOT EXISTS customer_formula_history (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    customer_id VARCHAR(64) NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    service_id VARCHAR(64),
    staff_id VARCHAR(64),
    formula_type VARCHAR(64) NOT NULL,
    formula_details TEXT NOT NULL,
    processing_time_mins INT,
    developer_volume VARCHAR(32),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 5. SERVICE CATALOG & PRICING MENU
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS service_categories (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS services (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    category VARCHAR(64) NOT NULL DEFAULT 'Hair',
    name VARCHAR(255) NOT NULL,
    duration_minutes INT NOT NULL DEFAULT 45,
    buffer_minutes INT NOT NULL DEFAULT 5,
    price NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    description TEXT,
    is_online_bookable BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    popular BOOLEAN DEFAULT FALSE,
    hsn_sac_code VARCHAR(32) DEFAULT '999721',
    material_used VARCHAR(256),
    material_item_id VARCHAR(64),
    material_quantity NUMERIC(10, 2) DEFAULT 0.00,
    material_unit VARCHAR(32) DEFAULT 'ml',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 6. STAFF ROSTER, ATTENDANCE & COMMISSIONS
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staff (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    user_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(32) NOT NULL,
    email VARCHAR(255),
    role VARCHAR(64) NOT NULL DEFAULT 'Master Stylist',
    commission_rate NUMERIC(5, 2) NOT NULL DEFAULT 15.00,
    is_clocked_in BOOLEAN DEFAULT FALSE,
    clocked_in_at VARCHAR(64),
    today_earnings NUMERIC(10, 2) DEFAULT 0.00,
    today_revenue NUMERIC(10, 2) DEFAULT 0.00,
    today_commission NUMERIC(10, 2) DEFAULT 0.00,
    today_services_count INT DEFAULT 0,
    total_services_completed INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    specialties JSONB DEFAULT '["Hair Specialist"]'::jsonb,
    avatar TEXT,
    rating NUMERIC(3, 2) DEFAULT 5.00,
    status VARCHAR(32) DEFAULT 'clocked_out' CHECK (status IN ('clocked_in', 'on_break', 'clocked_out')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staff_clock_logs (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    staff_id VARCHAR(64) NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    clock_action VARCHAR(32) NOT NULL CHECK (clock_action IN ('clock_in', 'clock_out', 'break_start', 'break_end')),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT
);

-- ----------------------------------------------------------------------------
-- 7. INVENTORY & RETAIL MERCHANDISING
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory_items (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(64) NOT NULL DEFAULT 'Retail Product',
    sku VARCHAR(64) NOT NULL,
    barcode VARCHAR(64),
    current_stock INT NOT NULL DEFAULT 0,
    min_threshold INT NOT NULL DEFAULT 5,
    cost_price NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    selling_price NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    retail_price NUMERIC(10, 2) DEFAULT 0.00,
    brand VARCHAR(128),
    unit VARCHAR(32) DEFAULT 'unit',
    usage_type VARCHAR(32) DEFAULT 'Retail Product' CHECK (usage_type IN ('Retail Product', 'Back-Bar Chemical', 'Skin Spa Retail', 'Consumable')),
    supplier VARCHAR(255) DEFAULT 'Official Distributor',
    last_restocked DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(salon_id, sku)
);

CREATE TABLE IF NOT EXISTS inventory_stock_ledger (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    item_id VARCHAR(64) NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    quantity_change INT NOT NULL,
    previous_stock INT NOT NULL,
    resulting_stock INT NOT NULL,
    reason VARCHAR(128) NOT NULL,
    invoice_id VARCHAR(64),
    performed_by VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inventory_ledger (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    item_id VARCHAR(64) NOT NULL,
    item_name VARCHAR(128) NOT NULL,
    change_qty INT NOT NULL,
    previous_stock INT DEFAULT 0,
    new_stock INT DEFAULT 0,
    reason VARCHAR(128) DEFAULT 'sale',
    performed_by VARCHAR(128) DEFAULT 'POS System',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 8. APPOINTMENTS & REAL-TIME SCHEDULING
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appointments (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    branch_id VARCHAR(64) DEFAULT 'Flagship',
    customer_id VARCHAR(64) NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    customer_name VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(32) NOT NULL,
    staff_id VARCHAR(64) NOT NULL REFERENCES staff(id) ON DELETE RESTRICT,
    staff_name VARCHAR(255) NOT NULL,
    service_id VARCHAR(64) NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    service_name VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    start_time VARCHAR(16) NOT NULL,
    end_time VARCHAR(16) NOT NULL,
    time VARCHAR(32) NOT NULL,
    duration_minutes INT NOT NULL DEFAULT 45,
    price NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    status VARCHAR(32) NOT NULL DEFAULT 'confirmed'
        CHECK (status IN ('scheduled', 'confirmed', 'arrived', 'in_service', 'completed', 'cancelled', 'no_show')),
    source VARCHAR(32) DEFAULT 'website' CHECK (source IN ('website', 'walk_in', 'front_desk', 'phone', 'google')),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 9. POS BILLING, INVOICES & INDIAN GST COMPLIANCE
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoices (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    invoice_number VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64) REFERENCES customers(id) ON DELETE SET NULL,
    customer_name VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(32) NOT NULL,
    staff_id VARCHAR(64) REFERENCES staff(id) ON DELETE SET NULL,
    staff_name VARCHAR(255),
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
    subtotal NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    discount_percent NUMERIC(5, 2) DEFAULT 0.00,
    discount_amount NUMERIC(10, 2) DEFAULT 0.00,
    tax_percent NUMERIC(5, 2) DEFAULT 18.00,
    cgst NUMERIC(10, 2) DEFAULT 0.00,
    sgst NUMERIC(10, 2) DEFAULT 0.00,
    tax_amount NUMERIC(10, 2) DEFAULT 0.00,
    grand_total NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    payment_method VARCHAR(32) NOT NULL DEFAULT 'UPI',
    payment_breakdown JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'paid' CHECK (status IN ('paid', 'draft', 'pending', 'refunded', 'voided')),
    amount_received NUMERIC(10, 2) DEFAULT 0.00,
    change_given NUMERIC(10, 2) DEFAULT 0.00,
    verified_by_name VARCHAR(128),
    verified_by_user_id VARCHAR(64),
    payment_reference VARCHAR(128),
    paid_at TIMESTAMPTZ,
    notes TEXT,
    date VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(salon_id, invoice_number)
);

CREATE TABLE IF NOT EXISTS payments (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    invoice_id VARCHAR(64) NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'INR',
    method VARCHAR(32) NOT NULL,
    status VARCHAR(32) DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
    provider_ref_id VARCHAR(255),
    verification_method VARCHAR(64) DEFAULT 'manual_receptionist_verification',
    verified_by_user_id VARCHAR(64),
    verified_by_name VARCHAR(128),
    amount_received NUMERIC(10, 2) DEFAULT 0.00,
    change_given NUMERIC(10, 2) DEFAULT 0.00,
    upi_vpa_snapshot VARCHAR(128),
    upi_payee_name_snapshot VARCHAR(128),
    upi_uri_snapshot TEXT,
    notes TEXT,
    audit_metadata_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);

-- ----------------------------------------------------------------------------
-- 10. RECEPTIONIST FRONT DESK: SHIFT CASH DRAWER & EXPENSES
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cash_register_shifts (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    opened_by_user_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    opened_by_name VARCHAR(128) DEFAULT 'Front Desk Cashier',
    closed_by_user_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    closed_by_name VARCHAR(128),
    opening_float NUMERIC(10, 2) DEFAULT 2000.00,
    cash_sales NUMERIC(10, 2) DEFAULT 0.00,
    upi_sales NUMERIC(10, 2) DEFAULT 0.00,
    card_sales NUMERIC(10, 2) DEFAULT 0.00,
    total_sales NUMERIC(10, 2) DEFAULT 0.00,
    expected_cash NUMERIC(10, 2) DEFAULT 2000.00,
    counted_cash NUMERIC(10, 2),
    cash_variance NUMERIC(10, 2) DEFAULT 0.00,
    status VARCHAR(32) DEFAULT 'open',
    notes TEXT DEFAULT '',
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS expenses (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    title VARCHAR(128) NOT NULL,
    category VARCHAR(64) DEFAULT 'Supplies',
    amount NUMERIC(10, 2) NOT NULL,
    payment_method VARCHAR(32) DEFAULT 'Cash',
    date VARCHAR(32),
    recorded_by_name VARCHAR(128) DEFAULT 'Salon Manager',
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 11. MARKETING, REPUTATION & AUDIT LOGS
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS followups (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    customer_id VARCHAR(64) NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    customer_name VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(32) NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    trigger_reason VARCHAR(255) NOT NULL,
    suggested_message TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'dismissed', 'booked')),
    due_date DATE NOT NULL,
    campaign_type VARCHAR(64) DEFAULT 'Rebooking Reminder',
    discount_offer VARCHAR(128),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    customer_name VARCHAR(255) NOT NULL,
    staff_name VARCHAR(255) NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    service_rating INT CHECK (service_rating BETWEEN 1 AND 5),
    comment TEXT,
    improvement_tags TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    date VARCHAR(64) NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    user_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(128) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(64),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id VARCHAR(64) PRIMARY KEY,
    salon_id VARCHAR(64) NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    recipient_phone VARCHAR(32) NOT NULL,
    customer_name VARCHAR(255),
    message_type VARCHAR(64) NOT NULL,
    template_name VARCHAR(128),
    meta_message_id VARCHAR(128),
    status VARCHAR(32) DEFAULT 'pending',
    idempotency_key VARCHAR(128),
    error_details TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 12. AUTOMATIC COLUMN UPGRADES (In case tables were created in earlier runs)
-- ----------------------------------------------------------------------------
ALTER TABLE salons ADD COLUMN IF NOT EXISTS logo VARCHAR(512) DEFAULT '/logo.png';
ALTER TABLE salons ADD COLUMN IF NOT EXISTS logo_url TEXT DEFAULT '/logo.png';
ALTER TABLE salons ADD COLUMN IF NOT EXISTS upi_id VARCHAR(128);
ALTER TABLE salons ADD COLUMN IF NOT EXISTS upi_payee_name VARCHAR(128);
ALTER TABLE salons ADD COLUMN IF NOT EXISTS upi_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE salons ADD COLUMN IF NOT EXISTS cash_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE salons ADD COLUMN IF NOT EXISTS payment_instructions TEXT;
ALTER TABLE salons ADD COLUMN IF NOT EXISTS bank_account_name VARCHAR(128);
ALTER TABLE salons ADD COLUMN IF NOT EXISTS bank_account_number VARCHAR(64);
ALTER TABLE salons ADD COLUMN IF NOT EXISTS bank_ifsc VARCHAR(32);
ALTER TABLE salons ADD COLUMN IF NOT EXISTS bank_name VARCHAR(128);
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_phone_number_id VARCHAR(128);
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_waba_id VARCHAR(128);
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_access_token TEXT;
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_display_number VARCHAR(32);
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_verified_name VARCHAR(255);
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_quality_rating VARCHAR(32) DEFAULT 'GREEN';
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_status VARCHAR(32) DEFAULT 'not_connected';
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_webhook_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_last_tested_at TIMESTAMPTZ;
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_error_message TEXT;
ALTER TABLE salons ADD COLUMN IF NOT EXISTS whatsapp_templates_status VARCHAR(64) DEFAULT 'unverified';
ALTER TABLE salons ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE salons ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days';
ALTER TABLE salons ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(32) DEFAULT 'trial';
ALTER TABLE salons ADD COLUMN IF NOT EXISTS subscription_plan VARCHAR(32) DEFAULT 'free_trial';

ALTER TABLE customers ADD COLUMN IF NOT EXISTS wallet_balance NUMERIC(12, 2) DEFAULT 0.00;

ALTER TABLE services ADD COLUMN IF NOT EXISTS material_used VARCHAR(256);
ALTER TABLE services ADD COLUMN IF NOT EXISTS material_item_id VARCHAR(64);
ALTER TABLE services ADD COLUMN IF NOT EXISTS material_quantity NUMERIC(10, 2) DEFAULT 0.00;
ALTER TABLE services ADD COLUMN IF NOT EXISTS material_unit VARCHAR(32) DEFAULT 'ml';

ALTER TABLE invoices ADD COLUMN IF NOT EXISTS upi_vpa_snapshot VARCHAR(128);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS upi_payee_name_snapshot VARCHAR(128);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS upi_uri_snapshot TEXT;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS cash_tendered NUMERIC(12, 2) DEFAULT 0.00;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS change_returned NUMERIC(12, 2) DEFAULT 0.00;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS amount_received NUMERIC(12, 2) DEFAULT 0.00;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS change_given NUMERIC(12, 2) DEFAULT 0.00;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS verified_by_name VARCHAR(128);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS verified_by_user_id VARCHAR(64);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS payment_reference VARCHAR(128);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS refund_amount NUMERIC(12, 2) DEFAULT 0.00;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS refund_reason TEXT;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMPTZ;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS points_redeemed INT DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS points_discount NUMERIC(12, 2) DEFAULT 0.00;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS split_payments JSONB;

-- ----------------------------------------------------------------------------
-- 13. INDEXES FOR ULTRA-FAST LOOKUPS & POS QUERIES
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_customers_salon_phone ON customers(salon_id, phone);
CREATE INDEX IF NOT EXISTS idx_customers_vip_tier ON customers(salon_id, vip_tier);
CREATE INDEX IF NOT EXISTS idx_services_salon_active ON services(salon_id, is_active, is_online_bookable);
CREATE INDEX IF NOT EXISTS idx_staff_salon_status ON staff(salon_id, is_active, status);
CREATE INDEX IF NOT EXISTS idx_inventory_salon_sku ON inventory_items(salon_id, sku);
CREATE INDEX IF NOT EXISTS idx_appointments_salon_date ON appointments(salon_id, date, status);
CREATE INDEX IF NOT EXISTS idx_appointments_staff_date ON appointments(staff_id, date);
CREATE INDEX IF NOT EXISTS idx_invoices_salon_date ON invoices(salon_id, created_at);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_followups_salon_due ON followups(salon_id, due_date, status);
CREATE INDEX IF NOT EXISTS idx_whatsapp_salon_status ON whatsapp_messages(salon_id, status);

-- ----------------------------------------------------------------------------
-- 14. MULTI-TENANT CONTEXT RESOLVER
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_current_tenant_id()
RETURNS VARCHAR(64) AS $$
BEGIN
    RETURN COALESCE(
        current_setting('request.jwt.claims', true)::jsonb->>'salon_id',
        current_setting('app.current_salon_id', true)
    );
END;
$$ LANGUAGE plpgsql STABLE;

-- ----------------------------------------------------------------------------
-- 15. ROW LEVEL SECURITY (RLS) POLICIES (IDEMPOTENT OVERRIDES)
-- ----------------------------------------------------------------------------
ALTER TABLE salons ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Tenant isolation for salons" ON salons;
DROP POLICY IF EXISTS tenant_isolation_salons ON salons;
CREATE POLICY tenant_isolation_salons ON salons FOR ALL USING (id = get_current_tenant_id());

ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Tenant isolation for customers" ON customers;
DROP POLICY IF EXISTS tenant_isolation_customers ON customers;
CREATE POLICY tenant_isolation_customers ON customers FOR ALL USING (salon_id = get_current_tenant_id());

ALTER TABLE services ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Tenant isolation for services" ON services;
DROP POLICY IF EXISTS tenant_isolation_services ON services;
CREATE POLICY tenant_isolation_services ON services FOR ALL USING (salon_id = get_current_tenant_id());

ALTER TABLE staff ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Tenant isolation for staff" ON staff;
DROP POLICY IF EXISTS tenant_isolation_staff ON staff;
CREATE POLICY tenant_isolation_staff ON staff FOR ALL USING (salon_id = get_current_tenant_id());

ALTER TABLE inventory_items ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_inventory ON inventory_items;
CREATE POLICY tenant_isolation_inventory ON inventory_items FOR ALL USING (salon_id = get_current_tenant_id());

ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Tenant isolation for appointments" ON appointments;
DROP POLICY IF EXISTS tenant_isolation_appointments ON appointments;
CREATE POLICY tenant_isolation_appointments ON appointments FOR ALL USING (salon_id = get_current_tenant_id());

ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Tenant isolation for invoices" ON invoices;
DROP POLICY IF EXISTS tenant_isolation_invoices ON invoices;
CREATE POLICY tenant_isolation_invoices ON invoices FOR ALL USING (salon_id = get_current_tenant_id());

ALTER TABLE cash_register_shifts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Tenant isolation for cash_register_shifts" ON cash_register_shifts;
DROP POLICY IF EXISTS tenant_isolation_cash_register_shifts ON cash_register_shifts;
CREATE POLICY tenant_isolation_cash_register_shifts ON cash_register_shifts FOR ALL USING (salon_id = get_current_tenant_id());

ALTER TABLE expenses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Tenant isolation for expenses" ON expenses;
DROP POLICY IF EXISTS tenant_isolation_expenses ON expenses;
CREATE POLICY tenant_isolation_expenses ON expenses FOR ALL USING (salon_id = get_current_tenant_id());

ALTER TABLE inventory_ledger ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Tenant isolation for inventory_ledger" ON inventory_ledger;
DROP POLICY IF EXISTS tenant_isolation_inventory_ledger ON inventory_ledger;
CREATE POLICY tenant_isolation_inventory_ledger ON inventory_ledger FOR ALL USING (salon_id = get_current_tenant_id());

-- Public Service Catalog for online booking widget
DROP POLICY IF EXISTS "Public read for published services" ON services;
DROP POLICY IF EXISTS public_services_read ON services;
CREATE POLICY public_services_read ON services FOR SELECT USING (is_active = TRUE AND is_online_bookable = TRUE);

-- ----------------------------------------------------------------------------
-- 16. CLEAN PRODUCTION DATABASE (No Default Dummy Salon)
-- Real salons will be dynamically registered when managers sign up.
-- ----------------------------------------------------------------------------
-- To remove any previously seeded default salon, run:
-- DELETE FROM salons WHERE id = 'salon_flagship_01';

