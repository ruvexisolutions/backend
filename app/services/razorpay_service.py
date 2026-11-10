# ============================================================================
# Ruvexi Platform SaaS Subscription Service (Razorpay Integration)
# Razorpay is used exclusively for Ruvexi platform subscriptions (B2B SaaS).
# Salon client billing uses direct-to-salon UPI (0% fees) and cash/POS terminals.
# ============================================================================

import os
import hmac
import hashlib
import uuid
from typing import Dict, Any, Optional

try:
    import razorpay
except ImportError:
    razorpay = None

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

PLAN_PRICES_INR = {
    "pro": 3499.0,
    "enterprise": 8999.0,
}

class RazorpayService:
    """
    Handles Ruvexi SaaS platform subscription orders, checkout verification,
    and webhook events. Razorpay is dedicated exclusively to platform subscription revenue.
    """
    def __init__(self):
        self.key_id = os.getenv("RAZORPAY_KEY_ID", "")
        self.key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
        self.webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
        self.is_configured = bool(self.key_id and self.key_secret and razorpay)

        if self.is_configured:
            self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
        else:
            self.client = None

    def get_plan_price(self, plan: str) -> float:
        return PLAN_PRICES_INR.get(plan.lower(), 3499.0)

    def create_subscription_order(
        self,
        salon_id: str,
        salon_name: str,
        plan: str,
        manager_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a Razorpay order dedicated to a Ruvexi platform subscription.
        Amount is converted to paise for Razorpay.
        """
        amount = self.get_plan_price(plan)
        amount_in_paise = int(round(amount * 100))
        receipt = f"sub_{salon_id[:12]}_{uuid.uuid4().hex[:6]}"

        notes = {
            "salon_id": salon_id,
            "salon_name": salon_name,
            "plan": plan.lower(),
            "type": "Ruvexi_platform_subscription",
            "manager_email": manager_email or "",
        }

        if self.is_configured and self.client:
            try:
                order_data = {
                    "amount": amount_in_paise,
                    "currency": "INR",
                    "receipt": receipt,
                    "payment_capture": 1,
                    "notes": notes,
                }
                order = self.client.order.create(data=order_data)
                return {
                    "success": True,
                    "order_id": order.get("id"),
                    "amount": amount,
                    "currency": "INR",
                    "key_id": self.key_id,
                    "plan": plan.lower(),
                    "is_live": True,
                    "raw": order
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "is_live": True
                }

        return {
            "success": False,
            "error": "Razorpay billing gateway is not configured on this server. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to enable live plan upgrades.",
            "is_live": False,
        }

    def create_order(self, amount: float, receipt: str, notes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generic order creation helper for backward compatibility."""
        amount_in_paise = int(round(amount * 100))
        if self.is_configured and self.client:
            try:
                order_data = {
                    "amount": amount_in_paise,
                    "currency": "INR",
                    "receipt": receipt,
                    "payment_capture": 1,
                    "notes": notes or {},
                }
                order = self.client.order.create(data=order_data)
                return {
                    "success": True,
                    "order_id": order.get("id"),
                    "amount": amount,
                    "currency": "INR",
                    "key_id": self.key_id,
                    "is_live": True,
                    "raw": order
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "is_live": True
                }

        mock_order_id = f"order_{uuid.uuid4().hex[:14]}"
        return {
            "success": True,
            "order_id": mock_order_id,
            "amount": amount,
            "currency": "INR",
            "key_id": self.key_id or "rzp_test_Ruvexi_sandbox",
            "is_live": False,
        }

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        """
        Verifies standard Razorpay HMAC SHA-256 signature after client checkout popup.
        Fails closed if key_secret is not configured.
        """
        if not self.key_secret or not order_id or not payment_id or not signature:
            return False

        msg = f"{order_id}|{payment_id}".encode("utf-8")
        generated_signature = hmac.new(
            self.key_secret.encode("utf-8"),
            msg,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(generated_signature, signature)

    def verify_webhook_signature(self, body_bytes: bytes, signature_header: str) -> bool:
        """
        Verifies Razorpay Webhook X-Razorpay-Signature with webhook secret.
        Fails closed if webhook_secret or signature header is missing.
        """
        if not self.webhook_secret or not signature_header:
            return False

        generated_signature = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(generated_signature, signature_header)

    def create_upi_qr_code(
        self,
        amount: float,
        invoice_number: str,
        salon_id: str,
        salon_name: str,
        close_after_seconds: int = 300,
    ) -> Dict[str, Any]:
        """
        Creates a single-use fixed-amount Razorpay UPI QR when Razorpay API keys are configured.
        Enables zero-webhook polling via `poll_payment_status`.
        """
        if not self.is_configured or not self.client:
            return {
                "success": False,
                "auto_verify_supported": False,
                "error": "Razorpay API keys not configured; use direct salon UPI VPA with manual verification.",
            }

        import time
        amount_paise = int(round(amount * 100))
        try:
            qr = self.client.qrcode.create({
                "type": "upi_qr",
                "name": f"{salon_name[:40]} - {invoice_number}",
                "usage": "single_use",
                "fixed_amount": True,
                "payment_amount": amount_paise,
                "description": f"Invoice {invoice_number}",
                "close_by": int(time.time()) + max(120, close_after_seconds),
                "notes": {
                    "salon_id": salon_id,
                    "invoice_number": invoice_number,
                },
            })
            return {
                "success": True,
                "auto_verify_supported": True,
                "qr_id": qr.get("id"),
                "image_url": qr.get("image_url"),
                "status": qr.get("status", "active"),
                "raw": qr,
            }
        except Exception as e:
            return {"success": False, "auto_verify_supported": False, "error": str(e)}

    def poll_payment_status(self, reference_id: str) -> Dict[str, Any]:
        """
        Polls Razorpay directly (no webhooks required) for an Order (`order_...`),
        UPI QR (`qr_...`), or Payment Link (`plink_...`).
        """
        if not self.is_configured or not self.client:
            return {
                "success": False,
                "auto_verify_supported": False,
                "paid": False,
                "status": "manual_verification_required",
            }

        ref = (reference_id or "").strip()
        try:
            if ref.startswith("qr_"):
                qr = self.client.qrcode.fetch(ref)
                payments_resp = self.client.qrcode.fetch_all_payments(ref)
                items = payments_resp.get("items", []) if isinstance(payments_resp, dict) else []
                captured = next((p for p in items if p.get("status") in ("captured", "authorized")), None)
                is_paid = bool(captured) or int(qr.get("payments_amount_received", 0)) > 0
                acquirer = (captured or {}).get("acquirer_data", {}) or {}
                utr = acquirer.get("rrn") or acquirer.get("upi_transaction_id") or (captured or {}).get("id")
                return {
                    "success": True,
                    "auto_verify_supported": True,
                    "paid": is_paid,
                    "status": "paid" if is_paid else qr.get("status", "active"),
                    "payment_id": (captured or {}).get("id"),
                    "utr": utr,
                }

            if ref.startswith("order_"):
                order = self.client.order.fetch(ref)
                payments_resp = self.client.order.payments(ref)
                items = payments_resp.get("items", []) if isinstance(payments_resp, dict) else []
                captured = next((p for p in items if p.get("status") == "captured"), None)
                is_paid = order.get("status") == "paid" or bool(captured)
                acquirer = (captured or {}).get("acquirer_data", {}) or {}
                utr = acquirer.get("rrn") or acquirer.get("upi_transaction_id") or (captured or {}).get("id")
                return {
                    "success": True,
                    "auto_verify_supported": True,
                    "paid": is_paid,
                    "status": "paid" if is_paid else order.get("status", "attempted"),
                    "payment_id": (captured or {}).get("id"),
                    "utr": utr,
                }

            if ref.startswith("plink_"):
                plink = self.client.payment_link.fetch(ref)
                is_paid = plink.get("status") == "paid"
                return {
                    "success": True,
                    "auto_verify_supported": True,
                    "paid": is_paid,
                    "status": plink.get("status", "created"),
                    "payment_id": (plink.get("payments") or [{}])[0].get("payment_id"),
                    "utr": None,
                }

            return {"success": False, "auto_verify_supported": True, "paid": False, "status": "unknown_reference"}
        except Exception as e:
            return {"success": False, "auto_verify_supported": True, "paid": False, "error": str(e)}

razorpay_service = RazorpayService()
