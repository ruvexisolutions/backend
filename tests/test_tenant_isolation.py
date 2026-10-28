import pytest

def test_tenant_customer_isolation(client, seed_test_data):
    headers_a = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}
    headers_b = {"Authorization": f"Bearer {seed_test_data['token_mgr_b']}"}

    # 1. Create a customer in Salon A
    resp_a = client.post(
        "/api/v1/customers",
        headers=headers_a,
        json={"name": "Client of Salon A", "phone": "+919876543210", "email": "clienta@test.com"},
    )
    assert resp_a.status_code == 200
    customer_a = resp_a.json()
    cust_id = customer_a["id"]
    assert customer_a["salonId"] == seed_test_data["salon_a"].id

    # 2. Salon A can read their customer
    resp_list_a = client.get("/api/v1/customers", headers=headers_a)
    assert resp_list_a.status_code == 200
    ids_a = [c["id"] for c in resp_list_a.json()]
    assert cust_id in ids_a

    # 3. Salon B CANNOT see Salon A's customer (Tenant Isolation)
    resp_list_b = client.get("/api/v1/customers", headers=headers_b)
    assert resp_list_b.status_code == 200
    ids_b = [c["id"] for c in resp_list_b.json()]
    assert cust_id not in ids_b

    # 4. Salon B CANNOT update Salon A's customer
    resp_update_b = client.put(
        f"/api/v1/customers/{cust_id}",
        headers=headers_b,
        json={"name": "Tampered Name"},
    )
    assert resp_update_b.status_code == 404


def test_tenant_appointment_isolation(client, seed_test_data):
    headers_a = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}
    headers_b = {"Authorization": f"Bearer {seed_test_data['token_mgr_b']}"}

    # 1. Salon A creates an appointment
    resp_apt = client.post(
        "/api/v1/appointments",
        headers=headers_a,
        json={
            "customerName": "VIP Guest A",
            "serviceName": "Balayage Couture",
            "chairNumber": 2,
            "price": 4500.0,
        },
    )
    assert resp_apt.status_code == 200
    apt_id = resp_apt.json()["id"]

    # 2. Salon A lists appointments
    resp_list_a = client.get("/api/v1/appointments", headers=headers_a)
    ids_a = [a["id"] for a in resp_list_a.json()]
    assert apt_id in ids_a

    # 3. Salon B does NOT see Salon A's appointment
    resp_list_b = client.get("/api/v1/appointments", headers=headers_b)
    ids_b = [a["id"] for a in resp_list_b.json()]
    assert apt_id not in ids_b


def test_tenant_inventory_isolation(client, seed_test_data):
    headers_b = {"Authorization": f"Bearer {seed_test_data['token_mgr_b']}"}
    headers_a = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}

    # Salon B (Pro) creates inventory item
    resp_inv = client.post(
        "/api/v1/inventory",
        headers=headers_b,
        json={
            "name": "Moroccanoil Treatment 100ml",
            "currentStock": 20,
            "costPrice": 1800,
            "sellingPrice": 3200,
        },
    )
    assert resp_inv.status_code == 200
    inv_id = resp_inv.json()["id"]

    # Salon A cannot see it
    resp_list_a = client.get("/api/v1/inventory", headers=headers_a)
    ids_a = [i["id"] for i in resp_list_a.json()]
    assert inv_id not in ids_a
