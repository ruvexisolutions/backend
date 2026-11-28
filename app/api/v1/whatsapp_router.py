"""Dual WhatsApp Business API Router (RUVEXI Official Channel + Per-Salon Tenant Channel + Webhooks)."""

import os
import hmac
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Body, Request, status, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import (
    SalonModel,
    UserModel,
    WhatsAppConnectionModel,
    WhatsAppMessageLogModel,
    WhatsAppNotificationPreferenceModel,
    WhatsAppTemplateModel,
    WhatsAppWebhookEventModel,
    WhatsAppAuditLogModel,
)
from app.api.v1.router import (
    get_current_user_and_salon,
    require_salon_manager,
    require_master_admin,
)
from app.services.whatsapp import (
    whatsapp_base_client,
    ruvexi_whatsapp_service,
    salon_whatsapp_service,
    whatsapp_message_router,
    MessageCategory,
    ChannelType,
    embedded_signup_service,
    whatsapp_template_service,
    whatsapp_webhook_service,
    whatsapp_report_service,
)

whatsapp_router = APIRouter(prefix="/api/v1", tags=["DualWhatsApp"])


DEFAULT_OWNER_PREFS = [
    ("daily_report", "daily", "09:00", True),
    ("weekly_report", "weekly", "09:00", True),
    ("monthly_report", "monthly", "09:00", True),
    ("revenue_alert", "realtime", "09:00", True),
    ("low_stock_alert", "daily", "10:00", True),
    ("subscription_alert", "daily", "09:00", True),
]

DEFAULT_SALON_PREFS = [
    ("BOOKING_CONFIRMATION", "realtime", True),
    ("APPOINTMENT_REMINDER", "realtime", True),
    ("APPOINTMENT_CANCELLATION", "realtime", True),
    ("APPOINTMENT_RESCHEDULE", "realtime", True),
    ("CUSTOMER_CHECKIN", "realtime", False),
    ("CUSTOMER_INVOICE", "realtime", True),
    ("PAYMENT_CONFIRMATION", "realtime", True),
    ("THANK_YOU", "realtime", True),
    ("FEEDBACK_REQUEST", "realtime", True),
    ("BIRTHDAY_WISH", "daily", True),
    ("CUSTOMER_PROMOTION", "realtime", True),
    ("FOLLOW_UP", "daily", True),
]


def _ensure_default_preferences(
    db: Session,
    tenant_id: str,
    channel_type: str,
    owner_id: Optional[str] = None,
    default_phone: str = "",
) -> List[WhatsAppNotificationPreferenceModel]:
    existing = (
        db.query(WhatsAppNotificationPreferenceModel)
        .filter(
            WhatsAppNotificationPreferenceModel.tenant_id == tenant_id,
            WhatsAppNotificationPreferenceModel.channel_type == channel_type,
        )
        .all()
    )
    if existing:
        return existing

    created: List[WhatsAppNotificationPreferenceModel] = []
    if channel_type == "RUVEXI":
        for ntype, freq, dtime, enabled in DEFAULT_OWNER_PREFS:
            row = WhatsAppNotificationPreferenceModel(
                tenant_id=tenant_id,
                owner_id=owner_id,
                channel_type="RUVEXI",
                recipient_phone=default_phone,
                notification_type=ntype,
                is_enabled=enabled,
                delivery_frequency=freq,
                preferred_delivery_time=dtime,
                opted_in=True,
            )
            db.add(row)
            created.append(row)
    else:
        for ntype, freq, enabled in DEFAULT_SALON_PREFS:
            row = WhatsAppNotificationPreferenceModel(
                tenant_id=tenant_id,
                owner_id=None,
                channel_type="SALON",
                recipient_phone="",
                notification_type=ntype,
                is_enabled=enabled,
                delivery_frequency=freq,
                preferred_delivery_time="10:00",
                opted_in=True,
            )
            db.add(row)
            created.append(row)

    db.commit()
    for r in created:
        db.refresh(r)
    return created


# ============================================================================
# 1. RUVEXI Official WhatsApp — Owner Insights & Preferences
# ============================================================================

@whatsapp_router.post("/whatsapp/owner/send-report")
async def send_owner_business_report(
    data: Dict[str, Any] = Body(default={}),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db),
):
    """Dispatches a real-data business report exclusively via RUVEXI Official WhatsApp API."""
    user, salon = context
    period = str(data.get("period") or "daily").lower()
    if period not in ("daily", "weekly", "monthly"):
        period = "daily"
    branch_id = str(data.get("branchId") or "").strip() or None
    recipient = str(data.get("recipientNumber") or salon.phone or "").strip()

    if not recipient:
        raise HTTPException(status_code=400, detail="Owner WhatsApp phone number is required.")

    metrics = whatsapp_report_service.build_business_report_metrics(
        db=db,
        tenant_id=salon.id,
        period=period,
        branch_id=branch_id,
    )
    message_text = whatsapp_report_service.format_daily_report_message(metrics)

    res = await whatsapp_message_router.route_and_send(
        db=db,
        tenant_id=salon.id,
        category=MessageCategory.OWNER_REPORT,
        recipient_number=recipient,
        message_text=message_text,
        customer_name=user.name or salon.name,
        template_name="ruvexi_daily_owner_report",
        idempotency_key=data.get("idempotencyKey"),
        requested_channel=data.get("channelType"),
        actor_user_id=user.id,
    )
    return {"metrics": metrics, **res}


@whatsapp_router.post("/whatsapp/owner/send-alert")
async def send_owner_operational_alert(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db),
):
    """Dispatches an operational or subscription alert exclusively via RUVEXI Official WhatsApp API."""
    user, salon = context
    alert_type = str(data.get("alertType") or "OWNER_ALERT").upper()
    category = (
        MessageCategory.SUBSCRIPTION_NOTIFICATION
        if alert_type == "SUBSCRIPTION_NOTIFICATION"
        else MessageCategory.OWNER_ALERT
    )
    title = str(data.get("title") or "Operational Alert").strip()
    body = str(data.get("message") or "").strip()
    recipient = str(data.get("recipientNumber") or salon.phone or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Alert message body is required.")
    if not recipient:
        raise HTTPException(status_code=400, detail="Owner phone number is required.")

    formatted = whatsapp_report_service.format_operational_alert(salon.name, title, body)
    return await whatsapp_message_router.route_and_send(
        db=db,
        tenant_id=salon.id,
        category=category,
        recipient_number=recipient,
        message_text=formatted,
        customer_name=user.name or salon.name,
        template_name="ruvexi_owner_operational_alert",
        idempotency_key=data.get("idempotencyKey"),
        requested_channel=data.get("channelType"),
        actor_user_id=user.id,
    )


@whatsapp_router.get("/whatsapp/owner/preferences")
def get_owner_notification_preferences(
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db),
):
    """Returns independent RUVEXI Official WhatsApp owner report/alert preferences."""
    user, salon = context
    prefs = _ensure_default_preferences(
        db=db,
        tenant_id=salon.id,
        channel_type="RUVEXI",
        owner_id=user.id,
        default_phone=salon.phone or "",
    )
    logs = (
        db.query(WhatsAppMessageLogModel)
        .filter(
            WhatsAppMessageLogModel.tenant_id == salon.id,
            WhatsAppMessageLogModel.channel_type == "RUVEXI",
        )
        .order_by(WhatsAppMessageLogModel.created_at.desc())
        .limit(25)
        .all()
    )
    return {
        "ruvexiChannel": ruvexi_whatsapp_service.get_public_status(),
        "preferences": [p.to_dict() for p in prefs],
        "recentReports": [l.to_dict() for l in logs],
    }


@whatsapp_router.put("/whatsapp/owner/preferences")
def update_owner_notification_preferences(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db),
):
    """Updates owner report/alert categories, frequency, delivery time (IST), opt-in, and phone numbers."""
    user, salon = context
    items = data.get("preferences")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="'preferences' list is required.")

    updated: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ntype = str(item.get("notificationType") or "").strip()
        if not ntype:
            continue
        phone = str(item.get("recipientPhone") if item.get("recipientPhone") is not None else (salon.phone or "")).strip()

        row = (
            db.query(WhatsAppNotificationPreferenceModel)
            .filter(
                WhatsAppNotificationPreferenceModel.tenant_id == salon.id,
                WhatsAppNotificationPreferenceModel.channel_type == "RUVEXI",
                WhatsAppNotificationPreferenceModel.notification_type == ntype,
            )
            .first()
        )
        if not row:
            row = WhatsAppNotificationPreferenceModel(
                tenant_id=salon.id,
                owner_id=user.id,
                channel_type="RUVEXI",
                notification_type=ntype,
            )
            db.add(row)

        if "isEnabled" in item:
            row.is_enabled = bool(item["isEnabled"])
        if "optedIn" in item:
            row.opted_in = bool(item["optedIn"])
        if item.get("deliveryFrequency"):
            row.delivery_frequency = str(item["deliveryFrequency"])
        if item.get("preferredDeliveryTime"):
            row.preferred_delivery_time = str(item["preferredDeliveryTime"])
        row.recipient_phone = phone
        row.updated_at = datetime.utcnow()
        updated.append(ntype)

    db.add(
        WhatsAppAuditLogModel(
            tenant_id=salon.id,
            actor_user_id=user.id,
            channel_type="RUVEXI",
            action="OWNER_PREFERENCES_UPDATED",
            details=f"Updated types={','.join(updated)}",
        )
    )
    db.commit()
    all_prefs = (
        db.query(WhatsAppNotificationPreferenceModel)
        .filter(
            WhatsAppNotificationPreferenceModel.tenant_id == salon.id,
            WhatsAppNotificationPreferenceModel.channel_type == "RUVEXI",
        )
        .all()
    )
    return {"success": True, "preferences": [p.to_dict() for p in all_prefs]}


# ============================================================================
# 2. Individual Salon WhatsApp — Connection, Embedded Signup, Templates, Logs
# ============================================================================

@whatsapp_router.get("/whatsapp/salon/oauth-state")
def get_salon_oauth_state(
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
):
    """Generates a CSRF-protected OAuth state token for Meta Embedded Signup."""
    user, salon = context
    state = embedded_signup_service.generate_oauth_state(salon.id, user.id)
    return {
        "state": state,
        "metaAppId": os.getenv("META_APP_ID", ""),
        "graphApiVersion": whatsapp_base_client.api_version,
    }


@whatsapp_router.get("/whatsapp/salon/status")
async def get_salon_whatsapp_status(
    request: Request,
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db),
):
    """Returns the authenticated tenant's own WhatsApp connection status (never exposes tokens)."""
    _, salon = context
    conn, phone_id, token = salon_whatsapp_service.resolve_tenant_credentials(db, salon.id)
    templates = await whatsapp_template_service.sync_salon_templates(db, salon.id) if (conn and token) else []
    prefs = _ensure_default_preferences(db, salon.id, "SALON")

    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/api/v1/webhooks/whatsapp"
    verify_token = os.getenv("META_WEBHOOK_VERIFY_TOKEN") or os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN") or ""

    return {
        "channel": "SALON",
        "isConnected": bool(conn and conn.connection_status == "connected" and phone_id and token),
        "connection": conn.to_dict() if conn else None,
        "templates": templates,
        "preferences": [p.to_dict() for p in prefs],
        "webhookUrl": webhook_url,
        "webhookVerifyToken": verify_token,
    }


@whatsapp_router.post("/whatsapp/salon/connect")
async def connect_salon_whatsapp(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db),
):
    """Connects a salon's own WhatsApp Business Account via manual credentials or Meta OAuth code."""
    user, salon = context
    code = str(data.get("code") or "").strip()
    access_token = str(data.get("accessToken") or data.get("access_token") or "").strip()
    waba_id = str(data.get("wabaId") or data.get("waba_id") or "").strip() or None
    phone_number_id = str(data.get("phoneNumberId") or data.get("phone_number_id") or "").strip() or None
    expires_in = None

    if code and not access_token:
        exch = await embedded_signup_service.exchange_code_for_token(code, redirect_uri=data.get("redirectUri"))
        if not exch.get("success"):
            raise HTTPException(status_code=400, detail=exch.get("error", "OAuth code exchange failed"))
        access_token = exch["access_token"]
        expires_in = exch.get("expires_in")

    if not access_token:
        raise HTTPException(status_code=400, detail="Access token or Meta Embedded Signup code is required.")

    res = await embedded_signup_service.connect_tenant(
        db=db,
        salon=salon,
        actor_user_id=user.id,
        waba_id=waba_id,
        phone_number_id=phone_number_id,
        access_token=access_token,
        display_number=data.get("displayNumber"),
        verified_name=data.get("verifiedName"),
        expires_in_seconds=expires_in,
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "WhatsApp connection failed"))

    await whatsapp_template_service.sync_salon_templates(db, salon.id)
    return res


@whatsapp_router.post("/whatsapp/salon/callback")
async def salon_embedded_signup_callback(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db),
):
    """Meta Embedded Signup OAuth callback with CSRF state verification & server-side token exchange."""
    user, salon = context
    state = str(data.get("state") or "").strip()
    code = str(data.get("code") or "").strip()
    if state and not embedded_signup_service.verify_oauth_state(state, salon.id, user.id):
        raise HTTPException(status_code=403, detail="Invalid or expired OAuth state parameter.")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code is required.")

    exch = await embedded_signup_service.exchange_code_for_token(code, redirect_uri=data.get("redirectUri"))
    if not exch.get("success"):
        raise HTTPException(status_code=400, detail=exch.get("error", "Token exchange failed."))

    res = await embedded_signup_service.connect_tenant(
        db=db,
        salon=salon,
        actor_user_id=user.id,
        waba_id=data.get("wabaId"),
        phone_number_id=data.get("phoneNumberId"),
        access_token=exch["access_token"],
        expires_in_seconds=exch.get("expires_in"),
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Connection setup failed"))

    await whatsapp_template_service.sync_salon_templates(db, salon.id)
    return res


@whatsapp_router.delete("/whatsapp/salon/disconnect")
async def disconnect_salon_whatsapp(
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db),
):
    """Disconnects ONLY the authenticated salon's WhatsApp connection without affecting RUVEXI Official API."""
    user, salon = context
    return await embedded_signup_service.disconnect_tenant(db, salon, user.id)


@whatsapp_router.get("/whatsapp/salon/templates")
async def get_salon_whatsapp_templates(
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db),
):
    _, salon = context
    templates = await whatsapp_template_service.sync_salon_templates(db, salon.id)
    return {"templates": templates}


@whatsapp_router.get("/whatsapp/salon/logs")
def get_salon_whatsapp_logs(
    limit: int = Query(50, ge=1, le=200),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db),
):
    """Returns customer-facing SALON channel message delivery logs strictly scoped to the caller's tenant."""
    _, salon = context
    logs = (
        db.query(WhatsAppMessageLogModel)
        .filter(
            WhatsAppMessageLogModel.tenant_id == salon.id,
            WhatsAppMessageLogModel.channel_type == "SALON",
        )
        .order_by(WhatsAppMessageLogModel.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"logs": [l.to_dict() for l in logs]}


@whatsapp_router.put("/whatsapp/salon/preferences")
def update_salon_customer_preferences(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_salon_manager),
    db: Session = Depends(get_db),
):
    """Configures automated customer messaging preferences on the SALON channel."""
    user, salon = context
    items = data.get("preferences")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="'preferences' list is required.")

    for item in items:
        if not isinstance(item, dict):
            continue
        ntype = str(item.get("notificationType") or "").strip()
        if not ntype:
            continue
        row = (
            db.query(WhatsAppNotificationPreferenceModel)
            .filter(
                WhatsAppNotificationPreferenceModel.tenant_id == salon.id,
                WhatsAppNotificationPreferenceModel.channel_type == "SALON",
                WhatsAppNotificationPreferenceModel.notification_type == ntype,
            )
            .first()
        )
        if not row:
            row = WhatsAppNotificationPreferenceModel(
                tenant_id=salon.id,
                channel_type="SALON",
                notification_type=ntype,
            )
            db.add(row)
        if "isEnabled" in item:
            row.is_enabled = bool(item["isEnabled"])
        row.updated_at = datetime.utcnow()

    db.add(
        WhatsAppAuditLogModel(
            tenant_id=salon.id,
            actor_user_id=user.id,
            channel_type="SALON",
            action="SALON_AUTOMATION_PREFS_UPDATED",
            details="Updated salon customer messaging preferences",
        )
    )
    db.commit()
    rows = (
        db.query(WhatsAppNotificationPreferenceModel)
        .filter(
            WhatsAppNotificationPreferenceModel.tenant_id == salon.id,
            WhatsAppNotificationPreferenceModel.channel_type == "SALON",
        )
        .all()
    )
    return {"success": True, "preferences": [r.to_dict() for r in rows]}


@whatsapp_router.post("/whatsapp/salon/send")
async def send_salon_customer_message(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(get_current_user_and_salon),
    db: Session = Depends(get_db),
):
    """
    Dispatches a customer-facing message strictly via the authenticated salon's own WhatsApp connection.
    Blocks any attempt to send RUVEXI channel categories or override tenant_id/channel_type.
    """
    user, salon = context
    if data.get("tenantId") and str(data.get("tenantId")) != salon.id:
        raise HTTPException(status_code=403, detail="Cross-tenant WhatsApp dispatch is forbidden.")

    raw_cat = str(data.get("messageType") or "FOLLOW_UP").upper()
    try:
        category = MessageCategory(raw_cat)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid messageType: {raw_cat}")

    if whatsapp_message_router.resolve_channel(category) != ChannelType.SALON:
        raise HTTPException(
            status_code=403,
            detail=f"Message category {category.value} is restricted to RUVEXI Official WhatsApp channel.",
        )

    recipient = str(data.get("recipientNumber") or "").strip()
    message_text = str(data.get("message") or "").strip()
    if not recipient or not message_text:
        raise HTTPException(status_code=400, detail="recipientNumber and message are required.")

    return await whatsapp_message_router.route_and_send(
        db=db,
        tenant_id=salon.id,
        category=category,
        recipient_number=recipient,
        message_text=message_text,
        customer_name=data.get("customerName"),
        template_name=data.get("templateName"),
        template_params=data.get("templateParams"),
        idempotency_key=data.get("idempotencyKey"),
        requested_channel=data.get("channelType"),
        actor_user_id=user.id,
    )


# ============================================================================
# 3. RUVEXI Platform Admin Monitoring & Announcements (MASTER_ADMIN only)
# ============================================================================

@whatsapp_router.get("/whatsapp/admin/overview")
async def get_admin_whatsapp_overview(
    context: tuple[UserModel, SalonModel] = Depends(require_master_admin),
    db: Session = Depends(get_db),
):
    """Platform-level RUVEXI Official WhatsApp telemetry and monitoring for MASTER_ADMIN."""
    all_ruvexi_logs = (
        db.query(WhatsAppMessageLogModel)
        .filter(WhatsAppMessageLogModel.channel_type == "RUVEXI")
        .order_by(WhatsAppMessageLogModel.created_at.desc())
        .limit(200)
        .all()
    )
    total_vol = len(all_ruvexi_logs)
    delivered_cnt = sum(1 for l in all_ruvexi_logs if l.delivery_status in ("sent", "delivered", "read"))
    failed_logs = [l.to_dict() for l in all_ruvexi_logs if l.delivery_status in ("failed", "dead_letter")]
    success_rate = round((delivered_cnt / total_vol) * 100, 1) if total_vol else 100.0

    scheduled_prefs = (
        db.query(WhatsAppNotificationPreferenceModel)
        .filter(
            WhatsAppNotificationPreferenceModel.channel_type == "RUVEXI",
            WhatsAppNotificationPreferenceModel.is_enabled == True,
        )
        .count()
    )
    connected_salons = (
        db.query(WhatsAppConnectionModel)
        .filter(WhatsAppConnectionModel.connection_status == "connected")
        .count()
    )
    templates = await whatsapp_template_service.sync_ruvexi_templates(db)

    return {
        "ruvexiStatus": ruvexi_whatsapp_service.get_public_status(),
        "metrics": {
            "totalMessages": total_vol,
            "deliveredMessages": delivered_cnt,
            "failedMessagesCount": len(failed_logs),
            "deliverySuccessRate": success_rate,
            "activeScheduledReports": scheduled_prefs,
            "connectedSalonsCount": connected_salons,
        },
        "templates": templates,
        "failedMessages": failed_logs[:20],
        "recentMessages": [l.to_dict() for l in all_ruvexi_logs[:25]],
    }


@whatsapp_router.post("/whatsapp/admin/broadcast")
async def send_platform_announcement(
    data: Dict[str, Any] = Body(...),
    context: tuple[UserModel, SalonModel] = Depends(require_master_admin),
    db: Session = Depends(get_db),
):
    """Sends a RUVEXI platform announcement via RUVEXI Official WhatsApp API."""
    user, _ = context
    recipient = str(data.get("recipientNumber") or "").strip()
    message_text = str(data.get("message") or "").strip()
    if not recipient or not message_text:
        raise HTTPException(status_code=400, detail="recipientNumber and message are required.")

    return await whatsapp_message_router.route_and_send(
        db=db,
        tenant_id=data.get("tenantId"),
        category=MessageCategory.PLATFORM_ANNOUNCEMENT,
        recipient_number=recipient,
        message_text=message_text,
        customer_name=data.get("ownerName"),
        idempotency_key=data.get("idempotencyKey"),
        actor_user_id=user.id,
    )


# ============================================================================
# 4. Meta Unified Webhook Endpoints (/api/v1/webhooks/whatsapp)
# ============================================================================

@whatsapp_router.get("/webhooks/whatsapp")
def verify_unified_whatsapp_webhook(request: Request):
    """Meta Webhook Verification Challenge."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    verify_token = (
        os.getenv("META_WEBHOOK_VERIFY_TOKEN")
        or os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
        or ""
    ).strip()
    if not verify_token:
        raise HTTPException(status_code=503, detail="META_WEBHOOK_VERIFY_TOKEN is not configured.")

    if mode == "subscribe" and token and hmac.compare_digest(str(token), verify_token):
        return PlainTextResponse(content=challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@whatsapp_router.post("/webhooks/whatsapp")
async def handle_unified_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Meta Webhook event handler with HMAC signature validation, deduplication, and channel resolution."""
    raw_body = await request.body()
    sig_header = request.headers.get("X-Hub-Signature-256")
    if not whatsapp_base_client.verify_webhook_signature(raw_body, sig_header):
        raise HTTPException(status_code=403, detail="Invalid X-Hub-Signature-256 webhook signature.")
    return whatsapp_webhook_service.process_webhook_payload(db, raw_body)
