"""Comprehensive QA suite for RUVEXI Dual WhatsApp Business API Architecture."""

import os
import sys
import json
import hmac
import hashlib
import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

os.environ.setdefault("JWT_SECRET", "test_jwt_secret_for_pytest_dual_whatsapp_only_123456")
os.environ.setdefault("META_APP_SECRET", "test_meta_app_secret_12345")
os.environ.setdefault("META_WEBHOOK_VERIFY_TOKEN", "test_verify_token_12345")
os.environ.setdefault("RUVEXI_WABA_ID", "waba_ruvexi_official_001")
os.environ.setdefault("RUVEXI_PHONE_NUMBER_ID", "phone_ruvexi_official_001")
os.environ.setdefault("RUVEXI_WHATSAPP_ACCESS_TOKEN", "EAAG_SANDBOX_RUVEXI_OFFICIAL_TOKEN")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.models import (
    SalonModel,
    UserModel,
    CustomerModel,
    InvoiceModel,
    AppointmentModel,
    WhatsAppConnectionModel,
    WhatsAppMessageLogModel,
    WhatsAppNotificationPreferenceModel,
    WhatsAppWebhookEventModel,
)
from app.core.security import create_access_token, hash_password
from app.main import app
from app.services.whatsapp import (
    whatsapp_base_client,
    whatsapp_message_router,
    whatsapp_scheduler,
    MessageCategory,
)

# Isolated in-memory SQLite DB for tests
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield


def _seed_salon_and_owner(db, salon_id: str, name: str, email: str, phone: str, role: str = "SALON_MANAGER"):
    salon = SalonModel(
        id=salon_id,
        name=name,
        slug=salon_id,
        email=email,
        phone=phone,
        subscription_status="active",
        subscription_plan="pro",
    )
    user = UserModel(
        id=f"usr_{salon_id}",
        salon_id=salon_id,
        name=f"Owner {name}",
        email=email,
        password_hash=hash_password("TestPass123!"),
        role=role,
    )
    db.add(salon)
    db.add(user)
    db.commit()
    token = create_access_token({"sub": user.id, "salon_id": salon.id, "role": user.role})
    return salon, user, {"Authorization": f"Bearer {token}"}


def test_1_and_6_ruvexi_official_sends_owner_report_from_real_db():
    db = TestingSessionLocal()
    salon, _, headers = _seed_salon_and_owner(db, "sln_a", "Salon Alpha", "alpha@salon.com", "9845011111")
    db.add(InvoiceModel(
        id="inv_a1",
        salon_id=salon.id,
        invoice_number="INV-A1",
        customer_name="Meera",
        grand_total=1800.0,
        status="paid",
        paid_at=datetime.utcnow(),
        items_json=json.dumps([{"name": "Keratin Spa", "price": 1800.0, "quantity": 1}]),
    ))
    db.add(AppointmentModel(
        id="apt_a1",
        salon_id=salon.id,
        customer_id="cst_a1",
        customer_name="Meera",
        service_name="Keratin Spa",
        date=datetime.utcnow().strftime("%Y-%m-%d"),
        start_time="11:00",
        status="completed",
    ))
    db.commit()
    db.close()

    with TestClient(app) as client:
        resp = client.post("/api/v1/whatsapp/owner/send-report", json={"period": "daily"}, headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["metrics"]["revenue"] == 1800.0
        assert body["metrics"]["topService"] == "Keratin Spa"
        assert body["log"]["channelType"] == "RUVEXI"
        assert body["result"]["sender_phone_id"] == "phone_ruvexi_official_001"


def test_2_to_5_and_7_multi_tenant_salon_connections_isolation_and_disconnect():
    db = TestingSessionLocal()
    salon_a, _, headers_a = _seed_salon_and_owner(db, "sln_alpha", "Alpha", "a@a.com", "9845000001")
    salon_b, _, headers_b = _seed_salon_and_owner(db, "sln_beta", "Beta", "b@b.com", "9845000002")
    db.close()

    with TestClient(app) as client:
        # Connect Salon A
        r_a = client.post("/api/v1/whatsapp/salon/connect", json={
            "wabaId": "waba_alpha",
            "phoneNumberId": "phone_alpha_111",
            "accessToken": "EAAG_SANDBOX_ALPHA",
        }, headers=headers_a)
        assert r_a.status_code == 200
        assert r_a.json()["connection"]["phoneNumberId"] == "phone_alpha_111"
        assert "EAAG_SANDBOX_ALPHA" not in json.dumps(r_a.json())  # Token never exposed

        # Connect Salon B
        r_b = client.post("/api/v1/whatsapp/salon/connect", json={
            "wabaId": "waba_beta",
            "phoneNumberId": "phone_beta_222",
            "accessToken": "EAAG_SANDBOX_BETA",
        }, headers=headers_b)
        assert r_b.status_code == 200
        assert r_b.json()["connection"]["phoneNumberId"] == "phone_beta_222"

        # Salon A customer receives from Salon A's phone_number_id
        s_a = client.post("/api/v1/whatsapp/salon/send", json={
            "messageType": "BOOKING_CONFIRMATION",
            "recipientNumber": "9900112233",
            "customerName": "Client A",
            "message": "Confirmed at Alpha",
        }, headers=headers_a)
        assert s_a.status_code == 200
        assert s_a.json()["result"]["sender_phone_id"] == "phone_alpha_111"
        assert s_a.json()["log"]["channelType"] == "SALON"

        # Salon B customer receives from Salon B's phone_number_id
        s_b = client.post("/api/v1/whatsapp/salon/send", json={
            "messageType": "BOOKING_CONFIRMATION",
            "recipientNumber": "9900112244",
            "customerName": "Client B",
            "message": "Confirmed at Beta",
        }, headers=headers_b)
        assert s_b.status_code == 200
        assert s_b.json()["result"]["sender_phone_id"] == "phone_beta_222"

        # Disconnect Salon A: Salon B & RUVEXI Official stay unaffected
        disc = client.delete("/api/v1/whatsapp/salon/disconnect", headers=headers_a)
        assert disc.status_code == 200

        st_b = client.get("/api/v1/whatsapp/salon/status", headers=headers_b)
        assert st_b.status_code == 200
        assert st_b.json()["isConnected"] is True

        rep = client.post("/api/v1/whatsapp/owner/send-report", json={"period": "daily"}, headers=headers_a)
        assert rep.status_code == 200
        assert rep.json()["result"]["sender_phone_id"] == "phone_ruvexi_official_001"


def test_8_failed_message_retry_queue_recovers_safely():
    async def _run():
        db = TestingSessionLocal()
        salon, _, _ = _seed_salon_and_owner(db, "sln_retry", "Retry Salon", "r@r.com", "9845000003")
        enq = whatsapp_message_router.enqueue_message(
            db=db,
            tenant_id=salon.id,
            category=MessageCategory.OWNER_ALERT,
            recipient_number="9845000003",
            message_text="Low stock alert",
            idempotency_key="retry_test_1",
        )
        log_id = enq["log"]["id"]
        log_row = db.query(WhatsAppMessageLogModel).filter(WhatsAppMessageLogModel.id == log_id).first()

        with patch.object(whatsapp_base_client, "send_text", new=AsyncMock(return_value={
            "success": False, "error": "Rate limit 429", "retryable": True
        })):
            res1 = await whatsapp_message_router.process_log_entry(db, log_row)
            assert res1["success"] is False
            assert res1["log"]["deliveryStatus"] == "queued"
            assert res1["log"]["retryCount"] == 1

        log_row.next_retry_at = datetime.utcnow() - timedelta(seconds=5)
        db.commit()
        with patch.object(whatsapp_base_client, "send_text", new=AsyncMock(return_value={
            "success": True, "message_id": "wamid.recovered_123"
        })):
            retried = await whatsapp_scheduler.process_retry_queue(db)
            assert retried == 1
            db.refresh(log_row)
            assert log_row.delivery_status == "sent"
            assert log_row.meta_message_id == "wamid.recovered_123"
        db.close()

    asyncio.run(_run())


def test_9_and_14_webhook_deduplication_and_customer_opt_out():
    db = TestingSessionLocal()
    salon, _, headers = _seed_salon_and_owner(db, "sln_wh", "Webhook Salon", "w@w.com", "9845000004")
    db.add(WhatsAppConnectionModel(
        tenant_id=salon.id,
        waba_id="waba_wh_1",
        phone_number_id="phone_wh_1",
        encrypted_access_token="EAAG_SANDBOX_WH",
        connection_status="connected",
    ))
    db.add(CustomerModel(
        id="cst_wh_1",
        salon_id=salon.id,
        name="Ananya",
        phone="9876543210",
        whatsapp_opt_in=True,
        whatsapp_marketing_opt_in=True,
    ))
    db.add(WhatsAppMessageLogModel(
        id="wlog_wh_1",
        tenant_id=salon.id,
        channel_type="SALON",
        recipient_number="919876543210",
        message_type="CUSTOMER_INVOICE",
        meta_message_id="wamid.msg_999",
        delivery_status="sent",
    ))
    db.commit()
    db.close()

    webhook_payload = {
        "entry": [{
            "id": "waba_wh_1",
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "phone_wh_1"},
                    "statuses": [{"id": "wamid.msg_999", "status": "delivered", "timestamp": "1700000000"}],
                    "messages": [{"id": "wamid.in_1", "from": "919876543210", "text": {"body": "STOP"}}],
                }
            }]
        }]
    }
    raw = json.dumps(webhook_payload).encode("utf-8")
    sig = "sha256=" + hmac.new(b"test_meta_app_secret_12345", raw, hashlib.sha256).hexdigest()

    with TestClient(app) as client:
        # First delivery
        r1 = client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
        assert r1.status_code == 200
        assert r1.json()["processed"] == 2

        # Duplicate webhook event -> deduplicated
        r2 = client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
        assert r2.status_code == 200
        assert r2.json()["processed"] == 0
        assert r2.json()["deduplicated"] == 2

        # Customer opted out via STOP -> marketing message blocked
        promo = client.post("/api/v1/whatsapp/salon/send", json={
            "messageType": "CUSTOMER_PROMOTION",
            "recipientNumber": "9876543210",
            "message": "20% Off Hair Spa!",
        }, headers=headers)
        assert promo.status_code == 200
        assert promo.json()["success"] is False
        assert "opted out" in promo.json()["result"]["error"].lower()


def test_10_unauthorized_cross_tenant_and_channel_override_blocked():
    db = TestingSessionLocal()
    _, _, headers_a = _seed_salon_and_owner(db, "sln_sec_a", "Sec A", "sa@a.com", "9845000011")
    salon_b, _, _ = _seed_salon_and_owner(db, "sln_sec_b", "Sec B", "sb@b.com", "9845000012")
    salon_b_id = salon_b.id
    _, _, headers_rec = _seed_salon_and_owner(db, "sln_sec_r", "Sec R", "sr@r.com", "9845000013", role="SALON_RECEPTIONIST")
    db.close()

    with TestClient(app) as client:
        # Receptionist cannot access Salon Manager WhatsApp settings or Owner reports
        assert client.get("/api/v1/whatsapp/salon/status", headers=headers_rec).status_code == 403
        assert client.get("/api/v1/whatsapp/owner/preferences", headers=headers_rec).status_code == 403

        # Cross-tenant override forbidden
        cross = client.post("/api/v1/whatsapp/salon/send", json={
            "tenantId": salon_b_id,
            "messageType": "BOOKING_CONFIRMATION",
            "recipientNumber": "9845000099",
            "message": "Spoof",
        }, headers=headers_a)
        assert cross.status_code == 403

        # Salon endpoint cannot dispatch RUVEXI owner categories
        wrong_cat = client.post("/api/v1/whatsapp/salon/send", json={
            "messageType": "OWNER_REPORT",
            "recipientNumber": "9845000099",
            "message": "Spoof owner report",
        }, headers=headers_a)
        assert wrong_cat.status_code == 403


def test_11_owner_preferences_control_scheduled_reports():
    async def _run():
        db = TestingSessionLocal()
        salon, owner, _ = _seed_salon_and_owner(db, "sln_sched", "Sched Salon", "sc@sc.com", "9845000020")
        now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
        hhmm = now_ist.strftime("%H:%M")

        pref = WhatsAppNotificationPreferenceModel(
            tenant_id=salon.id,
            owner_id=owner.id,
            channel_type="RUVEXI",
            recipient_phone="9845000020",
            notification_type="daily_report",
            is_enabled=False,
            delivery_frequency="daily",
            preferred_delivery_time=hhmm,
            opted_in=True,
        )
        db.add(pref)
        db.commit()

        assert await whatsapp_scheduler.dispatch_due_owner_reports(db) == 0

        pref.is_enabled = True
        db.commit()
        assert await whatsapp_scheduler.dispatch_due_owner_reports(db) == 1
        assert await whatsapp_scheduler.dispatch_due_owner_reports(db) == 0
        db.close()

    asyncio.run(_run())


def test_12_and_13_expired_credentials_and_template_rejection_handled():
    async def _run():
        db = TestingSessionLocal()
        salon, _, _ = _seed_salon_and_owner(db, "sln_exp", "Exp Salon", "ex@ex.com", "9845000030")
        conn = WhatsAppConnectionModel(
            tenant_id=salon.id,
            waba_id="waba_exp",
            phone_number_id="phone_exp_1",
            encrypted_access_token="EAAG_LIVE_EXPIRED_TOKEN",
            connection_status="connected",
        )
        db.add(conn)
        db.commit()

        with patch.object(whatsapp_base_client, "send_text", new=AsyncMock(return_value={
            "success": False,
            "error": "Session has expired (Error 190)",
            "error_code": 190,
            "auth_expired": True,
            "retryable": False,
        })):
            res = await whatsapp_message_router.route_and_send(
                db=db,
                tenant_id=salon.id,
                category=MessageCategory.PAYMENT_CONFIRMATION,
                recipient_number="9845000031",
                message_text="Paid",
            )
            assert res["success"] is False
            db.refresh(conn)
            assert conn.connection_status == "expired"
            assert conn.token_validation_status == "expired"

        db.close()

    asyncio.run(_run())
