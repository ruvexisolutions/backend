"""Individual Salon WhatsApp Service (exclusively for customer-facing salon communications)."""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.models import SalonModel, WhatsAppConnectionModel, CustomerModel, WhatsAppTemplateModel
from app.core.security import decrypt_secret
from .base_client import whatsapp_base_client, is_sandbox_token


class SalonWhatsAppService:
    """
    Tenant-isolated WhatsApp Cloud API channel for customer-facing salon messages.
    NEVER falls back to RUVEXI official credentials.
    """

    def resolve_tenant_credentials(
        self,
        db: Session,
        tenant_id: str,
    ) -> Tuple[Optional[WhatsAppConnectionModel], Optional[str], Optional[str]]:
        """
        Resolves `(connection, phone_number_id, decrypted_access_token)` for a specific tenant.
        Returns `(conn, None, None)` if disconnected or missing credentials.
        """
        conn = (
            db.query(WhatsAppConnectionModel)
            .filter(WhatsAppConnectionModel.tenant_id == tenant_id)
            .first()
        )
        if conn:
            if conn.connection_status != "connected":
                return conn, None, None
            token = decrypt_secret(conn.encrypted_access_token) if conn.encrypted_access_token else ""
            if not conn.phone_number_id or not token:
                return conn, None, None
            return conn, conn.phone_number_id, token

        # Backward-compatible read from legacy SalonModel columns if WhatsAppConnectionModel row wasn't created yet
        salon = db.query(SalonModel).filter(SalonModel.id == tenant_id).first()
        if salon and salon.whatsapp_status == "connected" and salon.whatsapp_phone_number_id and salon.whatsapp_access_token:
            token = decrypt_secret(salon.whatsapp_access_token) or ""
            if token:
                migrated = WhatsAppConnectionModel(
                    tenant_id=salon.id,
                    waba_id=salon.whatsapp_waba_id,
                    phone_number_id=salon.whatsapp_phone_number_id,
                    display_phone_number=salon.whatsapp_display_number or salon.phone,
                    verified_name=salon.whatsapp_verified_name or salon.name,
                    quality_rating=salon.whatsapp_quality_rating or "GREEN",
                    encrypted_access_token=salon.whatsapp_access_token,
                    connection_status="connected",
                    connected_at=salon.whatsapp_last_tested_at or datetime.utcnow(),
                    token_validation_status="valid",
                    webhook_subscription_status="subscribed" if salon.whatsapp_webhook_verified else "not_subscribed",
                    last_verified_at=salon.whatsapp_last_tested_at,
                )
                db.add(migrated)
                db.commit()
                db.refresh(migrated)
                return migrated, migrated.phone_number_id, token

        return None, None, None

    def check_customer_consent(
        self,
        db: Session,
        tenant_id: str,
        recipient_phone: str,
        is_marketing: bool = False,
    ) -> Tuple[bool, Optional[str], bool]:
        """
        Checks customer opt-in status and 24-hour service window.
        Returns `(allowed, reason, within_24h_window)`.
        """
        norm = whatsapp_base_client.normalize_phone(recipient_phone)
        if not norm:
            return False, "Invalid customer phone number", False

        tail = norm[-10:]
        customers = (
            db.query(CustomerModel)
            .filter(CustomerModel.salon_id == tenant_id)
            .all()
        )
        matched = next(
            (c for c in customers if whatsapp_base_client.normalize_phone(c.phone).endswith(tail)),
            None,
        )
        if not matched:
            return True, None, False

        if matched.whatsapp_opt_in is False:
            return False, "Customer has opted out of WhatsApp notifications.", False
        if is_marketing and matched.whatsapp_marketing_opt_in is False:
            return False, "Customer has opted out of promotional WhatsApp messages.", False

        within_24h = False
        if matched.whatsapp_last_inbound_at:
            within_24h = (datetime.utcnow() - matched.whatsapp_last_inbound_at) <= timedelta(hours=24)
        return True, None, within_24h

    async def dispatch(
        self,
        *,
        db: Session,
        tenant_id: str,
        to_phone: str,
        message_text: str,
        template_name: Optional[str] = None,
        template_params: Optional[List[str]] = None,
        language_code: str = "en_US",
        is_marketing: bool = False,
    ) -> Dict[str, Any]:
        """Dispatches a customer-facing message strictly using the salon's own WhatsApp credentials."""
        conn, phone_number_id, access_token = self.resolve_tenant_credentials(db, tenant_id)
        if not phone_number_id or not access_token:
            return {
                "success": False,
                "error": "Salon WhatsApp Business account is not connected.",
                "retryable": False,
            }

        allowed, reason, _ = self.check_customer_consent(db, tenant_id, to_phone, is_marketing=is_marketing)
        if not allowed:
            return {
                "success": False,
                "error": reason or "Customer opt-in required.",
                "retryable": False,
            }

        # Prefer an APPROVED template stored or registered for this salon
        if template_name and template_params is not None:
            approved_tpl = (
                db.query(WhatsAppTemplateModel)
                .filter(
                    WhatsAppTemplateModel.tenant_id == tenant_id,
                    WhatsAppTemplateModel.channel_type == "SALON",
                    WhatsAppTemplateModel.template_name == template_name,
                    WhatsAppTemplateModel.approval_status.in_(["APPROVED", "SANDBOX_PREVIEW"]),
                )
                .first()
            )
            if approved_tpl or is_sandbox_token(access_token):
                tpl_res = await whatsapp_base_client.send_template(
                    to_phone=to_phone,
                    template_name=template_name,
                    body_parameters=template_params,
                    language_code=(approved_tpl.language if approved_tpl else language_code) or "en_US",
                    phone_number_id=phone_number_id,
                    access_token=access_token,
                )
                if tpl_res.get("success") or tpl_res.get("error_code") != 132001:
                    return tpl_res

        res = await whatsapp_base_client.send_text(
            to_phone=to_phone,
            message_text=message_text,
            phone_number_id=phone_number_id,
            access_token=access_token,
        )

        # If token expired, mark connection status cleanly
        if res.get("auth_expired") and conn:
            conn.connection_status = "expired"
            conn.token_validation_status = "expired"
            conn.error_message = res.get("error")
            db.commit()

        return res


salon_whatsapp_service = SalonWhatsAppService()
