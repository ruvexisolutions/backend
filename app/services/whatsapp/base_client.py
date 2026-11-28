"""Shared Meta Graph API HTTP client, phone normalization, and webhook signature verification."""

import os
import hmac
import hashlib
from typing import Dict, Any, Optional, List
import httpx


RETRYABLE_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}
RETRYABLE_META_ERROR_CODES = {1, 2, 4, 17, 130429, 131016, 131048, 131056}
AUTH_EXPIRED_META_ERROR_CODES = {190, 102, 10}


def is_sandbox_token(token: Optional[str]) -> bool:
    if not token:
        return False
    low = token.lower()
    return (
        token.startswith("EAAG_SANDBOX")
        or token.startswith("EAAG_TEST")
        or token.startswith("test_")
        or "sandbox" in low
    )


class WhatsAppBaseClient:
    """Low-level Meta WhatsApp Cloud API client. Holds NO tenant or platform credentials of its own."""

    def __init__(self):
        self.default_country_code = os.getenv("DEFAULT_COUNTRY_CODE", "91")

    @property
    def api_version(self) -> str:
        return os.getenv("META_GRAPH_API_VERSION", "v20.0").strip() or "v20.0"

    def normalize_phone(self, phone: Optional[str]) -> str:
        """Normalize phone numbers to E.164 digits without '+'."""
        raw = (phone or "").strip()
        if not raw:
            return ""
        has_plus = raw.startswith("+")
        digits = "".join(filter(str.isdigit, raw))
        if len(digits) < 7 or len(digits) > 15:
            return ""
        if has_plus:
            return digits
        if len(digits) == 10:
            return f"{self.default_country_code}{digits}"
        if digits.startswith("0") and len(digits) == 11:
            return f"{self.default_country_code}{digits[1:]}"
        return digits

    def verify_webhook_signature(self, raw_body: bytes, signature_header: Optional[str]) -> bool:
        """Verifies Meta X-Hub-Signature-256 HMAC-SHA256 webhook signature (fail-closed in prod)."""
        app_secret = (os.getenv("META_APP_SECRET") or os.getenv("WHATSAPP_APP_SECRET") or "").strip()
        if not app_secret:
            is_prod = (
                os.getenv("ENVIRONMENT", "").lower() == "production"
                or bool(os.getenv("RAILWAY_ENVIRONMENT"))
            )
            if is_prod:
                return False
            return os.getenv("ALLOW_UNSIGNED_WEBHOOKS", "false").lower() == "true"

        if not signature_header or not signature_header.startswith("sha256="):
            return False

        expected_sig = hmac.new(
            app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        received_sig = signature_header[7:].strip()
        return hmac.compare_digest(expected_sig, received_sig)

    async def send_text(
        self,
        *,
        to_phone: str,
        message_text: str,
        phone_number_id: str,
        access_token: str,
    ) -> Dict[str, Any]:
        recipient = self.normalize_phone(to_phone)
        if not recipient:
            return {"success": False, "error": "Invalid recipient phone number", "retryable": False}
        if not phone_number_id or not access_token:
            return {"success": False, "error": "WhatsApp credentials missing", "retryable": False}

        if is_sandbox_token(access_token):
            digest = hashlib.md5(f"{phone_number_id}:{recipient}:{message_text}".encode("utf-8")).hexdigest()[:10]
            return {
                "success": True,
                "message_id": f"wamid.sandbox_{recipient}_{digest}",
                "is_live": False,
                "delivery_mode": "text",
                "sender_phone_id": phone_number_id,
            }

        url = f"https://graph.facebook.com/{self.api_version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": True, "body": message_text[:4096]},
        }
        return await self._post_message(url, access_token, payload, phone_number_id, "text")

    async def send_template(
        self,
        *,
        to_phone: str,
        template_name: str,
        body_parameters: List[str],
        language_code: str = "en_US",
        phone_number_id: str,
        access_token: str,
    ) -> Dict[str, Any]:
        recipient = self.normalize_phone(to_phone)
        if not recipient:
            return {"success": False, "error": "Invalid recipient phone number", "retryable": False}
        if not phone_number_id or not access_token:
            return {"success": False, "error": "WhatsApp credentials missing", "retryable": False}

        if is_sandbox_token(access_token):
            return {
                "success": True,
                "message_id": f"wamid.tpl_sandbox_{template_name}_{recipient[-4:]}",
                "is_live": False,
                "delivery_mode": "template",
                "template_name": template_name,
                "sender_phone_id": phone_number_id,
            }

        url = f"https://graph.facebook.com/{self.api_version}/{phone_number_id}/messages"
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code or "en_US"},
            },
        }
        if body_parameters:
            payload["template"]["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(p)[:1024]} for p in body_parameters],
                }
            ]
        return await self._post_message(url, access_token, payload, phone_number_id, "template", template_name)

    async def _post_message(
        self,
        url: str,
        access_token: str,
        payload: Dict[str, Any],
        phone_number_id: str,
        delivery_mode: str,
        template_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw_text": resp.text[:500]}

                if resp.status_code in (200, 201):
                    msg_id = (data.get("messages") or [{}])[0].get("id")
                    return {
                        "success": True,
                        "message_id": msg_id,
                        "is_live": True,
                        "delivery_mode": delivery_mode,
                        "template_name": template_name,
                        "sender_phone_id": phone_number_id,
                    }

                err_obj = data.get("error", {}) if isinstance(data, dict) else {}
                err_code = err_obj.get("code")
                err_msg = err_obj.get("message") or f"Meta Graph API HTTP {resp.status_code}"
                if err_code == 131047:
                    err_msg = "24-hour customer service window closed. Approved template required."
                retryable = (
                    resp.status_code in RETRYABLE_HTTP_STATUSES
                    or err_code in RETRYABLE_META_ERROR_CODES
                )
                auth_expired = err_code in AUTH_EXPIRED_META_ERROR_CODES
                return {
                    "success": False,
                    "error": err_msg,
                    "error_code": err_code,
                    "http_status": resp.status_code,
                    "retryable": retryable,
                    "auth_expired": auth_expired,
                    "is_live": True,
                }
        except (httpx.TimeoutException, httpx.NetworkError) as net_err:
            return {
                "success": False,
                "error": f"Network/timeout error: {str(net_err)}",
                "retryable": True,
                "is_live": True,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "retryable": False,
                "is_live": True,
            }

    async def validate_phone_credentials(
        self,
        *,
        phone_number_id: str,
        access_token: str,
    ) -> Dict[str, Any]:
        if not phone_number_id or not access_token:
            return {"success": False, "error": "Phone Number ID and Access Token are required."}

        if is_sandbox_token(access_token):
            return {
                "success": True,
                "is_live": False,
                "verified_name": "Ruvexi Sandbox Business",
                "display_phone_number": "+91 98450 11223",
                "quality_rating": "GREEN",
                "status": "connected",
            }

        url = f"https://graph.facebook.com/{self.api_version}/{phone_number_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"fields": "verified_name,display_phone_number,quality_rating,code_verification_status"}
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(url, headers=headers, params=params)
                data = resp.json()
                if resp.status_code == 200:
                    return {
                        "success": True,
                        "is_live": True,
                        "verified_name": data.get("verified_name") or "Verified WhatsApp Business",
                        "display_phone_number": data.get("display_phone_number") or "",
                        "quality_rating": data.get("quality_rating") or "GREEN",
                        "status": "connected",
                    }
                err = data.get("error", {})
                return {
                    "success": False,
                    "error": err.get("message") or "Meta Graph API verification failed",
                    "error_code": err.get("code"),
                    "auth_expired": err.get("code") in AUTH_EXPIRED_META_ERROR_CODES,
                }
        except Exception as exc:
            return {"success": False, "error": f"Meta Graph API request failed: {str(exc)}"}


whatsapp_base_client = WhatsAppBaseClient()
