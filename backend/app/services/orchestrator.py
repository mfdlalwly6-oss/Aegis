"""AEGIS Decision Orchestrator — unified fraud pipeline.
Transaction → Features → Rules → ML → Graph → AML → Behavior → Fuse → Decide → Persist → Alert → Audit
"""
from __future__ import annotations

import time
from typing import Any

import structlog

from app.core.config import settings
from app.models.schemas import Decision, RiskAssessment, RiskBand, Transaction

logger = structlog.get_logger(__name__)


class DecisionOrchestrator:
    def __init__(
        self, *, rules, ml, graph, aml_service, features,
        transactions, decisions, alerts, cases, audit, events, notifications,
    ):
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
        self.policy_version = "policy@2.0.0"

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

    def _band(self, score: float) -> RiskBand:
        if score >= settings.DECISION_THRESHOLD_BLOCK:
            return RiskBand.CRITICAL
        if score >= settings.DECISION_THRESHOLD_REVIEW:
            return RiskBand.HIGH
        if score >= settings.DECISION_THRESHOLD_CHALLENGE:
            return RiskBand.MEDIUM
        return RiskBand.LOW

    def _decide(self, score: float, aml_hit: bool) -> Decision:
        if aml_hit:
            return Decision.BLOCK
        if score >= settings.DECISION_THRESHOLD_BLOCK:
            return Decision.BLOCK
        if score >= settings.DECISION_THRESHOLD_REVIEW:
            return Decision.REVIEW
        if score >= settings.DECISION_THRESHOLD_CHALLENGE:
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

        # 2. Feature extraction (real queries against SQLite history)
        features = self.features.extract(tx)

        # 3. Rule engine (real rules from DB/YAML)
        rules_hits = self.rules.evaluate(tx, features)
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

        # 8. Weighted fusion
        final = min(1.0, max(0.0,
            rule_score * settings.WEIGHT_RULES +
            ml_prob * settings.WEIGHT_ML +
            graph_sig.score * settings.WEIGHT_GRAPH +
            aml_sig.score * settings.WEIGHT_AML +
            behavior_score * settings.WEIGHT_BEHAVIOR
        ))

        # 9. Decision — sanctions hit forces BLOCK; FX missing forces review
        fx_missing = getattr(tx, "fx_status", None) == "missing"
        if fx_missing:
            _pol = self._resolve_policy(tx.tenant_id) if hasattr(self, "_resolve_policy") else {}
            fx_missing_action = _pol.get("fx_missing_action", settings.FX_MISSING_DECISION)
            if fx_missing_action == "block":
                decision = Decision.BLOCK
                final = max(final, settings.DECISION_THRESHOLD_BLOCK)
            else:
                decision = Decision.REVIEW
                final = max(final, settings.DECISION_THRESHOLD_REVIEW)
        else:
            decision = self._decide(final, aml_sig.sanctions_hit)
        if aml_sig.sanctions_hit and final < settings.DECISION_THRESHOLD_BLOCK:
            final = settings.DECISION_THRESHOLD_BLOCK  # reported risk floor for hard blocks
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

        # 12. Build assessment (with FX proof for audit)
        fx_proof = {
            "original_amount": tx.amount,
            "original_currency": tx.currency,
            "reference_amount": getattr(tx, "reference_amount", None),
            "reference_currency": getattr(tx, "reference_currency", None),
            "fx_snapshot_id": getattr(tx, "fx_snapshot_id", None),
            "fx_status": getattr(tx, "fx_status", None),
        }
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
            fx_proof=fx_proof,
            tx_snapshot=tx.model_dump(mode="json"),
            features_snapshot=features if isinstance(features, dict) else {},
        )

        # 13. Persist transaction + decision
        tx_row = {
            "tx_id": tx.tx_id, "tenant_id": tx.tenant_id,
            "timestamp": tx.timestamp.isoformat(), "channel": tx.channel.value,
            "amount": tx.amount, "currency": tx.currency,
            "reference_amount": getattr(tx, "reference_amount", None),
            "reference_currency": getattr(tx, "reference_currency", None),
            "fx_snapshot_id": getattr(tx, "fx_snapshot_id", None),
            "fx_status": getattr(tx, "fx_status", None),
            "sender_account_id": tx.sender_account_id,
            "sender_user_id": tx.sender_user_id,
            "beneficiary_account_id": tx.beneficiary_account_id,
            "beneficiary_user_id": tx.beneficiary_user_id,
            "beneficiary_country": tx.beneficiary_country,
            "merchant_id": tx.merchant_id, "merchant_name": tx.merchant_name,
            "device_id": tx.device.device_id if tx.device else None,
            "ip": str(tx.device.ip) if tx.device and tx.device.ip else None,
            "ip_country": tx.device.ip_country if tx.device else None,
        }
        self.transactions.create(tx_row, features, raw_payload)
        self.decisions.create(assessment.model_dump(mode="json"), idempotency_key=idempotency_key)

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
        result["alert"] = created_alert
        result["case"] = created_case
        return result
