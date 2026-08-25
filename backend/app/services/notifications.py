"""Best-effort, tenant-scoped decision notification service."""

from __future__ import annotations

from typing import Any

import structlog

from app.notifications.providers import (
    ConsoleNotificationProvider,
    SmtpNotificationProvider,
    WebhookNotificationProvider,
)

logger = structlog.get_logger(__name__)


class NotificationService:
    def __init__(self, provider, audit=None):
        self.provider = provider
        self.audit = audit

    @staticmethod
    def message(event_type: str, alert: dict, decision: dict) -> dict[str, Any]:
        return {
            "tenant_id": alert["tenant_id"],
            "alert_id": alert["alert_id"],
            "decision_id": decision.get("decision_id"),
            "tx_id": alert.get("tx_id"),
            "decision": decision.get("decision"),
            "severity": alert.get("severity"),
            "event_type": event_type,
        }

    async def notify(self, event_type: str, alert: dict, decision: dict) -> bool:
        payload = self.message(event_type, alert, decision)
        try:
            ok = await self.provider.send(event_type, payload)
        except Exception:
            ok = False
        if self.audit:
            self.audit.log(
                payload["tenant_id"],
                "system",
                "notification.sent" if ok else "notification.failed",
                "alert",
                payload["alert_id"],
                None,
                {"event_type": event_type, "provider": type(self.provider).__name__},
            )
        return ok


def provider_from_settings(settings):
    if settings.NOTIFICATION_PROVIDER == "webhook" and settings.NOTIFICATION_WEBHOOK_URL:
        return WebhookNotificationProvider(
            settings.NOTIFICATION_WEBHOOK_URL,
            settings.NOTIFICATION_WEBHOOK_SECRET,
            settings.NOTIFICATION_TIMEOUT_SEC,
            settings.NOTIFICATION_RETRIES,
        )
    if settings.NOTIFICATION_PROVIDER == "smtp" and settings.NOTIFICATION_SMTP_HOST:
        return SmtpNotificationProvider(
            settings.NOTIFICATION_SMTP_HOST,
            settings.NOTIFICATION_SMTP_PORT,
            settings.NOTIFICATION_SMTP_USER,
            settings.NOTIFICATION_SMTP_PASSWORD,
            settings.NOTIFICATION_SMTP_FROM,
            settings.NOTIFICATION_SMTP_TO,
            settings.NOTIFICATION_SMTP_USE_TLS,
            settings.NOTIFICATION_TIMEOUT_SEC,
        )
    if settings.NOTIFICATION_PROVIDER not in {"console", "webhook", "smtp"}:
        logger.warning("notification.unknown_provider_fallback", provider=settings.NOTIFICATION_PROVIDER)
    return ConsoleNotificationProvider()
