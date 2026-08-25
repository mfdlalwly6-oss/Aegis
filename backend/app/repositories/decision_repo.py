from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db import Database
from app.security import generate_id


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class DecisionRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, assessment: dict, idempotency_key: str | None = None) -> dict:
        did = generate_id("dec")
        now = utcnow()
        self.db.execute(
            "INSERT INTO decisions "
            "(decision_id,tx_id,tenant_id,ts,decision,risk_score,risk_band,"
            "latency_ms,rule_score,ml_score,graph_score,aml_score,behavior_score,"
            "rules_json,ml_json,graph_json,aml_json,top_reasons_json,typology,"
            "reasoning_ar,ai_model,idempotency_key,created_at,"
            "fx_proof_json,tx_snapshot_json,features_snapshot_json,"
            "rule_set_version,model_version,config_version,request_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                did,
                assessment["tx_id"],
                assessment["tenant_id"],
                assessment.get("timestamp", now),
                assessment["decision"],
                assessment["risk_score"],
                assessment["risk_band"],
                assessment.get("latency_ms", 0),
                assessment.get("rule_score", 0),
                assessment.get("ml_score", 0),
                assessment.get("graph_score", 0),
                assessment.get("aml_score", 0),
                assessment.get("behavior_score", 0),
                json.dumps(assessment.get("rules", []), default=str),
                json.dumps(assessment.get("ml_models", assessment.get("ml", [])), default=str),
                json.dumps(assessment.get("graph_signal", assessment.get("graph", {})), default=str),
                json.dumps(assessment.get("aml_signal", assessment.get("aml", {})), default=str),
                json.dumps(assessment.get("top_reasons", []), ensure_ascii=False),
                assessment.get("typology"),
                assessment.get("reasoning_ar"),
                assessment.get("ai_model"),
                idempotency_key,
                now,
                json.dumps(assessment.get("fx_proof", {}), default=str),
                json.dumps(assessment.get("tx_snapshot", {}), default=str),
                json.dumps(assessment.get("features_snapshot", {}), default=str),
                assessment.get("policy_version"),
                assessment.get("model_id"),
                assessment.get("config_version") or "aegis-config@2.2.0",
                assessment.get("request_id"),
            ),
        )
        return {"decision_id": did, **assessment}

    def get_by_tx(self, tx_id: str) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM decisions WHERE tx_id=? ORDER BY created_at DESC LIMIT 1", (tx_id,)
        )

    def get_by_idempotency(self, key: str) -> dict | None:
        return self.db.query_one("SELECT * FROM decisions WHERE idempotency_key=?", (key,))

    def recent(self, limit: int = 50, tenant_id: str | None = None) -> list[dict]:
        if tenant_id:
            return self.db.query(
                "SELECT * FROM decisions WHERE tenant_id=? ORDER BY ts DESC LIMIT ?", (tenant_id, limit)
            )
        return self.db.query("SELECT * FROM decisions ORDER BY ts DESC LIMIT ?", (limit,))

    def count_by_tenant(self, tenant_id: str) -> dict:
        rows = self.db.query(
            "SELECT decision, COUNT(*) AS c, AVG(risk_score) AS avg_risk "
            "FROM decisions WHERE tenant_id=? GROUP BY decision",
            (tenant_id,),
        )
        by = {"allow": 0, "challenge": 0, "review": 0, "block": 0}
        total_risk, total = 0.0, 0
        for r in rows:
            by[r["decision"]] = r["c"]
            total += r["c"]
            total_risk += (r["avg_risk"] or 0) * r["c"]
        return {
            "tenant_id": tenant_id,
            "total_decisions": total,
            "by_decision": by,
            "avg_risk": round(total_risk / max(total, 1), 4),
        }

    def overview(self) -> dict:
        rows = self.db.query(
            "SELECT decision, COUNT(*) AS c, AVG(risk_score) AS avg_risk FROM decisions GROUP BY decision"
        )
        by = {"allow": 0, "challenge": 0, "review": 0, "block": 0}
        total_risk, total = 0.0, 0
        for r in rows:
            by[r["decision"]] = r["c"]
            total += r["c"]
            total_risk += (r["avg_risk"] or 0) * r["c"]
        return {"total": total, "by_decision": by, "avg_risk": round(total_risk / max(total, 1), 4)}

    def mark_seen(self, idempotency_key: str, tenant_id: str, tx_id: str) -> bool:
        """Returns True if this is a NEW key (not seen before)."""
        existing = self.db.query_one(
            "SELECT 1 FROM webhooks_seen WHERE idempotency_key=?", (idempotency_key,)
        )
        if existing:
            return False
        self.db.execute(
            "INSERT INTO webhooks_seen (idempotency_key,tenant_id,tx_id,first_seen) VALUES (?,?,?,?)",
            (idempotency_key, tenant_id, tx_id, utcnow()),
        )
        return True
