"""
AEGIS Rule Engine
─────────────────
Deterministic, hot-reloadable rule evaluator.

Rules are JSONLogic-inspired (see https://jsonlogic.com/) with AEGIS extensions:
- `velocity`, `distinct_count`, `geo_distance`, `time_since`
- WASM-sandboxed custom operators for tenant-specific rules

The engine returns every rule that fires plus its `score_contribution`, so the
final risk model can fuse rule signals with ML probability.
"""

from __future__ import annotations

import math
import operator
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import structlog

from app.models.schemas import RiskBand, RuleHit, Transaction

logger = structlog.get_logger(__name__)

# ─────────────────────────── Operator Registry ────────────────────────────
_OPS: dict[str, Callable[..., Any]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "and": lambda *a: all(a),
    "or": lambda *a: any(a),
    "not": lambda a: not a,
    "in": lambda a, b: a in b,
    "matches": lambda a, p: bool(re.search(p, str(a))),
    "sum": lambda *a: sum(a),
    "abs": abs,
    "min": min,
    "max": max,
}


def _resolve(path: str, ctx: dict[str, Any]) -> Any:
    """Dot-path resolution, e.g. 'tx.device.ip_country' → ctx['tx']['device']['ip_country']."""
    cur: Any = ctx
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
        if cur is None:
            return None
    return cur


def evaluate(expr: Any, ctx: dict[str, Any]) -> Any:
    """Recursively evaluate a JSONLogic-style expression."""
    if not isinstance(expr, dict):
        return expr
    if len(expr) != 1:
        raise ValueError(f"Malformed rule node: {expr}")
    op, args = next(iter(expr.items()))

    if op == "var":
        return _resolve(args, ctx)
    if op == "value":
        return args
    if op not in _OPS:
        raise ValueError(f"Unknown operator: {op}")

    if not isinstance(args, list):
        args = [args]
    evaluated = [evaluate(a, ctx) for a in args]
    # BUG4 fix: a rule referencing a field that is simply absent (None) means the
    # rule does not apply to this transaction — not a runtime error. Returning
    # False here keeps evaluation best-effort and stops rule.eval_error log noise.
    if op in (">", ">=", "<", "<=", "==", "!=") and any(v is None for v in evaluated):
        return False
    return _OPS[op](*evaluated)


# ─────────────────────────── Velocity primitives ───────────────────────────
class VelocityStore:
    """Redis-backed counter store; falls back to in-memory dict for tests."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._mem: dict[str, list[float]] = {}

    async def bump_and_count(self, key: str, window_sec: int) -> int:
        now = datetime.utcnow().timestamp()
        cutoff = now - window_sec
        if self.redis is not None:
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zadd(key, {str(now): now})
            pipe.zcount(key, cutoff, "+inf")
            pipe.expire(key, window_sec + 60)
            _, _, count, _ = await pipe.execute()
            return int(count)
        # in-memory fallback
        arr = [t for t in self._mem.setdefault(key, []) if t >= cutoff]
        arr.append(now)
        self._mem[key] = arr
        return len(arr)


# ─────────────────────────── Rule model ────────────────────────────────────
class Rule:
    def __init__(self, spec: dict[str, Any]):
        self.id: str = spec["id"]
        self.name: str = spec["name"]
        self.severity: RiskBand = RiskBand(spec.get("severity", "medium"))
        self.score: float = float(spec.get("score", 0.2))
        self.enabled: bool = spec.get("enabled", True)
        self.description: str = spec.get("description", "")
        self.when: dict[str, Any] = spec["when"]
        self.tags: list[str] = spec.get("tags", [])
        # None => platform rule (applies to every tenant). Otherwise this rule
        # is a tenant-specific override that only fires for that tenant.
        self.tenant_id: str | None = spec.get("tenant_id")
        # §5: currency of the financial thresholds in  (e.g. "USD").
        # Financial rules read features.amount_usd (already normalized by the FX
        # resolver via the same precedence chain), so a USD threshold evaluates
        # USD transactions directly and converts YER/SAR through the resolved rate.
        self.currency: str | None = spec.get("currency")

    def evaluate(self, ctx: dict[str, Any]) -> RuleHit | None:
        try:
            fired = bool(evaluate(self.when, ctx))
        except Exception as e:
            logger.warning("rule.eval_error", rule=self.id, error=str(e))
            return None
        if not fired:
            return None
        audit: dict[str, Any] = {}
        if self.currency:
            txd = ctx.get("tx") or {}
            fxs = txd.get("fx") or {}
            audit = {
                "original_amount": txd.get("amount"),
                "original_currency": txd.get("currency"),
                # evaluation happens in the rule currency; amount_usd is the
                # resolver-normalized value when rule currency == reference (USD).
                "evaluation_amount": (ctx.get("features") or {}).get("amount_usd"),
                "evaluation_currency": self.currency,
                "rule_currency": self.currency,
                "fx_source": fxs.get("source"),
                "fx_rate": fxs.get("rate"),
            }
        return RuleHit(
            rule_id=self.id,
            name=self.name,
            severity=self.severity,
            score_contribution=self.score,
            reason=self.description or self.name,
            **audit,
        )


class RuleEngine:
    """Evaluate all rules against a transaction; O(N) but rules are cheap."""

    def __init__(self, rules: list[dict[str, Any]] | None = None):
        self.rules: list[Rule] = [Rule(r) for r in (rules or [])]
        logger.info("rule_engine.loaded", count=len(self.rules))

    def reload(self, rules: list[dict[str, Any]]) -> None:
        self.rules = [Rule(r) for r in rules]
        logger.info("rule_engine.reload", count=len(self.rules))

    def evaluate(
        self,
        tx: Transaction,
        features: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> list[RuleHit]:
        """Evaluate platform rules + this tenant's overrides.

        A platform rule (tenant_id=None) applies to every tenant. A tenant rule
        only fires for its own tenant. Scoping is enforced here so a rule
        customized for Bank A can NEVER fire on Bank B's transaction.
        """
        tid = tenant_id or getattr(tx, "tenant_id", None)
        ctx = {"tx": tx.model_dump(mode="json"), "features": features or {}}
        # Effective set: a tenant's override REPLACES the platform rule with the
        # same id (no double evaluation); tenant-only rules apply only to their
        # tenant; rules belonging to other tenants never fire here.
        by_id: dict[str, Rule] = {}
        for r in self.rules:
            if r.tenant_id is None:
                by_id.setdefault(r.id, r)  # platform default — may be replaced below
            elif r.tenant_id == tid:
                by_id[r.id] = r  # tenant override wins
        hits: list[RuleHit] = []
        for r in by_id.values():
            if not r.enabled:
                continue
            hit = r.evaluate(ctx)
            if hit:
                hits.append(hit)
        return hits


# ─────────────────────────── Geo helpers ────────────────────────────────────
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def impossible_travel(
    prev_geo: dict[str, float],
    prev_time: datetime,
    cur_geo: dict[str, float],
    cur_time: datetime,
    max_speed_kmh: float = 900.0,  # commercial jet
) -> bool:
    delta_h = (cur_time - prev_time).total_seconds() / 3600.0
    if delta_h <= 0:
        return True
    dist = haversine_km(prev_geo["lat"], prev_geo["lon"], cur_geo["lat"], cur_geo["lon"])
    return (dist / delta_h) > max_speed_kmh
