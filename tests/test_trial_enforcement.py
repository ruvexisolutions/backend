import pytest

def test_seven_day_trial_restrictions_and_upgrade(client, seed_test_data):
    headers_mgr_a = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}
    headers_rec_a = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # 1. Verify Salon A status reports trial
    sub_res = client.get("/api/v1/subscription/status", headers=headers_mgr_a)
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["status"] == "trial"
    assert sub_data["isTrialActive"] is True
    assert sub_data["trialDaysLeft"] >= 0

    # 2. Receptionist daily intake works during trial
    cust_res = client.post(
        "/api/v1/customers",
        headers=headers_rec_a,
        json={"name": "Trial Guest", "phone": "+919876500000"},
    )
    assert cust_res.status_code == 200

    # 3. Manager restricted actions return HTTP 403 during trial:
    # 3a. Multi-branch creation
    branch_res = client.post(
        "/api/v1/branches",
        headers=headers_mgr_a,
        json={"name": "Second Branch"},
    )
    assert branch_res.status_code == 403
    assert "locked during the 7-day free trial" in branch_res.json()["detail"]

    # 3b. GSTIN tax customization
    gst_res = client.put(
        "/api/v1/salon",
        headers=headers_mgr_a,
        json={"gstin": "27XXXXX0000X1Z1"},
    )
    assert gst_res.status_code == 403
    assert "locked during the 7-day trial" in gst_res.json()["detail"]

    # 3c. WhatsApp API credential connection
    wa_res = client.post(
        "/api/v1/whatsapp/embedded-signup",
        headers=headers_mgr_a,
        json={"code": "auth_code_xyz"},
    )
    assert wa_res.status_code == 403
    assert "requires an active subscription" in wa_res.json()["detail"]

    # 4. Manager upgrades salon to Pro Plan
    upgrade_res = client.post(
        "/api/v1/subscription/upgrade",
        headers=headers_mgr_a,
        json={"plan": "pro"},
    )
    assert upgrade_res.status_code == 200
    assert upgrade_res.json()["success"] is True

    # 5. After upgrade, manager branch creation now succeeds!
    post_upgrade_branch = client.post(
        "/api/v1/branches",
        headers=headers_mgr_a,
        json={"name": "Second Branch Studio", "city": "Mumbai", "chairs": 6},
    )
    assert post_upgrade_branch.status_code == 200
    assert post_upgrade_branch.json()["name"] == "Second Branch Studio"


def test_expired_trial_locking_and_upgrade_recovery(client, seed_test_data, db_session):
    """When 7-day trial expires, operational APIs return HTTP 402 until upgraded."""
    from datetime import datetime, timedelta
    from app.core.models import SalonModel

    salon_a = seed_test_data["salon_a"]
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # 1. Expire the trial on Salon A
    salon_db = db_session.query(SalonModel).filter(SalonModel.id == salon_a.id).first()
    salon_db.trial_ends_at = datetime.utcnow() - timedelta(days=1)
    salon_db.subscription_status = "trial"
    db_session.commit()

    # 2. Status reports expired trial
    status_res = client.get("/api/v1/subscription/status", headers=headers_mgr)
    assert status_res.status_code == 200
    assert status_res.json()["isTrialActive"] is False

    # 3. Operational endpoints locked with HTTP 402 Payment Required
    res_cust = client.post(
        "/api/v1/customers",
        headers=headers_rec,
        json={"name": "Blocked Guest", "phone": "+919800099999"}
    )
    assert res_cust.status_code == 402
    assert "trial has expired" in res_cust.json()["detail"].lower()

    res_inv = client.post(
        "/api/v1/invoices",
        headers=headers_rec,
        json={"customerName": "Guest", "items": []}
    )
    assert res_inv.status_code == 402

    # 4. Manager upgrades salon
    upgrade_res = client.post(
        "/api/v1/subscription/upgrade",
        headers=headers_mgr,
        json={"plan": "pro"}
    )
    assert upgrade_res.status_code == 200

    # 5. Operational endpoints are immediately unlocked!
    unlocked_cust = client.post(
        "/api/v1/customers",
        headers=headers_rec,
        json={"name": "Unlocked Guest", "phone": "+919800099999"}
    )
    assert unlocked_cust.status_code == 200
    assert unlocked_cust.json()["name"] == "Unlocked Guest"
