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

class RazorpayService:
    def __init__(self):
        self.key_id = os.getenv("RAZORPAY_KEY_ID", "")
        self.key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
        self.webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
        self.is_configured = bool(self.key_id and self.key_secret and razorpay)

        if self.is_configured:
            self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
        else:
            self.client = None

    def create_order(self, amount: float, receipt: str, notes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Creates a standard Razorpay Order.
        Amount must be passed in Indian Rupees (INR) and is converted to paise.
        """
        amount_in_paise = int(round(amount * 100))
        if self.is_configured and self.client:
            try:
                order_data = {
                    "amount": amount_in_paise,
                    "currency": "INR",
                    "receipt": receipt,
                    "payment_capture": 1,  # Auto-capture payment
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

        # Sandbox / Offline Fallback if keys are pending configuration
        mock_order_id = f"order_{uuid.uuid4().hex[:14]}"
        return {
            "success": True,
            "order_id": mock_order_id,
            "amount": amount,
            "currency": "INR",
            "key_id": self.key_id or "rzp_test_billcare_sandbox",
            "is_live": False,
            "notice": "Operating in BillCare Razorpay Sandbox Mode. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in backend/.env for live transactions."
        }

    def create_payment_link(
        self,
        amount: float,
        customer_name: str,
        customer_phone: str,
        customer_email: Optional[str],
        description: str,
        receipt: str
    ) -> Dict[str, Any]:
        """
        Generates a live Razorpay Instant Payment Link with SMS & WhatsApp notification flags.
        """
        amount_in_paise = int(round(amount * 100))
        # Normalize phone number to 10 digits
        clean_phone = "".join(filter(str.isdigit, customer_phone))[-10:] if customer_phone else ""

        if self.is_configured and self.client:
            try:
                link_data = {
                    "amount": amount_in_paise,
                    "currency": "INR",
                    "accept_partial": False,
                    "description": description,
                    "customer": {
                        "name": customer_name,
                        "contact": f"+91{clean_phone}" if clean_phone else "",
                        "email": customer_email or "billing@billcare.io"
                    },
                    "notify": {
                        "sms": True,
                        "email": bool(customer_email),
                        "whatsapp": True
                    },
                    "reminder_enable": True,
                    "notes": {"receipt": receipt},
                }
                res = self.client.payment_link.create(data=link_data)
                return {
                    "success": True,
                    "link_id": res.get("id"),
                    "short_url": res.get("short_url"),
                    "status": res.get("status"),
                    "is_live": True
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "is_live": True
                }

        # Deterministic sandbox payment link
        return {
            "success": True,
            "link_id": f"plink_{uuid.uuid4().hex[:12]}",
            "short_url": f"https://rzp.io/i/{uuid.uuid4().hex[:7]}",
            "status": "created",
            "is_live": False,
            "notice": "Simulated Razorpay Payment Link. Add live keys to backend/.env."
        }

    def generate_upi_qr(
        self,
        amount: float,
        invoice_number: str,
        salon_name: str = "BillCare Salon",
        merchant_vpa: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates standard Indian NPCI UPI Intent String & QR Payload for Countertop POS tablets.
        Supports PhonePe, Google Pay, Paytm, BHIM, CRED.
        """
        import urllib.parse
        vpa = merchant_vpa or os.getenv("RAZORPAY_MERCHANT_VPA", "billcare.pos@icici")
        amount_str = f"{amount:.2f}"
        encoded_salon_name = urllib.parse.quote(salon_name)
        encoded_note = urllib.parse.quote(f"Bill {invoice_number}")

        # Standard NPCI UPI URI Scheme
        upi_string = f"upi://pay?pa={vpa}&pn={encoded_salon_name}&tr={invoice_number}&am={amount_str}&cu=INR&tn={encoded_note}"
        encoded_data = urllib.parse.quote(upi_string)

        return {
            "success": True,
            "upi_intent": upi_string,
            "amount": amount,
            "invoice_number": invoice_number,
            "merchant_vpa": vpa,
            "salon_name": salon_name,
            "qr_svg_url": f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&margin=8&data={encoded_data}"
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
