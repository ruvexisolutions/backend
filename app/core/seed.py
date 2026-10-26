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
)

from .security import hash_password

DEFAULT_SALON_ID = "sln_billcare_flagship"

def seed_database(db: Session):
    # Ensure salon table has upi_id and bank details (Safe idempotent schema upgrade)
    try:
        from sqlalchemy import text
        for col, col_type in [
            ("upi_id", "VARCHAR(128) DEFAULT 'billcare.pos@icici'"),
            ("bank_account_name", "VARCHAR(128)"),
            ("bank_account_number", "VARCHAR(64)"),
            ("bank_ifsc", "VARCHAR(32)"),
            ("bank_name", "VARCHAR(128)"),
        ]:
            try:
                db.execute(text(f"ALTER TABLE salons ADD COLUMN {col} {col_type}"))
                db.commit()
            except Exception:
                db.rollback()
    except Exception:
        pass

    # Ensure flagship owner account has valid bcrypt hash for login
    owner_user = db.query(UserModel).filter(UserModel.email == "owner@billcare.io").first()
    if owner_user and (not owner_user.password_hash or not owner_user.password_hash.startswith("$2b$")):
        owner_user.password_hash = hash_password("billcare2026")
        db.commit()

    # Ensure manager account exists for role testing
    manager_user = db.query(UserModel).filter(UserModel.email == "manager@billcare.io").first()
    if not manager_user:
        manager_user = UserModel(
            id="usr_billcare_manager",
            salon_id=DEFAULT_SALON_ID,
            name="Kavita Rao",
            email="manager@billcare.io",
            phone="+91 98450 33445",
            role="manager",
            avatar="K",
            password_hash=hash_password("billcare2026"),
        )
        db.add(manager_user)
        db.commit()
    elif not manager_user.password_hash or not manager_user.password_hash.startswith("$2b$"):
        manager_user.password_hash = hash_password("billcare2026")
        db.commit()

    # Ensure receptionist account exists for role testing
    reception_user = db.query(UserModel).filter(UserModel.email == "reception@billcare.io").first()
    if not reception_user:
        reception_user = UserModel(
            id="usr_billcare_receptionist",
            salon_id=DEFAULT_SALON_ID,
            name="Ananya Sen",
            email="reception@billcare.io",
            phone="+91 98450 55667",
            role="receptionist",
            avatar="A",
            password_hash=hash_password("billcare2026"),
        )
        db.add(reception_user)
        db.commit()
    elif not reception_user.password_hash or not reception_user.password_hash.startswith("$2b$"):
        reception_user.password_hash = hash_password("billcare2026")
        db.commit()

    existing_salon = db.query(SalonModel).filter(SalonModel.id == DEFAULT_SALON_ID).first()
    if existing_salon:
        return

    print("Seeding initial BillCare flagship salon and operational data...")

    # 1. Salon
    salon = SalonModel(
        id=DEFAULT_SALON_ID,
        name="BillCare Premier Atelier & Spa",
        slug="billcare-atelier",
        branch="Flagship Studio",
        city="Mumbai & Bengaluru",
        currency="₹",
        chairs=8,
        category="Luxury Hair Studio & Aesthetic Spa",
        logo_url="/logo.png",
        logo="/logo.png",
        gstin="27AABCB1234F1Z8",
        auto_gst=True,
        phone="+91 98450 11223",
        email="hello@billcare.io",
        address="Suite 401, Crescent Galleria, Indiranagar",
        timing="10:00 AM - 09:00 PM (All Days)",
        rating=4.9,
        review_count=418,
    )
    db.add(salon)

    # 2. User (Owner)
    owner = UserModel(
        id="usr_billcare_owner",
        salon_id=DEFAULT_SALON_ID,
        name="Sunil Kumar",
        email="owner@billcare.io",
        phone="+91 98450 11223",
        role="owner",
        avatar="S",
        password_hash=hash_password("billcare2026"),
    )
    db.add(owner)

    # 3. Services
    services = [
        ServiceModel(
            id="srv_1",
            salon_id=DEFAULT_SALON_ID,
            category="Hair",
            name="Master Stylist Haircut & Blowdry",
            duration_minutes=45,
            buffer_minutes=5,
            price=1800,
            description="Consultation, deep detox wash, scalp stimulation & precision styling.",
            is_online_bookable=True,
            is_active=True,
            popular=True,
        ),
        ServiceModel(
            id="srv_2",
            salon_id=DEFAULT_SALON_ID,
            category="Hair",
            name="Balayage & Root Glaze Treatment",
            duration_minutes=150,
            buffer_minutes=10,
            price=8500,
            description="Custom French balayage technique with bond builder & gloss finish.",
            is_online_bookable=True,
            is_active=True,
            popular=True,
        ),
        ServiceModel(
            id="srv_3",
            salon_id=DEFAULT_SALON_ID,
            category="Spa",
            name="Aroma Hot Stone Deep Tissue Spa",
            duration_minutes=60,
            buffer_minutes=10,
            price=3200,
            description="Heated volcanic basalt stones with organic lavender & chamomile oils.",
            is_online_bookable=True,
            is_active=True,
            popular=False,
        ),
        ServiceModel(
            id="srv_4",
            salon_id=DEFAULT_SALON_ID,
            category="Skin",
            name="Hydra-Glow Medical Facial Therapy",
            duration_minutes=75,
            buffer_minutes=10,
            price=4500,
            description="Vacuum vortex suction pore cleansing, ultrasound infusion & LED photo light.",
            is_online_bookable=True,
            is_active=True,
            popular=True,
        ),
        ServiceModel(
            id="srv_5",
            salon_id=DEFAULT_SALON_ID,
            category="Nails",
            name="Gel Sculpting & Russian Manicure",
            duration_minutes=60,
            buffer_minutes=5,
            price=2400,
            description="E-file cuticle detail, gel builder apex alignment & 3-week high shine.",
            is_online_bookable=True,
            is_active=True,
            popular=False,
        ),
        ServiceModel(
            id="srv_6",
            salon_id=DEFAULT_SALON_ID,
            category="Grooming",
            name="Gentleman Executive Beard & Hair Sculpt",
            duration_minutes=50,
            buffer_minutes=5,
            price=1500,
            description="Razor fade, steam towel conditioning & cedarwood beard oil sculpting.",
            is_online_bookable=True,
            is_active=True,
            popular=True,
        ),
    ]
    for s in services:
        db.add(s)

    # 4. Staff
    staff_members = [
        StaffModel(
            id="stf_1",
            salon_id=DEFAULT_SALON_ID,
            name="Priya Sharma",
            phone="+91 98450 22331",
            email="priya@billcare.io",
            role="Creative Hair Director",
            commission_rate=20.0,
            is_clocked_in=True,
            clocked_in_at="09:45 AM",
            today_earnings=1850.0,
            today_commission=1850.0,
            today_revenue=9250.0,
            today_services_count=4,
            total_services_completed=680,
            is_active=True,
            avatar="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=150&auto=format&fit=crop&q=80",
            specialties_json=json.dumps(["Precision Cuts", "Balayage", "Bridal"]),
            status="clocked_in",
            rating=4.9,
        ),
        StaffModel(
            id="stf_2",
            salon_id=DEFAULT_SALON_ID,
            name="Kavita Rao",
            phone="+91 98450 33442",
            email="kavita@billcare.io",
            role="Senior Aesthetician & Spa Lead",
            commission_rate=18.0,
            is_clocked_in=True,
            clocked_in_at="10:05 AM",
            today_earnings=1420.0,
            today_commission=1420.0,
            today_revenue=7880.0,
            today_services_count=3,
            total_services_completed=512,
            is_active=True,
            avatar="https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150&auto=format&fit=crop&q=80",
            specialties_json=json.dumps(["Medical Facials", "Hot Stone", "Body Polish"]),
            status="clocked_in",
            rating=4.95,
        ),
        StaffModel(
            id="stf_3",
            salon_id=DEFAULT_SALON_ID,
            name="Rahul Verma",
            phone="+91 98450 44553",
            email="rahul@billcare.io",
            role="Master Barber & Colorist",
            commission_rate=15.0,
            is_clocked_in=True,
            clocked_in_at="10:15 AM",
            today_earnings=1120.0,
            today_commission=1120.0,
            today_revenue=7460.0,
            today_services_count=4,
            total_services_completed=440,
            is_active=True,
            avatar="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80",
            specialties_json=json.dumps(["Fade Master", "Beard Sculpting", "Grey Blending"]),
            status="clocked_in",
            rating=4.85,
        ),
        StaffModel(
            id="stf_4",
            salon_id=DEFAULT_SALON_ID,
            name="Sneha Kapoor",
            phone="+91 98450 55664",
            email="sneha@billcare.io",
            role="Nail Artist & Technician",
            commission_rate=15.0,
            is_clocked_in=False,
            clocked_in_at="",
            today_earnings=0.0,
            today_commission=0.0,
            today_revenue=0.0,
            today_services_count=0,
            total_services_completed=310,
            is_active=True,
            avatar="https://images.unsplash.com/photo-1580489944761-15a19d654956?w=150&auto=format&fit=crop&q=80",
            specialties_json=json.dumps(["Russian Manicure", "Nail Extensions", "Gel Art"]),
            status="clocked_out",
            rating=4.9,
        ),
    ]
    for st in staff_members:
        db.add(st)

    # 5. Inventory
    inventory_items = [
        InventoryModel(
            id="inv_1",
            salon_id=DEFAULT_SALON_ID,
            name="Olaplex No. 1 Bond Multiplier (525ml)",
            category="Back-Bar Chemical",
            sku="OLA-BOND-01",
            current_stock=4,
            min_threshold=5,
            cost_price=4800,
            selling_price=7200,
            retail_price=7200,
            brand="Olaplex Professional",
            usage_type="Salon Professional",
            unit="bottle",
            supplier="Olaplex India Official",
            last_restocked="2026-10-05",
        ),
        InventoryModel(
            id="inv_2",
            salon_id=DEFAULT_SALON_ID,
            name="L'Oréal Dia Light Gel-Cream Acidic Gloss 50ml",
            category="Hair Color",
            sku="LOR-DIA-901",
            current_stock=18,
            min_threshold=8,
            cost_price=420,
            selling_price=850,
            retail_price=850,
            brand="L'Oréal Professionnel",
            usage_type="Salon Professional",
            unit="tube",
            supplier="Metro Salon Logistics",
            last_restocked="2026-10-14",
        ),
        InventoryModel(
            id="inv_3",
            salon_id=DEFAULT_SALON_ID,
            name="Moroccanoil Treatment Original (100ml)",
            category="Retail Product",
            sku="MOR-OIL-100",
            current_stock=14,
            min_threshold=6,
            cost_price=2600,
            selling_price=3800,
            retail_price=3800,
            brand="Moroccanoil",
            usage_type="Retail Sale",
            unit="bottle",
            supplier="Global Beauty Brands",
            last_restocked="2026-10-18",
        ),
        InventoryModel(
            id="inv_4",
            salon_id=DEFAULT_SALON_ID,
            name="Kérastase Genesis Anti-Hair Fall Serum (90ml)",
            category="Retail Product",
            sku="KER-GEN-090",
            current_stock=3,
            min_threshold=5,
            cost_price=3300,
            selling_price=4900,
            retail_price=4900,
            brand="Kérastase Paris",
            usage_type="Retail Sale",
            unit="bottle",
            supplier="L'Oréal Luxury Div",
            last_restocked="2026-09-28",
        ),
    ]
    for item in inventory_items:
        db.add(item)

    # 6. Customers
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    customers = [
        CustomerModel(
            id="cst_1",
            salon_id=DEFAULT_SALON_ID,
            name="Ananya Deshmukh",
            phone="+91 98765 43210",
            email="ananya.d@gmail.com",
            gender="female",
            total_visits=12,
            visits_count=12,
            total_spend=48500,
            total_spent=48500,
            loyalty_points=485,
            last_visit_date="2026-10-18",
            tags_json=json.dumps(["VIP", "Balayage", "Retail Buyer"]),
            notes="Prefers oat milk cappuccino. Cold rinse for toner longevity.",
            last_service="Balayage & Root Glaze Treatment",
            preferred_staff="Priya Sharma",
            vip_tier="Platinum VIP",
            formula_notes="Dia Light 9.01 (30g) + 10.12 (10g) with 6 Vol on zone 2-3.",
            patch_test_status="Verified Safe",
            patch_test_date="2026-08-15",
            allergies="Slight sensitivity to ammonia",
            rebooking_cadence_days=28,
            created_at="2025-11-10",
        ),
        CustomerModel(
            id="cst_2",
            salon_id=DEFAULT_SALON_ID,
            name="Vikram Malhotra",
            phone="+91 98111 22334",
            email="v.malhotra@corp.in",
            gender="male",
            total_visits=8,
            visits_count=8,
            total_spend=16800,
            total_spent=16800,
            loyalty_points=168,
            last_visit_date="2026-10-15",
            tags_json=json.dumps(["Executive", "Regular"]),
            notes="Zero fade taper on sides. Matte clay finish.",
            last_service="Gentleman Executive Beard & Hair Sculpt",
            preferred_staff="Rahul Verma",
            vip_tier="Gold Member",
            formula_notes="Pre-shave sandalwood oil steam, straight razor finish.",
            patch_test_status="Verified Safe",
            patch_test_date="2026-06-01",
            allergies="None Reported",
            rebooking_cadence_days=21,
            created_at="2026-01-20",
        ),
        CustomerModel(
            id="cst_3",
            salon_id=DEFAULT_SALON_ID,
            name="Meera Krishnan",
            phone="+91 98222 33445",
            email="meera.k@studio.com",
            gender="female",
            total_visits=5,
            visits_count=5,
            total_spend=21500,
            total_spent=21500,
            loyalty_points=215,
            last_visit_date="2026-09-28",
            tags_json=json.dumps(["Spa", "HydraFacial"]),
            notes="Sensitive skin. Uses only botanical products.",
            last_service="Hydra-Glow Medical Facial Therapy",
            preferred_staff="Kavita Rao",
            vip_tier="Gold Member",
            formula_notes="Low suction mode on T-zone, hyaluronic infusion, red LED.",
            patch_test_status="Verified Safe",
            patch_test_date="2026-09-28",
            allergies="None Reported",
            rebooking_cadence_days=30,
            created_at="2026-04-12",
        ),
    ]
    for c in customers:
        db.add(c)

    # 7. Appointments
    appointments = [
        AppointmentModel(
            id="apt_1",
            salon_id=DEFAULT_SALON_ID,
            customer_id="cst_1",
            customer_name="Ananya Deshmukh",
            customer_phone="+91 98765 43210",
            staff_id="stf_1",
            staff_name="Priya Sharma",
            service_id="srv_2",
            service_name="Balayage & Root Glaze Treatment",
            date=today_str,
            start_time="10:30",
            end_time="13:00",
            time="10:30 AM",
            duration_minutes=150,
            price=8500,
            status="in_service",
            notes="Zone 2 gloss toner refresh with bond builder.",
        ),
        AppointmentModel(
            id="apt_2",
            salon_id=DEFAULT_SALON_ID,
            customer_id="cst_2",
            customer_name="Vikram Malhotra",
            customer_phone="+91 98111 22334",
            staff_id="stf_3",
            staff_name="Rahul Verma",
            service_id="srv_6",
            service_name="Gentleman Executive Beard & Hair Sculpt",
            date=today_str,
            start_time="12:00",
            end_time="12:50",
            time="12:00 PM",
            duration_minutes=50,
            price=1500,
            status="confirmed",
            notes="Razor sharp fade. Warm steam towel requested.",
        ),
        AppointmentModel(
            id="apt_3",
            salon_id=DEFAULT_SALON_ID,
            customer_id="cst_3",
            customer_name="Meera Krishnan",
            customer_phone="+91 98222 33445",
            staff_id="stf_2",
            staff_name="Kavita Rao",
            service_id="srv_4",
            service_name="Hydra-Glow Medical Facial Therapy",
            date=today_str,
            start_time="14:00",
            end_time="15:15",
            time="02:00 PM",
            duration_minutes=75,
            price=4500,
            status="confirmed",
            notes="Special treatment before evening gala.",
        ),
    ]
    for apt in appointments:
        db.add(apt)

    # 8. Invoices
    invoices = [
        InvoiceModel(
            id="inv_rec_1",
            invoice_number="BC-INV-2026-0104",
            salon_id=DEFAULT_SALON_ID,
            customer_id="cst_1",
            customer_name="Ananya Deshmukh",
            customer_phone="+91 98765 43210",
            staff_id="stf_1",
            staff_name="Priya Sharma",
            items_json=json.dumps([
                {
                    "type": "service",
                    "id": "srv_1",
                    "name": "Master Stylist Haircut & Blowdry",
                    "quantity": 1,
                    "unitPrice": 1800,
                    "price": 1800,
                    "total": 1800,
                    "staffId": "stf_1",
                    "staffName": "Priya Sharma",
                },
                {
                    "type": "product",
                    "id": "inv_3",
                    "name": "Moroccanoil Treatment Original (100ml)",
                    "quantity": 1,
                    "unitPrice": 3800,
                    "price": 3800,
                    "total": 3800,
                },
            ]),
            subtotal=5600,
            discount_percent=10,
            discount_amount=560,
            tax_percent=18,
            cgst=453.6,
            sgst=453.6,
            tax_amount=907.2,
            grand_total=5947.2,
            payment_method="UPI",
            status="paid",
            notes="Complimentary beverage served.",
            date="Today, 11:30 AM",
        ),
        InvoiceModel(
            id="inv_rec_2",
            invoice_number="BC-INV-2026-0103",
            salon_id=DEFAULT_SALON_ID,
            customer_id="cst_2",
            customer_name="Vikram Malhotra",
            customer_phone="+91 98111 22334",
            staff_id="stf_3",
            staff_name="Rahul Verma",
            items_json=json.dumps([
                {
                    "type": "service",
                    "id": "srv_6",
                    "name": "Gentleman Executive Beard & Hair Sculpt",
                    "quantity": 1,
                    "unitPrice": 1500,
                    "price": 1500,
                    "total": 1500,
                    "staffId": "stf_3",
                    "staffName": "Rahul Verma",
                }
            ]),
            subtotal=1500,
            discount_percent=0,
            discount_amount=0,
            tax_percent=18,
            cgst=135,
            sgst=135,
            tax_amount=270,
            grand_total=1770,
            payment_method="Card",
            status="paid",
            notes="Quick executive grooming session.",
            date="Today, 09:15 AM",
        ),
    ]
    for inv in invoices:
        db.add(inv)

    # 9. Followups
    followups = [
        FollowUpModel(
            id="flw_1",
            salon_id=DEFAULT_SALON_ID,
            customer_id="cst_1",
            customer_name="Ananya Deshmukh",
            customer_phone="+91 98765 43210",
            service_name="Balayage & Root Glaze Treatment",
            trigger_reason="28-Day Root Touch-Up Due",
            suggested_message="Hi Ananya! ✨ It has been 4 weeks since your signature Balayage at BillCare. We recommend a quick gloss refresher to maintain your luminous tone. Would you like to reserve Thursday at 3 PM?",
            status="pending",
            due_date=(datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%d"),
            campaign_type="Rebooking Reminder",
            discount_offer="Complimentary Deep Gloss Conditioning",
        ),
        FollowUpModel(
            id="flw_2",
            salon_id=DEFAULT_SALON_ID,
            customer_id="cst_3",
            customer_name="Meera Krishnan",
            customer_phone="+91 98222 33445",
            service_name="Hydra-Glow Medical Facial Therapy",
            trigger_reason="30-Day Skin Hydration Cycle",
            suggested_message="Hello Meera! Hope your skin is glowing after the Hydra-Glow treatment. Your next monthly session is due next week. Reply BOOK to claim your 10% loyalty VIP credit.",
            status="pending",
            due_date=(datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%d"),
            campaign_type="VIP Retention",
            discount_offer="10% Loyalty Bonus Credit",
        ),
    ]
    for flw in followups:
        db.add(flw)

    # 10. Feedbacks
    feedbacks = [
        FeedbackModel(
            id="fb_1",
            salon_id=DEFAULT_SALON_ID,
            customer_name="Ananya Deshmukh",
            staff_name="Priya Sharma",
            service_name="Balayage & Root Glaze Treatment",
            rating=5,
            comment="Priya is a master colorist. The toner formula she created matched my inspiration photo 100%!",
            date="Today, 1:15 PM",
            tags_json=json.dumps(["Flawless blend 🎨", "Prompt service ⚡", "Luxury feel ✨"]),
        ),
        FeedbackModel(
            id="fb_2",
            salon_id=DEFAULT_SALON_ID,
            customer_name="Vikram Malhotra",
            staff_name="Rahul Verma",
            service_name="Gentleman Executive Beard & Hair Sculpt",
            rating=5,
            comment="Best razor fade in town. Super hygienic chairs.",
            date="Yesterday, 6:00 PM",
            tags_json=json.dumps(["Sharp & precise styling ✂️", "Clean & hygienic chairs"]),
        ),
    ]
    for fb in feedbacks:
        db.add(fb)

    db.commit()
    print("Database seeding completed successfully!")
