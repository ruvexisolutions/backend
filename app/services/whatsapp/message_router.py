"""Strict Message Routing & Idempotent Delivery Queue for Dual WhatsApp Channels."""

import json
import uuid
from enum import Enum
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.core.models import WhatsAppMessageLogModel, WhatsAppAuditLogModel
from .base_client import whatsapp_base_client
from .ruvexi_service import ruvexi_whatsapp_service
from .salon_service import salon_whatsapp_service


class ChannelType(str, Enum):
    RUVEXI = "RUVEXI"
    SALON = "SALON"


class MessageCategory(str, Enum):
    # RUVEXI Official Channel ONLY
    OWNER_REPORT = "OWNER_REPORT"
    OWNER_ALERT = "OWNER_ALERT"
    SUBSCRIPTION_NOTIFICATION = "SUBSCRIPTION_NOTIFICATION"
    PLATFORM_ANNOUNCEMENT = "PLATFORM_ANNOUNCEMENT"

    # Individual Salon Channel ONLY
    BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"
    APPOINTMENT_REMINDER = "APPOINTMENT_REMINDER"
    APPOINTMENT_CANCELLATION = "APPOINTMENT_CANCELLATION"
    APPOINTMENT_RESCHEDULE = "APPOINTMENT_RESCHEDULE"
    CUSTOMER_CHECKIN = "CUSTOMER_CHECKIN"
    CUSTOMER_INVOICE = "CUSTOMER_INVOICE"
    PAYMENT_CONFIRMATION = "PAYMENT_CONFIRMATION"
    THANK_YOU = "THANK_YOU"
    FEEDBACK_REQUEST = "FEEDBACK_REQUEST"
    BIRTHDAY_WISH = "BIRTHDAY_WISH"
    CUSTOMER_PROMOTION = "CUSTOMER_PROMOTION"
    FOLLOW_UP = "FOLLOW_UP"


CATEGORY_CHANNEL_MAP: Dict[MessageCategory, ChannelType] = {
    MessageCategory.OWNER_REPORT: ChannelType.RUVEXI,
    MessageCategory.OWNER_ALERT: ChannelType.RUVEXI,
    MessageCategory.SUBSCRIPTION_NOTIFICATION: ChannelType.RUVEXI,
    MessageCategory.PLATFORM_ANNOUNCEMENT: ChannelType.RUVEXI,
    MessageCategory.BOOKING_CONFIRMATION: ChannelType.SALON,
    MessageCategory.APPOINTMENT_REMINDER: ChannelType.SALON,
    MessageCategory.APPOINTMENT_CANCELLATION: ChannelType.SALON,
    MessageCategory.APPOINTMENT_RESCHEDULE: ChannelType.SALON,
    MessageCategory.CUSTOMER_CHECKIN: ChannelType.SALON,
    MessageCategory.CUSTOMER_INVOICE: ChannelType.SALON,
    MessageCategory.PAYMENT_CONFIRMATION: ChannelType.SALON,
    MessageCategory.THANK_YOU: ChannelType.SALON,
    MessageCategory.FEEDBACK_REQUEST: ChannelType.SALON,
    MessageCategory.BIRTHDAY_WISH: ChannelType.SALON,
    MessageCategory.CUSTOMER_PROMOTION: ChannelType.SALON,
    MessageCategory.FOLLOW_UP: ChannelType.SALON,
}

MARKETING_CATEGORIES = {
    MessageCategory.CUSTOMER_PROMOTION,
    MessageCategory.BIRTHDAY_WISH,
    MessageCategory.FOLLOW_UP,
}


class WhatsAppMessageRouter:
    """
    Central router enforcing strict separation between RUVEXI Official WhatsApp
    and Individual Salon WhatsApp.
    """

    def resolve_channel(self, category: MessageCategory) -> ChannelType:
        if category not in CATEGORY_CHANNEL_MAP:
            raise ValueError(f"Unsupported WhatsApp message category: {category}")
        return CATEGORY_CHANNEL_MAP[category]

    def enqueue_message(
        self,
        *,
        db: Session,
        tenant_id: Optional[str],
        category: MessageCategory,
        recipient_number: str,
        message_text: str,
        customer_name: Optional[str] = None,
        template_name: Optional[str] = None,
        template_params: Optional[List[str]] = None,
        language_code: str = "en_US",
        idempotency_key: Optional[str] = None,
        requested_channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Queues a message in `whatsapp_message_logs` with strict channel enforcement
        and idempotency deduplication.
        """
        channel = self.resolve_channel(category)
        if requested_channel and requested_channel.upper() != channel.value:
            raise PermissionError(
                f"Channel override denied: category {category.value} must use {channel.value}, not {requested_channel}."
            )

        if channel == ChannelType.SALON and not tenant_id:
            raise ValueError("tenant_id is required for SALON channel messages.")

        norm_phone = whatsapp_base_client.normalize_phone(recipient_number)
        if not norm_phone:
            return {"queued": False, "error": "Invalid recipient phone number"}

        if idempotency_key:
            existing = (
                db.query(WhatsAppMessageLogModel)
                .filter(WhatsAppMessageLogModel.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                return {"queued": False, "deduplicated": True, "log": existing.to_dict()}

        payload = {
            "message_text": message_text,
            "template_params": template_params,
            "language_code": language_code,
            "is_marketing": category in MARKETING_CATEGORIES,
        }
        log = WhatsAppMessageLogModel(
            id=f"wlog_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            channel_type=channel.value,
            recipient_number=norm_phone,
            customer_name=customer_name,
            message_type=category.value,
            template_name=template_name,
            delivery_status="queued",
            idempotency_key=idempotency_key,
            retry_count=0,
            max_retries=3,
            next_retry_at=datetime.utcnow(),
            payload_json=json.dumps(payload),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return {"queued": True, "deduplicated": False, "log": log.to_dict()}

    async def process_log_entry(self, db: Session, log: WhatsAppMessageLogModel) -> Dict[str, Any]:
        """Executes a single queued/retryable log entry through its strictly assigned service."""
        try:
            payload = json.loads(log.payload_json or "{}")
        except Exception:
            payload = {}

        message_text = str(payload.get("message_text") or "")
        template_params = payload.get("template_params")
        language_code = str(payload.get("language_code") or "en_US")
        is_marketing = bool(payload.get("is_marketing", False))

        # Re-verify category -> channel invariant before sending
        try:
            cat = MessageCategory(log.message_type)
            expected_channel = self.resolve_channel(cat).value
            if log.channel_type != expected_channel:
                log.delivery_status = "dead_letter"
                log.failure_reason = f"Channel invariant violation: {log.channel_type} != {expected_channel}"
                db.commit()
                return {"success": False, "error": log.failure_reason}
        except ValueError:
            pass

        if log.channel_type == ChannelType.RUVEXI.value:
            res = await ruvexi_whatsapp_service.dispatch(
                to_phone=log.recipient_number,
                message_text=message_text,
                template_name=log.template_name,
                template_params=template_params,
                language_code=language_code,
            )
        elif log.channel_type == ChannelType.SALON.value:
            if not log.tenant_id:
                res = {"success": False, "error": "Missing tenant_id for SALON channel", "retryable": False}
            else:
                res = await salon_whatsapp_service.dispatch(
                    db=db,
                    tenant_id=log.tenant_id,
                    to_phone=log.recipient_number,
                    message_text=message_text,
                    template_name=log.template_name,
                    template_params=template_params,
                    language_code=language_code,
                    is_marketing=is_marketing,
                )
        else:
            res = {"success": False, "error": f"Unknown channel_type {log.channel_type}", "retryable": False}

        now = datetime.utcnow()
        if res.get("success"):
            log.delivery_status = "sent"
            log.meta_message_id = res.get("message_id")
            log.sent_at = now
            log.failure_reason = None
            log.next_retry_at = None
        else:
            log.failure_reason = str(res.get("error") or "Dispatch failed")
            retryable = bool(res.get("retryable", False))
            if retryable and (log.retry_count or 0) < (log.max_retries or 3):
                log.retry_count = (log.retry_count or 0) + 1
                backoff_seconds = 60 * (2 ** (log.retry_count - 1))
                log.delivery_status = "queued"
                log.next_retry_at = now + timedelta(seconds=backoff_seconds)
            else:
                log.delivery_status = "failed"
                log.next_retry_at = None

        log.updated_at = now
        db.commit()
        db.refresh(log)
        return {"success": bool(res.get("success")), "result": res, "log": log.to_dict()}

    async def route_and_send(
        self,
        *,
        db: Session,
        tenant_id: Optional[str],
        category: MessageCategory,
        recipient_number: str,
        message_text: str,
        customer_name: Optional[str] = None,
        template_name: Optional[str] = None,
        template_params: Optional[List[str]] = None,
        language_code: str = "en_US",
        idempotency_key: Optional[str] = None,
        requested_channel: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enqueues and immediately attempts delivery; transient errors stay queued for retry."""
        enq = self.enqueue_message(
            db=db,
            tenant_id=tenant_id,
            category=category,
            recipient_number=recipient_number,
            message_text=message_text,
            customer_name=customer_name,
            template_name=template_name,
            template_params=template_params,
            language_code=language_code,
            idempotency_key=idempotency_key,
            requested_channel=requested_channel,
        )
        if enq.get("deduplicated"):
            return {"success": True, "deduplicated": True, "log": enq["log"]}
        if not enq.get("queued"):
            return {"success": False, "error": enq.get("error", "Unable to queue message")}

        log = db.query(WhatsAppMessageLogModel).filter(WhatsAppMessageLogModel.id == enq["log"]["id"]).first()
        if not log:
            return {"success": False, "error": "Log record not found"}

        if actor_user_id:
            db.add(
                WhatsAppAuditLogModel(
                    tenant_id=tenant_id,
                    actor_user_id=actor_user_id,
                    channel_type=log.channel_type,
                    action=f"DISPATCH_{category.value}",
                    details=f"Recipient={log.recipient_number}, LogID={log.id}",
                )
            )
            db.commit()

        return await self.process_log_entry(db, log)


whatsapp_message_router = WhatsAppMessageRouter()
