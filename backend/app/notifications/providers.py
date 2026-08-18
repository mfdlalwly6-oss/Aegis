"""Notification providers — adapter pattern.
Default is Console (logs). Webhook provider available if URL configured.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class NotificationProvider:
    async def send(self, event_type: str, payload: dict[str, Any]) -> bool:
        raise NotImplementedError


class ConsoleNotificationProvider(NotificationProvider):
    async def send(self, event_type: str, payload: dict[str, Any]) -> bool:
        logger.info("notification.console", event_type=event_type,
                    alert_id=payload.get("alert_id"), tenant_id=payload.get("tenant_id"))
        return True


class WebhookNotificationProvider(NotificationProvider):
    def __init__(self, url: str):
        self.url = url

    async def send(self, event_type: str, payload: dict[str, Any]) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as cli:
                r = await cli.post(self.url, json={
                    "event_type": event_type,
                    "payload": payload,
                })
                return r.status_code < 400
        except Exception as e:
            logger.warning("notification.webhook_failed", error=str(e))
            return False
