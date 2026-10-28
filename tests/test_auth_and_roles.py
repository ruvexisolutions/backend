import pytest

def test_manager_otp_full_flow(client, seed_test_data):
    manager_phone = seed_test_data["mgr_a"].phone # "+919800011111"

    # 1. Request OTP
    req_resp = client.post("/api/v1/auth/otp/request", json={"phone": manager_phone})
    assert req_resp.status_code == 200
    req_data = req_resp.json()
    assert req_data["success"] is True
    dev_otp = req_data.get("dev_otp")
    assert dev_otp is not None
    assert len(dev_otp) == 6

    # 2. Verify with incorrect OTP -> Should fail
    fail_resp = client.post("/api/v1/auth/otp/verify", json={"phone": manager_phone, "otp": "000000"})
    assert fail_resp.status_code == 400

    # 3. Verify with correct OTP -> Should succeed and return session JWT
    ok_resp = client.post("/api/v1/auth/otp/verify", json={"phone": manager_phone, "otp": dev_otp})
    assert ok_resp.status_code == 200
    auth_data = ok_resp.json()
    assert auth_data["success"] is True
    assert "token" in auth_data
    assert auth_data["user"]["role"] == "SALON_MANAGER"

    # 4. Replay the same OTP -> Must be rejected (single-use protection)
    replay_resp = client.post("/api/v1/auth/otp/verify", json={"phone": manager_phone, "otp": dev_otp})
    assert replay_resp.status_code == 400


def test_receptionist_invitation_flow(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}
    invite_email = "new_receptionist@lumiere.com"

    # 1. Manager generates receptionist invite
    invite_resp = client.post(
        "/api/v1/invitations",
        headers=headers_mgr,
        json={"email": invite_email},
    )
    assert invite_resp.status_code == 200
    invite_data = invite_resp.json()
    assert invite_data["success"] is True
    token = invite_data["invitation"]["token"]
    assert token is not None

    # 2. Public lookup of invite details
    lookup_resp = client.get(f"/api/v1/invitations/{token}")
    assert lookup_resp.status_code == 200
    lookup_data = lookup_resp.json()
    assert lookup_data["valid"] is True
    assert lookup_data["email"] == invite_email
    assert lookup_data["role"] == "SALON_RECEPTIONIST"

    # 3. Receptionist accepts invitation
    accept_resp = client.post(
        "/api/v1/invitations/accept",
        json={
            "token": token,
            "name": "Sunita Das",
            "phone": "+919877711223",
            "password": "receptionpass123",
        },
    )
    assert accept_resp.status_code == 200
    accept_data = accept_resp.json()
    assert accept_data["success"] is True
    assert accept_data["user"]["role"] == "SALON_RECEPTIONIST"
    assert accept_data["user"]["salonId"] == seed_test_data["salon_a"].id

    # 4. Replay acceptance -> Should fail (already used)
    replay_accept = client.post(
        "/api/v1/invitations/accept",
        json={
            "token": token,
            "name": "Sunita Das",
            "phone": "+919877711223",
            "password": "receptionpass123",
        },
    )
    assert replay_accept.status_code == 400


def test_receptionist_restricted_from_manager_endpoints(client, seed_test_data):
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # 1. Receptionist cannot create branch
    res_branch = client.post(
        "/api/v1/branches",
        headers=headers_rec,
        json={"name": "Rogue Branch"},
    )
    assert res_branch.status_code == 403

    # 2. Receptionist cannot modify salon settings
    res_salon = client.put(
        "/api/v1/salon",
        headers=headers_rec,
        json={"name": "Hacked Name"},
    )
    assert res_salon.status_code == 403

    # 3. Receptionist cannot configure WhatsApp credentials
    res_wa = client.post(
        "/api/v1/whatsapp/embedded-signup",
        headers=headers_rec,
        json={"code": "auth_code_xyz"},
    )
    assert res_wa.status_code == 403


def test_unauthenticated_requests_strictly_rejected_401(client, seed_test_data):
    """Anonymous requests without valid JWT Bearer tokens must receive HTTP 401."""
    # 1. No Authorization header
    res_cust = client.get("/api/v1/customers")
    assert res_cust.status_code == 401

    res_inv = client.post("/api/v1/invoices", json={})
    assert res_inv.status_code == 401

    res_boot = client.get("/api/v1/bootstrap")
    assert res_boot.status_code == 401

    res_appts = client.get("/api/v1/appointments")
    assert res_appts.status_code == 401

    # 2. Spoofed x-salon-id header without valid token must also be rejected with 401
    res_spoof = client.get(
        "/api/v1/customers",
        headers={"x-salon-id": seed_test_data["salon_a"].id}
    )
    assert res_spoof.status_code == 401
