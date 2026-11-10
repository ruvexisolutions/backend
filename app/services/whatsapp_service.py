import os
import hmac
import hashlib
import httpx
from typing import Dict, Any, Optional, List

WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "Ruvexi_meta_webhook_2026")
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v20.0")


def _is_sandbox_token(token: Optional[str]) -> bool:
    if not token:
        return False
    return (
        token.startswith("EAAG_SANDBOX")
        or token.startswith("EAAG_TEST")
        or token.startswith("test_")
        or "sandbox" in token.lower()
    )


class WhatsAppCloudService:
    def __init__(self):
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        self.verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "Ruvexi_meta_webhook_2026")
        self.api_version = os.getenv("META_GRAPH_API_VERSION", "v20.0")
        self.default_country_code = os.getenv("DEFAULT_COUNTRY_CODE", "91")
        self.is_configured = bool(self.phone_number_id and self.access_token)

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone numbers to E.164 digits without '+' (supports international & Indian 10-digit numbers)."""
        raw = (phone or "").strip()
        if not raw:
            return ""
        has_plus = raw.startswith("+")
        digits = "".join(filter(str.isdigit, raw))
        if len(digits) < 7:
            return ""
        if has_plus:
            return digits
        if len(digits) == 10:
            return f"{self.default_country_code}{digits}"
        if digits.startswith("0") and len(digits) == 11:
            return f"{self.default_country_code}{digits[1:]}"
        return digits

    def verify_webhook_signature(self, raw_body: bytes, signature_header: Optional[str]) -> bool:
        """
        Verifies Meta X-Hub-Signature-256 HMAC-SHA256 webhook signature when META_APP_SECRET is set.
        """
        app_secret = os.getenv("META_APP_SECRET") or os.getenv("WHATSAPP_APP_SECRET") or ""
        if not app_secret:
            # Signature secret not configured; enforce strictly only when explicitly required
            return os.getenv("REQUIRE_WHATSAPP_SIGNATURE", "false").lower() != "true"

        if not signature_header or not signature_header.startswith("sha256="):
            return False

        expected_sig = hmac.new(
            app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        received_sig = signature_header[7:].strip()
        return hmac.compare_digest(expected_sig, received_sig)

    async def send_text_message(
        self,
        to_phone: str,
        message_text: str,
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sends a session text WhatsApp message via Meta Cloud API (valid inside 24h customer reply window)."""
        recipient = self._normalize_phone(to_phone)
        if not recipient:
            return {"success": False, "error": "Invalid recipient phone number"}

        active_phone_id = phone_number_id or self.phone_number_id
        active_token = access_token or self.access_token

        if active_phone_id and active_token and _is_sandbox_token(active_token):
            return {
                "success": True,
                "message_id": f"wamid.sandbox_{recipient}_{hashlib.md5(message_text.encode('utf-8')).hexdigest()[:10]}",
                "is_live": False,
                "sender_phone_id": active_phone_id,
            }

        if active_phone_id and active_token:
            url = f"https://graph.facebook.com/{self.api_version}/{active_phone_id}/messages"
            headers = {
                "Authorization": f"Bearer {active_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {
                    "preview_url": True,
                    "body": message_text,
                },
            }

            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    data = resp.json()
                    if resp.status_code in [200, 201]:
                        msg_id = data.get("messages", [{}])[0].get("id")
                        return {
                            "success": True,
                            "message_id": msg_id,
                            "is_live": True,
                            "sender_phone_id": active_phone_id,
                            "delivery_mode": "text",
                            "raw": data,
                        }
                    err_obj = data.get("error", {})
                    err_code = err_obj.get("code")
                    err_msg = err_obj.get("message", "Meta API Error")
                    if err_code == 131047:
                        err_msg = "24-hour customer reply window closed. Register and approve an official Meta message template for business-initiated messages."
                    return {
                        "success": False,
                        "error": err_msg,
                        "error_code": err_code,
                        "is_live": True,
                        "raw": data,
                    }
            except Exception as e:
                return {"success": False, "error": str(e), "is_live": True}

        return {
            "success": False,
            "error": "WhatsApp Cloud API credentials not configured for this salon. Please connect via Salon Manager Settings.",
            "is_live": False,
            "sender_phone_id": active_phone_id,
        }

    async def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        body_parameters: List[str],
        language_code: str = "en_US",
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sends an official Meta-approved WhatsApp template message (works anytime, including outside 24h windows)."""
        recipient = self._normalize_phone(to_phone)
        if not recipient:
            return {"success": False, "error": "Invalid recipient phone number"}

        active_phone_id = phone_number_id or self.phone_number_id
        active_token = access_token or self.access_token

        if not active_phone_id or not active_token:
            return {
                "success": False,
                "error": "WhatsApp Cloud API credentials not configured for this salon.",
                "is_live": False,
            }

        if _is_sandbox_token(active_token):
            return {
                "success": True,
                "message_id": f"wamid.tpl_sandbox_{template_name}_{recipient[-4:]}",
                "is_live": False,
                "delivery_mode": "template",
                "template_name": template_name,
            }

        url = f"https://graph.facebook.com/{self.api_version}/{active_phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {active_token}",
            "Content-Type": "application/json",
        }
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

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                data = resp.json()
                if resp.status_code in [200, 201]:
                    msg_id = data.get("messages", [{}])[0].get("id")
                    return {
                        "success": True,
                        "message_id": msg_id,
                        "is_live": True,
                        "delivery_mode": "template",
                        "template_name": template_name,
                        "sender_phone_id": active_phone_id,
                        "raw": data,
                    }
                err_obj = data.get("error", {})
                return {
                    "success": False,
                    "error": err_obj.get("message", "Meta template dispatch error"),
                    "error_code": err_obj.get("code"),
                    "is_live": True,
                    "raw": data,
                }
        except Exception as e:
            return {"success": False, "error": str(e), "is_live": True}

    async def exchange_embedded_signup_code(self, code: str) -> Dict[str, Any]:
        """
        Exchanges the temporary code from Meta Embedded Signup popup
        for a Business Integration Access Token via Meta Graph API.
        """
        app_id = os.getenv("META_APP_ID", "")
        app_secret = os.getenv("META_APP_SECRET", "")

        if app_id and app_secret:
            url = f"https://graph.facebook.com/{self.api_version}/oauth/access_token"
            params = {
                "client_id": app_id,
                "client_secret": app_secret,
                "code": code,
            }
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.get(url, params=params)
                    data = resp.json()
                    if resp.status_code == 200 and data.get("access_token"):
                        return {"success": True, "access_token": data["access_token"], "is_live": True}
                    return {"success": False, "error": data.get("error", {}).get("message", "Token exchange failed")}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {
            "success": False,
            "error": "Meta App ID (META_APP_ID) and App Secret (META_APP_SECRET) must be configured in backend environment.",
        }

    async def validate_credentials(
        self,
        phone_number_id: str,
        access_token: str,
        waba_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validates credentials directly against Meta Graph API endpoint."""
        if not phone_number_id or not access_token:
            return {"success": False, "error": "Phone Number ID and Access Token are required"}

        if _is_sandbox_token(access_token):
            return {
                "success": True,
                "is_live": False,
                "verified_name": "Ruvexi Verified Atelier",
                "display_phone_number": "+91 98450 11223",
                "quality_rating": "GREEN",
                "status": "connected",
                "message": "Validated in sandbox mode",
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
                        "verified_name": data.get("verified_name") or "Verified Salon Atelier",
                        "display_phone_number": data.get("display_phone_number") or "",
                        "quality_rating": data.get("quality_rating") or "GREEN",
                        "status": "connected",
                    }
                err_msg = data.get("error", {}).get(
                    "message", "Meta Graph API authorization failed. Please check credentials."
                )
                return {"success": False, "error": err_msg}
        except Exception as e:
            return {"success": False, "error": f"Failed to connect to Meta Graph API: {str(e)}", "is_live": False}

    async def fetch_templates(
        self,
        waba_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetches actual approved/pending WhatsApp message templates from Meta Graph API (`/{waba_id}/message_templates`).
        """
        active_token = access_token or self.access_token
        if not active_token:
            return []

        if _is_sandbox_token(active_token):
            return [
                {
                    "name": "ruvexi_service_receipt",
                    "category": "UTILITY",
                    "language": "en_US",
                    "status": "SANDBOX_PREVIEW",
                    "description": "GST Salon Bill receipt template (register on Meta Business Manager for live delivery).",
                },
                {
                    "name": "ruvexi_appointment_confirmation",
                    "category": "UTILITY",
                    "language": "en_US",
                    "status": "SANDBOX_PREVIEW",
                    "description": "Appointment booking confirmation with stylist and time slot.",
                },
            ]

        if not waba_id:
            return []

        url = f"https://graph.facebook.com/{self.api_version}/{waba_id}/message_templates"
        headers = {"Authorization": f"Bearer {active_token}"}
        params = {"limit": 50, "fields": "name,category,language,status,components"}

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                templates = []
                for tpl in data.get("data", []):
                    body_comp = next((c for c in tpl.get("components", []) if c.get("type") == "BODY"), None)
                    templates.append({
                        "name": tpl.get("name"),
                        "category": tpl.get("category", "UTILITY"),
                        "language": tpl.get("language", "en_US"),
                        "status": tpl.get("status", "UNKNOWN"),
                        "description": (body_comp or {}).get("text", ""),
                    })
                return templates
        except Exception:
            return []

    async def _send_with_template_or_text(
        self,
        to_phone: str,
        template_name: str,
        body_parameters: List[str],
        fallback_text: str,
        waba_id: Optional[str],
        phone_number_id: Optional[str],
        access_token: Optional[str],
    ) -> Dict[str, Any]:
        """
        Prefers an APPROVED Meta template matching `template_name` on the salon's WABA so messages
        deliver outside the 24-hour session window; falls back to session text if template isn't registered yet.
        """
        approved_tpl = None
        if waba_id and access_token and not _is_sandbox_token(access_token):
            templates = await self.fetch_templates(waba_id=waba_id, access_token=access_token)
            approved_tpl = next(
                (
                    t
                    for t in templates
                    if t.get("status") == "APPROVED"
                    and t.get("name", "").lower() == template_name.lower()
                ),
                None,
            )

        if approved_tpl:
            tpl_res = await self.send_template_message(
                to_phone=to_phone,
                template_name=approved_tpl["name"],
                body_parameters=body_parameters,
                language_code=approved_tpl.get("language") or "en_US",
                phone_number_id=phone_number_id,
                access_token=access_token,
            )
            if tpl_res.get("success") or tpl_res.get("error_code") != 132001:
                return tpl_res

        return await self.send_text_message(
            to_phone=to_phone,
            message_text=fallback_text,
            phone_number_id=phone_number_id,
            access_token=access_token,
        )

    async def send_bill_notification(
        self,
        to_phone: str,
        customer_name: str,
        invoice_number: str,
        total_amount: float,
        items: List[Dict[str, Any]],
        salon_name: str = "Ruvexi Salon",
        payment_link: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
        waba_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches salon bill via Meta approved template (if registered) or session text."""
        items_text = "\n".join(
            [f"• {it.get('name', 'Service')} - ₹{float(it.get('price', 0)):,.2f}" for it in items[:4]]
        )
        if len(items) > 4:
            items_text += f"\n• ... +{len(items) - 4} more items"
        items_inline = ", ".join([str(it.get("name", "Service")) for it in items[:3]]) or "Salon Services"

        pay_text = f"\n\n💳 *Payment / Receipt Link:*\n{payment_link}" if payment_link else ""

        message_body = (
            f"✨ *Thank you for visiting {salon_name}, {customer_name}!*\n\n"
            f"🧾 *Invoice Details:*\n"
            f"• Invoice ID: *#{invoice_number}*\n"
            f"• Grand Total: *₹{total_amount:,.2f}*\n\n"
            f"📋 *Services:*\n{items_text}"
            f"{pay_text}\n\n"
            f"Warm regards,\n*{salon_name}*"
        )

        tpl_name = os.getenv("WHATSAPP_BILL_TEMPLATE", "ruvexi_service_receipt")
        return await self._send_with_template_or_text(
            to_phone=to_phone,
            template_name=tpl_name,
            body_parameters=[customer_name, salon_name, invoice_number, items_inline, f"₹{total_amount:,.2f}"],
            fallback_text=message_body,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            access_token=access_token,
        )

    async def send_appointment_confirmation(
        self,
        to_phone: str,
        customer_name: str,
        service_name: str,
        staff_name: str,
        date_time: str,
        salon_name: str = "Ruvexi Salon",
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
        waba_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches appointment confirmation via Meta approved template (if registered) or session text."""
        message_body = (
            f"📅 *Booking Confirmed with {salon_name}!*\n\n"
            f"Hello {customer_name},\n"
            f"Your appointment is confirmed:\n\n"
            f"💆 *Service:* {service_name}\n"
            f"✂️ *Stylist:* {staff_name}\n"
            f"⏰ *Date & Time:* {date_time}\n"
            f"📍 *Studio:* {salon_name}\n\n"
            f"Need to reschedule? Reply to this chat anytime."
        )

        tpl_name = os.getenv("WHATSAPP_APPT_TEMPLATE", "ruvexi_appointment_confirmation")
        return await self._send_with_template_or_text(
            to_phone=to_phone,
            template_name=tpl_name,
            body_parameters=[customer_name, salon_name, service_name, staff_name, date_time],
            fallback_text=message_body,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            access_token=access_token,
        )

    async def send_retention_campaign(
        self,
        to_phone: str,
        customer_name: str,
        custom_message: str,
        salon_name: str = "Ruvexi Salon",
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
        waba_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches personalized client retention / offer message via Meta approved template or session text."""
        message_body = f"{custom_message}\n\n- *{salon_name}*"
        tpl_name = os.getenv("WHATSAPP_CAMPAIGN_TEMPLATE", "ruvexi_rebooking_touchup")
        return await self._send_with_template_or_text(
            to_phone=to_phone,
            template_name=tpl_name,
            body_parameters=[customer_name, salon_name, custom_message],
            fallback_text=message_body,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            access_token=access_token,
        )


whatsapp_service = WhatsAppCloudService()
