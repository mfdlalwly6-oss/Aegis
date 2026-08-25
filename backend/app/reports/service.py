"""AEGIS Report Builder — real metrics, tenant timezone aware, UTC storage.
Periods: daily (since local 00:00), weekly (since local Monday 00:00),
monthly (since local 1st 00:00). All DB timestamps are stored UTC (ISO);
window boundaries are converted to UTC before querying.
Hijri display date is computed arithmetically (tabular) for presentation only.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

PERIODS = ("daily", "weekly", "monthly")
PERIOD_LABELS = {"daily": "يومي", "weekly": "أسبوعي", "monthly": "شهري"}


def _gregorian_to_hijri(y: int, m: int, d: int) -> tuple[int, int, int]:
    """Arithmetic (tabular) Islamic calendar conversion — display only."""
    jd = (
        (1461 * (y + 4800 + (m - 14) // 12)) // 4
        + (367 * (m - 2 - 12 * ((m - 14) // 12))) // 12
        - (3 * ((y + 4900 + (m - 14) // 12) // 100)) // 4
        + d
        - 32075
    )
    l = jd - 1948440 + 10632
    n = (l - 1) // 10631
    l2 = l - 10631 * n + 354
    j = ((10985 - l2) // 5316) * ((50 * l2) // 17719) + (l2 // 5670) * ((43 * l2) // 15238)
    l3 = l2 - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    mm = (24 * l3) // 709
    dd = l3 - (709 * mm) // 24
    yy = 30 * n + j - 30
    return dd, mm, yy


class ReportBuilder:
    def __init__(self, registry):
        self.registry = registry

    def compute(self, tenant_id: str, period: str, timezone_name: str | None = None) -> dict:
        if period not in PERIODS:
            raise ValueError(f"invalid_period:{period}")
        tenant = self.registry.tenants.get(tenant_id, reveal=True)
        if not tenant:
            raise ValueError("tenant_not_found")
        tz_name = timezone_name or tenant.get("timezone") or "Asia/Aden"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Asia/Aden")
            tz_name = "Asia/Aden"

        now_local = datetime.now(tz)
        today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "daily":
            start_local = today
        elif period == "weekly":
            start_local = today - timedelta(days=today.weekday())
        else:
            start_local = today.replace(day=1)

        start_utc = start_local.astimezone(UTC)
        end_utc = now_local.astimezone(UTC)

        db = self.registry.db
        dec_rows = db.query(
            "SELECT * FROM decisions WHERE tenant_id=? AND ts>=? AND ts<=? ORDER BY ts DESC",
            (tenant_id, start_utc.isoformat(), end_utc.isoformat()),
        )
        tx_count = db.query_one(
            "SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS s FROM transactions "
            "WHERE tenant_id=? AND ts>=? AND ts<=?",
            (tenant_id, start_utc.isoformat(), end_utc.isoformat()),
        )

        decision_counts = Counter(r["decision"] for r in dec_rows)
        bands = Counter(r["risk_band"] for r in dec_rows)
        scores = [r["risk_score"] for r in dec_rows] or [0.0]
        reasons = Counter()
        for r in dec_rows:
            try:
                for item in json.loads(r["top_reasons_json"] or "[]"):
                    key = item if isinstance(item, str) else item.get("reason", str(item))
                    reasons[key] += 1
            except Exception:
                continue

        alerts = db.query(
            "SELECT * FROM alerts WHERE tenant_id=? AND created_at>=? AND created_at<=?",
            (tenant_id, start_utc.isoformat(), end_utc.isoformat()),
        )
        cases = db.query(
            "SELECT * FROM cases WHERE tenant_id=? AND created_at>=? AND created_at<=?",
            (tenant_id, start_utc.isoformat(), end_utc.isoformat()),
        )
        manual = [a for a in alerts if a["status"].startswith("resolved_")]
        durations = []
        sla_breach = 0
        for a in manual:
            try:
                dur = (
                    datetime.fromisoformat(a["updated_at"]) - datetime.fromisoformat(a["created_at"])
                ).total_seconds() / 60
                durations.append(dur)
                if dur > 1440:
                    sla_breach += 1
            except Exception:
                continue

        inv_activity = Counter()
        for a in alerts:
            if a.get("assignee"):
                inv_activity[a["assignee"]] += 1

        rules_count = db.query_one("SELECT COUNT(*) AS c FROM rules")["c"]
        ml_ready = bool(self.registry.ml_scorer and self.registry.ml_scorer.ready)
        graph_nodes, graph_edges = 0, 0
        try:
            graph_nodes = self.registry.graph_engine.node_count()
            graph_edges = self.registry.graph_engine.edge_count()
        except Exception:
            pass

        now_local_str = now_local.strftime("%Y-%m-%d %H:%M")
        hy, hm, hd = _gregorian_to_hijri(now_local.year, now_local.month, now_local.day)

        summary_parts = []
        total = len(dec_rows)
        review = decision_counts.get("review", 0)
        block = decision_counts.get("block", 0)
        allow = decision_counts.get("allow", 0)
        summary_parts.append(f"خلال فترة التقرير ({PERIOD_LABELS[period]}) تم تقييم {total} عملية.")
        if total:
            summary_parts.append(
                f"تمت الموافقة على {allow} عملية تلقائيًا ({round(100 * allow / total)}%)، "
                f"وحظر {block} عملية ({round(100 * block / total)}%)، "
                f"وإحالة {review} عملية للمراجعة ({round(100 * review / total)}%)."
            )
        if manual:
            avg = round(sum(durations) / len(durations), 1)
            summary_parts.append(f"تمت معالجة {len(manual)} حالة يدويًا بمتوسط {avg} دقيقة للمراجعة.")
        else:
            summary_parts.append("لم توجد حالات معالجة يدويًا خلال الفترة.")
        if alerts:
            summary_parts.append(f"تم توليد {len(alerts)} تنبيهًا خلال الفترة.")

        mode = "التعلم الآلي جاهز" if ml_ready else "وضع احتياطي (قواعد + خوارزميات)"
        summary_parts.append(f"حالة النظام: {mode}.")

        return {
            "tenant_id": tenant_id,
            "tenant_name": tenant["name"],
            "tenant_type": tenant["type"],
            "tenant_country": tenant["country"],
            "tenant_plan": tenant["plan"],
            "tenant_status": tenant["status"],
            "tenant_timezone": tz_name,
            "period": period,
            "period_label": PERIOD_LABELS[period],
            "start_local": start_local.strftime("%Y-%m-%d %H:%M"),
            "end_local": now_local_str,
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "generated_at_local": now_local_str,
            "gregorian_date": now_local.strftime("%Y-%m-%d"),
            "hijri_date": f"{hd:02d}/{hm:02d}/{hy} هـ",
            "executive_summary": " ".join(summary_parts),
            "volume": {
                "transactions": tx_count["c"] if tx_count else 0,
                "amount_sum": round(tx_count["s"] or 0, 2) if tx_count else 0,
                "decisions": total,
                "allow": allow,
                "block": block,
                "review": review,
                "allow_pct": round(100 * allow / total, 1) if total else 0,
                "block_pct": round(100 * block / total, 1) if total else 0,
                "review_pct": round(100 * review / total, 1) if total else 0,
            },
            "risk": {
                "avg_score": round(sum(scores) / len(scores), 3),
                "bands": dict(bands),
            },
            "top_reasons": [{"reason": k, "count": v} for k, v in reasons.most_common(8)],
            "alerts": {
                "total": len(alerts),
                "by_status": {
                    s: sum(1 for a in alerts if a["status"] == s)
                    for s in (
                        "open",
                        "assigned",
                        "in_review",
                        "escalated",
                        "resolved_true_positive",
                        "resolved_false_positive",
                    )
                },
            },
            "cases": {
                "total": len(cases),
                "by_status": {
                    s: sum(1 for c in cases if c["status"] == s)
                    for s in ("open", "in_progress", "escalated", "closed")
                },
            },
            "manual_reviews": {
                "total": len(manual),
                "avg_duration_min": round(sum(durations) / len(durations), 1) if durations else 0,
                "sla_breach_over_24h": sla_breach,
            },
            "investigator_activity": [{"actor": k, "actions": v} for k, v in inv_activity.most_common(10)],
            "system": {
                "rules_loaded": rules_count,
                "ml_ready": ml_ready,
                "graph_nodes": graph_nodes,
                "graph_edges": graph_edges,
                "db_ok": True,
                "integration_status": tenant["status"],
                "aegis_version": getattr(self.registry, "version", "2.2.0"),
            },
        }
