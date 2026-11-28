"""Async Background Queue Processor & Report Scheduler for Dual WhatsApp Channels."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.models import (
    WhatsAppMessageLogModel,
    WhatsAppNotificationPreferenceModel,
    SalonModel,
)
from .message_router import whatsapp_message_router, MessageCategory
from .report_service import whatsapp_report_service


class WhatsAppScheduler:
    """
    Runs inside FastAPI lifespan without blocking booking/billing transactions.
    Processes queued & retryable WhatsApp messages and scheduled owner reports.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self):
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(f"[WhatsApp Scheduler Notice] {exc}")
            await asyncio.sleep(60)

    async def run_once(self) -> Dict[str, int]:
        db = SessionLocal()
        try:
            retried = await self.process_retry_queue(db)
            scheduled = await self.dispatch_due_owner_reports(db)
            return {"retried": retried, "scheduledReports": scheduled}
        finally:
            db.close()

    async def process_retry_queue(self, db: Session, limit: int = 25) -> int:
        now = datetime.utcnow()
        due_logs = (
            db.query(WhatsAppMessageLogModel)
            .filter(
                WhatsAppMessageLogModel.delivery_status == "queued",
                WhatsAppMessageLogModel.next_retry_at <= now,
            )
            .order_by(WhatsAppMessageLogModel.created_at.asc())
            .limit(limit)
            .all()
        )
        count = 0
        for log in due_logs:
            await whatsapp_message_router.process_log_entry(db, log)
            count += 1
        return count

    async def dispatch_due_owner_reports(self, db: Session) -> int:
        now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
        current_hhmm = now_ist.strftime("%H:%M")
        today_key = now_ist.strftime("%Y-%m-%d")

        prefs = (
            db.query(WhatsAppNotificationPreferenceModel)
            .filter(
                WhatsAppNotificationPreferenceModel.channel_type == "RUVEXI",
                WhatsAppNotificationPreferenceModel.is_enabled == True,
                WhatsAppNotificationPreferenceModel.opted_in == True,
                WhatsAppNotificationPreferenceModel.notification_type.in_(["daily_report", "weekly_report", "monthly_report"]),
            )
            .all()
        )

        dispatched = 0
        for pref in prefs:
            pref_time = (pref.preferred_delivery_time or "09:00").strip()
            if pref_time != current_hhmm:
                continue
            if pref.notification_type == "weekly_report" and now_ist.weekday() != 0:
                continue
            if pref.notification_type == "monthly_report" and now_ist.day != 1:
                continue

            salon = db.query(SalonModel).filter(SalonModel.id == pref.tenant_id).first()
            recipient = (pref.recipient_phone or (salon.phone if salon else "") or "").strip()
            if not salon or not recipient:
                continue

            period = pref.notification_type.replace("_report", "")
            idem_key = f"sched:{pref.tenant_id}:{pref.notification_type}:{today_key}:{recipient}"
            metrics = whatsapp_report_service.build_business_report_metrics(db, pref.tenant_id, period=period)
            body = whatsapp_report_service.format_daily_report_message(metrics)

            res = await whatsapp_message_router.route_and_send(
                db=db,
                tenant_id=pref.tenant_id,
                category=MessageCategory.OWNER_REPORT,
                recipient_number=recipient,
                message_text=body,
                customer_name=salon.name,
                template_name="ruvexi_daily_owner_report",
                idempotency_key=idem_key,
            )
            if res.get("success") and not res.get("deduplicated"):
                pref.last_dispatched_at = datetime.utcnow()
                db.commit()
                dispatched += 1

        return dispatched


whatsapp_scheduler = WhatsAppScheduler()
