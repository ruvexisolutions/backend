import pytest
import urllib.parse
from app.core.models import InvoiceModel, PaymentModel, CashRegisterShiftModel

def test_cash_checkout_exact_and_change_calculation(client, seed_test_data):
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # 1. Exact Cash Payment
    exact_res = client.post(
        "/api/v1/invoices",
        headers=headers_rec,
        json={
            "customerName": "Deepika Padukone",
            "items": [{"name": "Hair Spa", "price": 1000.0, "quantity": 1}],
            "discountPercent": 0.0,
            "taxPercent": 5.0, # Total: 1050.00
            "paymentMethod": "CASH",
            "amountReceived": 1050.0,
        }
    )
    assert exact_res.status_code == 200
    inv = exact_res.json()
    assert inv["status"] == "paid"
    assert inv["grandTotal"] == 1050.0
    assert inv["amountReceived"] == 1050.0
    assert inv["changeGiven"] == 0.0
    assert "BC-TXN-CASH" in inv["paymentReference"]

    # 2. Extra Cash Payment with Real-time Change
    extra_res = client.post(
        "/api/v1/invoices",
        headers=headers_rec,
        json={
            "customerName": "Priyanka Chopra",
            "items": [{"name": "Balayage Gloss", "price": 2000.0, "quantity": 1}],
            "discountPercent": 0.0,
            "taxPercent": 5.0, # Total: 2100.00
            "paymentMethod": "CASH",
            "amountReceived": 2500.0, # Tendered 2500 -> Change: 400
        }
    )
    assert extra_res.status_code == 200
    inv_extra = extra_res.json()
    assert inv_extra["status"] == "paid"
    assert inv_extra["grandTotal"] == 2100.0
    assert inv_extra["amountReceived"] == 2500.0
    assert inv_extra["changeGiven"] == 400.0

    # Verify audit payment records
    payments_res = client.get(f"/api/v1/invoices/{inv_extra['id']}/payments", headers=headers_rec)
    assert payments_res.status_code == 200
    payments = payments_res.json()
    assert len(payments) == 1
    assert payments[0]["method"] == "CASH"
    assert payments[0]["amount"] == 2100.0
    assert payments[0]["amountReceived"] == 2500.0
    assert payments[0]["changeGiven"] == 400.0
    assert payments[0]["status"] == "completed"
    assert payments[0]["verificationMethod"] == "manual_cash_counter"


def test_cash_checkout_validation_insufficient_and_negative(client, seed_test_data):
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # 1. Insufficient Cash should be rejected with HTTP 400
    res_insufficient = client.post(
        "/api/v1/invoices",
        headers=headers_rec,
        json={
            "customerName": "Anushka Sharma",
            "items": [{"name": "Blowdry", "price": 1000.0, "quantity": 1}],
            "discountPercent": 0.0,
            "taxPercent": 5.0, # Total: 1050.00
            "paymentMethod": "CASH",
            "amountReceived": 800.0, # Insufficient
        }
    )
    assert res_insufficient.status_code == 400
    assert "Insufficient cash received" in res_insufficient.json()["detail"]

    # 2. Negative Cash should be rejected with HTTP 400
    res_negative = client.post(
        "/api/v1/invoices",
        headers=headers_rec,
        json={
            "customerName": "Anushka Sharma",
            "items": [{"name": "Blowdry", "price": 1000.0, "quantity": 1}],
            "discountPercent": 0.0,
            "taxPercent": 5.0,
            "paymentMethod": "CASH",
            "amountReceived": -50.0,
        }
    )
    assert res_negative.status_code == 400
    assert "non-negative" in res_negative.json()["detail"]


def test_upi_dynamic_qr_generation_and_intent(client, seed_test_data):
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # Generate dynamic UPI QR
    res = client.post(
        "/api/v1/payments/generate-upi-qr",
        headers=headers_rec,
        json={
            "amount": 1850.50,
            "invoiceNumber": "BC-INV-2026-9999",
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["merchantVpa"] == "lumiere.pos@icici" # Tenant A configured VPA
    assert data["amount"] == 1850.50
    assert data["currency"] == "INR"
    assert "data:image/png;base64," in data["qrDataUrl"]

    # Validate UPI intent URI standard compliance
    upi_intent = data["upiIntent"]
    assert upi_intent.startswith("upi://pay?")
    assert "pa=lumiere.pos@icici" in upi_intent
    assert "am=1850.50" in upi_intent
    assert "cu=INR" in upi_intent
    assert "tn=Invoice" in upi_intent
    assert data["verificationRequired"] is True


def test_upi_pending_then_manual_confirmation(client, seed_test_data):
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # 1. Receptionist initiates checkout with status='pending'
    create_res = client.post(
        "/api/v1/invoices",
        headers=headers_rec,
        json={
            "customerName": "Katrina Kaif",
            "items": [{"name": "Aesthetic Facial", "price": 4000.0, "quantity": 1}],
            "discountPercent": 0.0,
            "taxPercent": 5.0, # Total: 4200.00
            "paymentMethod": "UPI",
            "status": "pending",
        }
    )
    assert create_res.status_code == 200
    inv = create_res.json()
    assert inv["status"] == "pending"
    inv_id = inv["id"]

    # 2. Receptionist attempts confirmation WITHOUT explicit verification boolean -> 400
    failed_confirm = client.post(
        f"/api/v1/invoices/{inv_id}/payments/confirm",
        headers=headers_rec,
        json={
            "paymentMethod": "UPI",
            "explicitVerification": False,
        }
    )
    assert failed_confirm.status_code == 400
    assert "explicitly verify" in failed_confirm.json()["detail"].lower()

    # 3. Receptionist confirms after checking salon UPI notification on phone
    success_confirm = client.post(
        f"/api/v1/invoices/{inv_id}/payments/confirm",
        headers=headers_rec,
        json={
            "paymentMethod": "UPI",
            "explicitVerification": True,
            "bankReference": "UPI/234901827492/AXIS",
        }
    )
    assert success_confirm.status_code == 200
    confirm_data = success_confirm.json()
    assert confirm_data["success"] is True
    assert confirm_data["invoice"]["status"] == "paid"
    assert confirm_data["payment"]["status"] == "completed"
    assert confirm_data["payment"]["verificationMethod"] == "manual_receptionist_upi_verification"
    assert confirm_data["receipt"]["status"] == "PAID"

    # 4. Duplicate confirmation attempt must be blocked
    dup_res = client.post(
        f"/api/v1/invoices/{inv_id}/payments/confirm",
        headers=headers_rec,
        json={"paymentMethod": "UPI", "explicitVerification": True}
    )
    assert dup_res.status_code == 400
    assert "already been paid" in dup_res.json()["detail"].lower()


def test_payment_settings_rbac_and_validation(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # 1. Receptionist can READ payment settings for rendering POS checkout
    rec_get = client.get("/api/v1/payments/settings", headers=headers_rec)
    assert rec_get.status_code == 200
    assert rec_get.json()["upiId"] == "lumiere.pos@icici"

    # 2. Receptionist is FORBIDDEN from altering salon payment destination (403)
    rec_put = client.put(
        "/api/v1/payments/settings",
        headers=headers_rec,
        json={"upiId": "attacker@paytm"}
    )
    assert rec_put.status_code == 403

    # 3. Manager attempts invalid UPI format -> 422 Unprocessable Entity
    invalid_upi = client.put(
        "/api/v1/payments/settings",
        headers=headers_mgr,
        json={"upiId": "invalid-vpa-no-at-sign"}
    )
    assert invalid_upi.status_code == 422
    assert "Invalid UPI ID format" in invalid_upi.json()["detail"]

    # 4. Manager successfully updates valid salon UPI settings
    valid_put = client.put(
        "/api/v1/payments/settings",
        headers=headers_mgr,
        json={
            "upiId": "atelier.lumiere@hdfcbank",
            "upiPayeeName": "Atelier Lumiere Bandra",
            "upiEnabled": True,
            "cashEnabled": True,
            "paymentInstructions": "Scan with any UPI app. Front desk verifies counter payment."
        }
    )
    assert valid_put.status_code == 200
    settings = valid_put.json()["settings"]
    assert settings["upiId"] == "atelier.lumiere@hdfcbank"
    assert settings["upiPayeeName"] == "Atelier Lumiere Bandra"
    assert settings["paymentInstructions"] == "Scan with any UPI app. Front desk verifies counter payment."


def test_disabled_upi_behaviour(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # Manager disables UPI
    client.put("/api/v1/payments/settings", headers=headers_mgr, json={"upiEnabled": False})

    # QR generation fails with 400
    qr_res = client.post("/api/v1/payments/generate-upi-qr", headers=headers_rec, json={"amount": 500})
    assert qr_res.status_code == 400
    assert "disabled or not configured" in qr_res.json()["detail"].lower()

    # Cash remains functional
    cash_res = client.post(
        "/api/v1/invoices",
        headers=headers_rec,
        json={
            "customerName": "Kiara Advani",
            "items": [{"name": "Quick Trim", "price": 500.0, "quantity": 1}],
            "discountPercent": 0.0,
            "taxPercent": 0.0,
            "paymentMethod": "CASH",
            "amountReceived": 500.0,
        }
    )
    assert cash_res.status_code == 200
    assert cash_res.json()["status"] == "paid"


def test_cross_tenant_payment_isolation(client, seed_test_data):
    headers_rec_a = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}
    headers_mgr_b = {"Authorization": f"Bearer {seed_test_data['token_mgr_b']}"}

    # Salon A creates pending invoice
    inv_a = client.post(
        "/api/v1/invoices",
        headers=headers_rec_a,
        json={
            "customerName": "Tenant A Customer",
            "items": [{"name": "Haircut", "price": 1000.0, "quantity": 1}],
            "status": "pending",
        }
    ).json()

    # Salon B attempts to confirm payment for Salon A's invoice -> 404 Not Found
    cross_confirm = client.post(
        f"/api/v1/invoices/{inv_a['id']}/payments/confirm",
        headers=headers_mgr_b,
        json={"paymentMethod": "CASH", "amountReceived": 1050.0}
    )
    assert cross_confirm.status_code == 404

    # Salon B attempts to view payments for Salon A's invoice -> 404 Not Found
    cross_get = client.get(
        f"/api/v1/invoices/{inv_a['id']}/payments",
        headers=headers_mgr_b
    )
    assert cross_get.status_code == 404
