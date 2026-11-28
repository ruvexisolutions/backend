"""Meta WhatsApp Embedded Signup & OAuth lifecycle service (server-side token exchange, validation, revocation)."""

import os
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import httpx
from sqlalchemy.orm import Session
from app.core.models import SalonModel, WhatsAppConnectionModel, WhatsAppAuditLogModel
from app.core.security import encrypt_secret, decrypt_secret, SECRET_KEY
from .base_client import whatsapp_base_client, is_sandbox_token


class EmbeddedSignupService:
    """Handles Meta OAuth state verification, code exchange, WABA/phone discovery, webhook subscription, and disconnect."""

    def generate_oauth_state(self, tenant_id: str, user_id: str) -> str:
        ts = str(int(time.time()))
        payload = f"{tenant_id}:{user_id}:{ts}"
        sig = hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        return f"{payload}:{sig}"

    def verify_oauth_state(self, state: str, tenant_id: str, user_id: str, max_age_seconds: int = 900) -> bool:
        parts = (state or "").split(":")
        if len(parts) != 4:
            return False
        s_tenant, s_user, s_ts, s_sig = parts
        if s_tenant != tenant_id or s_user != user_id:
            return False
        try:
            if abs(int(time.time()) - int(s_ts)) > max_age_seconds:
                return False
        except ValueError:
            return False
        payload = f"{s_tenant}:{s_user}:{s_ts}"
        expected = hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        return hmac.compare_digest(expected, s_sig)

    async def exchange_code_for_token(self, code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        app_id = os.getenv("META_APP_ID", "").strip()
        app_secret = os.getenv("META_APP_SECRET", "").strip()
        if not app_id or not app_secret:
            return {
                "success": False,
                "error": "META_APP_ID and META_APP_SECRET must be configured on the backend.",
            }
        if is_sandbox_token(code):
            return {"success": True, "access_token": code, "expires_in": 5184000, "is_live": False}

        url = f"https://graph.facebook.com/{whatsapp_base_client.api_version}/oauth/access_token"
        params: Dict[str, Any] = {
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
        }
        if redirect_uri:
            params["redirect_uri"] = redirect_uri

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params)
                data = resp.json()
                if resp.status_code == 200 and data.get("access_token"):
                    return {
                        "success": True,
                        "access_token": data["access_token"],
                        "expires_in": data.get("expires_in"),
                        "is_live": True,
                    }
                return {
                    "success": False,
                    "error": data.get("error", {}).get("message", "Meta OAuth token exchange failed"),
                }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def fetch_waba_phone_numbers(self, waba_id: str, access_token: str) -> List[Dict[str, Any]]:
        if not waba_id or not access_token:
            return []
        if is_sandbox_token(access_token):
            return [
                {
                    "id": "100000000000001",
                    "display_phone_number": "+91 98450 11223",
                    "verified_name": "Ruvexi Sandbox Salon",
                    "quality_rating": "GREEN",
                }
            ]
        url = f"https://graph.facebook.com/{whatsapp_base_client.api_version}/{waba_id}/phone_numbers"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp.json().get("data", [])
        except Exception:
            pass
        return []

    async def subscribe_waba_webhook(self, waba_id: str, access_token: str) -> bool:
        if not waba_id or not access_token:
            return False
        if is_sandbox_token(access_token):
            return True
        url = f"https://graph.facebook.com/{whatsapp_base_client.api_version}/{waba_id}/subscribed_apps"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(url, headers=headers)
                return resp.status_code in (200, 201) and bool(resp.json().get("success", True))
        except Exception:
            return False

    async def connect_tenant(
        self,
        *,
        db: Session,
        salon: SalonModel,
        actor_user_id: str,
        waba_id: Optional[str],
        phone_number_id: Optional[str],
        access_token: str,
        display_number: Optional[str] = None,
        verified_name: Optional[str] = None,
        expires_in_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Validates, subscribes webhook, encrypts token at rest, and persists tenant connection."""
        resolved_phone_id = (phone_number_id or "").strip()
        if not resolved_phone_id and waba_id:
            numbers = await self.fetch_waba_phone_numbers(waba_id, access_token)
            if numbers:
                resolved_phone_id = str(numbers[0].get("id") or "")
                display_number = display_number or numbers[0].get("display_phone_number")
                verified_name = verified_name or numbers[0].get("verified_name")

        if not resolved_phone_id:
            return {"success": False, "error": "Phone Number ID is required or could not be discovered from WABA."}

        validation = await whatsapp_base_client.validate_phone_credentials(
            phone_number_id=resolved_phone_id,
            access_token=access_token,
        )
        if not validation.get("success"):
            return {"success": False, "error": validation.get("error", "Meta credential validation failed.")}

        webhook_subscribed = await self.subscribe_waba_webhook(waba_id or "", access_token) if waba_id else False
        encrypted = encrypt_secret(access_token)
        now = datetime.utcnow()
        token_expiry = (now + timedelta(seconds=int(expires_in_seconds))) if expires_in_seconds else None

        conn = (
            db.query(WhatsAppConnectionModel)
            .filter(WhatsAppConnectionModel.tenant_id == salon.id)
            .first()
        )
        if not conn:
            conn = WhatsAppConnectionModel(tenant_id=salon.id)
            db.add(conn)

        conn.waba_id = (waba_id or "").strip() or None
        conn.phone_number_id = resolved_phone_id
        conn.display_phone_number = display_number or validation.get("display_phone_number") or salon.phone
        conn.verified_name = verified_name or validation.get("verified_name") or salon.name
        conn.quality_rating = validation.get("quality_rating") or "GREEN"
        conn.encrypted_access_token = encrypted
        conn.connection_status = "connected"
        conn.connected_at = conn.connected_at or now
        conn.token_expiry = token_expiry
        conn.token_validation_status = "valid"
        conn.webhook_subscription_status = "subscribed" if webhook_subscribed else "not_subscribed"
        conn.last_verified_at = now
        conn.error_message = None

        # Mirror to legacy SalonModel fields so existing screens/serializers stay consistent
        salon.whatsapp_waba_id = conn.waba_id
        salon.whatsapp_phone_number_id = conn.phone_number_id
        salon.whatsapp_access_token = encrypted
        salon.whatsapp_display_number = conn.display_phone_number
        salon.whatsapp_verified_name = conn.verified_name
        salon.whatsapp_quality_rating = conn.quality_rating
        salon.whatsapp_status = "connected"
        salon.whatsapp_last_tested_at = now
        salon.whatsapp_error_message = None
        salon.whatsapp_webhook_verified = webhook_subscribed

        db.add(
            WhatsAppAuditLogModel(
                tenant_id=salon.id,
                actor_user_id=actor_user_id,
                channel_type="SALON",
                action="WHATSAPP_CONNECTED",
                details=f"Connected WABA={conn.waba_id or 'N/A'}, PhoneNumberID={conn.phone_number_id}",
            )
        )
        db.commit()
        db.refresh(conn)
        return {"success": True, "connection": conn.to_dict()}

    async def disconnect_tenant(self, db: Session, salon: SalonModel, actor_user_id: str) -> Dict[str, Any]:
        conn = (
            db.query(WhatsAppConnectionModel)
            .filter(WhatsAppConnectionModel.tenant_id == salon.id)
            .first()
        )
        if conn:
            token = decrypt_secret(conn.encrypted_access_token) if conn.encrypted_access_token else ""
            if conn.waba_id and token and not is_sandbox_token(token):
                try:
                    url = f"https://graph.facebook.com/{whatsapp_base_client.api_version}/{conn.waba_id}/subscribed_apps"
                    async with httpx.AsyncClient(timeout=8.0) as client:
                        await client.delete(url, headers={"Authorization": f"Bearer {token}"})
                except Exception:
                    pass
            conn.encrypted_access_token = None
            conn.connection_status = "disconnected"
            conn.token_validation_status = "revoked"
            conn.webhook_subscription_status = "not_subscribed"
            conn.error_message = None

        salon.whatsapp_access_token = None
        salon.whatsapp_phone_number_id = None
        salon.whatsapp_waba_id = None
        salon.whatsapp_status = "not_connected"
        salon.whatsapp_webhook_verified = False
        salon.whatsapp_error_message = None

        db.add(
            WhatsAppAuditLogModel(
                tenant_id=salon.id,
                actor_user_id=actor_user_id,
                channel_type="SALON",
                action="WHATSAPP_DISCONNECTED",
                details="Tenant WhatsApp connection disconnected and token cleared.",
            )
        )
        db.commit()
        return {"success": True, "status": "disconnected"}


embedded_signup_service = EmbeddedSignupService()
