"""Meta WhatsApp Webhook Verification, Deduplication, Channel Resolution & Status Tracking."""

import json
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.core.models import (
    SalonModel,
    CustomerModel,
    WhatsAppConnectionModel,
    WhatsAppMessageLogModel,
    WhatsAppMessageModel,
    WhatsAppWebhookEventModel,
)
from .base_client import whatsapp_base_client
from .ruvexi_service import ruvexi_whatsapp_service


STATUS_HIERARCHY = {"queued": 0, "pending": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4, "dead_letter": 5}
OPT_OUT_KEYWORDS = {"STOP", "UNSUBSCRIBE", "OPTOUT", "OPT OUT", "CANCEL"}


class WhatsAppWebhookService:
    """Resolves webhook events strictly against stored RUVEXI or Salon WhatsApp identifiers."""

    def resolve_channel_and_tenant(
        self,
        db: Session,
        phone_number_id: Optional[str],
        waba_id: Optional[str],
    ) -> Tuple[str, Optional[str]]:
        if phone_number_id and ruvexi_whatsapp_service.phone_number_id and phone_number_id == ruvexi_whatsapp_service.phone_number_id:
            return "RUVEXI", None
        if waba_id and ruvexi_whatsapp_service.waba_id and waba_id == ruvexi_whatsapp_service.waba_id:
            return "RUVEXI", None

        if phone_number_id:
            conn = (
                db.query(WhatsAppConnectionModel)
                .filter(WhatsAppConnectionModel.phone_number_id == phone_number_id)
                .first()
            )
            if conn:
                return "SALON", conn.tenant_id

        if waba_id:
            conn = (
                db.query(WhatsAppConnectionModel)
                .filter(WhatsAppConnectionModel.waba_id == waba_id)
                .first()
            )
            if conn:
                return "SALON", conn.tenant_id

        return "UNKNOWN", None

    def process_webhook_payload(self, db: Session, raw_body: bytes) -> Dict[str, Any]:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        entries = payload.get("entry", [])
        processed_events = 0
        deduplicated_events = 0

        for entry in entries:
            waba_id = str(entry.get("id") or "")
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = str(metadata.get("phone_number_id") or "")
                channel_type, tenant_id = self.resolve_channel_and_tenant(db, phone_number_id, waba_id)

                # 1. Status Updates (sent, delivered, read, failed)
                for st in value.get("statuses", []):
                    meta_msg_id = str(st.get("id") or "")
                    new_status = str(st.get("status") or "").lower()
                    if not meta_msg_id or not new_status:
                        continue

                    event_id = f"status:{meta_msg_id}:{new_status}:{st.get('timestamp', '')}"
                    if self._is_duplicate_event(db, event_id):
                        deduplicated_events += 1
                        continue

                    evt = WhatsAppWebhookEventModel(
                        tenant_id=tenant_id,
                        channel_type=channel_type,
                        event_id=event_id,
                        event_type="status_update",
                        processing_status="received",
                        raw_payload=json.dumps(st),
                    )
                    db.add(evt)

                    self._apply_status_update(db, meta_msg_id, new_status, st, tenant_id)
                    evt.processing_status = "processed"
                    evt.processed_at = datetime.utcnow()
                    processed_events += 1

                # 2. Inbound Customer Messages (24h window + STOP opt-out handling)
                for msg in value.get("messages", []):
                    msg_id = str(msg.get("id") or "")
                    from_phone = str(msg.get("from") or "")
                    text_body = str((msg.get("text") or {}).get("body") or "").strip()
                    if not msg_id:
                        msg_id = hashlib.md5(json.dumps(msg, sort_keys=True).encode("utf-8")).hexdigest()

                    event_id = f"inbound:{msg_id}"
                    if self._is_duplicate_event(db, event_id):
                        deduplicated_events += 1
                        continue

                    is_opt_out = text_body.upper() in OPT_OUT_KEYWORDS
                    evt = WhatsAppWebhookEventModel(
                        tenant_id=tenant_id,
                        channel_type=channel_type,
                        event_id=event_id,
                        event_type="opt_out" if is_opt_out else "inbound_message",
                        processing_status="received",
                        raw_payload=json.dumps(msg),
                    )
                    db.add(evt)

                    if channel_type == "SALON" and tenant_id and from_phone:
                        self._update_customer_inbound_state(db, tenant_id, from_phone, is_opt_out)

                    evt.processing_status = "processed"
                    evt.processed_at = datetime.utcnow()
                    processed_events += 1

        db.commit()
        return {
            "status": "received",
            "processed": processed_events,
            "deduplicated": deduplicated_events,
        }

    def _is_duplicate_event(self, db: Session, event_id: str) -> bool:
        return (
            db.query(WhatsAppWebhookEventModel)
            .filter(WhatsAppWebhookEventModel.event_id == event_id)
            .first()
            is not None
        )

    def _apply_status_update(
        self,
        db: Session,
        meta_msg_id: str,
        new_status: str,
        st: Dict[str, Any],
        resolved_tenant_id: Optional[str],
    ) -> None:
        now = datetime.utcnow()
        errors = st.get("errors", [])
        err_text = None
        if errors:
            err_text = f"Code {errors[0].get('code', '')}: {errors[0].get('title', 'Delivery failure')}"

        # Update new unified log table
        log = (
            db.query(WhatsAppMessageLogModel)
            .filter(WhatsAppMessageLogModel.meta_message_id == meta_msg_id)
            .first()
        )
        if log:
            if STATUS_HIERARCHY.get(new_status, 0) >= STATUS_HIERARCHY.get(log.delivery_status, 0) or new_status == "failed":
                log.delivery_status = new_status
                log.updated_at = now
                if new_status == "delivered":
                    log.delivered_at = now
                elif new_status == "read":
                    log.read_at = now
                if err_text:
                    log.failure_reason = err_text

        # Also update legacy WhatsAppMessageModel for backward compatibility
        legacy_msg = (
            db.query(WhatsAppMessageModel)
            .filter(WhatsAppMessageModel.meta_message_id == meta_msg_id)
            .first()
        )
        if legacy_msg:
            if STATUS_HIERARCHY.get(new_status, 0) >= STATUS_HIERARCHY.get(legacy_msg.status, 0) or new_status == "failed":
                legacy_msg.status = new_status
                legacy_msg.updated_at = now
                if err_text:
                    legacy_msg.error_details = err_text

        target_tenant = resolved_tenant_id or (log.tenant_id if log else (legacy_msg.salon_id if legacy_msg else None))
        if target_tenant:
            conn = db.query(WhatsAppConnectionModel).filter(WhatsAppConnectionModel.tenant_id == target_tenant).first()
            if conn:
                conn.webhook_subscription_status = "subscribed"
                conn.last_verified_at = now
            salon = db.query(SalonModel).filter(SalonModel.id == target_tenant).first()
            if salon:
                salon.whatsapp_webhook_verified = True

    def _update_customer_inbound_state(
        self,
        db: Session,
        tenant_id: str,
        from_phone: str,
        is_opt_out: bool,
    ) -> None:
        norm = whatsapp_base_client.normalize_phone(from_phone)
        if not norm:
            return
        tail = norm[-10:]
        customers = db.query(CustomerModel).filter(CustomerModel.salon_id == tenant_id).all()
        for cust in customers:
            if whatsapp_base_client.normalize_phone(cust.phone).endswith(tail):
                cust.whatsapp_last_inbound_at = datetime.utcnow()
                if is_opt_out:
                    cust.whatsapp_marketing_opt_in = False
                    cust.whatsapp_opt_in = False


whatsapp_webhook_service = WhatsAppWebhookService()
