"""WhatsApp Template Management & Sync Service for RUVEXI and Per-Salon WABAs."""

from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
from sqlalchemy.orm import Session
from app.core.models import WhatsAppTemplateModel
from .base_client import whatsapp_base_client, is_sandbox_token
from .ruvexi_service import ruvexi_whatsapp_service
from .salon_service import salon_whatsapp_service


DEFAULT_RUVEXI_TEMPLATES = [
    {
        "name": "ruvexi_daily_owner_report",
        "category": "UTILITY",
        "language": "en_US",
        "description": "Daily business revenue, appointments, and top service summary for salon owners.",
    },
    {
        "name": "ruvexi_owner_operational_alert",
        "category": "UTILITY",
        "language": "en_US",
        "description": "Low-stock, pending payments, and subscription alerts for salon owners.",
    },
]

DEFAULT_SALON_SANDBOX_TEMPLATES = [
    {
        "name": "ruvexi_appointment_confirmation",
        "category": "UTILITY",
        "language": "en_US",
        "status": "SANDBOX_PREVIEW",
        "description": "Appointment confirmation with service, stylist, and slot.",
    },
    {
        "name": "ruvexi_service_receipt",
        "category": "UTILITY",
        "language": "en_US",
        "status": "SANDBOX_PREVIEW",
        "description": "Digital GST invoice and payment confirmation.",
    },
    {
        "name": "ruvexi_rebooking_touchup",
        "category": "MARKETING",
        "language": "en_US",
        "status": "SANDBOX_PREVIEW",
        "description": "Birthday wishes and promotional salon offers.",
    },
]


class WhatsAppTemplateService:
    async def fetch_remote_templates(self, waba_id: Optional[str], access_token: Optional[str]) -> List[Dict[str, Any]]:
        if not access_token:
            return []
        if is_sandbox_token(access_token):
            return list(DEFAULT_SALON_SANDBOX_TEMPLATES)
        if not waba_id:
            return []

        url = f"https://graph.facebook.com/{whatsapp_base_client.api_version}/{waba_id}/message_templates"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"limit": 100, "fields": "name,category,language,status,components"}
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                out = []
                for tpl in data.get("data", []):
                    body_comp = next((c for c in tpl.get("components", []) if c.get("type") == "BODY"), None)
                    out.append({
                        "name": tpl.get("name"),
                        "category": tpl.get("category", "UTILITY"),
                        "language": tpl.get("language", "en_US"),
                        "status": tpl.get("status", "UNKNOWN"),
                        "description": (body_comp or {}).get("text", ""),
                    })
                return out
        except Exception:
            return []

    async def sync_salon_templates(self, db: Session, tenant_id: str) -> List[Dict[str, Any]]:
        conn, _, access_token = salon_whatsapp_service.resolve_tenant_credentials(db, tenant_id)
        if not conn or not access_token:
            rows = (
                db.query(WhatsAppTemplateModel)
                .filter(WhatsAppTemplateModel.tenant_id == tenant_id, WhatsAppTemplateModel.channel_type == "SALON")
                .all()
            )
            return [r.to_dict() for r in rows]

        remote = await self.fetch_remote_templates(conn.waba_id, access_token)
        if remote:
            for item in remote:
                tpl_name = str(item.get("name") or "")
                if not tpl_name:
                    continue
                existing = (
                    db.query(WhatsAppTemplateModel)
                    .filter(
                        WhatsAppTemplateModel.tenant_id == tenant_id,
                        WhatsAppTemplateModel.channel_type == "SALON",
                        WhatsAppTemplateModel.template_name == tpl_name,
                    )
                    .first()
                )
                if not existing:
                    existing = WhatsAppTemplateModel(
                        tenant_id=tenant_id,
                        channel_type="SALON",
                        template_name=tpl_name,
                    )
                    db.add(existing)
                existing.language = str(item.get("language") or "en_US")
                existing.category = str(item.get("category") or "UTILITY")
                existing.approval_status = str(item.get("status") or "PENDING")
                existing.body_preview = str(item.get("description") or "")
                existing.updated_at = datetime.utcnow()
            db.commit()

        rows = (
            db.query(WhatsAppTemplateModel)
            .filter(WhatsAppTemplateModel.tenant_id == tenant_id, WhatsAppTemplateModel.channel_type == "SALON")
            .order_by(WhatsAppTemplateModel.template_name.asc())
            .all()
        )
        return [r.to_dict() for r in rows]

    async def sync_ruvexi_templates(self, db: Session) -> List[Dict[str, Any]]:
        if ruvexi_whatsapp_service.is_configured:
            remote = await self.fetch_remote_templates(
                ruvexi_whatsapp_service.waba_id,
                ruvexi_whatsapp_service.access_token,
            )
            for item in remote:
                tpl_name = str(item.get("name") or "")
                if not tpl_name:
                    continue
                existing = (
                    db.query(WhatsAppTemplateModel)
                    .filter(
                        WhatsAppTemplateModel.tenant_id.is_(None),
                        WhatsAppTemplateModel.channel_type == "RUVEXI",
                        WhatsAppTemplateModel.template_name == tpl_name,
                    )
                    .first()
                )
                if not existing:
                    existing = WhatsAppTemplateModel(
                        tenant_id=None,
                        channel_type="RUVEXI",
                        template_name=tpl_name,
                    )
                    db.add(existing)
                existing.language = str(item.get("language") or "en_US")
                existing.category = str(item.get("category") or "UTILITY")
                existing.approval_status = str(item.get("status") or "PENDING")
                existing.body_preview = str(item.get("description") or "")
                existing.updated_at = datetime.utcnow()
            db.commit()

        rows = (
            db.query(WhatsAppTemplateModel)
            .filter(WhatsAppTemplateModel.tenant_id.is_(None), WhatsAppTemplateModel.channel_type == "RUVEXI")
            .all()
        )
        if rows:
            return [r.to_dict() for r in rows]
        return [
            {
                "name": t["name"],
                "templateName": t["name"],
                "category": t["category"],
                "language": t["language"],
                "status": "NOT_SYNCED",
                "channelType": "RUVEXI",
                "description": t["description"],
            }
            for t in DEFAULT_RUVEXI_TEMPLATES
        ]


whatsapp_template_service = WhatsAppTemplateService()
