"""EmailService — single email abstraction for AEGIS transactional mail.

Provider selection is config-driven (EMAIL_PROVIDER):
  - console  (default, dev/test): emails are captured in-process and logged —
    NO external call. Tests read the captured message (and its invite/reset
    link) via `EmailService.outbox`. This is what makes the full invitation /
    reset flow testable without any real mail server.
  - brevo    (production): sends through the Brevo transactional API
    (BREVO_API_KEY / BREVO_SENDER_EMAIL / BREVO_SENDER_NAME).

Routers/services NEVER talk to a provider directly — they call
`EmailService.send_*`, so swapping providers later requires no auth changes.

Never logs passwords, raw tokens, or secrets — only the link's existence.
"""

from __future__ import annotations

import json
import urllib.request

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
        # console / anything else -> dev sink
        entry = {"to": to, "subject": subject, "text": text}
        self.outbox.append(entry)
        logger.info("email.console", to=to, subject=subject)
        return True

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
