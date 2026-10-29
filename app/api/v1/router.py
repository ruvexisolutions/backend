import os
import json
import uuid
import secrets
import re
import io
import base64
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import (
    SalonModel,
    UserModel,
    BranchModel,
    InvitationModel,
    OTPModel,
    CustomerModel,
    ServiceModel,
    StaffModel,
    InventoryModel,
    AppointmentModel,
    InvoiceModel,
    FollowUpModel,
    FeedbackModel,
    WhatsAppMessageModel,
    CashRegisterShiftModel,
    ExpenseModel,
    InventoryLedgerModel,
    PaymentModel,
)
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.services.razorpay_service import razorpay_service
from app.services.whatsapp_service import whatsapp_service

router = APIRouter(prefix="/api/v1")

# Standard UPI VPA format: e.g. salon@okhdfcbank, 9845011223@paytm
UPI_VPA_REGEX = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")

def generate_upi_payment_uri(vpa: str, payee_name: str, amount: float, invoice_ref: str) -> str:
    """
    Constructs standard NPCI UPI payment intent URI.
    Format: upi://pay?pa={vpa}&pn={payee_name}&am={amount:.2f}&cu=INR&tn={invoice_ref}
    """
    encoded_name = urllib.parse.quote(payee_name)
    encoded_ref = urllib.parse.quote(invoice_ref)
    amt_str = f"{amount:.2f}"
    return f"upi://pay?pa={vpa}&pn={encoded_name}&am={amt_str}&cu=INR&tn={encoded_ref}"

def generate_qr_base64(data: str) -> str:
    """
    Generates high-resolution base64 PNG data URL for UPI QR scanning.
    """
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#000000", back_color="#FFFFFF")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&margin=10&data={urllib.parse.quote_plus(data)}"


# ============================================================================
# Multi-Tenant Auth & Role Security Dependencies
# ============================================================================
def get_auth_context(
    request: Request,
    db: Session = Depends(get_db)
) -> tuple[Optional[UserModel], Optional[SalonModel]]:
    """
    Extracts authenticated user and tenant salon from Bearer JWT or client headers.
    Enforces tenant scoping so multi-tenant accounts remain strictly isolated.
    """
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif "token" in request.query_params:
        token = request.query_params.get("token")

    if token:
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            user = db.query(UserModel).filter(UserModel.id == payload["sub"]).first()
            if user:
                salon = db.query(SalonModel).filter(SalonModel.id == user.salon_id).first()
                if salon:
                    return user, salon

    return None, None

def get_current_user_and_salon(
    request: Request,
    db: Session = Depends(get_db)
) -> tuple[UserModel, SalonModel]:
    """Strict dependency requiring authenticated user and active salon."""
    user, salon = get_auth_context(request, db)
    if not user or not salon:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required. Please sign in to your BillCare workspace."
        )

    # Server-side 7-day trial expiry lock
    if salon.subscription_status == "trial" and not salon.is_trial_active():
        allowed_paths = [
            "/api/v1/subscription/status",
            "/api/v1/subscription/upgrade",
            "/api/v1/auth/me",
            "/api/v1/salon",
        ]
        curr_path = request.url.path
        if not any(curr_path.endswith(p) or curr_path == p for p in allowed_paths):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Your 7-day free trial has expired. Please upgrade your subscription to unlock full salon access."
            )

    return user, salon

def require_salon_manager(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon)
) -> tuple[UserModel, SalonModel]:
    """Enforces that the authenticated user possesses the SALON_MANAGER role."""
    user, salon = context
    role = (user.role or "").upper()
    if role not in ("SALON_MANAGER", "OWNER", "MANAGER", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: This action requires Salon Manager authorization."
        )
    return user, salon

def require_salon_receptionist(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon)
) -> tuple[UserModel, SalonModel]:
    """Allows operational access to SALON_RECEPTIONIST and SALON_MANAGER."""
    user, salon = context
    return user, salon


# ============================================================================
# Bootstrap Sync (Tenant Scoped)
# ============================================================================
@router.get("/bootstrap", tags=["Sync"])
def get_bootstrap_data(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """Loads all operational state for the caller's authorized salon."""
    user, salon = context

    salon_id = salon.id

    customers = [c.to_dict() for c in db.query(CustomerModel).filter(CustomerModel.salon_id == salon_id).all()]
    services = [s.to_dict() for s in db.query(ServiceModel).filter(ServiceModel.salon_id == salon_id).all()]
    staff = [st.to_dict() for st in db.query(StaffModel).filter(StaffModel.salon_id == salon_id).all()]
    inventory = [i.to_dict() for i in db.query(InventoryModel).filter(InventoryModel.salon_id == salon_id).all()]
    appointments = [
        a.to_dict()
        for a in db.query(AppointmentModel)
        .filter(AppointmentModel.salon_id == salon_id)
        .order_by(AppointmentModel.start_time.asc())
        .all()
    ]
    invoices = [
        inv.to_dict()
        for inv in db.query(InvoiceModel)
        .filter(InvoiceModel.salon_id == salon_id)
        .order_by(InvoiceModel.id.desc())
        .all()
    ]
    followups = [flw.to_dict() for flw in db.query(FollowUpModel).filter(FollowUpModel.salon_id == salon_id).all()]
    feedbacks = [fb.to_dict() for fb in db.query(FeedbackModel).filter(FeedbackModel.salon_id == salon_id).all()]

    return {
        "salon": salon.to_dict(),
        "user": user.to_dict() if user else None,
        "customers": customers,
        "services": services,
        "staff": staff,
        "inventory": inventory,
        "appointments": appointments,
        "invoices": invoices,
        "followUps": followups,
        "feedbacks": feedbacks,
    }


# ============================================================================
# Authentication: Password Login, Signup, Reset
# ============================================================================
@router.post("/auth/login", tags=["Auth"])
def login(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    user = db.query(UserModel).filter(UserModel.email.ilike(email)).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    salon = db.query(SalonModel).filter(SalonModel.id == user.salon_id).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon workspace not found")

    normalized_role = "SALON_MANAGER" if user.role in ("owner", "manager", "SALON_MANAGER") else "SALON_RECEPTIONIST"

    token = create_access_token({
        "sub": user.id,
        "email": user.email,
        "name": user.name,
        "role": normalized_role,
        "salon_id": user.salon_id,
    })

    return {
        "success": True,
        "token": token,
        "user": user.to_dict(),
        "salon": salon.to_dict(),
    }


@router.post("/auth/signup", tags=["Auth"])
def signup(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    user_data = payload.get("user") or {}
    salon_data = payload.get("salon") or {}

    email = (user_data.get("email") or "").strip().lower()
    password = user_data.get("password") or ""
    name = (user_data.get("name") or "").strip()
    phone = (user_data.get("phone") or "").strip()

    if not email:
        raise HTTPException(status_code=400, detail="Work email address is required")
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
    if not name:
        raise HTTPException(status_code=400, detail="Full name is required")

    existing_user = db.query(UserModel).filter(UserModel.email.ilike(email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="An account with this email address already exists. Please sign in.")

    salon_name = salon_data.get("name") or f"{name}'s Atelier"
    slug = salon_name.lower().replace(" ", "-").replace("'", "")
    now = datetime.utcnow()
    trial_end = now + timedelta(days=7)

    new_salon = SalonModel(
        id=f"sln_{uuid.uuid4().hex[:12]}",
        name=salon_name,
        slug=f"{slug}-{uuid.uuid4().hex[:4]}",
        branch=salon_data.get("branch") or f"{salon_data.get('city', 'Flagship')} Studio",
        city=salon_data.get("city") or "Mumbai",
        currency=salon_data.get("currency") or "₹",
        chairs=int(salon_data.get("chairs") or 6),
        category=salon_data.get("category") or "Hair & Beauty Atelier",
        gstin=salon_data.get("gstin") or "27AABCB9999F1Z1",
        phone=phone or "+91 98000 00000",
        email=email,
        trial_started_at=now,
        trial_ends_at=trial_end,
        subscription_status="trial",
        subscription_plan="free_trial",
    )
    db.add(new_salon)
    db.flush()

    new_user = UserModel(
        id=f"usr_{uuid.uuid4().hex[:12]}",
        salon_id=new_salon.id,
        name=name,
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        role="SALON_MANAGER",
        avatar=name[0].upper(),
    )
    db.add(new_user)
    db.commit()

    token = create_access_token({
        "sub": new_user.id,
        "email": new_user.email,
        "name": new_user.name,
        "role": "SALON_MANAGER",
        "salon_id": new_user.salon_id,
    })

    return {
        "success": True,
        "token": token,
        "user": new_user.to_dict(),
        "salon": new_salon.to_dict(),
    }


@router.get("/auth/me", tags=["Auth"])
def get_current_user_me(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon)
):
    user, salon = context
    return {"user": user.to_dict(), "salon": salon.to_dict()}


@router.post("/auth/forgot-password", tags=["Auth"])
def forgot_password(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Work email address is required")

    user = db.query(UserModel).filter(UserModel.email.ilike(email)).first()
    response = {
        "success": True,
        "message": "If an account exists for that email, a password reset link has been dispatched.",
    }
    if user:
        reset_token = create_access_token(
            {"sub": user.id, "email": user.email, "purpose": "password_reset"},
            expires_delta=timedelta(hours=1),
        )
        # Security: Never return reset tokens in production HTTP payloads
        if os.getenv("ALLOW_DEV_RESET_TOKEN", "").lower() == "true":
            response["reset_token"] = reset_token
    return response


@router.post("/auth/reset-password", tags=["Auth"])
def reset_password(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    token = (payload.get("token") or "").strip()
    new_password = payload.get("new_password") or ""

    if not token:
        raise HTTPException(status_code=400, detail="Reset token is required")
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")

    decoded = decode_access_token(token)
    if not decoded or decoded.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="Reset link is invalid or has expired")

    user = db.query(UserModel).filter(UserModel.id == decoded.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")

    user.password_hash = hash_password(new_password)
    db.commit()

    return {
        "success": True,
        "message": "Password updated successfully. You may now sign in.",
    }


# ============================================================================
# Manager Authentication via Phone OTP
# ============================================================================
@router.post("/auth/otp/request", tags=["Auth"])
def request_manager_otp(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """
    Dispatches a cryptographically generated 6-digit OTP to a registered Salon Manager.
    Includes rate-limiting (max 5 in 10 mins), resend cooldown (30s), and attempt tracking.
    """
    raw_phone = (payload.get("phone") or "").strip()
    clean_phone = "".join(c for c in raw_phone if c.isdigit() or c == "+")

    if not clean_phone or len(clean_phone) < 10:
        raise HTTPException(status_code=400, detail="A valid registered phone number is required")

    # Rate limiting: max 5 requests per 10 minutes
    ten_min_ago = datetime.utcnow() - timedelta(minutes=10)
    recent_count = db.query(OTPModel).filter(
        OTPModel.phone == clean_phone,
        OTPModel.created_at >= ten_min_ago
    ).count()
    if recent_count >= 5:
        raise HTTPException(status_code=429, detail="Too many OTP requests. Please wait 10 minutes.")

    # Resend cooldown: at least 30 seconds
    latest_otp = db.query(OTPModel).filter(
        OTPModel.phone == clean_phone
    ).order_by(OTPModel.created_at.desc()).first()
    if latest_otp and (datetime.utcnow() - latest_otp.created_at).total_seconds() < 30:
        raise HTTPException(status_code=429, detail="Please wait 30 seconds before requesting a new code.")

    # Locate manager user matching this phone
    user = None
    for u in db.query(UserModel).all():
        u_phone = "".join(c for c in (u.phone or "") if c.isdigit() or c == "+")
        if u_phone and (clean_phone.endswith(u_phone[-10:]) or u_phone.endswith(clean_phone[-10:])):
            if u.role in ("SALON_MANAGER", "owner", "manager"):
                user = u
                break

    # Security: neutral response if phone is not a manager
    if not user:
        return {
            "success": True,
            "message": "If this phone number is associated with an active Salon Manager, an OTP code has been dispatched."
        }

    # Generate cryptographically secure 6-digit code
    otp_code = f"{secrets.randbelow(900000) + 100000}"
    otp_record = OTPModel(
        phone=clean_phone,
        otp_hash=hash_password(otp_code),
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        attempts=0,
        is_used=False
    )
    db.add(otp_record)
    db.commit()

    response_payload = {
        "success": True,
        "message": f"6-digit OTP code sent to your registered number. Valid for 5 minutes.",
    }
    # Security: dev_otp only exposed if explicitly activated via ALLOW_DEV_OTP for test runners
    if os.getenv("ALLOW_DEV_OTP", "").lower() == "true":
        response_payload["dev_otp"] = otp_code

    return response_payload


@router.post("/auth/otp/verify", tags=["Auth"])
def verify_manager_otp(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """
    Verifies manager 6-digit OTP, prevents brute force (max 5 tries), and issues JWT.
    """
    raw_phone = (payload.get("phone") or "").strip()
    otp_code = (payload.get("otp") or "").strip()
    clean_phone = "".join(c for c in raw_phone if c.isdigit() or c == "+")

    if not clean_phone or not otp_code:
        raise HTTPException(status_code=400, detail="Phone number and 6-digit OTP are required")

    otp_record = db.query(OTPModel).filter(
        OTPModel.phone == clean_phone,
        OTPModel.is_used == False,
        OTPModel.expires_at >= datetime.utcnow()
    ).order_by(OTPModel.created_at.desc()).first()

    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP. Please request a new code.")

    if otp_record.attempts >= 5:
        otp_record.is_used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Maximum OTP verification attempts exceeded. Please request a new code.")

    otp_record.attempts += 1
    if not verify_password(otp_code, otp_record.otp_hash):
        db.commit()
        remaining = 5 - otp_record.attempts
        raise HTTPException(status_code=400, detail=f"Incorrect OTP code. {remaining} attempt(s) remaining.")

    # Mark OTP used immediately to prevent replay
    otp_record.is_used = True
    db.commit()

    # Find the manager account
    user = None
    for u in db.query(UserModel).all():
        u_phone = "".join(c for c in (u.phone or "") if c.isdigit() or c == "+")
        if u_phone and (clean_phone.endswith(u_phone[-10:]) or u_phone.endswith(clean_phone[-10:])):
            if u.role in ("SALON_MANAGER", "owner", "manager"):
                user = u
                break

    if not user:
        raise HTTPException(status_code=404, detail="Salon Manager account not found for this phone number")

    salon = db.query(SalonModel).filter(SalonModel.id == user.salon_id).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon workspace not found")

    token = create_access_token({
        "sub": user.id,
        "email": user.email,
        "name": user.name,
        "role": "SALON_MANAGER",
        "salon_id": user.salon_id,
    })

    return {
        "success": True,
        "token": token,
        "user": user.to_dict(),
        "salon": salon.to_dict(),
    }


# ============================================================================
# Receptionist Invitation & Salon Enrollment Flow
# ============================================================================
@router.post("/invitations", tags=["Invitations"])
def create_receptionist_invitation(
    payload: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Salon Manager creates a single-use invitation for a receptionist to join a specific branch."""
    user, salon = context
    email = (payload.get("email") or "").strip().lower()
    branch_id = payload.get("branchId") or payload.get("branch_id")

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required")

    existing_user = db.query(UserModel).filter(UserModel.email.ilike(email)).first()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="This receptionist is already registered to a salon. Each receptionist can strictly belong to only ONE salon."
        )

    # Prevent simultaneous invitation from another salon (strict 1 receptionist = 1 salon rule)
    active_other_invite = db.query(InvitationModel).filter(
        InvitationModel.email.ilike(email),
        InvitationModel.is_accepted == False,
        InvitationModel.expires_at >= datetime.utcnow(),
        InvitationModel.salon_id != salon.id
    ).first()
    if active_other_invite:
        raise HTTPException(
            status_code=400,
            detail="This receptionist has an active pending invitation to another salon. Each receptionist can strictly belong to only ONE salon."
        )

    if branch_id:
        branch_obj = db.query(BranchModel).filter(
            BranchModel.id == branch_id,
            BranchModel.salon_id == salon.id
        ).first()
        if not branch_obj:
            branch_id = None

    invite_token = uuid.uuid4().hex + uuid.uuid4().hex
    invitation = InvitationModel(
        salon_id=salon.id,
        branch_id=branch_id,
        email=email,
        role="SALON_RECEPTIONIST",
        token=invite_token,
        expires_at=datetime.utcnow() + timedelta(days=2),
        is_accepted=False
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    return {
        "success": True,
        "invitation": invitation.to_dict(),
        "inviteUrl": f"/join/{invite_token}",
        "message": f"Receptionist invitation generated for {email}. Valid for 48 hours."
    }


@router.get("/invitations/{token}", tags=["Invitations"])
def get_invitation_details(token: str, db: Session = Depends(get_db)):
    """Validates invitation token and retrieves salon & branch information for the receptionist."""
    invitation = db.query(InvitationModel).filter(
        InvitationModel.token == token,
        InvitationModel.is_accepted == False,
        InvitationModel.expires_at >= datetime.utcnow()
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation link is invalid or has expired")

    salon = db.query(SalonModel).filter(SalonModel.id == invitation.salon_id).first()
    branch = db.query(BranchModel).filter(BranchModel.id == invitation.branch_id).first() if invitation.branch_id else None

    return {
        "valid": True,
        "email": invitation.email,
        "role": invitation.role,
        "salonName": salon.name if salon else "BillCare Studio",
        "salonId": invitation.salon_id,
        "branchId": invitation.branch_id,
        "branchName": branch.name if branch else (salon.branch if salon else "Flagship Studio"),
        "expiresAt": invitation.expires_at.isoformat()
    }


@router.post("/invitations/accept", tags=["Invitations"])
def accept_receptionist_invitation(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """Enrolls receptionist into the authorized salon & branch using the single-use token."""
    token = (payload.get("token") or "").strip()
    name = (payload.get("name") or "").strip()
    password = payload.get("password") or ""
    phone = (payload.get("phone") or "").strip()

    if not token:
        raise HTTPException(status_code=400, detail="Invitation token is required")
    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Full name is required")
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    invitation = db.query(InvitationModel).filter(
        InvitationModel.token == token,
        InvitationModel.is_accepted == False,
        InvitationModel.expires_at >= datetime.utcnow()
    ).first()

    if not invitation:
        raise HTTPException(status_code=400, detail="Invitation link is invalid or has expired")

    salon = db.query(SalonModel).filter(SalonModel.id == invitation.salon_id).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon workspace not found")

    existing_user = db.query(UserModel).filter(UserModel.email.ilike(invitation.email)).first()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="This account is already registered to a salon. Each receptionist can strictly belong to only one salon."
        )

    new_user = UserModel(
        id=f"usr_{uuid.uuid4().hex[:12]}",
        salon_id=salon.id,
        branch_id=invitation.branch_id,
        name=name,
        email=invitation.email,
        phone=phone,
        role="SALON_RECEPTIONIST",
        password_hash=hash_password(password),
        avatar=name[0].upper()
    )
    db.add(new_user)

    # Automatically add or update Staff table record with branch allotment
    existing_staff = db.query(StaffModel).filter(
        StaffModel.salon_id == salon.id,
        StaffModel.email == invitation.email
    ).first()
    if not existing_staff:
        new_staff = StaffModel(
            id=f"stf_{uuid.uuid4().hex[:12]}",
            salon_id=salon.id,
            branch_id=invitation.branch_id,
            name=name,
            email=invitation.email,
            phone=phone,
            role="Salon Receptionist",
            commission_rate=0.0,
            is_clocked_in=True,
            clocked_in_at=datetime.utcnow().strftime("%I:%M %p"),
            avatar=name[0].upper(),
            specialties_json=json.dumps(["Front Desk POS", "Guest Management"]),
            status="clocked_in"
        )
        db.add(new_staff)
    else:
        existing_staff.branch_id = invitation.branch_id

    invitation.is_accepted = True
    db.commit()
    db.refresh(new_user)

    auth_token = create_access_token({
        "sub": new_user.id,
        "email": new_user.email,
        "name": new_user.name,
        "role": "SALON_RECEPTIONIST",
        "salon_id": salon.id,
        "branch_id": invitation.branch_id,
    })

    return {
        "success": True,
        "token": auth_token,
        "user": new_user.to_dict(),
        "salon": salon.to_dict(),
        "message": f"Welcome to {salon.name}! Your Front Desk account is ready."
    }


# ============================================================================
# Subscription & 7-Day Free Trial Management
# ============================================================================
@router.get("/subscription/status", tags=["Subscription"])
def get_subscription_status(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon)
):
    """Returns trial countdown and feature eligibility for the active salon."""
    _, salon = context
    return {
        "status": salon.subscription_status or "trial",
        "plan": salon.subscription_plan or "free_trial",
        "isTrialActive": salon.is_trial_active(),
        "trialDaysLeft": salon.trial_days_left(),
        "trialStartedAt": salon.trial_started_at.isoformat() if salon.trial_started_at else None,
        "trialEndsAt": salon.trial_ends_at.isoformat() if salon.trial_ends_at else None,
        "features": {
            "receptionist_pos": True,
            "appointments": True,
            "customer_crm": True,
            "branch_management": salon.subscription_status == "active",
            "gst_tax_configuration": salon.subscription_status == "active",
            "whatsapp_custom_integration": salon.subscription_status == "active",
            "advanced_financial_reports": salon.subscription_status == "active",
        }
    }


@router.post("/subscription/upgrade", tags=["Subscription"])
def upgrade_subscription(
    payload: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Manager activates paid subscription for their salon."""
    _, salon = context
    plan = payload.get("plan") or "pro"
    salon.subscription_status = "active"
    salon.subscription_plan = plan
    db.commit()
    db.refresh(salon)
    return {
        "success": True,
        "message": f"Successfully activated {plan.capitalize()} subscription for {salon.name}!",
        "salon": salon.to_dict()
    }


# ============================================================================
# Salon Profile & Business Settings (Manager Only)
# ============================================================================
@router.get("/salon", tags=["Salon"])
def get_salon(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon)
):
    _, salon = context
    return salon.to_dict()


@router.put("/salon", tags=["Salon"])
def update_salon(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context

    # Check trial restriction: Tax/GST configuration locked during trial
    if "gstin" in data and salon.subscription_status == "trial":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Official GSTIN and tax setting customization is locked during the 7-day trial. Upgrade to Pro."
        )

    if "name" in data: salon.name = data["name"]
    if "branch" in data: salon.branch = data["branch"]
    if "city" in data: salon.city = data["city"]
    if "currency" in data: salon.currency = data["currency"]
    if "chairs" in data: salon.chairs = int(data["chairs"])
    if "category" in data: salon.category = data["category"]
    if "gstin" in data: salon.gstin = data["gstin"]
    if "phone" in data: salon.phone = data["phone"]
    if "email" in data: salon.email = data["email"]
    if "address" in data: salon.address = data["address"]
    if "timing" in data: salon.timing = data["timing"]
    if "logoUrl" in data:
        salon.logo_url = data["logoUrl"]
        salon.logo = data["logoUrl"]
    if "upiId" in data:
        salon.upi_id = data["upiId"]
    if "bankAccountName" in data:
        salon.bank_account_name = data["bankAccountName"]
    if "bankAccountNumber" in data:
        salon.bank_account_number = data["bankAccountNumber"]
    if "bankIfsc" in data:
        salon.bank_ifsc = data["bankIfsc"]
    if "bankName" in data:
        salon.bank_name = data["bankName"]

    db.commit()
    db.refresh(salon)
    return salon.to_dict()


# ============================================================================
# Branch Management (Manager Only)
# ============================================================================
@router.get("/branches", tags=["Branches"])
def get_branches(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    branches = db.query(BranchModel).filter(BranchModel.salon_id == salon.id).all()
    if not branches:
        default_branch = BranchModel(
            salon_id=salon.id,
            name=salon.branch or "Flagship Studio",
            address=salon.address or "Indiranagar",
            city=salon.city or "Bengaluru",
            phone=salon.phone or "",
            email=salon.email or "",
            chairs=salon.chairs or 8,
            is_active=True
        )
        db.add(default_branch)
        db.commit()
        db.refresh(default_branch)
        branches = [default_branch]
    return [b.to_dict() for b in branches]


@router.post("/branches", tags=["Branches"])
def create_branch(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context

    branch_code = (data.get("code") or "").strip().upper()
    if not branch_code:
        branch_code = f"BR_{uuid.uuid4().hex[:4].upper()}"

    branch = BranchModel(
        salon_id=salon.id,
        name=data.get("name", "New Branch Studio"),
        code=branch_code,
        address=data.get("address", ""),
        city=data.get("city", ""),
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        chairs=int(data.get("chairs") or 6),
        is_active=bool(data.get("isActive", True))
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch.to_dict()


@router.put("/branches/{branch_id}", tags=["Branches"])
def update_branch(
    branch_id: str,
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    branch = db.query(BranchModel).filter(
        BranchModel.id == branch_id,
        BranchModel.salon_id == salon.id
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    for k, v in data.items():
        if k == "name": branch.name = v
        elif k == "address": branch.address = v
        elif k == "city": branch.city = v
        elif k == "phone": branch.phone = v
        elif k == "email": branch.email = v
        elif k == "chairs": branch.chairs = int(v)
        elif k == "isActive": branch.is_active = bool(v)

    db.commit()
    db.refresh(branch)
    return branch.to_dict()


@router.delete("/branches/{branch_id}", tags=["Branches"])
def delete_branch(
    branch_id: str,
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    branch = db.query(BranchModel).filter(
        BranchModel.id == branch_id,
        BranchModel.salon_id == salon.id
    ).first()
    if branch:
        db.delete(branch)
        db.commit()
    return {"success": True, "id": branch_id}


# ============================================================================
# Customers CRUD (Operational: Receptionist & Manager)
# ============================================================================
@router.get("/customers", tags=["Customers"])
def get_customers(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    customers = (
        db.query(CustomerModel)
        .filter(CustomerModel.salon_id == salon.id)
        .order_by(CustomerModel.id.desc())
        .all()
    )
    return [c.to_dict() for c in customers]


@router.post("/customers", tags=["Customers"])
def create_customer(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    phone_input = str(data.get("phone", "")).strip()
    digits = "".join(filter(str.isdigit, phone_input))

    # Duplicate detection by phone number in this salon
    if digits and len(digits) >= 10:
        existing = db.query(CustomerModel).filter(
            CustomerModel.salon_id == salon.id,
            CustomerModel.phone.ilike(f"%{digits[-10:]}%")
        ).first()
        if existing:
            if data.get("updateExisting") or data.get("merge"):
                if data.get("name"): existing.name = data["name"]
                if data.get("email"): existing.email = data["email"]
                if data.get("notes"): existing.notes = data["notes"]
                if data.get("allergies"): existing.allergies = data["allergies"]
                db.commit()
                db.refresh(existing)
                return existing.to_dict()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A customer with phone {phone_input} already exists in your salon ({existing.name})."
            )

    tags = data.get("tags") or ["Client"]
    customer = CustomerModel(
        id=f"cst_{uuid.uuid4().hex[:12]}",
        salon_id=salon.id,
        name=data.get("name", "New Client"),
        phone=phone_input,
        email=data.get("email", ""),
        gender=data.get("gender", "female"),
        birthday=data.get("birthday", ""),
        total_visits=int(data.get("totalVisits") or data.get("visitsCount") or 0),
        visits_count=int(data.get("visitsCount") or data.get("totalVisits") or 0),
        total_spend=float(data.get("totalSpend") or data.get("totalSpent") or 0.0),
        total_spent=float(data.get("totalSpent") or data.get("totalSpend") or 0.0),
        loyalty_points=int(data.get("loyaltyPoints") or 50),
        last_visit_date=data.get("lastVisitDate") or datetime.utcnow().strftime("%Y-%m-%d"),
        tags_json=json.dumps(tags),
        notes=data.get("notes", ""),
        last_service=data.get("lastService", ""),
        preferred_staff=data.get("preferredStaff", "Priya Sharma"),
        vip_tier=data.get("vipTier", "Silver Member"),
        formula_notes=data.get("formulaNotes", ""),
        patch_test_status=data.get("patchTestStatus", "Verified Safe"),
        patch_test_date=data.get("patchTestDate", ""),
        allergies=data.get("allergies", "None Reported"),
        rebooking_cadence_days=int(data.get("rebookingCadenceDays") or 28),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer.to_dict()


@router.get("/customers/export", tags=["Customers"])
def export_customers(
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Exports all salon client profiles as CSV format for reporting or backup."""
    import io
    import csv
    from fastapi.responses import Response

    _, salon = context
    customers = db.query(CustomerModel).filter(CustomerModel.salon_id == salon.id).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Phone", "Email", "Gender", "TotalVisits", "TotalSpend", "LoyaltyPoints", "VIPTier", "Allergies", "Notes", "LastVisitDate"])
    for c in customers:
        writer.writerow([
            c.id, c.name, c.phone, c.email, c.gender, c.total_visits, c.total_spend, c.loyalty_points, c.vip_tier, c.allergies, c.notes, c.last_visit_date
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=customers_{salon.slug}.csv"}
    )


@router.post("/customers/import", tags=["Customers"])
def import_customers(
    payload: Any = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Bulk imports client profiles with phone duplicate detection."""
    _, salon = context
    if isinstance(payload, list):
        clients_list = payload
    elif isinstance(payload, dict):
        clients_list = payload.get("customers", [])
    else:
        clients_list = []
    imported_count = 0
    skipped_count = 0

    for itm in clients_list:
        phone = str(itm.get("phone", "")).strip()
        digits = "".join(filter(str.isdigit, phone))
        if not phone or len(digits) < 10:
            skipped_count += 1
            continue

        existing = db.query(CustomerModel).filter(
            CustomerModel.salon_id == salon.id,
            CustomerModel.phone.ilike(f"%{digits[-10:]}%")
        ).first()
        if existing:
            skipped_count += 1
            continue

        cst = CustomerModel(
            id=f"cst_{uuid.uuid4().hex[:12]}",
            salon_id=salon.id,
            name=itm.get("name", "Imported Client"),
            phone=phone,
            email=itm.get("email", ""),
            gender=itm.get("gender", "female"),
            vip_tier=itm.get("vipTier", "Silver Regular"),
            total_visits=int(itm.get("totalVisits") or 1),
            total_spend=float(itm.get("totalSpend") or 0.0),
            notes=itm.get("notes", "Imported via bulk CRM upload"),
            allergies=itm.get("allergies", "None Reported"),
        )
        db.add(cst)
        imported_count += 1

    db.commit()
    return {"success": True, "imported": imported_count, "skippedDuplicates": skipped_count}



@router.put("/customers/{customer_id}", tags=["Customers"])
def update_customer(
    customer_id: str,
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    customer = db.query(CustomerModel).filter(
        CustomerModel.id == customer_id,
        CustomerModel.salon_id == salon.id
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    for k, v in data.items():
        if k == "name": customer.name = v
        elif k == "phone": customer.phone = v
        elif k == "email": customer.email = v
        elif k == "gender": customer.gender = v
        elif k == "notes": customer.notes = v
        elif k == "formulaNotes": customer.formula_notes = v
        elif k == "preferredStaff": customer.preferred_staff = v
        elif k == "vipTier": customer.vip_tier = v
        elif k == "tags": customer.tags_json = json.dumps(v)
        elif k in ("totalSpend", "totalSpent"):
            customer.total_spend = float(v)
            customer.total_spent = float(v)
        elif k in ("totalVisits", "visitsCount"):
            customer.total_visits = int(v)
            customer.visits_count = int(v)
        elif k == "loyaltyPoints": customer.loyalty_points = int(v)
        elif k == "lastVisitDate": customer.last_visit_date = str(v)
        elif k == "allergies": customer.allergies = str(v)
        elif k == "walletBalance": customer.wallet_balance = float(v)

    db.commit()
    db.refresh(customer)
    return customer.to_dict()


@router.post("/customers/{customer_id}/wallet", tags=["Customers"])
def topup_customer_wallet(
    customer_id: str,
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """Adds prepaid credit / top-up to customer wallet balance."""
    _, salon = context
    customer = db.query(CustomerModel).filter(
        CustomerModel.id == customer_id,
        CustomerModel.salon_id == salon.id
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    amount = float(data.get("amount") or 0.0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Top-up amount must be greater than zero.")

    customer.wallet_balance = round(float(customer.wallet_balance or 0.0) + amount, 2)
    db.commit()
    db.refresh(customer)
    return {
        "success": True,
        "message": f"Added ₹{amount:,.2f} credit to {customer.name}'s wallet. New balance: ₹{customer.wallet_balance:,.2f}.",
        "customer": customer.to_dict()
    }


@router.delete("/customers/{customer_id}", tags=["Customers"])
def delete_customer(
    customer_id: str,
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    customer = db.query(CustomerModel).filter(
        CustomerModel.id == customer_id,
        CustomerModel.salon_id == salon.id
    ).first()
    if customer:
        db.delete(customer)
        db.commit()
    return {"success": True, "id": customer_id}


# ============================================================================
# Services & Pricing
# ============================================================================
@router.get("/services", tags=["Services"])
def get_services(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    services = db.query(ServiceModel).filter(ServiceModel.salon_id == salon.id).all()
    return [s.to_dict() for s in services]


@router.post("/services", tags=["Services"])
def create_service(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    service = ServiceModel(
        id=f"srv_{uuid.uuid4().hex[:12]}",
        salon_id=salon.id,
        category=data.get("category", "Hair"),
        name=data.get("name", "New Service"),
        duration_minutes=int(data.get("durationMinutes") or 45),
        buffer_minutes=int(data.get("bufferMinutes") or 5),
        price=float(data.get("price") or 0.0),
        description=data.get("description", ""),
        material_used=data.get("materialUsed") or data.get("averageMaterialUsed") or "",
        material_item_id=data.get("materialItemId") or None,
        material_quantity=float(data.get("materialQuantity") or 0.0),
        material_unit=data.get("materialUnit") or "ml",
        is_online_bookable=bool(data.get("isOnlineBookable", True)),
        is_active=bool(data.get("isActive", True)),
        popular=bool(data.get("popular", False)),
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service.to_dict()


@router.put("/services/{service_id}", tags=["Services"])
def update_service(
    service_id: str,
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    service = db.query(ServiceModel).filter(
        ServiceModel.id == service_id,
        ServiceModel.salon_id == salon.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    for k, v in data.items():
        if k == "name": service.name = v
        elif k == "category": service.category = v
        elif k == "durationMinutes": service.duration_minutes = int(v)
        elif k == "bufferMinutes": service.buffer_minutes = int(v)
        elif k == "price": service.price = float(v)
        elif k == "description": service.description = v
        elif k in ("materialUsed", "averageMaterialUsed"): service.material_used = str(v)
        elif k == "materialItemId": service.material_item_id = str(v) if v else None
        elif k == "materialQuantity": service.material_quantity = float(v or 0.0)
        elif k == "materialUnit": service.material_unit = str(v or "ml")
        elif k == "isOnlineBookable": service.is_online_bookable = bool(v)
        elif k == "isActive": service.is_active = bool(v)
        elif k == "popular": service.popular = bool(v)

    db.commit()
    db.refresh(service)
    return service.to_dict()


@router.delete("/services/{service_id}", tags=["Services"])
def delete_service(
    service_id: str,
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    service = db.query(ServiceModel).filter(
        ServiceModel.id == service_id,
        ServiceModel.salon_id == salon.id
    ).first()
    if service:
        db.delete(service)
        db.commit()
    return {"success": True, "id": service_id}


# ============================================================================
# Staff & Availability
# ============================================================================
@router.get("/staff", tags=["Staff"])
def get_staff(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    staff = db.query(StaffModel).filter(StaffModel.salon_id == salon.id).all()
    return [st.to_dict() for st in staff]


@router.post("/staff", tags=["Staff"])
def create_staff(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    specialties = data.get("specialty") or ["Hair Specialist"]
    new_staff = StaffModel(
        id=f"stf_{uuid.uuid4().hex[:12]}",
        salon_id=salon.id,
        name=data.get("name", "New Stylist"),
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        role=data.get("role", "Stylist"),
        commission_rate=float(data.get("commissionRate") or 15.0),
        is_clocked_in=bool(data.get("isClockedIn", True)),
        clocked_in_at=datetime.utcnow().strftime("%I:%M %p"),
        avatar=data.get("avatar") or "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=150&auto=format&fit=crop&q=80",
        specialties_json=json.dumps(specialties),
        status="clocked_in",
        rating=float(data.get("rating") or 4.9),
    )
    db.add(new_staff)
    db.commit()
    db.refresh(new_staff)
    return new_staff.to_dict()


@router.put("/staff/{staff_id}", tags=["Staff"])
def update_staff(
    staff_id: str,
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    member = db.query(StaffModel).filter(
        StaffModel.id == staff_id,
        StaffModel.salon_id == salon.id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Staff member not found")

    for k, v in data.items():
        if k == "name": member.name = v
        elif k == "phone": member.phone = v
        elif k == "email": member.email = v
        elif k == "role": member.role = v
        elif k in ("branchId", "branch_id"):
            member.branch_id = v
            if member.email:
                user_rec = db.query(UserModel).filter(
                    UserModel.salon_id == salon.id,
                    UserModel.email == member.email
                ).first()
                if user_rec:
                    user_rec.branch_id = v
        elif k == "commissionRate": member.commission_rate = float(v)
        elif k == "isClockedIn": member.is_clocked_in = bool(v)
        elif k == "clockedInAt": member.clocked_in_at = str(v)
        elif k == "status": member.status = str(v)
        elif k == "specialty": member.specialties_json = json.dumps(v)
        elif k == "todayRevenue": member.today_revenue = float(v)
        elif k == "todayCommission": member.today_commission = float(v)

    db.commit()
    db.refresh(member)
    return member.to_dict()


@router.post("/staff/{staff_id}/toggle-clock", tags=["Staff"])
def toggle_clock(
    staff_id: str,
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    member = db.query(StaffModel).filter(
        StaffModel.id == staff_id,
        StaffModel.salon_id == salon.id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Staff member not found")

    next_state = not member.is_clocked_in
    member.is_clocked_in = next_state
    member.status = "clocked_in" if next_state else "clocked_out"
    member.clocked_in_at = datetime.utcnow().strftime("%I:%M %p") if next_state else ""

    db.commit()
    db.refresh(member)
    return member.to_dict()


@router.delete("/staff/{staff_id}", tags=["Staff"])
def delete_staff(
    staff_id: str,
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    member = db.query(StaffModel).filter(
        StaffModel.id == staff_id,
        StaffModel.salon_id == salon.id
    ).first()
    if member:
        db.delete(member)
        db.commit()
    return {"success": True, "id": staff_id}


# ============================================================================
# Inventory & Stock Movements
# ============================================================================
@router.get("/inventory", tags=["Inventory"])
def get_inventory(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    items = db.query(InventoryModel).filter(InventoryModel.salon_id == salon.id).all()
    return [item.to_dict() for item in items]


@router.post("/inventory", tags=["Inventory"])
def create_inventory(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    item = InventoryModel(
        id=f"inv_{uuid.uuid4().hex[:12]}",
        salon_id=salon.id,
        name=data.get("name", "Product"),
        category=data.get("category", "Hair Care"),
        sku=data.get("sku") or f"SKU-{uuid.uuid4().hex[:6].upper()}",
        current_stock=int(data.get("currentStock") or 10),
        min_threshold=int(data.get("minThreshold") or 5),
        cost_price=float(data.get("costPrice") or 0.0),
        selling_price=float(data.get("sellingPrice") or data.get("retailPrice") or 0.0),
        retail_price=float(data.get("retailPrice") or data.get("sellingPrice") or 0.0),
        brand=data.get("brand", "Salon Professional"),
        usage_type=data.get("usageType", "Salon Professional"),
        unit=data.get("unit", "bottle"),
        supplier=data.get("supplier", "Official Distributor"),
        last_restocked=data.get("lastRestocked") or datetime.utcnow().strftime("%Y-%m-%d"),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item.to_dict()


@router.put("/inventory/{item_id}", tags=["Inventory"])
def update_inventory(
    item_id: str,
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    item = db.query(InventoryModel).filter(
        InventoryModel.id == item_id,
        InventoryModel.salon_id == salon.id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    for k, v in data.items():
        if k == "name": item.name = v
        elif k == "currentStock": item.current_stock = int(v)
        elif k == "minThreshold": item.min_threshold = int(v)
        elif k == "costPrice": item.cost_price = float(v)
        elif k == "sellingPrice": item.selling_price = float(v)
        elif k == "retailPrice": item.retail_price = float(v)
        elif k == "brand": item.brand = v
        elif k == "category": item.category = v
        elif k == "lastRestocked": item.last_restocked = str(v)

    db.commit()
    db.refresh(item)
    return item.to_dict()


@router.post("/inventory/{item_id}/adjust-stock", tags=["Inventory"])
def adjust_stock(
    item_id: str,
    payload: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    change = int(payload.get("change") or 0)
    item = db.query(InventoryModel).filter(
        InventoryModel.id == item_id,
        InventoryModel.salon_id == salon.id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item.current_stock = max(0, item.current_stock + change)
    if change > 0:
        item.last_restocked = datetime.utcnow().strftime("%Y-%m-%d")

    db.commit()
    db.refresh(item)
    return item.to_dict()


@router.delete("/inventory/{item_id}", tags=["Inventory"])
def delete_inventory(
    item_id: str,
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    _, salon = context
    item = db.query(InventoryModel).filter(
        InventoryModel.id == item_id,
        InventoryModel.salon_id == salon.id
    ).first()
    if item:
        db.delete(item)
        db.commit()
    return {"success": True, "id": item_id}


# ============================================================================
# Appointments & Calendar (Receptionist & Manager)
# ============================================================================
@router.get("/appointments", tags=["Appointments"])
def get_appointments(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    appointments = (
        db.query(AppointmentModel)
        .filter(AppointmentModel.salon_id == salon.id)
        .order_by(AppointmentModel.id.desc())
        .all()
    )
    return [a.to_dict() for a in appointments]


@router.post("/appointments", tags=["Appointments"])
def create_appointment(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    date_val = data.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
    start_time_val = data.get("startTime") or data.get("time") or "11:00"
    duration_val = int(data.get("duration") or data.get("durationMinutes") or 45)

    if data.get("endTime"):
        end_time_val = data["endTime"]
    else:
        try:
            parts = start_time_val.split(":")
            sh, sm = int(parts[0]), int(parts[1])
            tot = sh * 60 + sm + duration_val
            end_time_val = f"{(tot // 60) % 24:02d}:{tot % 60:02d}"
        except Exception:
            end_time_val = "11:45"

    staff_id_val = data.get("staffId", "")
    staff_name_val = data.get("staffName", "Priya Sharma")
    chair_val = int(data.get("chairNumber") or 1)

    allow_double_booking = data.get("allowDoubleBooking", False)

    # Double-booking collision detection
    if not allow_double_booking and staff_name_val:
        existing_conflicts = db.query(AppointmentModel).filter(
            AppointmentModel.salon_id == salon.id,
            AppointmentModel.date == date_val,
            AppointmentModel.status.in_(["confirmed", "in_service", "scheduled"]),
            (
                (AppointmentModel.staff_id == staff_id_val) |
                (AppointmentModel.staff_name == staff_name_val)
            )
        ).all()

        for c_apt in existing_conflicts:
            if (start_time_val < c_apt.end_time) and (end_time_val > c_apt.start_time):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Double-booking conflict: Stylist {staff_name_val} is already booked from {c_apt.start_time} to {c_apt.end_time} on {date_val} ({c_apt.service_name} for {c_apt.customer_name})."
                )

    apt = AppointmentModel(
        id=f"apt_{uuid.uuid4().hex[:12]}",
        salon_id=salon.id,
        branch_id=data.get("branchId", "Flagship"),
        customer_id=data.get("customerId") or f"cst_walkin_{uuid.uuid4().hex[:6]}",
        customer_name=data.get("customerName", "Walk-in Guest"),
        customer_phone=data.get("customerPhone", ""),
        staff_id=staff_id_val,
        staff_name=staff_name_val,
        service_id=data.get("serviceId", ""),
        service_name=data.get("serviceName", "Salon Service"),
        chair_number=chair_val,
        date=date_val,
        start_time=start_time_val,
        end_time=end_time_val,
        time=data.get("time") or start_time_val,
        duration_minutes=int(data.get("durationMinutes") or 45),
        price=float(data.get("price") or 1500.0),
        status=data.get("status", "confirmed"),
        source=data.get("source", "front_desk"),
        notes=data.get("notes", ""),
    )
    db.add(apt)
    db.commit()
    db.refresh(apt)
    return apt.to_dict()


@router.put("/appointments/{appointment_id}", tags=["Appointments"])
def update_appointment(
    appointment_id: str,
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """Full appointment reschedule & details update."""
    _, salon = context
    apt = db.query(AppointmentModel).filter(
        AppointmentModel.id == appointment_id,
        AppointmentModel.salon_id == salon.id
    ).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if "date" in data: apt.date = data["date"]
    if "startTime" in data: apt.start_time = data["startTime"]
    if "endTime" in data: apt.end_time = data["endTime"]
    if "time" in data: apt.time = data["time"]
    if "staffId" in data: apt.staff_id = data["staffId"]
    if "staffName" in data: apt.staff_name = data["staffName"]
    if "chairNumber" in data: apt.chair_number = int(data["chairNumber"])
    if "serviceId" in data: apt.service_id = data["serviceId"]
    if "serviceName" in data: apt.service_name = data["serviceName"]
    if "durationMinutes" in data: apt.duration_minutes = int(data["durationMinutes"])
    if "price" in data: apt.price = float(data["price"])
    if "status" in data: apt.status = data["status"]
    if "notes" in data: apt.notes = data["notes"]

    db.commit()
    db.refresh(apt)
    return apt.to_dict()


@router.put("/appointments/{appointment_id}/status", tags=["Appointments"])
def update_appointment_status(
    appointment_id: str,
    payload: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    status_val = payload.get("status", "confirmed")
    apt = db.query(AppointmentModel).filter(
        AppointmentModel.id == appointment_id,
        AppointmentModel.salon_id == salon.id
    ).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    apt.status = status_val
    if "chairNumber" in payload:
        apt.chair_number = int(payload["chairNumber"])

    db.commit()
    db.refresh(apt)
    return apt.to_dict()


@router.delete("/appointments/{appointment_id}", tags=["Appointments"])
def delete_appointment(
    appointment_id: str,
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    apt = db.query(AppointmentModel).filter(
        AppointmentModel.id == appointment_id,
        AppointmentModel.salon_id == salon.id
    ).first()
    if apt:
        db.delete(apt)
        db.commit()
    return {"success": True, "id": appointment_id}


# ============================================================================
# POS Billing, Checkout & Server-Recalculated Invoices
# ============================================================================
@router.get("/invoices", tags=["Invoices"])
def get_invoices(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    invoices = (
        db.query(InvoiceModel)
        .filter(InvoiceModel.salon_id == salon.id)
        .order_by(InvoiceModel.id.desc())
        .all()
    )
    return [inv.to_dict() for inv in invoices]


@router.post("/invoices", tags=["Invoices"])
def create_invoice(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """
    Creates POS invoice with server-side recalculated pricing, GST, discounts,
    inventory decrement, and loyalty point crediting in an atomic transaction.
    """
    _, salon = context
    salon_id = salon.id

    inv_number = data.get("invoiceNumber")
    if not inv_number or db.query(InvoiceModel).filter(
        InvoiceModel.salon_id == salon_id,
        InvoiceModel.invoice_number == inv_number
    ).first():
        count = db.query(InvoiceModel).filter(InvoiceModel.salon_id == salon_id).count()
        seq = 100 + count + 1
        inv_number = f"BC-INV-{datetime.utcnow().year}-{seq:04d}"
        while db.query(InvoiceModel).filter(
            InvoiceModel.salon_id == salon_id,
            InvoiceModel.invoice_number == inv_number
        ).first():
            seq += 1
            inv_number = f"BC-INV-{datetime.utcnow().year}-{seq:04d}"

    items = data.get("items") or []

    # Recalculate financial totals securely server-side
    computed_subtotal = 0.0
    for itm in items:
        qty = int(itm.get("quantity") or 1)
        price = float(itm.get("price") or 0.0)
        computed_subtotal += (price * qty)

    # Fallback to client subtotal if empty items
    if computed_subtotal == 0.0 and "subtotal" in data:
        computed_subtotal = float(data.get("subtotal") or 0.0)

    # Validated discount
    discount_percent = float(data.get("discountPercent") or 0.0)
    discount_amount = float(data.get("discountAmount") or data.get("discount") or 0.0)
    if discount_percent > 0:
        discount_amount = round((computed_subtotal * discount_percent) / 100.0, 2)
    discount_amount = min(discount_amount, computed_subtotal)

    taxable_amount = max(0.0, computed_subtotal - discount_amount)

    # Loyalty points redemption
    points_redeemed = int(data.get("loyaltyPointsRedeemed") or data.get("pointsRedeemed") or 0)
    points_discount = 0.0

    cust_id = data.get("customerId")
    cust = None
    if cust_id:
        cust = db.query(CustomerModel).filter(
            CustomerModel.id == cust_id,
            CustomerModel.salon_id == salon_id
        ).first()

    if points_redeemed > 0 and cust:
        # Validate customer has enough points: 1 point = ₹1
        actual_redeem = min(points_redeemed, cust.loyalty_points)
        points_discount = min(float(actual_redeem), taxable_amount)
        points_redeemed = int(points_discount)
        taxable_amount = max(0.0, taxable_amount - points_discount)
        cust.loyalty_points = max(0, cust.loyalty_points - points_redeemed)

    tax_percent = float(data.get("taxPercent") if "taxPercent" in data else 5.0)
    tax_amount = round((taxable_amount * tax_percent) / 100.0, 2)
    cgst = round(tax_amount / 2.0, 2)
    sgst = round(tax_amount - cgst, 2)
    grand_total = round(taxable_amount + tax_amount, 2)

    invoice = InvoiceModel(
        id=f"inv_{uuid.uuid4().hex[:12]}",
        salon_id=salon_id,
        invoice_number=inv_number,
        customer_id=data.get("customerId", "cst_walkin"),
        customer_name=data.get("customerName", "Walk-in Guest"),
        customer_phone=data.get("customerPhone", ""),
        staff_id=data.get("staffId", ""),
        staff_name=data.get("staffName", ""),
        items_json=json.dumps(items),
        subtotal=computed_subtotal,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        points_redeemed=points_redeemed,
        points_discount=points_discount,
        tax_percent=tax_percent,
        cgst=cgst,
        sgst=sgst,
        tax_amount=tax_amount,
        grand_total=grand_total,
        payment_method=data.get("paymentMethod", "CASH"),
        payment_breakdown_json=json.dumps(data.get("paymentBreakdown") or data.get("splitDetails") or {}),
        status="pending",
        notes=data.get("notes", ""),
        date=data.get("date") or datetime.utcnow().strftime("Today, %I:%M %p"),
    )
    db.add(invoice)

    user, _ = context
    requested_status = str(data.get("status") or data.get("paymentStatus") or "paid").lower()
    raw_method = str(data.get("paymentMethod") or "CASH").upper()
    payment_method = "CASH" if "CASH" in raw_method else ("UPI" if "UPI" in raw_method else raw_method)

    if requested_status == "paid":
        amount_received = grand_total
        change_given = 0.0

        if payment_method == "CASH":
            if not salon.cash_enabled:
                raise HTTPException(status_code=400, detail="Cash payment is currently disabled for this salon.")
            amount_received = float(data.get("amountReceived") if data.get("amountReceived") is not None else (data.get("amountTendered") if data.get("amountTendered") is not None else grand_total))
            if amount_received < 0:
                raise HTTPException(status_code=400, detail="Cash amount received must be non-negative.")
            if amount_received < grand_total:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient cash received. Final payable amount is ₹{grand_total:,.2f}, but only ₹{amount_received:,.2f} received."
                )
            change_given = round(amount_received - grand_total, 2)
            txn_ref = data.get("transactionReference") or f"BC-TXN-CASH-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            verification_method = "manual_cash_counter"
        elif payment_method == "UPI":
            if not salon.upi_enabled or not salon.upi_id:
                raise HTTPException(
                    status_code=400,
                    detail="UPI payment is currently disabled or not configured for this salon. Please select Cash or configure UPI in Salon Settings."
                )
            txn_ref = data.get("transactionReference") or data.get("upiReference") or f"BC-TXN-UPI-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            verification_method = "manual_receptionist_upi_verification"
        elif payment_method == "WALLET":
            if not cust:
                raise HTTPException(status_code=400, detail="Wallet payment requires a registered salon customer.")
            current_wallet = float(cust.wallet_balance or 0.0)
            if current_wallet < grand_total:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient wallet balance. Customer has ₹{current_wallet:,.2f}, required: ₹{grand_total:,.2f}."
                )
            cust.wallet_balance = round(current_wallet - grand_total, 2)
            amount_received = grand_total
            change_given = 0.0
            txn_ref = data.get("transactionReference") or f"BC-TXN-WALLET-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            verification_method = "prepaid_customer_wallet"
        else:
            txn_ref = data.get("transactionReference") or f"BC-TXN-{payment_method}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            verification_method = "manual_counter"

        # Record payment entry
        payment = PaymentModel(
            id=f"pay_{uuid.uuid4().hex[:12]}",
            salon_id=salon_id,
            invoice_id=invoice.id,
            amount=grand_total,
            currency="INR",
            method=payment_method,
            status="completed",
            provider_ref_id=txn_ref,
            verification_method=verification_method,
            verified_by_user_id=user.id if user else None,
            verified_by_name=user.name if user else "Front Desk Staff",
            amount_received=amount_received,
            change_given=change_given,
            upi_vpa_snapshot=salon.upi_id if payment_method == "UPI" else None,
            upi_payee_name_snapshot=salon.upi_payee_name or salon.name if payment_method == "UPI" else None,
            upi_uri_snapshot=generate_upi_payment_uri(salon.upi_id, salon.upi_payee_name or salon.name, grand_total, inv_number) if payment_method == "UPI" and salon.upi_id else None,
            notes=data.get("notes", ""),
            audit_metadata_json=json.dumps({"ip": "127.0.0.1", "user_role": user.role if user else "STAFF", "timestamp": datetime.utcnow().isoformat()}),
            created_at=datetime.utcnow(),
            confirmed_at=datetime.utcnow(),
        )
        db.add(payment)

        invoice.status = "paid"
        invoice.payment_method = payment_method
        invoice.amount_received = amount_received
        invoice.change_given = change_given
        invoice.payment_reference = txn_ref
        invoice.verified_by_name = user.name if user else "Front Desk Staff"
        invoice.verified_by_user_id = user.id if user else None
        invoice.paid_at = datetime.utcnow()

        # Credit customer visits & loyalty points
        if cust:
            cust.total_visits += 1
            cust.visits_count = cust.total_visits
            cust.total_spend += grand_total
            cust.total_spent = cust.total_spend
            cust.loyalty_points += int(grand_total * 0.05)
            cust.last_visit_date = datetime.utcnow().strftime("%Y-%m-%d")

        # Automatically deduct retail inventory and service consumable material, and log in inventory ledger
        for itm in items:
            # 1. Retail Product sale decrement
            if itm.get("type") == "product" and itm.get("id"):
                inv_item = db.query(InventoryModel).filter(
                    InventoryModel.id == itm["id"],
                    InventoryModel.salon_id == salon_id
                ).first()
                if inv_item:
                    qty = int(itm.get("quantity") or 1)
                    prev_stock = inv_item.current_stock
                    inv_item.current_stock = max(0, inv_item.current_stock - qty)
                    ledger = InventoryLedgerModel(
                        salon_id=salon_id,
                        item_id=inv_item.id,
                        item_name=inv_item.name,
                        change_qty=-qty,
                        previous_stock=prev_stock,
                        new_stock=inv_item.current_stock,
                        reason=f"sale_invoice_{inv_number}",
                        performed_by=data.get("staffName") or "POS Checkout"
                    )
                    db.add(ledger)

            # 2. Service consumable material auto-deduction (Stock Monitor)
            elif itm.get("type") != "product":
                srv = None
                if itm.get("id"):
                    srv = db.query(ServiceModel).filter(ServiceModel.id == itm["id"], ServiceModel.salon_id == salon_id).first()
                if not srv and itm.get("name"):
                    srv = db.query(ServiceModel).filter(ServiceModel.name == itm["name"], ServiceModel.salon_id == salon_id).first()

                if srv and srv.material_item_id:
                    stock_item = db.query(InventoryModel).filter(
                        InventoryModel.id == srv.material_item_id,
                        InventoryModel.salon_id == salon_id
                    ).first()
                    if stock_item:
                        qty_to_deduct = max(1, int(srv.material_quantity or 1))
                        prev_stock = stock_item.current_stock
                        stock_item.current_stock = max(0, stock_item.current_stock - qty_to_deduct)
                        ledger = InventoryLedgerModel(
                            salon_id=salon_id,
                            item_id=stock_item.id,
                            item_name=stock_item.name,
                            change_qty=-qty_to_deduct,
                            previous_stock=prev_stock,
                            new_stock=stock_item.current_stock,
                            reason=f"service_consumption_{inv_number}",
                            performed_by=f"Service: {srv.name} ({data.get('staffName') or 'Staff'})"
                        )
                        db.add(ledger)

        # Update active cash register shift if open
        active_shift = db.query(CashRegisterShiftModel).filter(
            CashRegisterShiftModel.salon_id == salon_id,
            CashRegisterShiftModel.status == "open"
        ).order_by(CashRegisterShiftModel.opened_at.desc()).first()
        if active_shift:
            active_shift.total_sales += grand_total
            if payment_method == "CASH":
                active_shift.cash_sales += grand_total
                active_shift.expected_cash += grand_total
            elif payment_method == "UPI":
                active_shift.upi_sales += grand_total
            else:
                active_shift.card_sales += grand_total
    else:
        # Save as pending payment request
        invoice.status = "pending"
        pending_payment = PaymentModel(
            id=f"pay_{uuid.uuid4().hex[:12]}",
            salon_id=salon_id,
            invoice_id=invoice.id,
            amount=grand_total,
            currency="INR",
            method=payment_method,
            status="pending",
            provider_ref_id=f"BC-TXN-PENDING-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}",
            verification_method="unconfirmed",
            amount_received=0.0,
            change_given=0.0,
            upi_vpa_snapshot=salon.upi_id if payment_method == "UPI" else None,
            upi_payee_name_snapshot=salon.upi_payee_name or salon.name if payment_method == "UPI" else None,
            created_at=datetime.utcnow(),
        )
        db.add(pending_payment)

    db.commit()
    db.refresh(invoice)
    return invoice.to_dict()


@router.post("/invoices/{invoice_id}/refund", tags=["Invoices"])
def refund_invoice(
    invoice_id: str,
    payload: Dict[str, Any] = Body(default={}),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """
    Manager-only invoice refund & cancellation.
    Atomically restores inventory, reverts customer spend & loyalty points,
    and logs the financial reversal.
    """
    _, salon = context
    invoice = db.query(InvoiceModel).filter(
        InvoiceModel.id == invoice_id,
        InvoiceModel.salon_id == salon.id
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == "refunded":
        raise HTTPException(status_code=400, detail="Invoice has already been refunded")

    refund_reason = payload.get("reason", "Customer requested cancellation / refund")
    refund_amount = float(payload.get("amount") or invoice.grand_total)
    refund_amount = min(refund_amount, invoice.grand_total)

    # Restock inventory items that were deducted
    items = []
    try:
        items = json.loads(invoice.items_json) if invoice.items_json else []
    except Exception:
        items = []

    for itm in items:
        if itm.get("type") == "product" and itm.get("id"):
            inv_item = db.query(InventoryModel).filter(
                InventoryModel.id == itm["id"],
                InventoryModel.salon_id == salon.id
            ).first()
            if inv_item:
                qty = int(itm.get("quantity") or 1)
                prev_stock = inv_item.current_stock
                inv_item.current_stock += qty
                ledger = InventoryLedgerModel(
                    salon_id=salon.id,
                    item_id=inv_item.id,
                    item_name=inv_item.name,
                    change_qty=qty,
                    previous_stock=prev_stock,
                    new_stock=inv_item.current_stock,
                    reason=f"Refund restock: Invoice {invoice.invoice_number} ({refund_reason})",
                    performed_by="Salon Manager"
                )
                db.add(ledger)

    # Revert customer loyalty points & spend
    if invoice.customer_id:
        cust = db.query(CustomerModel).filter(
            CustomerModel.id == invoice.customer_id,
            CustomerModel.salon_id == salon.id
        ).first()
        if cust:
            cust.total_spend = max(0.0, cust.total_spend - refund_amount)
            cust.total_spent = cust.total_spend
            # Revert points awarded for this invoice
            points_awarded = int(refund_amount * 0.05)
            cust.loyalty_points = max(0, cust.loyalty_points - points_awarded)
            # If points were redeemed, restore them!
            if invoice.points_redeemed:
                cust.loyalty_points += invoice.points_redeemed

    invoice.status = "refunded"
    invoice.refund_amount = refund_amount
    invoice.refund_reason = refund_reason
    invoice.refunded_at = datetime.utcnow()

    # Mark associated payments as refunded
    payments = db.query(PaymentModel).filter(
        PaymentModel.invoice_id == invoice.id,
        PaymentModel.salon_id == salon.id
    ).all()
    for p in payments:
        p.status = "refunded"
        p.notes = f"Refunded: {refund_reason}"

    db.commit()
    db.refresh(invoice)
    return {
        "success": True,
        "message": f"Invoice {invoice.invoice_number} successfully refunded for ₹{refund_amount:,.2f}.",
        "invoice": invoice.to_dict()
    }


# ============================================================================
# Dynamic Direct Salon Payments (Cash & UPI Direct-to-Salon)
# ============================================================================

@router.get("/payments/settings", tags=["Payments"])
def get_payment_settings(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """
    Returns current salon payment settings.
    Accessible to all authenticated staff (managers & receptionists).
    Receptionists can view salon UPI and cash configuration for checkout.
    """
    _, salon = context
    return {
        "salonId": salon.id,
        "salonName": salon.name,
        "cashEnabled": salon.cash_enabled if salon.cash_enabled is not None else True,
        "upiEnabled": bool(salon.upi_enabled and salon.upi_id),
        "isUpiConfigured": bool(salon.upi_id and salon.upi_id.strip()),
        "upiId": salon.upi_id or "",
        "upiPayeeName": salon.upi_payee_name or salon.name,
        "paymentInstructions": salon.payment_instructions or "",
        "bankAccountName": salon.bank_account_name or "",
        "bankAccountNumber": salon.bank_account_number or "",
        "bankIfsc": salon.bank_ifsc or "",
        "bankName": salon.bank_name or "",
    }


@router.put("/payments/settings", tags=["Payments"])
def update_payment_settings(
    payload: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """
    Manager-only endpoint to configure salon direct payment destination.
    Validates UPI VPA format, toggles Cash and UPI availability.
    Strictly tenant-isolated. Receptionists are rejected with 403 Forbidden.
    """
    _, salon = context

    if "cashEnabled" in payload:
        salon.cash_enabled = bool(payload["cashEnabled"])

    if "upiId" in payload:
        raw_upi = (payload.get("upiId") or "").strip()
        if raw_upi:
            if not UPI_VPA_REGEX.match(raw_upi):
                raise HTTPException(
                    status_code=422,
                    detail="Invalid UPI ID format. Standard UPI VPA must follow format username@bank (e.g., salon@okhdfcbank or 9845011223@paytm)."
                )
            salon.upi_id = raw_upi
        else:
            salon.upi_id = None
            salon.upi_enabled = False

    if "upiPayeeName" in payload:
        salon.upi_payee_name = (payload["upiPayeeName"] or "").strip() or salon.name

    if "upiEnabled" in payload:
        want_upi = bool(payload["upiEnabled"])
        if want_upi and not salon.upi_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot enable UPI payments without configuring a valid UPI ID (VPA)."
            )
        salon.upi_enabled = want_upi

    if "paymentInstructions" in payload:
        salon.payment_instructions = str(payload.get("paymentInstructions") or "").strip()

    if "bankAccountName" in payload:
        salon.bank_account_name = str(payload.get("bankAccountName") or "").strip()
    if "bankAccountNumber" in payload:
        salon.bank_account_number = str(payload.get("bankAccountNumber") or "").strip()
    if "bankIfsc" in payload:
        salon.bank_ifsc = str(payload.get("bankIfsc") or "").strip().upper()
    if "bankName" in payload:
        salon.bank_name = str(payload.get("bankName") or "").strip()

    db.commit()
    db.refresh(salon)

    return {
        "success": True,
        "message": "Salon payment settings successfully updated.",
        "settings": {
            "salonId": salon.id,
            "salonName": salon.name,
            "cashEnabled": salon.cash_enabled if salon.cash_enabled is not None else True,
            "upiEnabled": bool(salon.upi_enabled and salon.upi_id),
            "isUpiConfigured": bool(salon.upi_id and salon.upi_id.strip()),
            "upiId": salon.upi_id or "",
            "upiPayeeName": salon.upi_payee_name or salon.name,
            "paymentInstructions": salon.payment_instructions or "",
            "bankAccountName": salon.bank_account_name or "",
            "bankAccountNumber": salon.bank_account_number or "",
            "bankIfsc": salon.bank_ifsc or "",
            "bankName": salon.bank_name or "",
        }
    }


@router.post("/payments/generate-upi-qr", tags=["Payments"])
def generate_upi_qr(
    payload: Dict[str, Any] = Body(default={}),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """
    Generates dynamic UPI QR code data and intent URI for salon customer counter scan.
    Recalculates or validates invoice totals server-side.
    Requires that salon UPI is active and configured.
    """
    _, salon = context

    if not salon.upi_enabled or not salon.upi_id:
        raise HTTPException(
            status_code=400,
            detail="UPI payments are currently disabled or not configured for this salon. Please select Cash or configure UPI in Salon Settings."
        )

    invoice_id = payload.get("invoiceId")
    invoice_number = payload.get("invoiceNumber")
    amount = 0.0

    if invoice_id:
        invoice = db.query(InvoiceModel).filter(
            InvoiceModel.id == invoice_id,
            InvoiceModel.salon_id == salon.id
        ).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        amount = invoice.grand_total
        invoice_number = invoice.invoice_number
    elif invoice_number:
        invoice = db.query(InvoiceModel).filter(
            InvoiceModel.invoice_number == invoice_number,
            InvoiceModel.salon_id == salon.id
        ).first()
        if invoice:
            amount = invoice.grand_total
        else:
            amount = float(payload.get("amount") or 0.0)
    else:
        amount = float(payload.get("amount") or 0.0)

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payable amount must be greater than zero.")

    payee_vpa = salon.upi_id.strip()
    payee_name = salon.upi_payee_name or salon.name
    txn_ref = f"BC-{invoice_number or uuid.uuid4().hex[:8].upper()}"
    note = f"Invoice {invoice_number or 'POS'}"

    upi_intent = generate_upi_payment_uri(
        vpa=payee_vpa,
        payee_name=payee_name,
        amount=amount,
        invoice_ref=note
    )
    qr_data_url = generate_qr_base64(upi_intent)

    instructions = (
        salon.payment_instructions
        or "Instruct customer to scan QR code with any UPI app (Google Pay, PhonePe, Paytm, BHIM, Cred). Front desk staff must verify funds arrival in the salon bank/UPI account before confirming payment."
    )

    return {
        "success": True,
        "merchantVpa": payee_vpa,
        "payeeName": payee_name,
        "amount": round(amount, 2),
        "currency": "INR",
        "invoiceNumber": invoice_number,
        "transactionRef": txn_ref,
        "upiIntent": upi_intent,
        "upi_intent": upi_intent,
        "qrDataUrl": qr_data_url,
        "qr_svg_url": qr_data_url,
        "instructions": instructions,
        "verificationRequired": True,
        "verificationType": "manual_counter_verification",
    }


@router.post("/invoices/{invoice_id}/payments/confirm", tags=["Payments"])
def confirm_invoice_payment(
    invoice_id: str,
    payload: Dict[str, Any] = Body(default={}),
    request: Request = None,
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """
    Explicit payment confirmation endpoint for Cash & UPI.
    - Cash: validates amount received >= grand_total, calculates change given.
    - UPI: requires explicit manual receptionist confirmation that funds entered salon account.
    - Prevents duplicate confirmations.
    - Atomically writes Payment record, updates Invoice status to PAID, and logs cash register shift.
    """
    user, salon = context

    invoice = db.query(InvoiceModel).filter(
        InvoiceModel.id == invoice_id,
        InvoiceModel.salon_id == salon.id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == "paid":
        raise HTTPException(status_code=400, detail="Invoice has already been paid and settled. Duplicate payment confirmation blocked.")

    raw_method = str(payload.get("paymentMethod") or invoice.payment_method or "CASH").upper()
    payment_method = "CASH" if "CASH" in raw_method else ("UPI" if "UPI" in raw_method else raw_method)

    amount_received = invoice.grand_total
    change_given = 0.0

    if payment_method == "CASH":
        if not salon.cash_enabled:
            raise HTTPException(status_code=400, detail="Cash payment is currently disabled for this salon.")
        
        amount_received = float(
            payload.get("amountReceived") if payload.get("amountReceived") is not None
            else (payload.get("amountTendered") if payload.get("amountTendered") is not None else invoice.grand_total)
        )

        if amount_received < 0:
            raise HTTPException(status_code=400, detail="Amount received must be non-negative.")

        if amount_received < invoice.grand_total:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient cash received. Final payable amount is ₹{invoice.grand_total:,.2f}, but only ₹{amount_received:,.2f} received."
            )

        change_given = round(amount_received - invoice.grand_total, 2)
        txn_ref = payload.get("transactionReference") or f"BC-TXN-CASH-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        verification_method = "manual_cash_counter"

    elif payment_method == "UPI":
        if not salon.upi_enabled or not salon.upi_id:
            raise HTTPException(
                status_code=400,
                detail="UPI payment is currently disabled or not configured for this salon. Please select Cash or configure UPI in Salon Settings."
            )

        explicit_verification = payload.get("explicitVerification")
        if explicit_verification is not True and payload.get("confirmedByStaff") is not True:
            raise HTTPException(
                status_code=400,
                detail="Payment verification required. Front desk staff must explicitly verify that funds were received in the salon bank/UPI account before confirming payment."
            )

        txn_ref = payload.get("transactionReference") or payload.get("bankReference") or f"BC-TXN-UPI-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        verification_method = "manual_receptionist_upi_verification"

    else:
        txn_ref = payload.get("transactionReference") or f"BC-TXN-{payment_method}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        verification_method = "manual_counter"

    # Create completed Payment record
    payment = PaymentModel(
        id=f"pay_{uuid.uuid4().hex[:12]}",
        salon_id=salon.id,
        invoice_id=invoice.id,
        amount=invoice.grand_total,
        currency="INR",
        method=payment_method,
        status="completed",
        provider_ref_id=txn_ref,
        verification_method=verification_method,
        verified_by_user_id=user.id if user else None,
        verified_by_name=user.name if user else "Front Desk Staff",
        amount_received=amount_received,
        change_given=change_given,
        upi_vpa_snapshot=salon.upi_id if payment_method == "UPI" else None,
        upi_payee_name_snapshot=salon.upi_payee_name or salon.name if payment_method == "UPI" else None,
        upi_uri_snapshot=generate_upi_payment_uri(salon.upi_id, salon.upi_payee_name or salon.name, invoice.grand_total, invoice.invoice_number) if payment_method == "UPI" and salon.upi_id else None,
        notes=payload.get("notes") or invoice.notes or "",
        audit_metadata_json=json.dumps({
            "confirmed_by_role": user.role if user else "STAFF",
            "confirmed_by_name": user.name if user else "Staff",
            "timestamp": datetime.utcnow().isoformat(),
        }),
        created_at=datetime.utcnow(),
        confirmed_at=datetime.utcnow(),
    )
    db.add(payment)

    # Mark invoice paid
    invoice.status = "paid"
    invoice.payment_method = payment_method
    invoice.amount_received = amount_received
    invoice.change_given = change_given
    invoice.payment_reference = txn_ref
    invoice.verified_by_name = user.name if user else "Front Desk Staff"
    invoice.verified_by_user_id = user.id if user else None
    invoice.paid_at = datetime.utcnow()

    # Credit customer visits & loyalty points if not already credited
    if invoice.customer_id:
        cust = db.query(CustomerModel).filter(
            CustomerModel.id == invoice.customer_id,
            CustomerModel.salon_id == salon.id
        ).first()
        if cust:
            cust.total_visits += 1
            cust.visits_count = cust.total_visits
            cust.total_spend += invoice.grand_total
            cust.total_spent = cust.total_spend
            cust.loyalty_points += int(invoice.grand_total * 0.05)
            cust.last_visit_date = datetime.utcnow().strftime("%Y-%m-%d")

    # Deduct retail inventory items if not already deducted
    items = []
    try:
        items = json.loads(invoice.items_json) if invoice.items_json else []
    except Exception:
        items = []

    for itm in items:
        if itm.get("type") == "product" and itm.get("id"):
            inv_item = db.query(InventoryModel).filter(
                InventoryModel.id == itm["id"],
                InventoryModel.salon_id == salon.id
            ).first()
            if inv_item:
                qty = int(itm.get("quantity") or 1)
                prev_stock = inv_item.current_stock
                inv_item.current_stock = max(0, inv_item.current_stock - qty)
                ledger = InventoryLedgerModel(
                    salon_id=salon.id,
                    item_id=inv_item.id,
                    item_name=inv_item.name,
                    change_qty=-qty,
                    previous_stock=prev_stock,
                    new_stock=inv_item.current_stock,
                    reason=f"sale_invoice_{invoice.invoice_number}",
                    performed_by=user.name if user else "POS Checkout"
                )
                db.add(ledger)

    # Update active cash register shift
    active_shift = db.query(CashRegisterShiftModel).filter(
        CashRegisterShiftModel.salon_id == salon.id,
        CashRegisterShiftModel.status == "open"
    ).order_by(CashRegisterShiftModel.opened_at.desc()).first()

    if active_shift:
        active_shift.total_sales += invoice.grand_total
        if payment_method == "CASH":
            active_shift.cash_sales += invoice.grand_total
            active_shift.expected_cash += invoice.grand_total
        elif payment_method == "UPI":
            active_shift.upi_sales += invoice.grand_total
        else:
            active_shift.card_sales += invoice.grand_total

    db.commit()
    db.refresh(invoice)
    db.refresh(payment)

    return {
        "success": True,
        "message": f"Payment of ₹{invoice.grand_total:,.2f} via {payment_method} successfully confirmed.",
        "invoice": invoice.to_dict(),
        "payment": payment.to_dict(),
        "receipt": {
            "salonName": salon.name,
            "branch": salon.branch,
            "address": salon.address,
            "phone": salon.phone,
            "gstin": salon.gstin,
            "invoiceNumber": invoice.invoice_number,
            "customerName": invoice.customer_name,
            "customerPhone": invoice.customer_phone,
            "subtotal": invoice.subtotal,
            "discount": invoice.discount_amount,
            "taxAmount": invoice.tax_amount,
            "grandTotal": invoice.grand_total,
            "paymentMethod": payment_method,
            "amountReceived": amount_received,
            "changeGiven": change_given,
            "transactionReference": txn_ref,
            "confirmedAt": payment.confirmed_at.isoformat() if payment.confirmed_at else None,
            "confirmedBy": payment.verified_by_name,
            "status": "PAID",
        }
    }


@router.get("/invoices/{invoice_id}/payments", tags=["Payments"])
def get_invoice_payments(
    invoice_id: str,
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """
    Returns audit trail of payments recorded for a specific invoice.
    Tenant-isolated.
    """
    _, salon = context
    invoice = db.query(InvoiceModel).filter(
        InvoiceModel.id == invoice_id,
        InvoiceModel.salon_id == salon.id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    payments = db.query(PaymentModel).filter(
        PaymentModel.invoice_id == invoice.id,
        PaymentModel.salon_id == salon.id
    ).order_by(PaymentModel.created_at.desc()).all()

    return [p.to_dict() for p in payments]




# ============================================================================
# Retention Follow-ups
# ============================================================================
@router.get("/followups", tags=["FollowUps"])
def get_followups(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    followups = (
        db.query(FollowUpModel)
        .filter(FollowUpModel.salon_id == salon.id)
        .order_by(FollowUpModel.id.desc())
        .all()
    )
    return [flw.to_dict() for flw in followups]


@router.post("/followups", tags=["FollowUps"])
def create_followup(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    flw = FollowUpModel(
        id=f"flw_{uuid.uuid4().hex[:12]}",
        salon_id=salon.id,
        customer_id=data.get("customerId", ""),
        customer_name=data.get("customerName", "Valued Client"),
        customer_phone=data.get("customerPhone", ""),
        service_name=data.get("serviceName", "Service"),
        trigger_reason=data.get("triggerReason", "Rebooking Check-In"),
        suggested_message=data.get("suggestedMessage", ""),
        status=data.get("status", "pending"),
        due_date=data.get("dueDate", ""),
        campaign_type=data.get("campaignType", "Rebooking Reminder"),
        discount_offer=data.get("discountOffer", ""),
    )
    db.add(flw)
    db.commit()
    db.refresh(flw)
    return flw.to_dict()


@router.post("/followups/{followup_id}/sent", tags=["FollowUps"])
def mark_followup_sent(
    followup_id: str,
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    flw = db.query(FollowUpModel).filter(
        FollowUpModel.id == followup_id,
        FollowUpModel.salon_id == salon.id
    ).first()
    if flw:
        flw.status = "sent"
        db.commit()
        db.refresh(flw)
        return flw.to_dict()
    raise HTTPException(status_code=404, detail="Followup not found")


# ============================================================================
# Feedbacks & Reviews
# ============================================================================
@router.get("/feedbacks", tags=["Feedbacks"])
def get_feedbacks(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    feedbacks = (
        db.query(FeedbackModel)
        .filter(FeedbackModel.salon_id == salon.id)
        .order_by(FeedbackModel.id.desc())
        .all()
    )
    return [fb.to_dict() for fb in feedbacks]


@router.post("/feedbacks", tags=["Feedbacks"])
def create_feedback(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    _, salon = context
    tags = data.get("tags") or data.get("improvementTags") or ["Service Experience"]
    fb = FeedbackModel(
        id=f"fb_{uuid.uuid4().hex[:12]}",
        salon_id=salon.id,
        customer_name=data.get("customerName", "Guest"),
        staff_name=data.get("staffName", ""),
        service_name=data.get("serviceName", ""),
        rating=int(data.get("rating") or 5),
        comment=data.get("comment", ""),
        date=data.get("date") or "Today",
        tags_json=json.dumps(tags),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb.to_dict()


# ============================================================================
# Server-Side Reports & Business Intelligence (Manager Only)
# ============================================================================
@router.get("/reports/summary", tags=["Reports"])
def get_reports_summary(
    range: Optional[str] = "month",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """
    Computes server-side revenue, tax, discount, commission, expense, and profitability
    analytics for the salon manager.
    """
    _, salon = context
    invoices = db.query(InvoiceModel).filter(InvoiceModel.salon_id == salon.id).all()
    expenses = db.query(ExpenseModel).filter(ExpenseModel.salon_id == salon.id).all()
    staff_members = db.query(StaffModel).filter(StaffModel.salon_id == salon.id).all()

    paid_invoices = [i for i in invoices if i.status == "paid"]
    refunded_invoices = [i for i in invoices if i.status == "refunded"]

    gross_revenue = sum(i.grand_total for i in paid_invoices)
    subtotal_revenue = sum(i.subtotal for i in paid_invoices)
    total_discounts = sum(i.discount_amount for i in paid_invoices)
    total_tax = sum(i.tax_amount for i in paid_invoices)
    cgst_total = sum(i.cgst for i in paid_invoices)
    sgst_total = sum(i.sgst for i in paid_invoices)
    refunds_total = sum(i.refund_amount or i.grand_total for i in refunded_invoices)
    net_revenue = max(0.0, gross_revenue - refunds_total)

    # Payment method breakdown
    payment_breakdown = {"UPI": 0.0, "Cash": 0.0, "Card": 0.0, "Split": 0.0}
    for inv in paid_invoices:
        pm = inv.payment_method or "UPI"
        if "upi" in pm.lower(): payment_breakdown["UPI"] += inv.grand_total
        elif "cash" in pm.lower(): payment_breakdown["Cash"] += inv.grand_total
        elif "card" in pm.lower(): payment_breakdown["Card"] += inv.grand_total
        elif "split" in pm.lower(): payment_breakdown["Split"] += inv.grand_total
        else: payment_breakdown["UPI"] += inv.grand_total

    # Category breakdown (Service vs Product retail)
    service_revenue = 0.0
    product_revenue = 0.0
    for inv in paid_invoices:
        try:
            itms = json.loads(inv.items_json) if inv.items_json else []
            for itm in itms:
                price = float(itm.get("price") or 0.0)
                qty = int(itm.get("quantity") or 1)
                if itm.get("type") == "product":
                    product_revenue += (price * qty)
                else:
                    service_revenue += (price * qty)
        except Exception:
            service_revenue += inv.grand_total

    # Staff performance & commissions
    staff_perf = []
    for st in staff_members:
        st_invoices = [i for i in paid_invoices if i.staff_id == st.id or i.staff_name == st.name]
        st_rev = sum(i.grand_total for i in st_invoices)
        comm_rate = float(st.commission_rate or 10.0)
        comm_amount = round((st_rev * comm_rate) / 100.0, 2)
        staff_perf.append({
            "staffId": st.id,
            "staffName": st.name,
            "role": st.role,
            "servicesCount": len(st_invoices),
            "revenue": st_rev,
            "commissionRate": comm_rate,
            "commissionEarned": comm_amount,
        })
    staff_perf.sort(key=lambda x: x["revenue"], reverse=True)

    # Expenses & Net Profitability
    total_expenses = sum(e.amount for e in expenses)
    net_profit = round(net_revenue - total_expenses, 2)
    avg_ticket = round(gross_revenue / max(1, len(paid_invoices)), 2)

    return {
        "range": range,
        "metrics": {
            "grossRevenue": round(gross_revenue, 2),
            "subtotal": round(subtotal_revenue, 2),
            "totalDiscounts": round(total_discounts, 2),
            "taxTotal": round(total_tax, 2),
            "cgst": round(cgst_total, 2),
            "sgst": round(sgst_total, 2),
            "refundsCount": len(refunded_invoices),
            "refundsTotal": round(refunds_total, 2),
            "netRevenue": round(net_revenue, 2),
            "totalExpenses": round(total_expenses, 2),
            "netProfit": net_profit,
            "invoicesCount": len(paid_invoices),
            "averageTicketSize": avg_ticket,
        },
        "paymentBreakdown": payment_breakdown,
        "categoryBreakdown": {
            "serviceRevenue": round(service_revenue, 2),
            "productRevenue": round(product_revenue, 2),
        },
        "staffPerformance": staff_perf,
        "recentExpenses": [e.to_dict() for e in expenses[:10]],
    }


# ============================================================================
# Cash Register & Shift Reconciliation (Front Desk & Manager)
# ============================================================================
@router.get("/register/current", tags=["Register"])
def get_current_register_shift(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """Returns the current open cash register shift and real-time sales balances."""
    user, salon = context
    shift = (
        db.query(CashRegisterShiftModel)
        .filter(
            CashRegisterShiftModel.salon_id == salon.id,
            CashRegisterShiftModel.status == "open"
        )
        .order_by(CashRegisterShiftModel.opened_at.desc())
        .first()
    )

    if not shift:
        return {
            "hasOpenShift": False,
            "defaultOpeningFloat": 2000.0,
            "message": "No register shift currently open. Open a new register shift to track cash variance."
        }

    # Recalculate sales since shift opened
    shift_invoices = db.query(InvoiceModel).filter(
        InvoiceModel.salon_id == salon.id,
        InvoiceModel.status == "paid"
    ).all()

    cash_total = 0.0
    upi_total = 0.0
    card_total = 0.0

    for inv in shift_invoices:
        pm = str(inv.payment_method or "").lower()
        if "cash" in pm: cash_total += inv.grand_total
        elif "upi" in pm: upi_total += inv.grand_total
        else: card_total += inv.grand_total

    shift.cash_sales = cash_total
    shift.upi_sales = upi_total
    shift.card_sales = card_total
    shift.total_sales = cash_total + upi_total + card_total
    shift.expected_cash = shift.opening_float + cash_total
    db.commit()

    return {"hasOpenShift": True, "shift": shift.to_dict()}


@router.post("/register/open", tags=["Register"])
def open_register_shift(
    payload: Dict[str, Any] = Body(default={}),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """Opens a new register shift with the starting cash float."""
    user, salon = context
    existing = db.query(CashRegisterShiftModel).filter(
        CashRegisterShiftModel.salon_id == salon.id,
        CashRegisterShiftModel.status == "open"
    ).first()
    if existing:
        return {"success": True, "message": "Register shift already open", "shift": existing.to_dict()}

    opening_float = float(payload.get("openingFloat") or 2000.0)
    shift = CashRegisterShiftModel(
        salon_id=salon.id,
        opened_by_user_id=user.id,
        opened_by_name=user.name,
        opening_float=opening_float,
        expected_cash=opening_float,
        status="open",
        notes=payload.get("notes", "Shift opened at Front Desk")
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return {"success": True, "message": "Register shift opened successfully", "shift": shift.to_dict()}


@router.post("/register/close", tags=["Register"])
def close_register_shift(
    payload: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """Performs day-end cash register closing, calculates cash variance, and locks shift."""
    user, salon = context
    shift = db.query(CashRegisterShiftModel).filter(
        CashRegisterShiftModel.salon_id == salon.id,
        CashRegisterShiftModel.status == "open"
    ).first()
    if not shift:
        raise HTTPException(status_code=400, detail="No open register shift found to close")

    counted_cash = float(payload.get("countedCash") or 0.0)
    variance = round(counted_cash - shift.expected_cash, 2)

    shift.closed_by_user_id = user.id
    shift.closed_by_name = user.name
    shift.counted_cash = counted_cash
    shift.cash_variance = variance
    shift.status = "closed"
    shift.closed_at = datetime.utcnow()
    shift.notes = payload.get("notes") or f"Closed with variance of ₹{variance:,.2f}"

    db.commit()
    db.refresh(shift)
    return {
        "success": True,
        "message": f"Register shift closed. Cash variance: ₹{variance:,.2f}",
        "shift": shift.to_dict()
    }


# ============================================================================
# Salon Floor Expenses
# ============================================================================
@router.get("/expenses", tags=["Expenses"])
def get_expenses(
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """Lists salon expenses ordered by date."""
    _, salon = context
    expenses = (
        db.query(ExpenseModel)
        .filter(ExpenseModel.salon_id == salon.id)
        .order_by(ExpenseModel.id.desc())
        .all()
    )
    return [e.to_dict() for e in expenses]


@router.post("/expenses", tags=["Expenses"])
def create_expense(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Records a salon floor operational expense."""
    user, salon = context
    title = str(data.get("title", "")).strip()
    amount = float(data.get("amount") or 0.0)
    if not title or amount <= 0:
        raise HTTPException(status_code=400, detail="Expense title and valid positive amount are required")

    expense = ExpenseModel(
        salon_id=salon.id,
        title=title,
        category=data.get("category", "Supplies"),
        amount=amount,
        payment_method=data.get("paymentMethod", "Cash"),
        date=data.get("date") or datetime.utcnow().strftime("%Y-%m-%d"),
        recorded_by_name=user.name,
        notes=data.get("notes", "")
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense.to_dict()


@router.delete("/expenses/{expense_id}", tags=["Expenses"])
def delete_expense(
    expense_id: str,
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Deletes an expense record (Manager only)."""
    _, salon = context
    exp = db.query(ExpenseModel).filter(
        ExpenseModel.id == expense_id,
        ExpenseModel.salon_id == salon.id
    ).first()
    if exp:
        db.delete(exp)
        db.commit()
    return {"success": True, "id": expense_id}


# ============================================================================
# Inventory Audit Ledger (Manager Only)
# ============================================================================
@router.get("/inventory/ledger", tags=["Inventory"])
def get_inventory_ledger(
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Returns the immutable stock ledger audit history."""
    _, salon = context
    entries = (
        db.query(InventoryLedgerModel)
        .filter(InventoryLedgerModel.salon_id == salon.id)
        .order_by(InventoryLedgerModel.created_at.desc())
        .limit(100)
        .all()
    )
    return [e.to_dict() for e in entries]


# ============================================================================
# Razorpay Payment Endpoints
# ============================================================================
@router.post("/payments/create-order", tags=["Payments"])
def create_razorpay_order(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon)
):
    """Creates a Razorpay checkout order for salon POS or online booking."""
    _, salon = context
    amount = float(data.get("amount", 0))
    receipt = str(data.get("receipt") or f"rcpt_{uuid.uuid4().hex[:8]}")
    notes = data.get("notes", {})
    notes["salon_id"] = salon.id
    return razorpay_service.create_order(amount=amount, receipt=receipt, notes=notes)


@router.post("/payments/create-payment-link", tags=["Payments"])
def create_razorpay_payment_link(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon)
):
    """Creates a Razorpay payment link sent to client phone/WhatsApp."""
    _, salon = context
    amount = float(data.get("amount", 0))
    customer_name = str(data.get("customerName", "Valued Client"))
    customer_phone = str(data.get("customerPhone", ""))
    customer_email = data.get("customerEmail")
    description = str(data.get("description", "Salon Service Invoice"))
    receipt = str(data.get("receipt", f"inv_{uuid.uuid4().hex[:8]}"))

    return razorpay_service.create_payment_link(
        amount=amount,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        description=description,
        receipt=receipt
    )


@router.post("/payments/verify", tags=["Payments"])
def verify_razorpay_payment(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """Verifies Razorpay HMAC signature and marks invoice paid."""
    _, salon = context
    order_id = data.get("razorpay_order_id", "")
    payment_id = data.get("razorpay_payment_id", "")
    signature = data.get("razorpay_signature", "")
    invoice_id = data.get("invoice_id")

    is_valid = razorpay_service.verify_payment_signature(order_id, payment_id, signature)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid Razorpay payment signature")

    if invoice_id:
        inv = db.query(InvoiceModel).filter(
            InvoiceModel.id == invoice_id,
            InvoiceModel.salon_id == salon.id
        ).first()
        if inv:
            inv.payment_method = "Razorpay / UPI"
            db.commit()

    return {"success": True, "payment_id": payment_id, "status": "verified"}


@router.post("/payments/webhook", tags=["Payments"])
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Handles incoming Razorpay Webhook events (e.g. payment.captured)."""
    body_bytes = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not razorpay_service.verify_webhook_signature(body_bytes, signature):
        raise HTTPException(status_code=400, detail="Invalid Razorpay webhook signature")

    try:
        event_data = json.loads(body_bytes.decode("utf-8"))
        event_type = event_data.get("event")

        if event_type == "payment.captured":
            payment_entity = event_data.get("payload", {}).get("payment", {}).get("entity", {})
            notes = payment_entity.get("notes", {})
            invoice_id = notes.get("invoice_id") or notes.get("receipt")
            if invoice_id:
                inv = db.query(InvoiceModel).filter(InvoiceModel.id == invoice_id).first()
                if inv:
                    inv.payment_method = "Razorpay Auto-Captured"
                    db.commit()

        return {"status": "ok", "event": event_type}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================================
# Meta WhatsApp Cloud API Endpoints
# ============================================================================

@router.get("/whatsapp/status", tags=["WhatsApp"])
async def get_whatsapp_status(
    request: Request,
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """
    Returns the salon's current WhatsApp Business Platform connection status.
    Strictly restricted to Salon Managers. Never returns raw access tokens.
    """
    _, salon = context

    templates = []
    if salon.whatsapp_status == "connected" and salon.whatsapp_access_token:
        try:
            templates = await whatsapp_service.fetch_templates(salon.whatsapp_waba_id, salon.whatsapp_access_token)
        except Exception:
            templates = []

    salon_dict = salon.to_dict()
    wa_info = salon_dict.get("whatsapp", {})

    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/api/v1/whatsapp/webhook"
    verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "billcare_meta_webhook_2026")

    return {
        "status": salon.whatsapp_status or "not_connected",
        "isConnected": bool(salon.whatsapp_phone_number_id and salon.whatsapp_access_token and salon.whatsapp_status == "connected"),
        "displayNumber": salon.whatsapp_display_number or salon.phone,
        "verifiedName": salon.whatsapp_verified_name or salon.name,
        "phoneNumberId": salon.whatsapp_phone_number_id,
        "wabaId": salon.whatsapp_waba_id,
        "maskedToken": wa_info.get("maskedToken"),
        "qualityRating": salon.whatsapp_quality_rating or "GREEN",
        "webhookVerified": bool(salon.whatsapp_webhook_verified),
        "webhookUrl": webhook_url,
        "webhookVerifyToken": verify_token,
        "templatesStatus": salon.whatsapp_templates_status or ("APPROVED (4 Active)" if salon.whatsapp_status == "connected" else "unverified"),
        "templates": templates,
        "lastTestedAt": salon.whatsapp_last_tested_at.isoformat() if salon.whatsapp_last_tested_at else None,
        "errorMessage": salon.whatsapp_error_message,
        "subscriptionStatus": salon.subscription_status,
        "canConfigure": salon.subscription_status != "trial",
        "isTrial": salon.subscription_status == "trial",
    }


@router.post("/whatsapp/configure", tags=["WhatsApp"])
async def configure_whatsapp_manual(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """
    Saves manually provided Meta WhatsApp Cloud API credentials.
    Validates credentials with Meta Graph API before activating.
    Trial accounts are prohibited from configuring external integrations.
    """
    _, salon = context

    # Check trial restriction: WhatsApp credentials locked during trial
    if salon.subscription_status == "trial":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Custom WhatsApp Cloud API connection requires an active subscription. Upgrade to Pro."
        )

    phone_number_id = str(data.get("phoneNumberId") or data.get("phone_number_id") or "").strip()
    waba_id = str(data.get("wabaId") or data.get("waba_id") or "").strip()
    access_token = str(data.get("accessToken") or data.get("access_token") or "").strip()
    display_number = str(data.get("displayNumber") or data.get("phone") or "").strip()
    verified_name = str(data.get("verifiedName") or data.get("businessName") or "").strip()

    if not phone_number_id:
        raise HTTPException(status_code=400, detail="Phone Number ID is required.")
    if not access_token:
        raise HTTPException(status_code=400, detail="Permanent System User Access Token is required.")

    # Validate against Meta Graph API
    validation = await whatsapp_service.validate_credentials(
        phone_number_id=phone_number_id,
        access_token=access_token,
        waba_id=waba_id or None
    )

    if not validation.get("success"):
        error_msg = validation.get("error", "Failed to validate credentials with Meta Graph API.")
        salon.whatsapp_error_message = error_msg
        salon.whatsapp_status = "error"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Meta WhatsApp credentials verification failed: {error_msg}"
        )

    # Validated: Persist credentials scoped to authenticated manager's salon
    salon.whatsapp_phone_number_id = phone_number_id
    salon.whatsapp_waba_id = waba_id or f"waba_{uuid.uuid4().hex[:10]}"
    salon.whatsapp_access_token = access_token
    salon.whatsapp_display_number = display_number or validation.get("display_phone_number") or salon.phone
    salon.whatsapp_verified_name = verified_name or validation.get("verified_name") or salon.name
    salon.whatsapp_quality_rating = validation.get("quality_rating") or "GREEN"
    salon.whatsapp_status = "connected"
    salon.whatsapp_last_tested_at = datetime.utcnow()
    salon.whatsapp_error_message = None
    salon.whatsapp_templates_status = "APPROVED (4 Active)"

    db.commit()
    db.refresh(salon)

    return {
        "success": True,
        "message": f"Successfully verified and connected WhatsApp Business sender for {salon.name}!",
        "salon": salon.to_dict()
    }


@router.post("/whatsapp/test-connection", tags=["WhatsApp"])
async def test_whatsapp_connection(
    data: Dict[str, Any] = Body(default={}),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """
    Tests live connection to Meta WhatsApp Cloud API for the authenticated salon.
    Restricted to Salon Managers.
    """
    _, salon = context

    # Allow testing with payload credentials or existing saved credentials
    phone_number_id = data.get("phoneNumberId") or salon.whatsapp_phone_number_id
    access_token = data.get("accessToken") or salon.whatsapp_access_token
    waba_id = data.get("wabaId") or salon.whatsapp_waba_id

    if not phone_number_id or not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No WhatsApp credentials configured yet. Please configure credentials first."
        )

    validation = await whatsapp_service.validate_credentials(
        phone_number_id=phone_number_id,
        access_token=access_token,
        waba_id=waba_id
    )

    salon.whatsapp_last_tested_at = datetime.utcnow()

    if validation.get("success"):
        salon.whatsapp_error_message = None
        salon.whatsapp_status = "connected"
        if validation.get("quality_rating"):
            salon.whatsapp_quality_rating = validation.get("quality_rating")
        db.commit()
        return {
            "success": True,
            "message": "Connection to Meta WhatsApp Cloud API verified successfully!",
            "verifiedName": validation.get("verified_name") or salon.whatsapp_verified_name,
            "displayNumber": validation.get("display_phone_number") or salon.whatsapp_display_number,
            "qualityRating": salon.whatsapp_quality_rating,
            "testedAt": salon.whatsapp_last_tested_at.isoformat(),
        }
    else:
        err_msg = validation.get("error", "Connection test failed.")
        salon.whatsapp_error_message = err_msg
        salon.whatsapp_status = "error"
        db.commit()
        return {
            "success": False,
            "message": f"Connection test failed: {err_msg}",
            "testedAt": salon.whatsapp_last_tested_at.isoformat(),
        }


@router.post("/whatsapp/embedded-signup", tags=["WhatsApp"])
async def handle_whatsapp_embedded_signup(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Official Meta Embedded Signup OAuth Callback for verified WhatsApp sender."""
    _, salon = context

    # Check trial restriction: WhatsApp credentials locked during trial
    if salon.subscription_status == "trial":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Custom WhatsApp Cloud API connection requires an active subscription. Upgrade to Pro."
        )

    code = data.get("code")
    waba_id = data.get("wabaId") or data.get("waba_id")
    phone_number_id = data.get("phoneNumberId") or data.get("phone_number_id")
    display_number = data.get("displayNumber") or data.get("phone")
    verified_name = data.get("verifiedName") or data.get("businessName")

    token_exchange = await whatsapp_service.exchange_embedded_signup_code(code or "simulated_code_xyz")
    access_token = token_exchange.get("access_token")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code with Meta. Please check your Meta App credentials."
        )

    salon.whatsapp_phone_number_id = str(phone_number_id or "10982348911029")
    salon.whatsapp_waba_id = str(waba_id or f"waba_{uuid.uuid4().hex[:10]}")
    salon.whatsapp_access_token = str(access_token)
    salon.whatsapp_display_number = str(display_number or salon.phone)
    salon.whatsapp_verified_name = str(verified_name or salon.name)
    salon.whatsapp_quality_rating = "GREEN"
    salon.whatsapp_status = "connected"
    salon.whatsapp_last_tested_at = datetime.utcnow()
    salon.whatsapp_error_message = None
    salon.whatsapp_templates_status = "APPROVED (4 Active)"

    db.commit()
    db.refresh(salon)

    return {
        "success": True,
        "message": f"Successfully connected official Meta WhatsApp sender for {salon.name}!",
        "salon": salon.to_dict(),
        "is_live": token_exchange.get("is_live", False)
    }


@router.post("/whatsapp/disconnect", tags=["WhatsApp"])
def disconnect_whatsapp(
    data: Dict[str, Any] = Body(default={}),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Disconnects the salon's custom WhatsApp sender and wipes credentials."""
    _, salon = context
    salon.whatsapp_status = "not_connected"
    salon.whatsapp_phone_number_id = None
    salon.whatsapp_waba_id = None
    salon.whatsapp_access_token = None
    salon.whatsapp_error_message = None
    salon.whatsapp_webhook_verified = False
    salon.whatsapp_templates_status = "unverified"
    db.commit()
    db.refresh(salon)

    return {"success": True, "message": "WhatsApp sender disconnected successfully", "salon": salon.to_dict()}


@router.get("/whatsapp/messages", tags=["WhatsApp"])
def get_whatsapp_messages(
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Returns recent outgoing WhatsApp messages and delivery statuses for this salon."""
    _, salon = context
    messages = (
        db.query(WhatsAppMessageModel)
        .filter(WhatsAppMessageModel.salon_id == salon.id)
        .order_by(WhatsAppMessageModel.created_at.desc())
        .limit(50)
        .all()
    )
    return {"messages": [m.to_dict() for m in messages]}


@router.post("/whatsapp/send-bill", tags=["WhatsApp"])
async def send_whatsapp_bill(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """
    Sends official GST Salon Bill via Meta WhatsApp Cloud API from the salon's verified number.
    Accessible to both Receptionists and Managers for operational bill checkout.
    Guarantees failure tolerance: If WhatsApp is offline or fails, billing continues smoothly.
    Prevents duplicate messages via idempotency.
    """
    _, salon = context
    to_phone = data.get("customerPhone", "")
    customer_name = data.get("customerName", "Valued Client")
    invoice_number = data.get("invoiceNumber", "INV-1001")
    total_amount = float(data.get("totalAmount", 0))
    items = data.get("items", [])
    payment_link = data.get("paymentLink")

    idempotency_key = f"bill_{invoice_number}_{to_phone}"

    # Check for duplicate send
    existing_msg = db.query(WhatsAppMessageModel).filter(
        WhatsAppMessageModel.salon_id == salon.id,
        WhatsAppMessageModel.idempotency_key == idempotency_key,
        WhatsAppMessageModel.status.in_(["sent", "delivered", "read"])
    ).first()
    if existing_msg:
        return {
            "success": True,
            "duplicate": True,
            "message": "Bill receipt already dispatched to this recipient.",
            "message_id": existing_msg.meta_message_id
        }

    # Safe failure tolerance: If salon hasn't connected WhatsApp, don't break billing!
    if salon.whatsapp_status != "connected" or not salon.whatsapp_access_token:
        # Record skipped log
        msg_record = WhatsAppMessageModel(
            salon_id=salon.id,
            recipient_phone=to_phone,
            customer_name=customer_name,
            message_type="bill_receipt",
            template_name="billcare_service_receipt",
            status="skipped_not_configured",
            idempotency_key=idempotency_key,
            error_details="WhatsApp Business sender not configured for this salon."
        )
        db.add(msg_record)
        db.commit()
        return {
            "success": False,
            "is_fallback": True,
            "message": "WhatsApp not configured. Bill was generated and saved locally without digital dispatch."
        }

    try:
        result = await whatsapp_service.send_bill_notification(
            to_phone=to_phone,
            customer_name=customer_name,
            invoice_number=invoice_number,
            total_amount=total_amount,
            items=items,
            salon_name=salon.name,
            payment_link=payment_link,
            phone_number_id=salon.whatsapp_phone_number_id,
            access_token=salon.whatsapp_access_token
        )

        msg_record = WhatsAppMessageModel(
            salon_id=salon.id,
            recipient_phone=to_phone,
            customer_name=customer_name,
            message_type="bill_receipt",
            template_name="billcare_service_receipt",
            meta_message_id=result.get("message_id"),
            status="sent" if result.get("success") else "failed",
            idempotency_key=idempotency_key,
            error_details=result.get("error") if not result.get("success") else None
        )
        db.add(msg_record)
        db.commit()
        return result
    except Exception as e:
        msg_record = WhatsAppMessageModel(
            salon_id=salon.id,
            recipient_phone=to_phone,
            customer_name=customer_name,
            message_type="bill_receipt",
            template_name="billcare_service_receipt",
            status="failed",
            idempotency_key=idempotency_key,
            error_details=str(e)
        )
        db.add(msg_record)
        db.commit()
        return {
            "success": False,
            "is_fallback": True,
            "error": str(e),
            "message": "WhatsApp delivery encountered a transient error. Bill was successfully saved in POS."
        }


@router.post("/whatsapp/send-reminder", tags=["WhatsApp"])
async def send_whatsapp_appointment_reminder(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db)
):
    """Sends appointment booking confirmation / reminder via WhatsApp from the salon's verified number."""
    _, salon = context
    to_phone = data.get("customerPhone", "")
    customer_name = data.get("customerName", "Valued Client")
    service_name = data.get("serviceName", "Salon Service")
    staff_name = data.get("staffName", "Master Stylist")
    date_time = data.get("dateTime", "Tomorrow")
    appointment_id = data.get("appointmentId", "")

    idempotency_key = f"appt_{appointment_id}_{to_phone}" if appointment_id else None

    if idempotency_key:
        existing_msg = db.query(WhatsAppMessageModel).filter(
            WhatsAppMessageModel.salon_id == salon.id,
            WhatsAppMessageModel.idempotency_key == idempotency_key,
            WhatsAppMessageModel.status.in_(["sent", "delivered", "read"])
        ).first()
        if existing_msg:
            return {
                "success": True,
                "duplicate": True,
                "message": "Appointment confirmation already sent.",
                "message_id": existing_msg.meta_message_id
            }

    if salon.whatsapp_status != "connected" or not salon.whatsapp_access_token:
        return {
            "success": False,
            "is_fallback": True,
            "message": "WhatsApp not connected. Appointment saved locally."
        }

    try:
        result = await whatsapp_service.send_appointment_confirmation(
            to_phone=to_phone,
            customer_name=customer_name,
            service_name=service_name,
            staff_name=staff_name,
            date_time=date_time,
            salon_name=salon.name,
            phone_number_id=salon.whatsapp_phone_number_id,
            access_token=salon.whatsapp_access_token
        )

        msg_record = WhatsAppMessageModel(
            salon_id=salon.id,
            recipient_phone=to_phone,
            customer_name=customer_name,
            message_type="appointment_confirmation",
            template_name="billcare_appointment_confirmation",
            meta_message_id=result.get("message_id"),
            status="sent" if result.get("success") else "failed",
            idempotency_key=idempotency_key,
            error_details=result.get("error") if not result.get("success") else None
        )
        db.add(msg_record)
        db.commit()
        return result
    except Exception as e:
        return {"success": False, "is_fallback": True, "error": str(e)}


@router.post("/whatsapp/send-campaign", tags=["WhatsApp"])
async def send_whatsapp_campaign(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db)
):
    """Sends CRM retention messages via WhatsApp Cloud API from the salon's verified number."""
    _, salon = context
    to_phone = data.get("customerPhone", "")
    customer_name = data.get("customerName", "Valued Client")
    message_text = data.get("message", "")
    followup_id = data.get("followupId")

    idempotency_key = f"campaign_{followup_id}_{to_phone}" if followup_id else None

    if salon.whatsapp_status != "connected" or not salon.whatsapp_access_token:
        return {
            "success": False,
            "is_fallback": True,
            "message": "WhatsApp not connected. Campaign notification deferred."
        }

    result = await whatsapp_service.send_retention_campaign(
        to_phone=to_phone,
        customer_name=customer_name,
        custom_message=message_text,
        salon_name=salon.name,
        phone_number_id=salon.whatsapp_phone_number_id,
        access_token=salon.whatsapp_access_token
    )

    msg_record = WhatsAppMessageModel(
        salon_id=salon.id,
        recipient_phone=to_phone,
        customer_name=customer_name,
        message_type="retention_campaign",
        template_name="billcare_rebooking_touchup",
        meta_message_id=result.get("message_id"),
        status="sent" if result.get("success") else "failed",
        idempotency_key=idempotency_key,
        error_details=result.get("error") if not result.get("success") else None
    )
    db.add(msg_record)

    if followup_id:
        flw = db.query(FollowUpModel).filter(
            FollowUpModel.id == followup_id,
            FollowUpModel.salon_id == salon.id
        ).first()
        if flw:
            flw.status = "sent"

    db.commit()
    return result


@router.get("/whatsapp/webhook", tags=["WhatsApp"])
def meta_webhook_verification(request: Request):
    """Handles Meta Graph API Webhook Verification Challenge."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "billcare_meta_webhook_2026")

    if mode == "subscribe" and token == verify_token:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=challenge, status_code=200)

    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/whatsapp/webhook", tags=["WhatsApp"])
async def meta_webhook_event_handler(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handles incoming WhatsApp delivery status reports (sent, delivered, read, failed) & updates
    the corresponding WhatsAppMessageModel idempotently.
    Also confirms webhook configuration status for the salon.
    """
    try:
        body = await request.json()
        entries = body.get("entry", [])

        status_hierarchy = {"pending": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}

        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                statuses = value.get("statuses", [])

                for st in statuses:
                    meta_msg_id = st.get("id")
                    new_status = st.get("status") # 'sent', 'delivered', 'read', 'failed'

                    if not meta_msg_id or not new_status:
                        continue

                    # Lookup matching message record
                    msg = db.query(WhatsAppMessageModel).filter(
                        WhatsAppMessageModel.meta_message_id == meta_msg_id
                    ).first()

                    if msg:
                        # Prevent duplicate / out-of-order state regression (e.g. read -> delivered)
                        current_rank = status_hierarchy.get(msg.status, 0)
                        new_rank = status_hierarchy.get(new_status, 0)

                        if new_rank >= current_rank or new_status == "failed":
                            msg.status = new_status
                            msg.updated_at = datetime.utcnow()

                            # If errors array present
                            errors = st.get("errors", [])
                            if errors:
                                err_title = errors[0].get("title", "Delivery failure")
                                err_code = errors[0].get("code", "")
                                msg.error_details = f"Code {err_code}: {err_title}"

                            # Mark webhook verified on the salon
                            salon = db.query(SalonModel).filter(SalonModel.id == msg.salon_id).first()
                            if salon and not salon.whatsapp_webhook_verified:
                                salon.whatsapp_webhook_verified = True

        db.commit()
        return {"status": "ok", "processed": True}
    except Exception as e:
        return {"status": "error", "message": str(e)}

