# ============================================================================
# BillCare Platform SaaS Subscription Service (Razorpay Integration)
# Razorpay is used exclusively for BillCare platform subscriptions (B2B SaaS).
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
    Handles BillCare SaaS platform subscription orders, checkout verification,
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
        Creates a Razorpay order dedicated to a BillCare platform subscription.
        Amount is converted to paise for Razorpay.
        """
        amount = self.get_plan_price(plan)
        amount_in_paise = int(round(amount * 100))
        receipt = f"sub_{salon_id[:12]}_{uuid.uuid4().hex[:6]}"

        notes = {
            "salon_id": salon_id,
            "salon_name": salon_name,
            "plan": plan.lower(),
            "type": "billcare_platform_subscription",
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

        # Sandbox / Fallback for local dev or when keys not yet provisioned
        mock_order_id = f"order_sub_{uuid.uuid4().hex[:14]}"
        return {
            "success": True,
            "order_id": mock_order_id,
            "amount": amount,
            "currency": "INR",
            "key_id": self.key_id or "rzp_test_billcare_sandbox",
            "plan": plan.lower(),
            "is_live": False,
            "notice": "Operating in BillCare Platform Subscription Sandbox. Add live RAZORPAY_KEY_ID & RAZORPAY_KEY_SECRET to backend/.env."
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
            "key_id": self.key_id or "rzp_test_billcare_sandbox",
            "is_live": False,
        }

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        """
        Verifies standard Razorpay HMAC SHA-256 signature after client checkout popup.
        """
        if not self.key_secret:
            # Pass in sandbox mode
            return True

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
        """
        if not self.webhook_secret:
            return True

        generated_signature = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(generated_signature, signature_header)

razorpay_service = RazorpayService()
