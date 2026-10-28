import os
import pytest
from app.core.models import WhatsAppMessageModel, SalonModel

def test_receptionist_denied_whatsapp_settings(client, seed_test_data):
    """Receptionist must receive HTTP 403 when trying to access WhatsApp integration settings."""
    token_rec = seed_test_data["token_rec_a"]

    # Status check
    res = client.get(
        "/api/v1/whatsapp/status",
        headers={"Authorization": f"Bearer {token_rec}"}
    )
    assert res.status_code == 403
    assert "Manager" in res.json().get("detail", "")

    # Configure credentials
    res_cfg = client.post(
        "/api/v1/whatsapp/configure",
        headers={"Authorization": f"Bearer {token_rec}"},
        json={"phoneNumberId": "12345", "accessToken": "EAAG_TEST"}
    )
    assert res_cfg.status_code == 403

    # Disconnect
    res_disc = client.post(
        "/api/v1/whatsapp/disconnect",
        headers={"Authorization": f"Bearer {token_rec}"},
        json={}
    )
    assert res_disc.status_code == 403


def test_manager_access_and_trial_restriction(client, seed_test_data):
    """
    Manager of salon in trial cannot configure external credentials (returns 403),
    while Manager of active Pro subscription can configure.
    """
    token_mgr_a = seed_test_data["token_mgr_a"] # Trial salon
    token_mgr_b = seed_test_data["token_mgr_b"] # Active Pro salon

    # Trial salon manager gets status (can read status)
    res_a = client.get(
        "/api/v1/whatsapp/status",
        headers={"Authorization": f"Bearer {token_mgr_a}"}
    )
    assert res_a.status_code == 200
    assert res_a.json()["isTrial"] is True
    assert res_a.json()["canConfigure"] is False

    # Trial salon manager attempting to configure credentials receives 403
    res_trial_cfg = client.post(
        "/api/v1/whatsapp/configure",
        headers={"Authorization": f"Bearer {token_mgr_a}"},
        json={"phoneNumberId": "10982348911029", "accessToken": "EAAG_TEST_TOKEN_XYZ123"}
    )
    assert res_trial_cfg.status_code == 403
    assert "active subscription" in res_trial_cfg.json()["detail"].lower()

    # Active salon manager gets status and can configure
    res_b = client.get(
        "/api/v1/whatsapp/status",
        headers={"Authorization": f"Bearer {token_mgr_b}"}
    )
    assert res_b.status_code == 200
    assert res_b.json()["isTrial"] is False
    assert res_b.json()["canConfigure"] is True


def test_invalid_credentials_rejected(client, seed_test_data):
    """Submitting empty or incomplete credentials must be rejected with HTTP 400."""
    token_mgr_b = seed_test_data["token_mgr_b"]

    res_missing_token = client.post(
        "/api/v1/whatsapp/configure",
        headers={"Authorization": f"Bearer {token_mgr_b}"},
        json={"phoneNumberId": "10982348911029", "accessToken": ""}
    )
    assert res_missing_token.status_code == 400

    res_missing_phone = client.post(
        "/api/v1/whatsapp/configure",
        headers={"Authorization": f"Bearer {token_mgr_b}"},
        json={"phoneNumberId": "", "accessToken": "EAAG_SOME_TOKEN"}
    )
    assert res_missing_phone.status_code == 400


def test_successful_connection_and_token_secrecy(client, seed_test_data, db_session):
    """
    Configuring test credentials validates and connects.
    Access tokens must NEVER be returned in plaintext.
    """
    token_mgr_b = seed_test_data["token_mgr_b"]
    raw_token = "EAAG_TEST_PERMANENT_SECRET_TOKEN_998877"

    res_cfg = client.post(
        "/api/v1/whatsapp/configure",
        headers={"Authorization": f"Bearer {token_mgr_b}"},
        json={
            "phoneNumberId": "10982348911029",
            "wabaId": "waba_salon_b_test",
            "accessToken": raw_token,
            "displayNumber": "+91 98450 11223",
            "verifiedName": "Velvet Crown Verified"
        }
    )
    assert res_cfg.status_code == 200
    cfg_data = res_cfg.json()
    assert cfg_data["success"] is True

    # Check that raw token is NOT in salon dict
    salon_dict = cfg_data["salon"]
    assert raw_token not in str(salon_dict)
    assert salon_dict["whatsapp"]["maskedToken"].startswith("EAAG")
    assert "••••••••" in salon_dict["whatsapp"]["maskedToken"]

    # Check status endpoint also returns masked token
    res_status = client.get(
        "/api/v1/whatsapp/status",
        headers={"Authorization": f"Bearer {token_mgr_b}"}
    )
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["status"] == "connected"
    assert status_data["isConnected"] is True
    assert raw_token not in str(status_data)
    assert status_data["maskedToken"] == salon_dict["whatsapp"]["maskedToken"]


def test_cross_salon_credential_isolation(client, seed_test_data):
    """Salon A cannot read or access Salon B's WhatsApp credentials."""
    token_mgr_a = seed_test_data["token_mgr_a"]
    token_mgr_b = seed_test_data["token_mgr_b"]

    # Configure on Salon B
    client.post(
        "/api/v1/whatsapp/configure",
        headers={"Authorization": f"Bearer {token_mgr_b}"},
        json={
            "phoneNumberId": "phone_id_salon_b",
            "wabaId": "waba_salon_b",
            "accessToken": "EAAG_TEST_TOKEN_FOR_SALON_B",
            "displayNumber": "+91 98000 33333"
        }
    )

    # Check Salon A status: must be clean and not have Salon B's credentials
    res_a = client.get(
        "/api/v1/whatsapp/status",
        headers={"Authorization": f"Bearer {token_mgr_a}"}
    )
    data_a = res_a.json()
    assert data_a["phoneNumberId"] != "phone_id_salon_b"
    assert data_a["wabaId"] != "waba_salon_b"


def test_test_connection_endpoint(client, seed_test_data):
    """Test connection endpoint executes ping and returns verified status."""
    token_mgr_b = seed_test_data["token_mgr_b"]

    # Configure first
    client.post(
        "/api/v1/whatsapp/configure",
        headers={"Authorization": f"Bearer {token_mgr_b}"},
        json={
            "phoneNumberId": "10982348911029",
            "accessToken": "EAAG_TEST_TOKEN_PINGER"
        }
    )

    # Ping connection
    res = client.post(
        "/api/v1/whatsapp/test-connection",
        headers={"Authorization": f"Bearer {token_mgr_b}"},
        json={}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "verified" in data["message"].lower()
    assert data["testedAt"] is not None


def test_meta_webhook_verification(client):
    """Hub verification challenge handshake."""
    verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "billcare_meta_webhook_2026")

    # Valid challenge
    res = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": verify_token,
            "hub.challenge": "challenge_token_8877"
        }
    )
    assert res.status_code == 200
    assert res.text == "challenge_token_8877"

    # Invalid verify token
    res_bad = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "challenge_token_8877"
        }
    )
    assert res_bad.status_code == 403


def test_webhook_delivery_tracking_and_idempotency(client, seed_test_data, db_session):
    """Webhook updates WhatsAppMessageModel status idempotently without state regression."""
    salon_b = seed_test_data["salon_b"]
    meta_id = "wamid.HBgLMjcxMjk4NDUxMA=="

    # Seed an outgoing message record
    msg = WhatsAppMessageModel(
        id="wmsg_test_001",
        salon_id=salon_b.id,
        recipient_phone="919845011223",
        customer_name="Priya Sharma",
        message_type="bill_receipt",
        template_name="billcare_service_receipt",
        meta_message_id=meta_id,
        status="sent",
        idempotency_key="bill_INV-1001_919845011223"
    )
    db_session.add(msg)
    db_session.commit()

    # Dispatch delivered webhook
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba_123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "123", "phone_number_id": "456"},
                    "statuses": [{
                        "id": meta_id,
                        "status": "delivered",
                        "timestamp": "1730000000",
                        "recipient_id": "919845011223"
                    }]
                },
                "field": "messages"
            }]
        }]
    }

    res_wh = client.post("/api/v1/whatsapp/webhook", json=payload)
    assert res_wh.status_code == 200
    assert res_wh.json()["status"] == "ok"

    # Verify status progressed to delivered
    db_session.refresh(msg)
    assert msg.status == "delivered"

    # Now dispatch read status
    payload["entry"][0]["changes"][0]["value"]["statuses"][0]["status"] = "read"
    res_wh2 = client.post("/api/v1/whatsapp/webhook", json=payload)
    assert res_wh2.status_code == 200

    db_session.refresh(msg)
    assert msg.status == "read"

    # Duplicate / delayed delivered webhook should NOT regress read -> delivered
    payload["entry"][0]["changes"][0]["value"]["statuses"][0]["status"] = "delivered"
    client.post("/api/v1/whatsapp/webhook", json=payload)
    db_session.refresh(msg)
    assert msg.status == "read" # Remained read!


def test_disconnect_wipes_credentials(client, seed_test_data):
    """Disconnecting WhatsApp resets status and clears stored credentials."""
    token_mgr_b = seed_test_data["token_mgr_b"]

    # Configure first
    client.post(
        "/api/v1/whatsapp/configure",
        headers={"Authorization": f"Bearer {token_mgr_b}"},
        json={"phoneNumberId": "phone_123", "accessToken": "EAAG_TEST_TOKEN"}
    )

    # Disconnect
    res_disc = client.post(
        "/api/v1/whatsapp/disconnect",
        headers={"Authorization": f"Bearer {token_mgr_b}"},
        json={}
    )
    assert res_disc.status_code == 200
    assert res_disc.json()["success"] is True

    # Status check
    res_st = client.get(
        "/api/v1/whatsapp/status",
        headers={"Authorization": f"Bearer {token_mgr_b}"}
    )
    assert res_st.json()["status"] == "not_connected"
    assert res_st.json()["isConnected"] is False
    assert res_st.json()["phoneNumberId"] is None


def test_pos_billing_resiliency_when_whatsapp_offline(client, seed_test_data):
    """
    When WhatsApp is not connected or offline, bill checkout triggers graceful fallback
    and NEVER crashes or blocks POS billing.
    """
    token_rec_a = seed_test_data["token_rec_a"] # Receptionist in salon with WhatsApp disconnected

    res = client.post(
        "/api/v1/whatsapp/send-bill",
        headers={"Authorization": f"Bearer {token_rec_a}"},
        json={
            "customerPhone": "+91 98450 99887",
            "customerName": "Ananya Roy",
            "invoiceNumber": "INV-OFFLINE-001",
            "totalAmount": 1850.0,
            "items": [{"name": "Classic Haircut & Blowdry", "price": 1850.0}]
        }
    )
    # Must succeed gracefully with is_fallback=True, not raise 500 error!
    assert res.status_code == 200
    data = res.json()
    assert data["is_fallback"] is True
    assert "not configured" in data["message"].lower() or "offline" in data["message"].lower()
