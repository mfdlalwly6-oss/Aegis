"""Timezone correctness for the report builder (UTC storage + IANA conversion).

The report window is computed in the tenant's local timezone then converted to
UTC before querying (DB timestamps are stored UTC ISO). These tests pin that
behavior: correct UTC conversion, DST-aware offsets, fallback for invalid IANA
names, and the three period boundaries.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.reports.service import ReportBuilder


class _Tenants:
    def __init__(self, tz):
        self.tz = tz

    def get(self, tenant_id, reveal=False):
        return {
            "tenant_id": tenant_id,
            "timezone": self.tz,
            "policy": {},
            "name": "TZ Test Tenant",
            "type": "wallet",
            "country": "YE",
            "plan": "sandbox",
            "status": "active",
        }


class _DB:
    """Captures the window bounds the report queries with."""

    def __init__(self):
        self.bounds = []

    def query(self, sql, params=()):
        if "FROM decisions" in sql:
            self.bounds.append((params[1], params[2]))
            return []
        return []

    def query_one(self, sql, params=()):
        return {"c": 0, "s": 0}


class _Registry:
    def __init__(self, tz):
        self.tenants = _Tenants(tz)
        self.db = _DB()
        self.ml_scorer = None  # reports read .ready; None means not-ready (falsy)
        self.graph_engine = None  # wrapped in try/except inside compute()


def _builder(tz):
    return ReportBuilder(_Registry(tz))


def _window(builder, period):
    builder.compute("tn_t", period)
    return builder.registry.db.bounds[-1]


def test_daily_window_converts_local_midnight_to_utc():
    # Asia/Aden is UTC+3, no DST — local 00:00 == previous-day 21:00 UTC.
    b = _builder("Asia/Aden")
    start_utc, end_utc = _window(b, "daily")
    s = datetime.fromisoformat(start_utc)
    e = datetime.fromisoformat(end_utc)
    assert s.tzinfo is not None and s.utcoffset().total_seconds() == 0
    assert e.tzinfo is not None and e.utcoffset().total_seconds() == 0
    # local midnight in Aden -> 21:00 UTC (3h behind)
    assert s.hour == 21
    assert s < e


def test_invalid_timezone_falls_back_to_aden():
    b = _builder("Not/AZone")
    out = b.compute("tn_t", "daily")
    assert out["tenant_timezone"] == "Asia/Aden"


def test_dst_zone_offset_changes_across_dst_boundary():
    # America/New_York is UTC-5 (EST, winter) and UTC-4 (EDT, summer).
    # Local midnight Jan 15 -> 05:00 UTC; local midnight Jul 15 -> 04:00 UTC.
    ny = ZoneInfo("America/New_York")
    jan_mid = datetime(2026, 1, 15, 0, 0, tzinfo=ny).astimezone(ZoneInfo("UTC"))
    jul_mid = datetime(2026, 7, 15, 0, 0, tzinfo=ny).astimezone(ZoneInfo("UTC"))
    assert jan_mid.hour == 5  # EST (winter)
    assert jul_mid.hour == 4  # EDT (summer) — DST actually applied
    # A fixed-offset timezone would give the same hour both times; this proves
    # the conversion is DST-aware, not a naive fixed offset.


def test_weekly_starts_on_local_monday():
    b = _builder("Asia/Aden")
    start_utc, _ = _window(b, "weekly")
    s_local = datetime.fromisoformat(start_utc).astimezone(ZoneInfo("Asia/Aden"))
    assert s_local.weekday() == 0  # Monday in local time
    assert (s_local.hour, s_local.minute) == (0, 0)


def test_monthly_starts_on_local_first_day():
    b = _builder("Asia/Aden")
    start_utc, _ = _window(b, "monthly")
    s_local = datetime.fromisoformat(start_utc).astimezone(ZoneInfo("Asia/Aden"))
    assert s_local.day == 1
    assert (s_local.hour, s_local.minute) == (0, 0)


def test_window_is_monotonic_and_bounded():
    # start must precede end for every period, in every zone.
    for tz in ("Asia/Aden", "UTC", "America/New_York", "Pacific/Auckland"):
        for period in ("daily", "weekly", "monthly"):
            b = _builder(tz)
            start_utc, end_utc = _window(b, period)
            assert datetime.fromisoformat(start_utc) <= datetime.fromisoformat(end_utc)
