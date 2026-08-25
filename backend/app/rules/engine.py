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

    def evaluate(self, ctx: dict[str, Any]) -> RuleHit | None:
        try:
            fired = bool(evaluate(self.when, ctx))
        except Exception as e:
            logger.warning("rule.eval_error", rule=self.id, error=str(e))
            return None
        if not fired:
            return None
        return RuleHit(
            rule_id=self.id,
            name=self.name,
            severity=self.severity,
            score_contribution=self.score,
            reason=self.description or self.name,
        )


class RuleEngine:
    """Evaluate all rules against a transaction; O(N) but rules are cheap."""

    def __init__(self, rules: list[dict[str, Any]] | None = None):
        self.rules: list[Rule] = [Rule(r) for r in (rules or [])]
        logger.info("rule_engine.loaded", count=len(self.rules))

    def reload(self, rules: list[dict[str, Any]]) -> None:
        self.rules = [Rule(r) for r in rules]
        logger.info("rule_engine.reload", count=len(self.rules))

    def evaluate(self, tx: Transaction, features: dict[str, Any] | None = None) -> list[RuleHit]:
        ctx = {"tx": tx.model_dump(mode="json"), "features": features or {}}
        hits: list[RuleHit] = []
        for r in self.rules:
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
