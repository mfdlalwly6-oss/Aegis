"""Outbound notification providers; never raise into the decision path."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import smtplib
import socket
import ssl
from email.message import EmailMessage
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)


class NotificationProvider(Protocol):
    async def send(self, event_type: str, payload: dict[str, Any]) -> bool: ...


class ConsoleNotificationProvider(NotificationProvider):
    async def send(self, event_type: str, payload: dict[str, Any]) -> bool:
        logger.info(
            "notification.console",
            event_type=event_type,
            alert_id=payload.get("alert_id"),
            tenant_id=payload.get("tenant_id"),
        )
        return True


def _safe_webhook_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        return False
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(
                parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
            )
        }
        # is_global rejects loopback/private/link-local AND multicast/reserved/unspecified
        return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)
    except (OSError, ValueError):
        return False


class WebhookNotificationProvider(NotificationProvider):
    def __init__(self, url: str, signing_secret: str = "", timeout_sec: float = 5, retries: int = 2):
        self.url, self.signing_secret = url, signing_secret
        self.timeout_sec, self.retries = max(0.1, timeout_sec), max(0, retries)

    async def send(self, event_type: str, payload: dict[str, Any]) -> bool:
        if not _safe_webhook_url(self.url):
            logger.warning("notification.webhook_rejected")
            return False
        body = json.dumps({"event_type": event_type, "payload": payload}, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if self.signing_secret:
            headers["X-Aegis-Signature"] = hmac.new(
                self.signing_secret.encode(), body, hashlib.sha256
            ).hexdigest()
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_sec, follow_redirects=False) as client:
                    resp = await client.post(self.url, content=body, headers=headers)
                    # 2xx only: 3xx is a redirect (not followed) and must NOT
                    # count as delivered; >=400 is an outright failure.
                    if 200 <= resp.status_code < 300:
                        return True
            except httpx.HTTPError:
                pass
            if attempt < self.retries:
                await asyncio.sleep(min(0.1 * (attempt + 1), 1.0))
        logger.warning("notification.webhook_failed")
        return False


class SmtpNotificationProvider(NotificationProvider):
    """Email delivery via SMTP (TLS). Best-effort: never raises into the decision path."""

    def __init__(
        self,
        host: str,
        port: int = 587,
        user: str = "",
        password: str = "",
        from_addr: str = "",
        to_addr: str = "",
        use_tls: bool = True,
        timeout_sec: float = 5.0,
    ):
        self.host, self.port = host, int(port)
        self.user, self._password = user, password
        self.from_addr, self.to_addr = from_addr, to_addr
        self.use_tls, self.timeout_sec = use_tls, max(0.1, timeout_sec)

    async def send(self, event_type: str, payload: dict[str, Any]) -> bool:
        if not self.host or not self.from_addr or not self.to_addr:
            logger.warning("notification.smtp_unconfigured")
            return False
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.from_addr, self.to_addr, f"AEGIS {event_type}"
        # Minimal body: identifiers only, no secrets
        msg.set_content(
            json.dumps(
                {
                    "event_type": event_type,
                    "tenant_id": payload.get("tenant_id"),
                    "alert_id": payload.get("alert_id"),
                    "decision": payload.get("decision"),
                    "tx_id": payload.get("tx_id"),
                    "severity": payload.get("severity"),
                },
                indent=2,
            )
        )
        try:
            await asyncio.wait_for(asyncio.to_thread(self._send_sync, msg), timeout=self.timeout_sec)
            return True
        except Exception:
            logger.warning("notification.smtp_failed", host=self.host)
            return False

    def _send_sync(self, msg: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_sec) as server:
            if self.use_tls:
                server.starttls(context=ssl.create_default_context())
            if self.user and self._password:
                server.login(self.user, self._password)
            server.send_message(msg)
