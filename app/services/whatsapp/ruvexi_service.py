"""RUVEXI Official WhatsApp Service (exclusively for salon owners, insights, alerts & platform comms)."""

import os
from typing import Dict, Any, Optional, List
from .base_client import whatsapp_base_client, is_sandbox_token


class RuvexiWhatsAppService:
    """
    Centralized RUVEXI Official WhatsApp Cloud API channel.
    Strictly isolated from tenant/salon customer credentials.
    Uses ONLY RUVEXI_WABA_ID, RUVEXI_PHONE_NUMBER_ID, and RUVEXI_WHATSAPP_ACCESS_TOKEN.
    """

    @property
    def waba_id(self) -> str:
        return os.getenv("RUVEXI_WABA_ID", "").strip()

    @property
    def phone_number_id(self) -> str:
        return os.getenv("RUVEXI_PHONE_NUMBER_ID", "").strip()

    @property
    def access_token(self) -> str:
        return os.getenv("RUVEXI_WHATSAPP_ACCESS_TOKEN", "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.phone_number_id and self.access_token)

    def get_public_status(self) -> Dict[str, Any]:
        """Returns safe status metadata without ever exposing the raw access token."""
        token = self.access_token
        masked = None
        if token:
            masked = "••••••••" if len(token) <= 10 else f"{token[:4]}••••••••{token[-4:]}"
        return {
            "channel": "RUVEXI",
            "isConfigured": self.is_configured,
            "isSandbox": is_sandbox_token(token) if token else False,
            "wabaId": self.waba_id or None,
            "phoneNumberId": self.phone_number_id or None,
            "maskedToken": masked,
            "graphApiVersion": whatsapp_base_client.api_version,
        }

    async def validate_platform_connection(self) -> Dict[str, Any]:
        if not self.is_configured:
            return {
                "success": False,
                "error": "RUVEXI_PHONE_NUMBER_ID and RUVEXI_WHATSAPP_ACCESS_TOKEN must be configured.",
            }
        return await whatsapp_base_client.validate_phone_credentials(
            phone_number_id=self.phone_number_id,
            access_token=self.access_token,
        )

    async def dispatch(
        self,
        *,
        to_phone: str,
        message_text: str,
        template_name: Optional[str] = None,
        template_params: Optional[List[str]] = None,
        language_code: str = "en_US",
    ) -> Dict[str, Any]:
        """Dispatches an owner/platform notification strictly via RUVEXI's official WhatsApp number."""
        if not self.is_configured:
            return {
                "success": False,
                "error": "RUVEXI Official WhatsApp API credentials are not configured.",
                "retryable": False,
            }

        if template_name and template_params is not None:
            tpl_res = await whatsapp_base_client.send_template(
                to_phone=to_phone,
                template_name=template_name,
                body_parameters=template_params,
                language_code=language_code,
                phone_number_id=self.phone_number_id,
                access_token=self.access_token,
            )
            if tpl_res.get("success") or tpl_res.get("error_code") != 132001:
                return tpl_res

        return await whatsapp_base_client.send_text(
            to_phone=to_phone,
            message_text=message_text,
            phone_number_id=self.phone_number_id,
            access_token=self.access_token,
        )


ruvexi_whatsapp_service = RuvexiWhatsAppService()
