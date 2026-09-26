"""EmailService — single email abstraction for AEGIS transactional mail.

Provider selection is config-driven (EMAIL_PROVIDER):
  - console  (default, dev/test): emails are captured in-process and logged —
    NO external call. Tests read the captured message (and its invite/reset
    link) via `EmailService.outbox`. This is what makes the full invitation /
    reset flow testable without any real mail server.
  - brevo    (production): sends through the Brevo transactional API
    (BREVO_API_KEY / BREVO_SENDER_EMAIL / BREVO_SENDER_NAME).
  - smtp     (real integration / production): sends through any SMTP relay
    (e.g. Gmail smtp.gmail.com:587 STARTTLS) via GMAIL_SMTP_* / generic
    SMTP_* settings. Credentials come ONLY from the environment — never from
    code, git, migrations, tests, or logs.

Routers/services NEVER talk to a provider directly — they call
`EmailService.send_*`, so swapping providers later requires no auth changes.

Never logs passwords, raw tokens, or secrets — only the link's existence.
"""

from __future__ import annotations

import json
import smtplib
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


def _invite_link(token: str) -> str:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/merchant/?view=accept-invitation&token={token}"


def _reset_link(token: str) -> str:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/merchant/?view=reset-password&token={token}"


class EmailService:
    def __init__(self):
        self.provider = (getattr(settings, "EMAIL_PROVIDER", "console") or "console").lower()
        # Dev/test sink: captured outbound mail (never persisted, per-process).
        self.outbox: list[dict] = []

    # ------------------------------------------------------------------ io --
    def _deliver(self, to: str, subject: str, text: str) -> bool:
        if self.provider == "brevo":
            return self._send_brevo(to, subject, text)
        if self.provider == "smtp":
            return self._send_smtp(to, subject, text)
        # console / anything else -> dev sink
        entry = {"to": to, "subject": subject, "text": text}
        self.outbox.append(entry)
        logger.info("email.console", to=to, subject=subject)
        return True

    # ----------------------------------------------------------------- smtp --
    def _smtp_config(self) -> dict:
        """Resolve SMTP settings. Prefers GMAIL_SMTP_* (the configured Gmail
        relay) and falls back to generic SMTP_* names, so any relay works
        without code changes. Password is read from env only."""
        g = lambda k, d="": (getattr(settings, k, d) or d)  # noqa: E731
        host = g("GMAIL_SMTP_HOST") or g("SMTP_HOST") or "smtp.gmail.com"
        return {
            "host": host,
            "port": int(g("GMAIL_SMTP_PORT") or g("SMTP_PORT") or 587),
            "username": g("GMAIL_SMTP_USERNAME") or g("SMTP_USERNAME"),
            "password": g("GMAIL_SMTP_PASSWORD") or g("SMTP_PASSWORD"),
            "use_tls": str(g("GMAIL_SMTP_USE_TLS", "true") or g("SMTP_USE_TLS", "true")).lower() in ("1", "true", "yes"),
            "sender_email": g("GMAIL_SMTP_SENDER_EMAIL") or g("SMTP_SENDER_EMAIL") or g("GMAIL_SMTP_USERNAME"),
            "sender_name": g("GMAIL_SMTP_SENDER_NAME") or g("SMTP_SENDER_NAME") or "AEGIS",
            "timeout": float(g("SMTP_TIMEOUT_SEC", "15") or 15),
        }

    def _send_smtp(self, to: str, subject: str, text: str) -> bool:
        cfg = self._smtp_config()
        if not cfg["username"] or not cfg["password"] or not cfg["sender_email"]:
            logger.warning("email.smtp_misconfigured_fallback_console", to=to)
            self.outbox.append({"to": to, "subject": subject, "text": text})
            return False
        msg = EmailMessage()
        msg["From"] = formataddr((cfg["sender_name"], cfg["sender_email"]))
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        try:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=cfg["timeout"]) as s:
                s.ehlo()
                if cfg["use_tls"]:
                    s.starttls()
                    s.ehlo()
                s.login(cfg["username"], cfg["password"])
                s.send_message(msg)
            logger.info("email.smtp", to=to, subject=subject, host=cfg["host"])
            return True
        except Exception as e:  # noqa: BLE001 — mail must never crash the request
            # Never log the exception payload blindly (it can echo credentials on
            # some auth failures); log only the safe error class.
            logger.warning("email.smtp_failed", to=to, error_type=type(e).__name__)
            return False

    def _send_brevo(self, to: str, subject: str, text: str) -> bool:
        api_key = getattr(settings, "BREVO_API_KEY", "") or ""
        sender_email = getattr(settings, "BREVO_SENDER_EMAIL", "") or ""
        if not api_key or not sender_email:
            logger.warning("email.brevo_misconfigured_fallback_console", to=to)
            self.outbox.append({"to": to, "subject": subject, "text": text})
            return False
        payload = {
            "sender": {
                "email": sender_email,
                "name": getattr(settings, "BREVO_SENDER_NAME", "") or "AEGIS",
            },
            "to": [{"email": to}],
            "subject": subject,
            "textContent": text,
        }
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode(),
            headers={"api-key": api_key, "Content-Type": "application/json", "accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                ok = 200 <= r.status < 300
                logger.info("email.brevo", to=to, subject=subject, status=r.status)
                return ok
        except Exception as e:  # noqa: BLE001 — mail must never crash the request
            logger.warning("email.brevo_failed", to=to, error=str(e)[:120])
            return False

    # -------------------------------------------------------------- messages --
    def send_invitation(self, *, to: str, tenant_name: str, owner_name: str, token: str) -> bool:
        link = _invite_link(token)
        text = (
            f"مرحبًا {owner_name},\n\n"
            f"تمت دعوتك لإدارة مؤسسة «{tenant_name}» على منصة AEGIS.\n"
            f"لتفعيل حسابك وإنشاء كلمة المرور، افتح الرابط التالي (صالح لمدة "
            f"{settings.INVITATION_TTL_HOURS} ساعة):\n\n{link}\n\n"
            "إذا لم تطلب هذه الدعوة، تجاهل هذه الرسالة.\n— AEGIS"
        )
        return self._deliver(to, f"دعوتك لإدارة «{tenant_name}» على AEGIS", text)

    def send_password_reset(self, *, to: str, tenant_name: str, token: str) -> bool:
        link = _reset_link(token)
        text = (
            "مرحبًا،\n\n"
            f"طلبت إعادة تعيين كلمة المرور لحسابك في «{tenant_name}» على AEGIS.\n"
            f"الرابط صالح لمدة {settings.RESET_TOKEN_TTL_HOURS} ساعة:\n\n{link}\n\n"
            "إذا لم تطلب ذلك، تجاهل هذه الرسالة — كلمة مرورك الحالية تبقى كما هي.\n— AEGIS"
        )
        return self._deliver(to, "إعادة تعيين كلمة المرور — AEGIS", text)

    # ------------------------------------------------------------- test api --
    def last_link(self, to: str | None = None, kind: str = "accept-invitation") -> str | None:
        """Test/dev helper: extract the latest link of a kind from the outbox."""
        for entry in reversed(self.outbox):
            if to and entry["to"] != to:
                continue
            for line in entry["text"].splitlines():
                line = line.strip()
                if f"view={kind}" in line:
                    return line
        return None
