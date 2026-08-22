"""AEGIS Decision Orchestrator — unified fraud pipeline.
Transaction → Features → Rules → ML → Graph → AML → Behavior → Fuse → Decide → Persist → Alert → Audit
"""
from __future__ import annotations

import time
from typing import Any

import structlog

from app.core.config import settings
from app.models.schemas import (Decision, FxStatus, RiskAssessment, RiskBand,
                                Transaction)

logger = structlog.get_logger(__name__)


class DecisionOrchestrator:
    def __init__(
        self, *, rules, ml, graph, aml_service, features,
        transactions, decisions, alerts, cases, audit, events, notifications,
        fx_service=None, policy_engine=None, tenants_repo=None,
    ):
        self.fx_service = fx_service
        self.policy_engine = policy_engine
        self.tenants_repo = tenants_repo
        self.rules = rules
        self.ml = ml
        self.graph = graph
        self.aml_service = aml_service
        self.features = features
        self.transactions = transactions
        self.decisions = decisions
        self.alerts = alerts
        self.cases = cases
        self.audit = audit
        self.events = events
        self.notifications = notifications
        from app.services.policy_engine import POLICY_SCHEMA_VERSION
        self.policy_version = POLICY_SCHEMA_VERSION

    def _resolve_policy(self, tenant_id: str) -> dict:
        """Effective tenant policy (clamped, safe). Falls back to settings defaults."""
        if self.policy_engine is None:
            return None
        tenant = None
        if self.tenants_repo is not None:
            try:
                tenant = self.tenants_repo.get(tenant_id)
            except Exception:
                tenant = None
        return self.policy_engine.resolve(tenant)

    def _behavior_score(self, tx: Transaction) -> float:
        if not tx.behavior:
            return 0.0
        score = 0.0
        if tx.behavior.biometric_match_score is not None and tx.behavior.biometric_match_score < 0.4:
            score += 0.45
        if tx.behavior.keystroke_entropy is not None and tx.behavior.keystroke_entropy < 1.2:
            score += 0.20
        if tx.behavior.session_duration_ms is not None and tx.behavior.session_duration_ms > 600000:
            score += 0.15
        return min(score, 1.0)

    def _band(self, score: float, th: dict | None = None) -> RiskBand:
        th = th or {}
        if score >= th.get("block", settings.DECISION_THRESHOLD_BLOCK):
            return RiskBand.CRITICAL
        if score >= th.get("review", settings.DECISION_THRESHOLD_REVIEW):
            return RiskBand.HIGH
        if score >= th.get("challenge", settings.DECISION_THRESHOLD_CHALLENGE):
            return RiskBand.MEDIUM
        return RiskBand.LOW

    def _decide(self, score: float, aml_hit: bool, th: dict | None = None) -> Decision:
        th = th or {}
        if aml_hit:
            return Decision.BLOCK
        if score >= th.get("block", settings.DECISION_THRESHOLD_BLOCK):
            return Decision.BLOCK
        if score >= th.get("review", settings.DECISION_THRESHOLD_REVIEW):
            return Decision.REVIEW
        if score >= th.get("challenge", settings.DECISION_THRESHOLD_CHALLENGE):
            return Decision.CHALLENGE
        return Decision.ALLOW

    async def evaluate_and_persist(
        self, tx: Transaction, raw_payload: dict, actor: str,
        request_id: str | None = None, idempotency_key: str | None = None,
    ) -> dict:
        started = time.perf_counter()

        # 1. Idempotency — return cached decision if same key seen before
        if idempotency_key:
            if not self.decisions.mark_seen(idempotency_key, tx.tenant_id, tx.tx_id):
                cached = self.decisions.get_by_idempotency(idempotency_key)
                if cached:
                    return {**cached, "duplicate": True}

        # 1b. Money normalization — resolve FX + reference value BEFORE any risk logic.
        # The institution-reported rate is stored for comparison but never drives risk.
        if self.fx_service is not None and tx.money is None:
            inst_rate = None
            try:
                raw_ir = (tx.metadata or {}).get("institution_fx_rate")
                inst_rate = float(raw_ir) if raw_ir is not None else None
            except (TypeError, ValueError):
                inst_rate = None
            tx.money = self.fx_service.normalize(
                tx.amount, tx.currency, region=tx.region,
                institution_rate=inst_rate, at=tx.timestamp)

        # 2. Feature extraction (real queries against SQLite history)
        features = self.features.extract(tx)

        # 2b. Resolve effective tenant policy (safe-bounded) — drives fusion + decision.
        policy = self._resolve_policy(tx.tenant_id)

        # 3. Rule engine (real rules from DB/YAML), honoring policy-disabled rules
        # (protected core rules can never be disabled — enforced in PolicyEngine).
        rules_hits = self.rules.evaluate(tx, features)
        if policy and policy.get("disabled_rules"):
            disabled = set(policy["disabled_rules"])
            rules_hits = [h for h in rules_hits if h.rule_id not in disabled]
        rule_score = min(1.0, sum(h.score_contribution for h in rules_hits))

        # 4. ML scoring (real model if trained, graceful fallback)
        vector = self.features.vector(tx, features)
        ml_prob, ml_reports = self.ml.score(vector)

        # 5. Graph analysis (real NetworkX graph fed from DB)
        graph_sig = self.graph.score(tx)

        # 6. AML screening (real DB watchlists)
        aml_sig = await self.aml_service.screen(tx, features)

        # 7. Behavior score
        behavior_score = self._behavior_score(tx)

        # 8. Weighted fusion — policy weights (bounded) + risk sensitivity.
        w = (policy or {}).get("weights") or {}
        final = min(1.0, max(0.0,
            rule_score * w.get("rules", settings.WEIGHT_RULES) +
            ml_prob * w.get("ml", settings.WEIGHT_ML) +
            graph_sig.score * w.get("graph", settings.WEIGHT_GRAPH) +
            aml_sig.score * w.get("aml", settings.WEIGHT_AML) +
            behavior_score * w.get("behavior", settings.WEIGHT_BEHAVIOR)
        ))
        sensitivity = (policy or {}).get("risk_sensitivity", 1.0)
        if sensitivity != 1.0:
            final = min(1.0, max(0.0, final * sensitivity))

        th = (policy or {}).get("thresholds")

        # 9. Decision — sanctions hit forces BLOCK and reflects as critical score/band
        decision = self._decide(final, aml_sig.sanctions_hit, th)
        block_floor = (th or {}).get("block", settings.DECISION_THRESHOLD_BLOCK)
        if aml_sig.sanctions_hit and final < block_floor:
            final = block_floor  # reported risk floor for hard blocks

        # 9b. FX-status floor — a transaction that cannot be reliably valued must not
        # silently ALLOW; and a divergent institution rate must never lower risk.
        fx_status = tx.money.fx.status if (tx.money and tx.money.fx) else None
        if fx_status == FxStatus.MISSING and decision in (Decision.ALLOW, Decision.CHALLENGE):
            # Policy-controlled: default REVIEW, may be strengthened to BLOCK,
            # but NEVER weakened to a silent ALLOW.
            action = (policy or {}).get("fx_missing_action", "review")
            decision = Decision.BLOCK if action == "block" else Decision.REVIEW
            final = max(final, (th or {}).get("review", settings.DECISION_THRESHOLD_REVIEW))
        elif fx_status == FxStatus.DIVERGENT:
            final = min(1.0, final + 0.10)   # divergence raises risk, never lowers it
            if decision == Decision.ALLOW:
                decision = Decision.CHALLENGE
        latency_ms = (time.perf_counter() - started) * 1000

        # 10. Top reasons
        top_reasons = [h.reason for h in sorted(rules_hits, key=lambda r: -r.score_contribution)[:5]]
        if graph_sig.reason and graph_sig.reason != "no_graph_risk":
            top_reasons.append(graph_sig.reason)
        for flag in aml_sig.risk_flags[:3]:
            top_reasons.append(flag)
        if not top_reasons:
            top_reasons.append("لا مخاطر جوهرية مرصودة")

        # 11. AI explanation (optional, graceful fallback)
        ai_model = None
        reasoning_ar = " ؛ ".join(top_reasons[:4])
        if final >= settings.AI_MIN_SCORE and settings.AI_ENABLED:
            try:
                from app.agents.fraud_agent import FraudAgent
                agent = FraudAgent()
                ai_out = await agent.analyze(
                    tx.model_dump(mode="json"),
                    rules_hits,
                    ml_prob,
                )
                if ai_out.get("reasoning_ar"):
                    reasoning_ar = ai_out["reasoning_ar"]
                ai_model = ai_out.get("model")
            except Exception as e:
                logger.warning("ai.explanation_failed", error=str(e))

        # 12. Build assessment
        assessment = RiskAssessment(
            tx_id=tx.tx_id, tenant_id=tx.tenant_id, timestamp=tx.timestamp,
            decision=decision, risk_score=round(final, 4),
            risk_band=self._band(final), latency_ms=round(latency_ms, 2),
            rule_score=round(rule_score, 4), ml_score=round(ml_prob, 4),
            graph_score=round(graph_sig.score, 4), aml_score=round(aml_sig.score, 4),
            behavior_score=round(behavior_score, 4),
            rules=rules_hits, ml_models=ml_reports,
            graph_signal=graph_sig, aml_signal=aml_sig,
            top_reasons=top_reasons, reasoning_ar=reasoning_ar,
            ai_model=ai_model,
            typology=aml_sig.typology_matches[0] if aml_sig.typology_matches else
                     ("high_risk" if final >= settings.DECISION_THRESHOLD_REVIEW else "normal"),
            model_id="aegis-ensemble@2.0.0", policy_version=self.policy_version,
        )

        # 13. Persist transaction (with reference money + FX + event) + decision snapshot
        money = tx.money
        tx_row = {
            "tx_id": tx.tx_id, "tenant_id": tx.tenant_id,
            "timestamp": tx.timestamp.isoformat(), "channel": tx.channel.value,
            "amount": tx.amount, "currency": tx.currency,
            "sender_account_id": tx.sender_account_id,
            "sender_user_id": tx.sender_user_id,
            "beneficiary_account_id": tx.beneficiary_account_id,
            "beneficiary_user_id": tx.beneficiary_user_id,
            "beneficiary_country": tx.beneficiary_country,
            "merchant_id": tx.merchant_id, "merchant_name": tx.merchant_name,
            "device_id": tx.device.device_id if tx.device else None,
            "ip": str(tx.device.ip) if tx.device and tx.device.ip else None,
            "ip_country": tx.device.ip_country if tx.device else None,
            # reference money + FX proof + financial-event semantics
            "reference_amount": (money.reference_amount if money else None),
            "reference_currency": (money.reference_currency if money else None),
            "fx_snapshot_id": (money.fx.snapshot_id if money and money.fx else None),
            "fx_status": (money.fx.status.value if money and money.fx else None),
            "region": tx.region,
            "event_type": (tx.event_type.value if tx.event_type else "transfer"),
            "direction": tx.direction,
            "is_internal": 1 if tx.is_internal else 0,
            "linked_tx_id": tx.linked_tx_id,
        }
        self.transactions.create(tx_row, features, raw_payload)
        # Immutable audit snapshot: what the engine saw at decision time.
        dec_payload = assessment.model_dump(mode="json")
        dec_payload["tx_snapshot"] = tx.model_dump(mode="json")
        dec_payload["features_snapshot"] = features
        dec_payload["fx_proof"] = (money.fx.model_dump(mode="json") if money and money.fx else None)
        self.decisions.create(dec_payload, idempotency_key=idempotency_key)

        # 14. Feed graph for future scoring
        self.graph.add_transaction(tx)

        # 15. Create alert + case for elevated decisions
        created_alert = None
        created_case = None
        if decision in (Decision.CHALLENGE, Decision.REVIEW, Decision.BLOCK):
            severity = "critical" if decision == Decision.BLOCK else \
                       "high" if decision == Decision.REVIEW else "medium"
            created_alert = self.alerts.create(
                tx.tenant_id, tx.tx_id, severity,
                f"{decision.value.upper()} — risk={final:.2f}",
                reasoning_ar)
            if decision in (Decision.REVIEW, Decision.BLOCK):
                created_case = self.cases.create(
                    tx.tenant_id, f"Case: {tx.tx_id[:16]}",
                    priority=severity, narrative=reasoning_ar,
                    tx_ids=[tx.tx_id], alert_ids=[created_alert["alert_id"]])

        # 16. Audit
        self.audit.log(tx.tenant_id, actor, "transaction.scored",
                       "transaction", tx.tx_id, request_id,
                       {"decision": decision.value, "risk_score": final})
        if created_alert:
            self.audit.log(tx.tenant_id, actor, "alert.created",
                           "alert", created_alert["alert_id"], request_id,
                           {"tx_id": tx.tx_id, "severity": severity})

        # 17. Notify + publish event
        if created_alert:
            await self.notifications.send("alert.created", created_alert)
        await self.events.publish("decision.created", assessment.model_dump(mode="json"))

        result = assessment.model_dump(mode="json")
        # Surface money/FX context to the caller for transparency (reference value,
        # not a re-statement of the financial truth which stays original).
        if tx.money:
            result["money"] = {
                "original_amount": tx.money.original_amount,
                "original_currency": tx.money.original_currency,
                "reference_amount": tx.money.reference_amount,
                "reference_currency": tx.money.reference_currency,
                "fx_status": (tx.money.fx.status.value if tx.money.fx else None),
            }
        result["alert"] = created_alert
        result["case"] = created_case
        return result
