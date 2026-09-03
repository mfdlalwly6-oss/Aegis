"""AEGIS Decision Orchestrator — unified fraud pipeline.
Transaction → Features → Rules → ML → Graph → AML → Behavior → Fuse → Decide → Persist → Alert → Audit
"""

from __future__ import annotations

import time

import structlog

from app.core.config import settings
from app.models.schemas import AMLSignal, Decision, GraphSignal, RiskAssessment, RiskBand, Transaction
from app.services.policy_engine import PolicyEngine

logger = structlog.get_logger(__name__)


class DecisionOrchestrator:
    def __init__(
        self,
        *,
        rules,
        ml,
        graph,
        aml_service,
        features,
        transactions,
        decisions,
        alerts,
        cases,
        audit,
        events,
        notifications,
        tenants=None,
        policy_repo=None,
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
        self.tenants = tenants
        self.policy_repo = policy_repo
        # Single source of truth for policy resolution (bounds, profiles,
        # protected rules). The old inline _resolve_policy duplicate is gone.
        self.policy_engine = PolicyEngine()

    def _resolve_policy(self, tenant_id: str) -> dict:
        """Resolve the effective policy via PolicyEngine (the single resolver).

        Pulls the full tenant row (type + policy) when the repository supports
        it, falling back to policy-only for lightweight/test doubles. All safety
        guarantees (clamped thresholds, bounded weights, protected rules,
        FX-never-silent-allow) are enforced inside PolicyEngine.resolve.
        """
        tenant: dict | None = None
        if self.tenants is not None:
            getter = getattr(self.tenants, "get", None)
            if callable(getter):
                try:
                    tenant = getter(tenant_id)
                except Exception:  # noqa: BLE001 — never let policy lookup kill a decision
                    tenant = None
            if tenant is None and hasattr(self.tenants, "get_policy"):
                tenant = {"policy": self.tenants.get_policy(tenant_id)}
        return self.policy_engine.resolve(tenant)

    def _policy_version(self, tenant_id: str) -> str:
        """Version stamp stored on every decision: schema version plus the
        tenant's active immutable policy version + content hash, so any past
        decision traces to the exact policy row that governed it."""
        base = self.policy_engine.version()
        if not self.policy_repo or not tenant_id:
            return base
        try:
            active = self.policy_repo.active(tenant_id)
            if active:
                return f"{base}#v{active['version']}:{active['policy_hash']}"
        except Exception:  # noqa: BLE001 — versioning must never block a decision
            pass
        return base

    def _behavior_score(self, tx: Transaction) -> float:
        if not tx.behavior:
            return 0.0
        score = 0.0
        if (
            tx.behavior.biometric_match_score is not None
            and tx.behavior.biometric_match_score < 0.4
        ):
            score += 0.45
        if tx.behavior.keystroke_entropy is not None and tx.behavior.keystroke_entropy < 1.2:
            score += 0.20
        if tx.behavior.session_duration_ms is not None and tx.behavior.session_duration_ms > 600000:
            score += 0.15
        return min(score, 1.0)

    def _band(self, score: float, policy: dict | None = None) -> RiskBand:
        thresholds = (policy or self._resolve_policy(""))["thresholds"]
        if score >= thresholds["block"]:
            return RiskBand.CRITICAL
        if score >= thresholds["review"]:
            return RiskBand.HIGH
        if score >= thresholds["challenge"]:
            return RiskBand.MEDIUM
        return RiskBand.LOW

    def _decide(self, score: float, aml_hit: bool, policy: dict | None = None) -> Decision:
        thresholds = (policy or self._resolve_policy(""))["thresholds"]
        if aml_hit:
            return Decision.BLOCK
        if score >= thresholds["block"]:
            return Decision.BLOCK
        if score >= thresholds["review"]:
            return Decision.REVIEW
        if score >= thresholds["challenge"]:
            return Decision.CHALLENGE
        return Decision.ALLOW

    async def evaluate_and_persist(
        self,
        tx: Transaction,
        raw_payload: dict,
        actor: str,
        request_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        started = time.perf_counter()

        # 1. Idempotency — return cached decision if same key seen before
        if idempotency_key:
            if not self.decisions.mark_seen(idempotency_key, tx.tenant_id, tx.tx_id):
                cached = self.decisions.get_by_idempotency(idempotency_key)
                if cached:
                    return {**cached, "duplicate": True}
            # Same tx resubmitted under a DIFFERENT key must still replay the
            # stored decision — retries (new key, same tx) are semantically the
            # same operation; re-scoring would violate idempotency.
            # Tenant-scoped: tx_id collisions across tenants must never leak a
            # cached decision to another tenant.
            prior_tx = self.decisions.get_by_tx(tx.tx_id)
            if prior_tx and prior_tx.get("tenant_id") == tx.tenant_id:
                return {**prior_tx, "duplicate": True}

        # 2. Feature extraction (real queries against PostgreSQL history)
        features = self.features.extract(tx)

        # Component health tracker: every engine reports its state and the
        # decision records it verbatim. An unavailable component NEVER silently
        # contributes 0 — its weight is redistributed over the healthy ones and
        # the decision is marked degraded so it can be rebuilt/audited later.
        health: dict[str, dict] = {}

        # 3. Rule engine (real rules from DB/YAML)
        try:
            rules_hits = self.rules.evaluate(tx, features, tenant_id=tx.tenant_id)
            rule_score = min(1.0, sum(h.score_contribution for h in rules_hits))
            health["rules"] = {"status": "healthy", "hits": len(rules_hits)}
        except Exception as e:
            logger.error("component.rules_unavailable", error=str(e), tenant_id=tx.tenant_id)
            rules_hits = []
            rule_score = 0.0
            health["rules"] = {"status": "unavailable", "error": type(e).__name__}

        # 4. ML scoring — distinguish trained model from labeled heuristic fallback
        try:
            vector = self.features.vector(tx, features)
            ml_prob, ml_reports = self.ml.score(vector)
            if getattr(self.ml, "ready", False):
                health["ml"] = {"status": "healthy", "models": len(ml_reports)}
            else:
                health["ml"] = {"status": "unavailable", "detail": "no trained model; heuristic fallback not scored"}
                ml_prob = None  # heuristic is explainable but NOT evidence — do not score it
        except Exception as e:
            logger.error("component.ml_unavailable", error=str(e), tenant_id=tx.tenant_id)
            ml_prob, ml_reports = None, []
            health["ml"] = {"status": "unavailable", "error": type(e).__name__}

        # 5. Graph analysis (real NetworkX graph fed from DB)
        try:
            graph_sig = self.graph.score(tx)
            health["graph"] = {"status": "healthy"}
        except Exception as e:
            logger.error("component.graph_unavailable", error=str(e), tenant_id=tx.tenant_id)
            graph_sig = GraphSignal()
            health["graph"] = {"status": "unavailable", "error": type(e).__name__}

        # 6. AML screening (real DB watchlists) — CRITICAL: unavailable AML must
        # never fail open (sanctions obligation). Fail-closed handled below.
        aml_unavailable = False
        try:
            aml_sig = await self.aml_service.screen(tx, features)
            health["aml"] = {"status": "healthy", "evidence": len(aml_sig.watchlist_evidence)}
        except Exception as e:
            logger.error("component.aml_unavailable", error=str(e), tenant_id=tx.tenant_id)
            aml_sig = AMLSignal()
            aml_unavailable = True
            health["aml"] = {"status": "unavailable", "error": type(e).__name__}

        # 7. Behavior score — absent behavior payload is degraded, not failed
        try:
            behavior_score = self._behavior_score(tx)
            health["behavior"] = {"status": "healthy" if tx.behavior else "degraded"}
        except Exception as e:
            logger.error("component.behavior_unavailable", error=str(e), tenant_id=tx.tenant_id)
            behavior_score = 0.0
            health["behavior"] = {"status": "unavailable", "error": type(e).__name__}

        # 8. Availability-aware weighted fusion: weights renormalize over the
        # components that actually scored, so a dead engine never drags the
        # score to 0 or silently inflates the others.
        policy = self._resolve_policy(tx.tenant_id)
        weights = policy["weights"]
        comp_scores: dict[str, float | None] = {
            "rules": rule_score if health["rules"]["status"] == "healthy" else None,
            "ml": ml_prob if health["ml"]["status"] == "healthy" else None,
            "graph": graph_sig.score if health["graph"]["status"] == "healthy" else None,
            "aml": aml_sig.score if health["aml"]["status"] == "healthy" else None,
            "behavior": behavior_score if health["behavior"]["status"] == "healthy" else None,
        }
        active = {k: v for k, v in comp_scores.items() if v is not None}
        active_weight = sum(weights[k] for k in active)
        applied_weights = (
            {k: weights[k] / active_weight for k in active} if active_weight > 0 else {}
        )
        for k in health:
            health[k]["weight_applied"] = round(applied_weights.get(k, 0.0), 6)
        final = min(1.0, max(0.0, sum(comp_scores[k] * applied_weights[k] for k in applied_weights)))

        degraded_mode = any(h["status"] != "healthy" for h in health.values())
        degraded_reason = (
            "; ".join(f"{k}={h['status']}" for k, h in health.items() if h["status"] != "healthy")
            if degraded_mode
            else None
        )

        # Confidence: explicit, interpretable, non-retroactive. Computed from the
        # NOMINAL policy weights (before availability renormalization) weighted by
        # each component's state at decision time: healthy=1.0, degraded=0.5,
        # unavailable=0.0. A failed/degraded engine therefore shrinks confidence
        # by exactly its nominal share — a degraded decision can never look more
        # confident than the evidence that produced it. Fully reconstructible
        # from the persisted component_health + policy weights.
        confidence = round(
            min(
                1.0,
                max(
                    0.0,
                    sum(
                        {"healthy": 1.0, "degraded": 0.5}.get(h["status"], 0.0)
                        * weights.get(k, 0.0)
                        for k, h in health.items()
                    ),
                ),
            ),
            4,
        )

        # 9. Decision — sanctions hit forces BLOCK; FX missing forces review;
        # AML unavailable fails CLOSED (sanctions obligation: never silently
        # allow when we could not screen); heavy component loss forces REVIEW.
        #
        # Fail-safe floors (component degradation must never downgrade a
        # hard-signalled transaction to ALLOW):
        #   * watchlisted account (non-sanctions list) -> REVIEW floor
        #   * any HIGH-severity rule hit                -> CHALLENGE floor
        if getattr(aml_sig, "watchlist_account_hit", False) and not aml_sig.sanctions_hit:
            final = max(final, policy["thresholds"]["review"])
        high_rule_hit = any(
            getattr(h, "severity", "") == "high" for h in rules_hits
        )
        if high_rule_hit and health.get("behavior", {}).get("status") != "healthy":
            final = max(final, policy["thresholds"]["challenge"])
        if aml_unavailable:
            decision = Decision.REVIEW
            final = max(final, policy["thresholds"]["review"])
            if degraded_reason:
                degraded_reason = "AML_UNAVAILABLE_FAIL_CLOSED; " + degraded_reason
            else:
                degraded_reason = "AML_UNAVAILABLE_FAIL_CLOSED"
        fx_missing = getattr(tx, "fx_status", None) == "missing"
        if fx_missing:
            fx_missing_action = policy["fx_missing_action"]
            if fx_missing_action == "block":
                decision = Decision.BLOCK
                final = max(final, policy["thresholds"]["block"])
            else:
                decision = Decision.REVIEW
                final = max(final, policy["thresholds"]["review"])
        else:
            decision = self._decide(final, aml_sig.sanctions_hit, policy)
        if aml_sig.sanctions_hit and final < policy["thresholds"]["block"]:
            final = policy["thresholds"]["block"]  # reported risk floor for hard blocks
        latency_ms = (time.perf_counter() - started) * 1000

        # 10. Top reasons
        top_reasons = [
            h.reason for h in sorted(rules_hits, key=lambda r: -r.score_contribution)[:5]
        ]
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
        _fxs = getattr(tx, "fx", None)
        fx_proof = {
            "original_amount": tx.amount,
            "original_currency": tx.currency,
            "reference_amount": getattr(tx, "reference_amount", None),
            "reference_currency": getattr(tx, "reference_currency", None),
            "fx_snapshot_id": getattr(tx, "fx_snapshot_id", None),
            "fx_status": getattr(tx, "fx_status", None),
            # Full audit trail of the rate actually used at decision time.
            "rate": getattr(_fxs, "rate", None),
            "rate_type": getattr(_fxs, "rate_type", None),
            "source": getattr(_fxs, "source", None),
            "region": getattr(_fxs, "region", None),
            "institution_rate": getattr(_fxs, "institution_rate", None),
            "divergence_pct": getattr(_fxs, "divergence_pct", None),
            "is_stale": getattr(_fxs, "is_stale", None),
            "valid_from": (str(getattr(_fxs, "valid_from")) if getattr(_fxs, "valid_from", None) else None),
        }
        assessment = RiskAssessment(
            tx_id=tx.tx_id,
            tenant_id=tx.tenant_id,
            timestamp=tx.timestamp,
            decision=decision,
            risk_score=round(final, 4),
            risk_band=self._band(final, policy),
            latency_ms=round(latency_ms, 2),
            rule_score=round(rule_score, 4),
            ml_score=round(ml_prob, 4) if ml_prob is not None else 0.0,
            graph_score=round(graph_sig.score, 4),
            aml_score=round(aml_sig.score, 4),
            behavior_score=round(behavior_score, 4),
            rules=rules_hits,
            ml_models=ml_reports,
            graph_signal=graph_sig,
            aml_signal=aml_sig,
            top_reasons=top_reasons,
            reasoning_ar=reasoning_ar,
            ai_model=ai_model,
            typology=aml_sig.typology_matches[0]
            if aml_sig.typology_matches
            else ("high_risk" if final >= settings.DECISION_THRESHOLD_REVIEW else "normal"),
            model_id="aegis-ensemble@2.0.0",
            policy_version=self._policy_version(tx.tenant_id),
            fx_proof=fx_proof,
            tx_snapshot=tx.model_dump(mode="json"),
            features_snapshot=features if isinstance(features, dict) else {},
            request_id=request_id,
            component_health=health,
            degraded_mode=degraded_mode,
            degraded_reason=degraded_reason,
            confidence=confidence,
        )

        # 13. Persist transaction + decision
        tx_row = {
            "tx_id": tx.tx_id,
            "tenant_id": tx.tenant_id,
            "timestamp": tx.timestamp.isoformat(),
            "channel": tx.channel.value,
            "amount": tx.amount,
            "currency": tx.currency,
            "reference_amount": getattr(tx, "reference_amount", None),
            "reference_currency": getattr(tx, "reference_currency", None),
            "fx_snapshot_id": getattr(tx, "fx_snapshot_id", None),
            "fx_status": getattr(tx, "fx_status", None),
            "sender_account_id": tx.sender_account_id,
            "sender_user_id": tx.sender_user_id,
            "beneficiary_account_id": tx.beneficiary_account_id,
            "beneficiary_user_id": tx.beneficiary_user_id,
            "beneficiary_country": tx.beneficiary_country,
            "merchant_id": tx.merchant_id,
            "merchant_name": tx.merchant_name,
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
            severity = (
                "critical"
                if decision == Decision.BLOCK
                else "high"
                if decision == Decision.REVIEW
                else "medium"
            )
            created_alert = self.alerts.create(
                tx.tenant_id,
                tx.tx_id,
                severity,
                f"{decision.value.upper()} — risk={final:.2f}",
                reasoning_ar,
            )
            if decision in (Decision.REVIEW, Decision.BLOCK):
                created_case = self.cases.create(
                    tx.tenant_id,
                    f"Case: {tx.tx_id[:16]}",
                    priority=severity,
                    narrative=reasoning_ar,
                    tx_ids=[tx.tx_id],
                    alert_ids=[created_alert["alert_id"]],
                )

        # 16. Audit
        self.audit.log(
            tx.tenant_id,
            actor,
            "transaction.scored",
            "transaction",
            tx.tx_id,
            request_id,
            {"decision": decision.value, "risk_score": final},
        )
        if created_alert:
            self.audit.log(
                tx.tenant_id,
                actor,
                "alert.created",
                "alert",
                created_alert["alert_id"],
                request_id,
                {"tx_id": tx.tx_id, "severity": severity},
            )

        # 17. Notify + publish event (best-effort: NotificationService.notify
        # already swallows provider errors internally — TASK 12)
        if created_alert and decision in (Decision.REVIEW, Decision.BLOCK):
            await self.notifications.notify(
                f"decision.{decision.value}", created_alert, assessment.model_dump(mode="json")
            )
        await self.events.publish("decision.created", assessment.model_dump(mode="json"))

        result = assessment.model_dump(mode="json")
        result["alert"] = created_alert
        result["case"] = created_case
        # FX reference fields exposed at response root so integrators can read
        # the FATF-equivalent amount/currency without digging into fx_proof.
        result["reference_amount"] = getattr(tx, "reference_amount", None)
        result["reference_currency"] = getattr(tx, "reference_currency", None)
        return result
