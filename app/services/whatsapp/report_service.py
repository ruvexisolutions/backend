"""Real Database Business Report & Operational Alert Generator for RUVEXI Official WhatsApp."""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.core.models import (
    SalonModel,
    InvoiceModel,
    AppointmentModel,
    CustomerModel,
    InventoryModel,
    StaffModel,
)


class WhatsAppReportService:
    """Computes owner reports strictly from real database records scoped to tenant_id."""

    def _ist_now(self) -> datetime:
        return datetime.utcnow() + timedelta(hours=5, minutes=30)

    def _parse_dt(self, raw: Any) -> Optional[datetime]:
        if isinstance(raw, datetime):
            return raw
        if not raw:
            return None
        s = str(raw).strip().replace("Z", "")
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s[:26], fmt)
            except Exception:
                continue
        return None

    def build_business_report_metrics(
        self,
        db: Session,
        tenant_id: str,
        period: str = "daily",
        branch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        salon = db.query(SalonModel).filter(SalonModel.id == tenant_id).first()
        if not salon:
            raise ValueError("Salon not found")

        now_ist = self._ist_now()
        today_str = now_ist.strftime("%Y-%m-%d")
        if period == "weekly":
            cutoff = datetime.utcnow() - timedelta(days=7)
            date_label = f"{(now_ist - timedelta(days=7)).strftime('%d %b')} - {now_ist.strftime('%d %b %Y')}"
        elif period == "monthly":
            cutoff = datetime.utcnow() - timedelta(days=30)
            date_label = f"{(now_ist - timedelta(days=30)).strftime('%d %b')} - {now_ist.strftime('%d %b %Y')}"
        else:
            cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            date_label = now_ist.strftime("%d %b %Y")

        invoices = db.query(InvoiceModel).filter(InvoiceModel.salon_id == tenant_id).all()
        appointments = db.query(AppointmentModel).filter(AppointmentModel.salon_id == tenant_id).all()
        customers = db.query(CustomerModel).filter(CustomerModel.salon_id == tenant_id).all()
        inventory = db.query(InventoryModel).filter(InventoryModel.salon_id == tenant_id).all()
        staff = db.query(StaffModel).filter(StaffModel.salon_id == tenant_id).all()

        if branch_id:
            invoices = [i for i in invoices if not i.branch_id or i.branch_id == branch_id]
            appointments = [a for a in appointments if not a.branch_id or a.branch_id == branch_id]
            staff = [s for s in staff if not s.branch_id or s.branch_id == branch_id]

        def in_period(raw_dt: Any) -> bool:
            if period == "daily" and isinstance(raw_dt, str) and raw_dt.startswith(today_str):
                return True
            parsed = self._parse_dt(raw_dt)
            return bool(parsed and parsed >= cutoff)

        period_invoices = [i for i in invoices if in_period(i.paid_at or i.created_at)]
        paid_invoices = [i for i in period_invoices if (i.status or "").lower() == "paid"]
        pending_invoices = [i for i in invoices if (i.status or "").lower() in ("pending", "partially_paid")]

        revenue = sum(float(i.grand_total or 0.0) for i in paid_invoices)
        pending_amount = sum(float(i.grand_total or 0.0) for i in pending_invoices)

        period_appts = [a for a in appointments if in_period(a.date or a.created_at)]
        total_appts = len(period_appts)
        completed_appts = sum(1 for a in period_appts if (a.status or "").lower() == "completed")
        cancelled_appts = sum(1 for a in period_appts if (a.status or "").lower() == "cancelled")

        new_customers = sum(1 for c in customers if in_period(c.created_at))
        returning_customers = max(0, len(paid_invoices) - new_customers)

        service_rev: Dict[str, float] = {}
        staff_rev: Dict[str, float] = {}
        for inv in paid_invoices:
            try:
                items = json.loads(inv.items_json) if inv.items_json else []
            except Exception:
                items = []
            for it in items:
                if it.get("type") == "product":
                    continue
                sname = str(it.get("name") or "").strip()
                amt = float(it.get("price") or 0.0) * int(it.get("quantity") or 1)
                if sname:
                    service_rev[sname] = service_rev.get(sname, 0.0) + amt
                st_name = str(it.get("staffName") or inv.staff_name or "").strip()
                if st_name:
                    staff_rev[st_name] = staff_rev.get(st_name, 0.0) + amt

        top_service = max(service_rev.items(), key=lambda kv: kv[1])[0] if service_rev else "N/A"
        top_staff = max(staff_rev.items(), key=lambda kv: kv[1])[0] if staff_rev else "N/A"
        low_stock_items = [
            {"name": i.name, "stock": i.current_stock, "threshold": i.min_threshold}
            for i in inventory
            if (i.current_stock or 0) <= (i.min_threshold or 0)
        ]

        return {
            "salonName": salon.name,
            "period": period,
            "date": date_label,
            "revenue": round(revenue, 2),
            "totalAppointments": total_appts,
            "completedAppointments": completed_appts,
            "cancelledAppointments": cancelled_appts,
            "newCustomers": new_customers,
            "returningCustomers": returning_customers,
            "pendingPayments": round(pending_amount, 2),
            "topService": top_service,
            "topStaff": top_staff,
            "lowStockCount": len(low_stock_items),
            "lowStockItems": low_stock_items[:5],
            "staffCount": len(staff),
        }

    def format_daily_report_message(self, metrics: Dict[str, Any]) -> str:
        header = "Good morning!" if metrics["period"] == "daily" else f"Here is your {metrics['period'].title()} RUVEXI Summary!"
        return (
            f"{header}\n\n"
            f"Here is your RUVEXI Business Report for {metrics['salonName']}.\n\n"
            f"Date: {metrics['date']}\n\n"
            f"Revenue: ₹{metrics['revenue']:,.0f}\n"
            f"Total Appointments: {metrics['totalAppointments']}\n"
            f"Completed Appointments: {metrics['completedAppointments']}\n"
            f"Cancelled Appointments: {metrics['cancelledAppointments']}\n"
            f"New Customers: {metrics['newCustomers']}\n"
            f"Returning Customers: {metrics['returningCustomers']}\n"
            f"Pending Payments: ₹{metrics['pendingPayments']:,.0f}\n\n"
            f"Your top-performing service: {metrics['topService']}\n\n"
            f"Log in to RUVEXI to view your complete business analytics."
        )

    def format_operational_alert(self, salon_name: str, alert_title: str, alert_body: str) -> str:
        return (
            f"⚠️ *RUVEXI Operational Alert — {salon_name}*\n\n"
            f"*{alert_title}*\n"
            f"{alert_body}\n\n"
            f"Log in to RUVEXI to take action."
        )


whatsapp_report_service = WhatsAppReportService()
