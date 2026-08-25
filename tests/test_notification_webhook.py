"""Comprehensive WebhookProvider security/behavior tests.

Covers the SSRF guard, HMAC signing, retry behavior, redirect rejection,
and timeout handling — without any real external server (respx mocks httpx).
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import socket

import httpx
import pytest
import respx
from app.notifications.providers import (
    SmtpNotificationProvider,
    WebhookNotificationProvider,
    _safe_webhook_url,
)


# Isolated test env has no DNS; the SSRF guard calls socket.getaddrinfo().
# Stub DNS so a public hostname resolves to a PUBLIC IP, without touching the
# production guard logic. Rejection tests use literal private IPs and bypass DNS.
@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    def _fake_getaddrinfo(host, *a, **k):
        if host == "hooks.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        raise OSError("no dns in test env")

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    yield


# ---------- SSRF guard ----------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://hooks.example.com/aegis",  # public host
    ],
)
def test_safe_url_accepts_public_https(url):
    assert _safe_webhook_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/hook",  # loopback
        "http://localhost/hook",  # loopback name
        "http://169.254.169.254/latest/meta-data",  # cloud metadata (link-local)
        "http://10.0.0.5/hook",  # RFC1918
        "http://192.168.1.10/hook",  # RFC1918
        "http://172.16.0.9/hook",  # RFC1918
        "ftp://hooks.example.com/x",  # bad scheme
        "https://user:pass@hooks.example.com/x",  # userinfo rejected
        "https:///no-host",  # missing host
        "",  # empty
    ],
)
def test_safe_url_rejects_ssrf_and_bad_input(url):
    assert _safe_webhook_url(url) is False


# ---------- HMAC signing ---------------------------------------------------


@respx.mock
async def test_hmac_signature_header_matches_body():
    url = "https://hooks.example.com/aegis"
    secret = "test-signing-secret"
    route = respx.post(url).mock(return_value=httpx.Response(200))
    provider = WebhookNotificationProvider(url, signing_secret=secret)

    payload = {"tenant_id": "t1", "alert_id": "a1", "decision": "block"}
    ok = await provider.send("decision.block", payload)

    assert ok is True
    assert route.called
    request = route.calls[0].request
    expected_body = json.dumps(
        {"event_type": "decision.block", "payload": payload}, separators=(",", ":")
    ).encode()
    expected_sig = hmac_mod.new(secret.encode(), expected_body, hashlib.sha256).hexdigest()
    assert request.headers["X-Aegis-Signature"] == expected_sig
    assert request.content == expected_body


@respx.mock
async def test_no_signature_header_without_secret():
    url = "https://hooks.example.com/aegis"
    route = respx.post(url).mock(return_value=httpx.Response(200))
    provider = WebhookNotificationProvider(url)  # no secret
    ok = await provider.send("decision.review", {"tenant_id": "t1", "alert_id": "a1"})
    assert ok is True
    assert "X-Aegis-Signature" not in route.calls[0].request.headers


# ---------- SSRF blocks send ----------------------------------------------


async def test_ssrf_url_returns_false_without_http_call():
    provider = WebhookNotificationProvider("http://169.254.169.254/latest/meta-data")
    # No respx mock: any real HTTP attempt would fail/raise; the guard must
    # short-circuit before any socket work.
    assert await provider.send("decision.block", {"tenant_id": "t1"}) is False


# ---------- Retry behavior -------------------------------------------------


@respx.mock
async def test_retries_exhausted_then_false():
    url = "https://hooks.example.com/aegis"
    route = respx.post(url).mock(return_value=httpx.Response(500))
    provider = WebhookNotificationProvider(url, retries=2)
    ok = await provider.send("decision.block", {"tenant_id": "t1", "alert_id": "a1"})
    assert ok is False
    assert len(route.calls) == 3  # initial + 2 retries


@respx.mock
async def test_success_on_first_attempt_no_retry():
    url = "https://hooks.example.com/aegis"
    route = respx.post(url).mock(return_value=httpx.Response(200))
    provider = WebhookNotificationProvider(url, retries=2)
    ok = await provider.send("decision.review", {"tenant_id": "t1", "alert_id": "a1"})
    assert ok is True
    assert len(route.calls) == 1


@respx.mock
async def test_retry_recovers_after_failure():
    url = "https://hooks.example.com/aegis"
    route = respx.post(url).mock(side_effect=[httpx.Response(500), httpx.Response(200)])
    provider = WebhookNotificationProvider(url, retries=2)
    ok = await provider.send("decision.block", {"tenant_id": "t1", "alert_id": "a1"})
    assert ok is True
    assert len(route.calls) == 2


# ---------- Timeout handling ----------------------------------------------


@respx.mock
async def test_timeout_is_caught_and_returns_false():
    url = "https://hooks.example.com/aegis"
    route = respx.post(url).mock(side_effect=httpx.ReadTimeout("slow"))
    provider = WebhookNotificationProvider(url, timeout_sec=0.5, retries=0)
    ok = await provider.send("decision.block", {"tenant_id": "t1", "alert_id": "a1"})
    assert ok is False
    assert route.called


# ---------- Redirect rejection --------------------------------------------


@respx.mock
async def test_redirect_not_followed_and_counts_as_failure():
    url = "https://hooks.example.com/aegis"
    route = respx.post(url).mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example.com/x"})
    )
    provider = WebhookNotificationProvider(url, retries=0)
    ok = await provider.send("decision.block", {"tenant_id": "t1", "alert_id": "a1"})
    assert ok is False
    assert len(route.calls) == 1  # did NOT follow the redirect


# ---------- SmtpProvider (R1) ----------------------------------------------


async def test_smtp_unconfigured_returns_false():
    provider = SmtpNotificationProvider(host="", from_addr="", to_addr="")
    assert await provider.send("decision.block", {"tenant_id": "t1"}) is False


async def test_smtp_failure_is_best_effort(monkeypatch):
    def boom(self, msg):
        raise OSError("connection refused")

    monkeypatch.setattr(SmtpNotificationProvider, "_send_sync", boom)
    provider = SmtpNotificationProvider(
        host="smtp.example.com",
        port=587,
        from_addr="aegis@example.com",
        to_addr="sec@example.com",
    )
    # must swallow the error and return False, never raise
    assert await provider.send("decision.block", {"tenant_id": "t1"}) is False


# ---------- provider_from_settings -----------------------------------------


def test_provider_selection_smtp():
    from app.services.notifications import provider_from_settings

    class _S:
        NOTIFICATION_PROVIDER = "smtp"
        NOTIFICATION_SMTP_HOST = "smtp.example.com"
        NOTIFICATION_SMTP_PORT = 587
        NOTIFICATION_SMTP_USER = "u"
        NOTIFICATION_SMTP_PASSWORD = "p"
        NOTIFICATION_SMTP_FROM = "aegis@example.com"
        NOTIFICATION_SMTP_TO = "sec@example.com"
        NOTIFICATION_SMTP_USE_TLS = True
        NOTIFICATION_TIMEOUT_SEC = 5.0

    provider = provider_from_settings(_S())
    # Behavior-based identity: conftest wipes app.* modules from sys.modules between
    # tests, so the class object imported at module top can differ from the one
    # re-imported inside provider_from_settings. Assert the contract, not identity.
    assert type(provider).__name__ == "SmtpNotificationProvider"
    assert provider.host == "smtp.example.com"
    assert provider.port == 587
    assert provider.from_addr == "aegis@example.com"


# ---------- additional sandbox-verified coverage -----------------------------


def test_safe_url_rejects_unresolvable_host():
    assert _safe_webhook_url("https://no-such-host.invalid/x") is False


async def test_empty_url_is_rejected():
    provider = WebhookNotificationProvider("")
    assert await provider.send("decision.block", {"tenant_id": "t1"}) is False


@respx.mock
async def test_http_4xx_is_failure_with_bounded_retries():
    url = "https://hooks.example.com/aegis"
    route = respx.post(url).mock(return_value=httpx.Response(400))
    provider = WebhookNotificationProvider(url, retries=1)
    ok = await provider.send("decision.block", {"tenant_id": "t1"})
    assert ok is False
    assert route.call_count == 2


@respx.mock
async def test_transport_error_does_not_raise():
    url = "https://hooks.example.com/aegis"
    route = respx.post(url).mock(side_effect=httpx.ConnectError("refused"))
    provider = WebhookNotificationProvider(url, retries=0)
    assert await provider.send("decision.block", {"tenant_id": "t1"}) is False
    assert route.call_count == 1


async def test_smtp_success_path(monkeypatch):
    sent = {}

    def fake_send(self, msg):
        sent["to"] = msg["To"]
        sent["subject"] = msg["Subject"]

    monkeypatch.setattr(SmtpNotificationProvider, "_send_sync", fake_send)
    provider = SmtpNotificationProvider(
        "smtp.example.com", 587, from_addr="aegis@example.com", to_addr="sec@example.com"
    )
    ok = await provider.send("decision.block", {"tenant_id": "t1", "alert_id": "a1"})
    assert ok is True
    assert sent["to"] == "sec@example.com"
