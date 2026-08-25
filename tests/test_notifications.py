import asyncio

from app.services.notifications import NotificationService, provider_from_settings


class Provider:
    def __init__(self, result=True):
        self.result = result
        self.calls = 0

    async def send(self, event_type, payload):
        self.calls += 1
        return self.result


class Audit:
    def __init__(self):
        self.events = []

    def log(self, *args):
        self.events.append(args[2])


def test_notification_message_is_minimal_and_audited():
    audit, provider = Audit(), Provider()
    service = NotificationService(provider, audit)
    ok = asyncio.run(
        service.notify(
            "decision.review",
            {"tenant_id": "t1", "alert_id": "a1", "tx_id": "x", "severity": "high", "hmac_secret": "no"},
            {"decision": "review", "api_key": "no"},
        )
    )
    assert ok and provider.calls == 1 and audit.events == ["notification.sent"]
    assert "hmac_secret" not in service.message("x", {"tenant_id": "t1", "alert_id": "a1"}, {})


def test_failure_is_best_effort_and_audited():
    audit = Audit()
    assert not asyncio.run(
        NotificationService(Provider(False), audit).notify(
            "decision.block", {"tenant_id": "t", "alert_id": "a"}, {}
        )
    )
    assert audit.events == ["notification.failed"]


def test_provider_selection_defaults_to_console():
    class Settings:
        NOTIFICATION_PROVIDER = "console"
        NOTIFICATION_WEBHOOK_URL = ""
        NOTIFICATION_WEBHOOK_SECRET = ""
        NOTIFICATION_TIMEOUT_SEC = 1
        NOTIFICATION_RETRIES = 0

    assert type(provider_from_settings(Settings())).__name__ == "ConsoleNotificationProvider"


def test_provider_exception_is_swallowed_and_audited():
    class Boom:
        async def send(self, event_type, payload):
            raise RuntimeError("provider bug")

    audit = Audit()
    ok = asyncio.run(
        NotificationService(Boom(), audit).notify("decision.block", {"tenant_id": "t", "alert_id": "a"}, {})
    )
    assert not ok and audit.events == ["notification.failed"]


def test_unknown_provider_falls_back_to_console():
    class Settings:
        NOTIFICATION_PROVIDER = "carrier-pigeon"
        NOTIFICATION_WEBHOOK_URL = ""
        NOTIFICATION_WEBHOOK_SECRET = ""
        NOTIFICATION_TIMEOUT_SEC = 1
        NOTIFICATION_RETRIES = 0

    assert type(provider_from_settings(Settings())).__name__ == "ConsoleNotificationProvider"
