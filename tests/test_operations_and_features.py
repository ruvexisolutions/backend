import pytest
from datetime import datetime, timedelta

def test_invoice_refund_and_inventory_restock(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # 1. Create a retail inventory product
    prod_res = client.post(
        "/api/v1/inventory",
        headers=headers_mgr,
        json={
            "name": "Olaplex No. 3 Hair Perfector",
            "currentStock": 15,
            "sellingPrice": 2500.0,
            "costPrice": 1500.0,
        },
    )
    assert prod_res.status_code == 200
    prod = prod_res.json()
    prod_id = prod["id"]

    # 2. Create customer
    cust_res = client.post(
        "/api/v1/customers",
        headers=headers_mgr,
        json={"name": "Kareena Kapoor", "phone": "+919833344455", "loyaltyPoints": 200},
    )
    assert cust_res.status_code == 200
    cust_id = cust_res.json()["id"]

    # 3. Create POS invoice
    inv_res = client.post(
        "/api/v1/invoices",
        headers=headers_mgr,
        json={
            "customerId": cust_id,
            "customerName": "Kareena Kapoor",
            "items": [
                {"id": prod_id, "name": "Olaplex No. 3", "type": "product", "price": 2500.0, "quantity": 2},
            ],
            "discountPercent": 0.0,
            "taxPercent": 18.0,
            "paymentMethod": "UPI",
        },
    )
    assert inv_res.status_code == 200
    inv = inv_res.json()
    inv_id = inv["id"]
    grand_total = inv["grandTotal"]
    assert grand_total == 5900.0  # 5000 + 18% GST (900)

    # Verify inventory was deducted from 15 to 13
    inv_items = client.get("/api/v1/inventory", headers=headers_mgr).json()
    prod_after_sale = next(p for p in inv_items if p["id"] == prod_id)
    assert prod_after_sale["currentStock"] == 13

    # 4. Receptionist attempting refund should be forbidden (403)
    rec_refund = client.post(
        f"/api/v1/invoices/{inv_id}/refund",
        headers=headers_rec,
        json={"amount": grand_total, "reason": "Customer changed mind", "restockInventory": True},
    )
    assert rec_refund.status_code == 403

    # 5. Manager performs refund
    mgr_refund = client.post(
        f"/api/v1/invoices/{inv_id}/refund",
        headers=headers_mgr,
        json={"amount": grand_total, "reason": "Customer returned unopened product", "restockInventory": True},
    )
    refund_data = mgr_refund.json()
    assert refund_data["success"] is True
    assert refund_data["invoice"]["status"] == "refunded"
    assert refund_data["invoice"]["refundAmount"] == grand_total

    # 6. Verify inventory was restored back to 15
    inv_items_after_refund = client.get("/api/v1/inventory", headers=headers_mgr).json()
    prod_after_refund = next(p for p in inv_items_after_refund if p["id"] == prod_id)
    assert prod_after_refund["currentStock"] == 15

    # 7. Verify inventory ledger captured the refund restock
    ledger_res = client.get("/api/v1/inventory/ledger", headers=headers_mgr)
    assert ledger_res.status_code == 200
    ledger_entries = ledger_res.json()
    refund_entry = next((e for e in ledger_entries if e["itemId"] == prod_id and "Refund restock" in e["reason"]), None)
    assert refund_entry is not None
    assert refund_entry["changeQty"] == 2


def test_loyalty_points_redemption_at_checkout(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}

    # Create customer with 100 points
    cust_res = client.post(
        "/api/v1/customers",
        headers=headers_mgr,
        json={"name": "Deepika Padukone", "phone": "+919877788899", "loyaltyPoints": 100},
    )
    assert cust_res.status_code == 200
    cust_id = cust_res.json()["id"]

    # Checkout with 50 loyalty points redeemed (₹50 discount)
    inv_res = client.post(
        "/api/v1/invoices",
        headers=headers_mgr,
        json={
            "customerId": cust_id,
            "customerName": "Deepika Padukone",
            "items": [
                {"id": "srv_facial", "name": "Hydra Facial", "type": "service", "price": 1000.0, "quantity": 1},
            ],
            "loyaltyPointsRedeemed": 50,
            "discountPercent": 0.0,
            "taxPercent": 0.0,
            "paymentMethod": "CASH",
        },
    )
    assert inv_res.status_code == 200
    inv = inv_res.json()
    assert inv["pointsRedeemed"] == 50
    assert inv["pointsDiscount"] == 50.0
    assert inv["grandTotal"] == 950.0

    # Verify customer points balance updated
    cust_check = client.get("/api/v1/customers", headers=headers_mgr).json()
    cust = next(c for c in cust_check if c["id"] == cust_id)
    # 100 - 50 redeemed + 5% earned on 950 (47 points) = 97 points
    assert cust["loyaltyPoints"] == 50 + int(950 * 0.05)


def test_appointment_double_booking_collision_prevention(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}

    # 1. Book an appointment from 14:00 to 15:00
    app1_res = client.post(
        "/api/v1/appointments",
        headers=headers_mgr,
        json={
            "customerName": "Pooja Hegde",
            "customerPhone": "+919844455566",
            "staffName": "Master Stylist Rohit",
            "serviceName": "Balayage",
            "date": "2026-11-01",
            "time": "14:00",
            "duration": 60,
        },
    )
    assert app1_res.status_code == 200
    app1 = app1_res.json()
    app1_id = app1["id"]

    # 2. Attempt to book an overlapping appointment for same stylist (14:30 to 15:30)
    conflict_res = client.post(
        "/api/v1/appointments",
        headers=headers_mgr,
        json={
            "customerName": "Kiara Advani",
            "customerPhone": "+919855566677",
            "staffName": "Master Stylist Rohit",
            "serviceName": "Blowdry",
            "date": "2026-11-01",
            "time": "14:30",
            "duration": 60,
        },
    )
    assert conflict_res.status_code == 409
    assert "Double-booking conflict" in conflict_res.json()["detail"]

    # 3. Booking with allowDoubleBooking=True succeeds
    override_res = client.post(
        "/api/v1/appointments",
        headers=headers_mgr,
        json={
            "customerName": "Kiara Advani",
            "customerPhone": "+919855566677",
            "staffName": "Master Stylist Rohit",
            "serviceName": "Blowdry",
            "date": "2026-11-01",
            "time": "14:30",
            "duration": 60,
            "allowDoubleBooking": True,
        },
    )
    assert override_res.status_code == 200

    # 4. Reschedule appointment 1 to a different time
    resched_res = client.put(
        f"/api/v1/appointments/{app1_id}",
        headers=headers_mgr,
        json={
            "customerName": "Pooja Hegde",
            "customerPhone": "+919844455566",
            "staffName": "Master Stylist Rohit",
            "serviceName": "Balayage",
            "date": "2026-11-01",
            "time": "16:00",
            "duration": 60,
            "status": "confirmed",
        },
    )
    assert resched_res.status_code == 200
    assert resched_res.json()["time"] == "16:00"


def test_customer_duplicate_phone_prevention_and_export_import(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}

    unique_phone = "+919900088877"

    # 1. Create first customer
    c1 = client.post(
        "/api/v1/customers",
        headers=headers_mgr,
        json={"name": "Ananya Panday", "phone": unique_phone},
    )
    assert c1.status_code == 200

    # 2. Create duplicate phone -> 409 Conflict
    c_dup = client.post(
        "/api/v1/customers",
        headers=headers_mgr,
        json={"name": "Ananya P Duplicate", "phone": unique_phone},
    )
    assert c_dup.status_code == 409
    assert "already exists" in c_dup.json()["detail"]

    # 3. Create duplicate with updateExisting=True -> 200 OK (merges profile)
    c_merge = client.post(
        "/api/v1/customers",
        headers=headers_mgr,
        json={"name": "Ananya Panday VIP", "phone": unique_phone, "updateExisting": True, "notes": "VIP client"},
    )
    assert c_merge.status_code == 200
    assert c_merge.json()["name"] == "Ananya Panday VIP"

    # 4. Export customers CSV
    export_res = client.get("/api/v1/customers/export", headers=headers_mgr)
    assert export_res.status_code == 200
    assert "text/csv" in export_res.headers["content-type"]
    assert "Ananya Panday VIP" in export_res.text

    # 5. Bulk import customers
    import_res = client.post(
        "/api/v1/customers/import",
        headers=headers_mgr,
        json=[
            {"name": "Sara Ali Khan", "phone": "+919812398123", "email": "sara@example.com"},
            {"name": "Janhvi Kapoor", "phone": "+919845698456", "email": "janhvi@example.com"},
            {"name": "Duplicate Should Skip", "phone": unique_phone},
        ],
    )
    assert import_res.status_code == 200
    import_data = import_res.json()
    assert import_data["imported"] == 2
    assert import_data["skippedDuplicates"] == 1


def test_server_side_reports_and_role_permissions(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # 1. Receptionist accessing reports summary -> 403 Forbidden
    rec_res = client.get("/api/v1/reports/summary", headers=headers_rec)
    assert rec_res.status_code == 403

    # 2. Manager accessing reports summary -> 200 OK
    mgr_res = client.get("/api/v1/reports/summary", headers=headers_mgr)
    assert mgr_res.status_code == 200
    summary = mgr_res.json()
    assert "grossRevenue" in summary["metrics"]
    assert "netRevenue" in summary["metrics"]
    assert "taxTotal" in summary["metrics"]
    assert "paymentBreakdown" in summary
    assert "totalExpenses" in summary["metrics"]
    assert "netProfit" in summary["metrics"]


def test_cash_register_shift_lifecycle(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}

    # 1. Open register shift with ₹3,000 float
    open_res = client.post(
        "/api/v1/register/open",
        headers=headers_mgr,
        json={"openingFloat": 3000.0, "notes": "Morning opening drawer"},
    )
    assert open_res.status_code == 200
    shift = open_res.json()["shift"]
    assert shift["status"] == "open"
    assert shift["openingFloat"] == 3000.0
    shift_id = shift["id"]

    # 2. Current register returns open shift
    curr_res = client.get("/api/v1/register/current", headers=headers_mgr)
    assert curr_res.status_code == 200
    assert curr_res.json()["shift"]["id"] == shift_id

    # 3. Close register shift with ₹3,000 counted cash
    close_res = client.post(
        "/api/v1/register/close",
        headers=headers_mgr,
        json={"countedCash": 3000.0, "notes": "Evening shift reconciliation exact match"},
    )
    assert close_res.status_code == 200
    closed_shift = close_res.json()["shift"]
    assert closed_shift["status"] == "closed"
    assert closed_shift["cashVariance"] == 0.0


def test_expense_tracking(client, seed_test_data):
    headers_mgr = {"Authorization": f"Bearer {seed_test_data['token_mgr_a']}"}
    headers_rec = {"Authorization": f"Bearer {seed_test_data['token_rec_a']}"}

    # 1. Receptionist recording expense -> 403 Forbidden (financial control)
    rec_res = client.post(
        "/api/v1/expenses",
        headers=headers_rec,
        json={"title": "Coffee and Refreshments", "category": "Pantry", "amount": 450.0},
    )
    assert rec_res.status_code == 403

    # 2. Manager records expense
    mgr_res = client.post(
        "/api/v1/expenses",
        headers=headers_mgr,
        json={"title": "Laundry & Fresh Towels", "category": "Cleaning", "amount": 1200.0, "paymentMethod": "CASH"},
    )
    assert mgr_res.status_code == 200
    exp = mgr_res.json()
    assert exp["amount"] == 1200.0
    exp_id = exp["id"]

    # 3. List expenses
    exp_list = client.get("/api/v1/expenses", headers=headers_mgr).json()
    assert any(e["id"] == exp_id for e in exp_list)
