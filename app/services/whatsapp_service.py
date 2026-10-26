import os
import httpx
from typing import Dict, Any, Optional, List

WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "billcare_meta_webhook_2026")
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v20.0")

class WhatsAppCloudService:
    def __init__(self):
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        self.verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "billcare_meta_webhook_2026")
        self.api_version = os.getenv("META_GRAPH_API_VERSION", "v20.0")
        self.is_configured = bool(self.phone_number_id and self.access_token)

    def _normalize_phone(self, phone: str) -> str:
        """Normalize Indian phone numbers to E.164 without '+' or leading '0'."""
        digits = "".join(filter(str.isdigit, phone))
        if len(digits) == 10:
            return f"91{digits}"
        if digits.startswith("0") and len(digits) == 11:
            return f"91{digits[1:]}"
        return digits

    async def send_text_message(
        self,
        to_phone: str,
        message_text: str,
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sends a direct interactive WhatsApp message via Meta Cloud API using salon credentials or fallback."""
        recipient = self._normalize_phone(to_phone)
        if not recipient:
            return {"success": False, "error": "Invalid recipient phone number"}

        active_phone_id = phone_number_id or self.phone_number_id
        active_token = access_token or self.access_token

        if active_phone_id and active_token and not active_token.startswith("EAAG_SANDBOX"):
            url = f"https://graph.facebook.com/{self.api_version}/{active_phone_id}/messages"
            headers = {
                "Authorization": f"Bearer {active_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {
                    "preview_url": True,
                    "body": message_text
                }
            }

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    data = resp.json()
                    if resp.status_code in [200, 201]:
                        msg_id = data.get("messages", [{}])[0].get("id")
                        return {"success": True, "message_id": msg_id, "is_live": True, "sender_phone_id": active_phone_id, "raw": data}
                    else:
                        return {"success": False, "error": data.get("error", {}).get("message", "Meta API Error"), "is_live": True, "raw": data}
            except Exception as e:
                return {"success": False, "error": str(e), "is_live": True}

        # Simulated Sandbox Delivery when token is not yet configured
        return {
            "success": True,
            "message_id": f"wamid_mock_{recipient}",
            "recipient": recipient,
            "is_live": False,
            "sender_phone_id": active_phone_id or "meta_shared_billcare_sandbox",
            "preview": message_text[:120] + "...",
            "notice": "Meta Cloud API Sandbox Mode. Complete Embedded Signup to link your official salon phone number."
        }

    async def exchange_embedded_signup_code(self, code: str) -> Dict[str, Any]:
        """
        Exchanges the temporary code from Meta Embedded Signup popup
        for a permanent System User Access Token via Meta Graph API.
        """
        app_id = os.getenv("META_APP_ID", "")
        app_secret = os.getenv("META_APP_SECRET", "")

        if app_id and app_secret:
            url = f"https://graph.facebook.com/{self.api_version}/oauth/access_token"
            params = {
                "client_id": app_id,
                "client_secret": app_secret,
                "code": code
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, params=params)
                    data = resp.json()
                    if resp.status_code == 200:
                        return {"success": True, "access_token": data.get("access_token"), "is_live": True}
                    else:
                        return {"success": False, "error": data.get("error", {}).get("message", "Token exchange failed")}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Sandbox emulator for development/testing
        return {
            "success": True,
            "access_token": f"EAAG_SANDBOX_{code[:16]}",
            "is_live": False
        }

    async def send_bill_notification(
        self,
        to_phone: str,
        customer_name: str,
        invoice_number: str,
        total_amount: float,
        items: List[Dict[str, Any]],
        salon_name: str = "BillCare Luxury Salon",
        payment_link: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Formats and dispatches official GST Salon Invoice message with line-item breakdown
        and instant digital receipt / payment link.
        """
        items_text = "\n".join([f"• {it.get('name', 'Service')} - ₹{it.get('price', 0):,.2f}" for it in items[:4]])
        if len(items) > 4:
            items_text += f"\n• ... +{len(items) - 4} more items"

        pay_text = f"\n\n💳 *Instant Payment / Receipt Link:*\n{payment_link}" if payment_link else ""

        message_body = (
            f"✨ *Thank you for visiting {salon_name}, {customer_name}!* ✨\n\n"
            f"🧾 *Invoice Details:*\n"
            f"• Invoice ID: *#{invoice_number}*\n"
            f"• Grand Total: *₹{total_amount:,.2f}*\n\n"
            f"📋 *Summary of Services:*\n{items_text}"
            f"{pay_text}\n\n"
            f"We hope you loved your experience today. Please let us know if you need anything!\n"
            f"Warm regards,\n*{salon_name} Team*"
        )

        return await self.send_text_message(
            to_phone=to_phone,
            message_text=message_body,
            phone_number_id=phone_number_id,
            access_token=access_token
        )

    async def send_appointment_confirmation(
        self,
        to_phone: str,
        customer_name: str,
        service_name: str,
        staff_name: str,
        date_time: str,
        salon_name: str = "BillCare Luxury Salon",
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Dispatches automated appointment reservation confirmation."""
        message_body = (
            f"🗓️ *Booking Confirmed with {salon_name}!*\n\n"
            f"Hello {customer_name},\n"
            f"Your appointment is confirmed with our top specialist:\n\n"
            f"💇 *Service:* {service_name}\n"
            f"✂️ *Stylist / Specialist:* {staff_name}\n"
            f"⏰ *Date & Time:* {date_time}\n"
            f"📍 *Location:* {salon_name} Studio\n\n"
            f"Need to reschedule or cancel? Reply to this message directly or call us.\n"
            f"We look forward to pampering you!"
        )
        return await self.send_text_message(
            to_phone=to_phone,
            message_text=message_body,
            phone_number_id=phone_number_id,
            access_token=access_token
        )

    async def send_retention_campaign(
        self,
        to_phone: str,
        customer_name: str,
        custom_message: str,
        salon_name: str = "BillCare Luxury Salon",
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Dispatches personalized client retention and touch-up reminders."""
        message_body = f"{custom_message}\n\n- *{salon_name}*"
        return await self.send_text_message(
            to_phone=to_phone,
            message_text=message_body,
            phone_number_id=phone_number_id,
            access_token=access_token
        )

whatsapp_service = WhatsAppCloudService()

