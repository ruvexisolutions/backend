import json
import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
)
from .database import Base

class SalonModel(Base):
    __tablename__ = "salons"

    id = Column(String(64), primary_key=True, default=lambda: f"sln_{uuid.uuid4().hex[:12]}")
    name = Column(String(255), nullable=False)
    slug = Column(String(128), unique=True, index=True)
    branch = Column(String(128), default="Flagship Studio")
    city = Column(String(128), default="Mumbai & Bengaluru")
    currency = Column(String(10), default="₹")
    chairs = Column(Integer, default=8)
    category = Column(String(128), default="Luxury Hair Studio & Aesthetic Spa")
    logo_url = Column(String(512), default="/logo.png")
    logo = Column(String(512), default="/logo.png")
    gstin = Column(String(32), default="27AABCB1234F1Z8")
    auto_gst = Column(Boolean, default=True)
    phone = Column(String(32), default="+91 98450 11223")
    email = Column(String(128), default="hello@billcare.io")
    address = Column(String(255), default="Suite 401, Crescent Galleria, Indiranagar")
    timing = Column(String(128), default="10:00 AM - 09:00 PM (All Days)")
    rating = Column(Float, default=4.9)
    review_count = Column(Integer, default=418)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Salon UPI & Banking Settlement Details
    upi_id = Column(String(128), default="billcare.pos@icici")
    bank_account_name = Column(String(128), nullable=True)
    bank_account_number = Column(String(64), nullable=True)
    bank_ifsc = Column(String(32), nullable=True)
    bank_name = Column(String(128), nullable=True)

    # Meta WhatsApp Embedded Signup Credentials
    whatsapp_phone_number_id = Column(String(128), nullable=True)
    whatsapp_waba_id = Column(String(128), nullable=True)
    whatsapp_access_token = Column(Text, nullable=True)
    whatsapp_display_number = Column(String(32), nullable=True)
    whatsapp_verified_name = Column(String(255), nullable=True)
    whatsapp_quality_rating = Column(String(32), default="GREEN")
    whatsapp_status = Column(String(32), default="not_connected")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "branch": self.branch,
            "city": self.city,
            "currency": self.currency,
            "chairs": self.chairs,
            "category": self.category,
            "logoUrl": self.logo_url,
            "logo": self.logo or self.logo_url,
            "gstin": self.gstin,
            "autoGst": self.auto_gst,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "timing": self.timing,
            "rating": self.rating,
            "reviewCount": self.review_count,
            "upiId": self.upi_id or "billcare.pos@icici",
            "bankAccountName": self.bank_account_name or self.name,
            "bankAccountNumber": self.bank_account_number or "",
            "bankIfsc": self.bank_ifsc or "",
            "bankName": self.bank_name or "",
            "whatsapp": {
                "status": self.whatsapp_status or "not_connected",
                "displayNumber": self.whatsapp_display_number,
                "verifiedName": self.whatsapp_verified_name,
                "phoneNumberId": self.whatsapp_phone_number_id,
                "wabaId": self.whatsapp_waba_id,
                "qualityRating": self.whatsapp_quality_rating or "GREEN",
                "isConnected": bool(self.whatsapp_phone_number_id and self.whatsapp_access_token),
            }
        }

class UserModel(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=lambda: f"usr_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    email = Column(String(128), unique=True, index=True, nullable=False)
    phone = Column(String(32), default="")
    password_hash = Column(String(256), default="")
    role = Column(String(32), default="owner")
    avatar = Column(String(512), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "avatar": self.avatar,
        }

class CustomerModel(Base):
    __tablename__ = "customers"

    id = Column(String(64), primary_key=True, default=lambda: f"cst_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    phone = Column(String(32), nullable=False, index=True)
    email = Column(String(128), default="")
    gender = Column(String(32), default="female")
    birthday = Column(String(64), default="")
    total_visits = Column(Integer, default=0)
    visits_count = Column(Integer, default=0)
    total_spend = Column(Float, default=0.0)
    total_spent = Column(Float, default=0.0)
    loyalty_points = Column(Integer, default=50)
    last_visit_date = Column(String(64), default="")
    tags_json = Column(Text, default="[]")
    notes = Column(Text, default="")
    last_service = Column(String(128), default="")
    preferred_staff = Column(String(128), default="Priya Sharma")
    vip_tier = Column(String(64), default="Silver Member")
    formula_notes = Column(Text, default="")
    patch_test_status = Column(String(64), default="Verified Safe")
    patch_test_date = Column(String(64), default="")
    allergies = Column(String(255), default="None Reported")
    rebooking_cadence_days = Column(Integer, default=28)
    created_at = Column(String(64), default=lambda: datetime.utcnow().isoformat())

    def to_dict(self):
        tags = []
        try:
            tags = json.loads(self.tags_json) if self.tags_json else []
        except Exception:
            tags = []
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "gender": self.gender,
            "birthday": self.birthday,
            "totalVisits": self.total_visits,
            "visitsCount": self.visits_count or self.total_visits,
            "totalSpend": self.total_spend,
            "totalSpent": self.total_spent or self.total_spend,
            "loyaltyPoints": self.loyalty_points,
            "lastVisitDate": self.last_visit_date,
            "tags": tags,
            "notes": self.notes,
            "lastService": self.last_service,
            "preferredStaff": self.preferred_staff,
            "vipTier": self.vip_tier,
            "formulaNotes": self.formula_notes,
            "patchTestStatus": self.patch_test_status,
            "patchTestDate": self.patch_test_date,
            "allergies": self.allergies,
            "rebookingCadenceDays": self.rebooking_cadence_days,
            "createdAt": self.created_at,
        }

class ServiceModel(Base):
    __tablename__ = "services"

    id = Column(String(64), primary_key=True, default=lambda: f"srv_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(64), default="Hair")
    name = Column(String(128), nullable=False)
    duration_minutes = Column(Integer, default=45)
    buffer_minutes = Column(Integer, default=5)
    price = Column(Float, nullable=False)
    description = Column(Text, default="")
    is_online_bookable = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    popular = Column(Boolean, default=False)

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "category": self.category,
            "name": self.name,
            "durationMinutes": self.duration_minutes,
            "bufferMinutes": self.buffer_minutes,
            "price": self.price,
            "description": self.description,
            "isOnlineBookable": self.is_online_bookable,
            "isActive": self.is_active,
            "popular": self.popular,
        }

class StaffModel(Base):
    __tablename__ = "staff"

    id = Column(String(64), primary_key=True, default=lambda: f"stf_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    phone = Column(String(32), default="")
    email = Column(String(128), default="")
    role = Column(String(64), default="Senior Stylist")
    commission_rate = Column(Float, default=15.0)
    is_clocked_in = Column(Boolean, default=True)
    clocked_in_at = Column(String(64), default="")
    today_earnings = Column(Float, default=0.0)
    today_commission = Column(Float, default=0.0)
    today_revenue = Column(Float, default=0.0)
    today_services_count = Column(Integer, default=0)
    total_services_completed = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    avatar = Column(String(512), default="")
    specialties_json = Column(Text, default='["Hair Specialist"]')
    status = Column(String(32), default="clocked_in")
    rating = Column(Float, default=4.9)

    def to_dict(self):
        specialty = ["Hair Specialist"]
        try:
            specialty = json.loads(self.specialties_json) if self.specialties_json else ["Hair Specialist"]
        except Exception:
            specialty = ["Hair Specialist"]
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "role": self.role,
            "commissionRate": self.commission_rate,
            "isClockedIn": self.is_clocked_in,
            "clockedInAt": self.clocked_in_at,
            "todayEarnings": self.today_earnings,
            "todayCommission": self.today_commission,
            "todayRevenue": self.today_revenue,
            "todayServicesCount": self.today_services_count,
            "totalServicesCompleted": self.total_services_completed,
            "isActive": self.is_active,
            "avatar": self.avatar,
            "specialty": specialty,
            "status": self.status,
            "rating": self.rating,
        }

class InventoryModel(Base):
    __tablename__ = "inventory"

    id = Column(String(64), primary_key=True, default=lambda: f"inv_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    category = Column(String(64), default="Hair Care")
    sku = Column(String(64), unique=True, index=True)
    current_stock = Column(Integer, default=10)
    min_threshold = Column(Integer, default=5)
    cost_price = Column(Float, default=0.0)
    selling_price = Column(Float, default=0.0)
    retail_price = Column(Float, default=0.0)
    brand = Column(String(64), default="Salon Professional")
    usage_type = Column(String(64), default="Salon Professional")
    unit = Column(String(32), default="bottle")
    supplier = Column(String(128), default="Official Distributor")
    last_restocked = Column(String(64), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "name": self.name,
            "category": self.category,
            "sku": self.sku,
            "currentStock": self.current_stock,
            "minThreshold": self.min_threshold,
            "costPrice": self.cost_price,
            "sellingPrice": self.selling_price,
            "retailPrice": self.retail_price or self.selling_price,
            "brand": self.brand,
            "usageType": self.usage_type,
            "unit": self.unit,
            "supplier": self.supplier,
            "lastRestocked": self.last_restocked,
        }

class AppointmentModel(Base):
    __tablename__ = "appointments"

    id = Column(String(64), primary_key=True, default=lambda: f"apt_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(String(64), default="Flagship")
    customer_id = Column(String(64), nullable=False)
    customer_name = Column(String(128), nullable=False)
    customer_phone = Column(String(32), default="")
    staff_id = Column(String(64), default="")
    staff_name = Column(String(128), default="")
    service_id = Column(String(64), default="")
    service_name = Column(String(128), default="")
    date = Column(String(32), default="")
    start_time = Column(String(32), default="11:00")
    end_time = Column(String(32), default="11:45")
    time = Column(String(32), default="11:00 AM")
    duration_minutes = Column(Integer, default=45)
    price = Column(Float, default=0.0)
    status = Column(String(32), default="confirmed")
    source = Column(String(32), default="website")
    notes = Column(Text, default="")
    created_at = Column(String(64), default=lambda: datetime.utcnow().isoformat())

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "branchId": self.branch_id,
            "customerId": self.customer_id,
            "customerName": self.customer_name,
            "customerPhone": self.customer_phone,
            "staffId": self.staff_id,
            "staffName": self.staff_name,
            "serviceId": self.service_id,
            "serviceName": self.service_name,
            "date": self.date,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "time": self.time,
            "durationMinutes": self.duration_minutes,
            "price": self.price,
            "status": self.status,
            "source": self.source,
            "notes": self.notes,
            "createdAt": self.created_at,
        }

class InvoiceModel(Base):
    __tablename__ = "invoices"

    id = Column(String(64), primary_key=True, default=lambda: f"inv_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    invoice_number = Column(String(64), unique=True, index=True, nullable=False)
    customer_id = Column(String(64), default="cst_walkin")
    customer_name = Column(String(128), nullable=False)
    customer_phone = Column(String(32), default="")
    staff_id = Column(String(64), default="")
    staff_name = Column(String(128), default="")
    items_json = Column(Text, default="[]")
    subtotal = Column(Float, default=0.0)
    discount_percent = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    tax_percent = Column(Float, default=5.0)
    cgst = Column(Float, default=0.0)
    sgst = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    grand_total = Column(Float, default=0.0)
    payment_method = Column(String(32), default="UPI")
    payment_breakdown_json = Column(Text, default="{}")
    status = Column(String(32), default="paid")
    notes = Column(Text, default="")
    date = Column(String(64), default="")
    created_at = Column(String(64), default=lambda: datetime.utcnow().isoformat())

    def to_dict(self):
        items = []
        breakdown = {}
        try:
            items = json.loads(self.items_json) if self.items_json else []
        except Exception:
            items = []
        try:
            breakdown = json.loads(self.payment_breakdown_json) if self.payment_breakdown_json else {}
        except Exception:
            breakdown = {}
        return {
            "id": self.id,
            "invoiceNumber": self.invoice_number,
            "salonId": self.salon_id,
            "customerId": self.customer_id,
            "customerName": self.customer_name,
            "customerPhone": self.customer_phone,
            "staffId": self.staff_id,
            "staffName": self.staff_name,
            "items": items,
            "subtotal": self.subtotal,
            "discountPercent": self.discount_percent,
            "discountAmount": self.discount_amount,
            "discount": self.discount_amount,
            "taxPercent": self.tax_percent,
            "cgst": self.cgst,
            "sgst": self.sgst,
            "taxAmount": self.tax_amount,
            "gstAmount": self.tax_amount,
            "grandTotal": self.grand_total,
            "total": self.grand_total,
            "paymentMethod": self.payment_method,
            "paymentBreakdown": breakdown,
            "splitDetails": breakdown,
            "status": self.status,
            "notes": self.notes,
            "date": self.date,
            "createdAt": self.created_at,
        }

class FollowUpModel(Base):
    __tablename__ = "followups"

    id = Column(String(64), primary_key=True, default=lambda: f"flw_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(String(64), default="")
    customer_name = Column(String(128), default="")
    customer_phone = Column(String(32), default="")
    service_name = Column(String(128), default="")
    trigger_reason = Column(String(128), default="")
    suggested_message = Column(Text, default="")
    status = Column(String(32), default="pending")
    due_date = Column(String(32), default="")
    campaign_type = Column(String(64), default="Rebooking Reminder")
    discount_offer = Column(String(64), default="")
    created_at = Column(String(64), default=lambda: datetime.utcnow().isoformat())

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "customerId": self.customer_id,
            "customerName": self.customer_name,
            "customerPhone": self.customer_phone,
            "serviceName": self.service_name,
            "triggerReason": self.trigger_reason,
            "suggestedMessage": self.suggested_message,
            "status": self.status,
            "dueDate": self.due_date,
            "campaignType": self.campaign_type,
            "discountOffer": self.discount_offer,
            "createdAt": self.created_at,
        }

class FeedbackModel(Base):
    __tablename__ = "feedbacks"

    id = Column(String(64), primary_key=True, default=lambda: f"fb_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    customer_name = Column(String(128), nullable=False)
    staff_name = Column(String(128), default="")
    service_name = Column(String(128), default="")
    rating = Column(Integer, default=5)
    comment = Column(Text, default="")
    date = Column(String(64), default="")
    tags_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        tags = []
        try:
            tags = json.loads(self.tags_json) if self.tags_json else []
        except Exception:
            tags = []
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "customerName": self.customer_name,
            "staffName": self.staff_name,
            "serviceName": self.service_name,
            "rating": self.rating,
            "serviceRating": self.rating,
            "comment": self.comment,
            "date": self.date,
            "improvementTags": tags,
            "tags": tags,
        }
