import json
import uuid
from typing import Optional, List, Dict, Any
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
    # Subscription & 7-Day Free Trial
    trial_started_at = Column(DateTime, default=datetime.utcnow)
    trial_ends_at = Column(DateTime, nullable=True)
    subscription_status = Column(String(32), default="trial") # 'trial', 'active', 'expired', 'suspended'
    subscription_plan = Column(String(64), default="free_trial")

    # Settlement Banking & Dynamic UPI (Per-Salon Configured Direct Payment)
    upi_id = Column(String(128), nullable=True)
    upi_payee_name = Column(String(128), nullable=True)
    upi_enabled = Column(Boolean, default=False)
    cash_enabled = Column(Boolean, default=True)
    payment_instructions = Column(Text, nullable=True)
    bank_account_name = Column(String(128), nullable=True)
    bank_account_number = Column(String(64), nullable=True)
    bank_ifsc = Column(String(32), nullable=True)
    bank_name = Column(String(128), nullable=True)

    # Meta WhatsApp Cloud API credentials
    whatsapp_phone_number_id = Column(String(128), nullable=True)
    whatsapp_waba_id = Column(String(128), nullable=True)
    whatsapp_access_token = Column(Text, nullable=True)
    whatsapp_display_number = Column(String(32), nullable=True)
    whatsapp_verified_name = Column(String(128), nullable=True)
    whatsapp_quality_rating = Column(String(32), default="GREEN")
    whatsapp_status = Column(String(32), default="not_connected")
    whatsapp_webhook_verified = Column(Boolean, default=False)
    whatsapp_last_tested_at = Column(DateTime, nullable=True)
    whatsapp_error_message = Column(Text, nullable=True)
    whatsapp_templates_status = Column(String(64), default="APPROVED (3 Active)")

    def is_trial_active(self) -> bool:
        if self.subscription_status == "active":
            return True
        if self.subscription_status == "trial" and self.trial_ends_at:
            return datetime.utcnow() <= self.trial_ends_at
        return False

    def trial_days_left(self) -> int:
        if not self.trial_ends_at:
            return 7
        delta = self.trial_ends_at - datetime.utcnow()
        return max(0, delta.days)

    def to_dict(self):
        is_active = self.is_trial_active()
        days_left = self.trial_days_left()

        def mask_token(t: Optional[str]) -> Optional[str]:
            if not t:
                return None
            if len(t) <= 10:
                return "••••••••"
            return f"{t[:4]}••••••••{t[-4:]}"

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
            "upiId": self.upi_id or "",
            "upiPayeeName": self.upi_payee_name or self.name,
            "upiEnabled": bool(self.upi_enabled and self.upi_id),
            "cashEnabled": self.cash_enabled if self.cash_enabled is not None else True,
            "paymentInstructions": self.payment_instructions or "",
            "paymentSettings": {
                "cashEnabled": self.cash_enabled if self.cash_enabled is not None else True,
                "upiEnabled": bool(self.upi_enabled and self.upi_id),
                "isUpiConfigured": bool(self.upi_id and self.upi_id.strip()),
                "upiId": self.upi_id or "",
                "upiPayeeName": self.upi_payee_name or self.name,
                "paymentInstructions": self.payment_instructions or "",
            },
            "bankAccountName": self.bank_account_name or self.name,
            "bankAccountNumber": self.bank_account_number or "",
            "bankIfsc": self.bank_ifsc or "",
            "bankName": self.bank_name or "",
            "trialStartedAt": self.trial_started_at.isoformat() if self.trial_started_at else None,
            "trialEndsAt": self.trial_ends_at.isoformat() if self.trial_ends_at else None,
            "subscriptionStatus": self.subscription_status or "trial",
            "subscriptionPlan": self.subscription_plan or "free_trial",
            "isTrialActive": is_active,
            "trialDaysLeft": days_left,
            "whatsapp": {
                "status": self.whatsapp_status or "not_connected",
                "displayNumber": self.whatsapp_display_number,
                "verifiedName": self.whatsapp_verified_name,
                "phoneNumberId": self.whatsapp_phone_number_id,
                "wabaId": self.whatsapp_waba_id,
                "qualityRating": self.whatsapp_quality_rating or "GREEN",
                "isConnected": bool(self.whatsapp_phone_number_id and self.whatsapp_access_token and self.whatsapp_status == "connected"),
                "isWebhookVerified": bool(self.whatsapp_webhook_verified),
                "lastTestedAt": self.whatsapp_last_tested_at.isoformat() if self.whatsapp_last_tested_at else None,
                "errorMessage": self.whatsapp_error_message,
                "templatesStatus": self.whatsapp_templates_status or "APPROVED (3 Active)",
                "maskedToken": mask_token(self.whatsapp_access_token),
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
    role = Column(String(32), default="SALON_MANAGER")
    avatar = Column(String(512), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        # Normalize role for API consumers
        normalized_role = self.role
        if normalized_role in ("owner", "manager", "SALON_MANAGER"):
            normalized_role = "SALON_MANAGER"
        elif normalized_role in ("receptionist", "SALON_RECEPTIONIST"):
            normalized_role = "SALON_RECEPTIONIST"

        return {
            "id": self.id,
            "salonId": self.salon_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "role": normalized_role,
            "avatar": self.avatar,
        }

class InvitationModel(Base):
    __tablename__ = "invitations"

    id = Column(String(64), primary_key=True, default=lambda: f"inv_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(128), nullable=False)
    role = Column(String(32), default="SALON_RECEPTIONIST")
    token = Column(String(128), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_accepted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "email": self.email,
            "role": self.role,
            "token": self.token,
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
            "isAccepted": self.is_accepted,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }

class OTPModel(Base):
    __tablename__ = "otps"

    id = Column(String(64), primary_key=True, default=lambda: f"otp_{uuid.uuid4().hex[:12]}")
    phone = Column(String(32), nullable=False, index=True)
    otp_hash = Column(String(256), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class BranchModel(Base):
    __tablename__ = "branches"

    id = Column(String(64), primary_key=True, default=lambda: f"brn_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    address = Column(String(255), default="")
    city = Column(String(64), default="")
    phone = Column(String(32), default="")
    email = Column(String(128), default="")
    chairs = Column(Integer, default=6)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "phone": self.phone,
            "email": self.email,
            "chairs": self.chairs,
            "isActive": self.is_active,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
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
    chair_number = Column(Integer, default=1)
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
            "chairNumber": self.chair_number,
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
    status = Column(String(32), default="paid") # 'paid', 'refunded', 'partially_paid', 'cancelled', 'pending'
    amount_received = Column(Float, default=0.0)
    change_given = Column(Float, default=0.0)
    verified_by_name = Column(String(128), nullable=True)
    verified_by_user_id = Column(String(64), nullable=True)
    payment_reference = Column(String(128), nullable=True)
    paid_at = Column(DateTime, nullable=True)
    refund_amount = Column(Float, default=0.0)
    refund_reason = Column(Text, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    points_redeemed = Column(Integer, default=0)
    points_discount = Column(Float, default=0.0)
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
            "paymentStatus": self.status,
            "amountReceived": self.amount_received or 0.0,
            "changeGiven": self.change_given or 0.0,
            "verifiedByName": self.verified_by_name,
            "verifiedByUserId": self.verified_by_user_id,
            "paymentReference": self.payment_reference,
            "paidAt": self.paid_at.isoformat() if self.paid_at else None,
            "refundAmount": self.refund_amount or 0.0,
            "refundReason": self.refund_reason,
            "refundedAt": self.refunded_at.isoformat() if self.refunded_at else None,
            "pointsRedeemed": self.points_redeemed or 0,
            "pointsDiscount": self.points_discount or 0.0,
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

class WhatsAppMessageModel(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(String(64), primary_key=True, default=lambda: f"wmsg_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_phone = Column(String(32), nullable=False)
    customer_name = Column(String(128), default="Valued Client")
    message_type = Column(String(64), nullable=False) # 'bill_receipt', 'appointment_confirmation', 'appointment_reminder', 'retention_campaign'
    template_name = Column(String(64), default="billcare_service_receipt")
    meta_message_id = Column(String(128), nullable=True, index=True)
    status = Column(String(32), default="sent") # 'sent', 'delivered', 'read', 'failed'
    idempotency_key = Column(String(128), nullable=True, index=True)
    error_details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "recipientPhone": self.recipient_phone,
            "customerName": self.customer_name,
            "messageType": self.message_type,
            "templateName": self.template_name,
            "metaMessageId": self.meta_message_id,
            "status": self.status,
            "idempotencyKey": self.idempotency_key,
            "errorDetails": self.error_details,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }

class CashRegisterShiftModel(Base):
    __tablename__ = "cash_register_shifts"

    id = Column(String(64), primary_key=True, default=lambda: f"shift_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False, index=True)
    opened_by_user_id = Column(String(64), nullable=True)
    opened_by_name = Column(String(128), default="Front Desk Cashier")
    closed_by_user_id = Column(String(64), nullable=True)
    closed_by_name = Column(String(128), nullable=True)
    opening_float = Column(Float, default=2000.0) # Starting cash in drawer
    cash_sales = Column(Float, default=0.0)
    upi_sales = Column(Float, default=0.0)
    card_sales = Column(Float, default=0.0)
    total_sales = Column(Float, default=0.0)
    expected_cash = Column(Float, default=2000.0) # opening_float + cash_sales
    counted_cash = Column(Float, nullable=True) # Actual counted cash at close
    cash_variance = Column(Float, default=0.0) # counted_cash - expected_cash
    status = Column(String(32), default="open") # 'open', 'closed'
    notes = Column(Text, default="")
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "openedByUserId": self.opened_by_user_id,
            "openedByName": self.opened_by_name,
            "closedByUserId": self.closed_by_user_id,
            "closedByName": self.closed_by_name,
            "openingFloat": self.opening_float,
            "cashSales": self.cash_sales,
            "upiSales": self.upi_sales,
            "cardSales": self.card_sales,
            "totalSales": self.total_sales,
            "expectedCash": self.expected_cash,
            "countedCash": self.counted_cash,
            "cashVariance": self.cash_variance,
            "status": self.status,
            "notes": self.notes,
            "openedAt": self.opened_at.isoformat() if self.opened_at else None,
            "closedAt": self.closed_at.isoformat() if self.closed_at else None,
        }

class ExpenseModel(Base):
    __tablename__ = "expenses"

    id = Column(String(64), primary_key=True, default=lambda: f"exp_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(128), nullable=False)
    category = Column(String(64), default="Supplies") # 'Supplies', 'Laundry', 'Refreshments', 'Utilities', 'Maintenance', 'Marketing'
    amount = Column(Float, nullable=False)
    payment_method = Column(String(32), default="Cash") # 'Cash', 'UPI', 'Bank Transfer'
    date = Column(String(32), default=lambda: datetime.utcnow().strftime("%Y-%m-%d"))
    recorded_by_name = Column(String(128), default="Salon Manager")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "title": self.title,
            "category": self.category,
            "amount": self.amount,
            "paymentMethod": self.payment_method,
            "date": self.date,
            "recordedByName": self.recorded_by_name,
            "notes": self.notes,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }

class InventoryLedgerModel(Base):
    __tablename__ = "inventory_ledger"

    id = Column(String(64), primary_key=True, default=lambda: f"ledg_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(String(64), ForeignKey("inventory.id", ondelete="CASCADE"), nullable=False)
    item_name = Column(String(128), nullable=False)
    change_qty = Column(Integer, nullable=False) # e.g. -2 for sale, +10 for restock, +2 for refund restock
    previous_stock = Column(Integer, default=0)
    new_stock = Column(Integer, default=0)
    reason = Column(String(128), default="sale") # 'sale', 'restock', 'refund_restock', 'adjustment', 'damage'
    performed_by = Column(String(128), default="POS System")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "itemId": self.item_id,
            "itemName": self.item_name,
            "changeQty": self.change_qty,
            "previousStock": self.previous_stock,
            "newStock": self.new_stock,
            "reason": self.reason,
            "performedBy": self.performed_by,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }

class PaymentModel(Base):
    __tablename__ = "payments"

    id = Column(String(64), primary_key=True, default=lambda: f"pay_{uuid.uuid4().hex[:12]}")
    salon_id = Column(String(64), ForeignKey("salons.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id = Column(String(64), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Float, nullable=False, default=0.0)
    currency = Column(String(10), default="INR")
    method = Column(String(32), nullable=False, default="CASH")  # 'CASH', 'UPI'
    status = Column(String(32), default="pending")  # 'pending', 'completed', 'failed', 'refunded'
    provider_ref_id = Column(String(255), nullable=True)  # Unique transaction reference (BC-TXN-...)
    verification_method = Column(String(64), default="manual_receptionist_verification")
    verified_by_user_id = Column(String(64), nullable=True)
    verified_by_name = Column(String(128), nullable=True)
    amount_received = Column(Float, default=0.0)
    change_given = Column(Float, default=0.0)
    upi_vpa_snapshot = Column(String(128), nullable=True)
    upi_payee_name_snapshot = Column(String(128), nullable=True)
    upi_uri_snapshot = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    audit_metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        audit_data = {}
        try:
            audit_data = json.loads(self.audit_metadata_json) if self.audit_metadata_json else {}
        except Exception:
            audit_data = {}
        return {
            "id": self.id,
            "salonId": self.salon_id,
            "invoiceId": self.invoice_id,
            "amount": self.amount,
            "currency": self.currency,
            "method": self.method,
            "paymentMethod": self.method,
            "status": self.status,
            "paymentStatus": self.status,
            "transactionReference": self.provider_ref_id,
            "providerRefId": self.provider_ref_id,
            "verificationMethod": self.verification_method,
            "verifiedByUserId": self.verified_by_user_id,
            "verifiedByName": self.verified_by_name,
            "amountReceived": self.amount_received,
            "changeGiven": self.change_given,
            "upiVpaSnapshot": self.upi_vpa_snapshot,
            "upiPayeeNameSnapshot": self.upi_payee_name_snapshot,
            "upiUriSnapshot": self.upi_uri_snapshot,
            "notes": self.notes,
            "auditMetadata": audit_data,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "confirmedAt": self.confirmed_at.isoformat() if self.confirmed_at else None,
        }

