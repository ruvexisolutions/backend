import pytest

def test_pos_invoice_server_recalculation_and_inventory(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_b']}"}

    # 1. Create a retail inventory product
    prod_res = client.post(
        "/api/v1/inventory",
        headers=headers_mgr,
        json={
            "name": "Kerastase Elixir Ultime 100ml",
            "currentStock": 10,
            "sellingPrice": 2000.0,
            "costPrice": 1200.0,
        },
    )
    assert prod_res.status_code == 200
    prod = prod_res.json()
    prod_id = prod["id"]

    # 2. Create customer
    cust_res = client.post(
        "/api/v1/customers",
        headers=headers_mgr,
        json={"name": "Alia Bhatt", "phone": "+919811122233", "loyaltyPoints": 50},
    )
    assert cust_res.status_code == 200
    cust_id = cust_res.json()["id"]

    # 3. Create POS invoice with:
    # Service: ₹3,000 x 1
    # Product: ₹2,000 x 2 (Kerastase)
    # Expected subtotal: ₹7,000
    # Discount: 10% -> ₹700
    # Taxable: ₹6,300
    # 5% GST: ₹315 (CGST ₹157.50, SGST ₹157.50)
    # Expected grand total: ₹6,615.00
    inv_res = client.post(
        "/api/v1/invoices",
        headers=headers_mgr,
        json={
            "customerId": cust_id,
            "customerName": "Alia Bhatt",
            "items": [
                {"id": "srv_hair", "name": "Global Color", "type": "service", "price": 3000.0, "quantity": 1},
                {"id": prod_id, "name": "Kerastase Elixir", "type": "product", "price": 2000.0, "quantity": 2},
            ],
            "discountPercent": 10.0,
            "taxPercent": 5.0,
            "paymentMethod": "UPI",
        },
    )
    assert inv_res.status_code == 200
    inv_data = inv_res.json()

    assert inv_data["subtotal"] == 7000.0
    assert inv_data["discountAmount"] == 700.0
    assert inv_data["taxAmount"] == 315.0
    assert inv_data["grandTotal"] == 6615.0

    # 4. Verify inventory stock was automatically deducted by 2 (10 -> 8)
    inv_check = client.get("/api/v1/inventory", headers=headers_mgr)
    updated_prod = next(i for i in inv_check.json() if i["id"] == prod_id)
    assert updated_prod["currentStock"] == 8

    # 5. Verify customer total spend and loyalty points were credited
    cust_check = client.get("/api/v1/customers", headers=headers_mgr)
    updated_cust = next(c for c in cust_check.json() if c["id"] == cust_id)
    assert updated_cust["totalVisits"] == 1
    assert updated_cust["totalSpend"] == 6615.0
    assert updated_cust["loyaltyPoints"] == 50 + int(6615 * 0.05)
