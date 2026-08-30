"""AML screening — technical detection platform, NOT a legal compliance substitute.

Screens transactions against tenant-scoped watchlists (sanctions / PEP /
high_risk_country / custom) using:
- country codes: exact match (as before)
- entity names: fuzzy matching with secondary-attribute confidence
  (delegated to app.aml.matching)

Every hit is recorded with point-in-time evidence (entry id/list/value/source
/matched_on/score/secondary/tenant) so the decision remains auditable even
after the watchlist changes.
"""

from __future__ import annotations

from typing import Any

from app.aml.matching import match_name
from app.models.schemas import AMLSignal, Transaction
from app.repositories.watchlist_repo import WatchlistRepository


def _classify(match: dict, list_type: str) -> str:
    """Explicit match-result taxonomy (AML best practice):

    - ``confirmed``  : exact/alias/country match, or fuzzy whose score is strong
      enough on its own (>=0.95) or is reinforced by secondary attributes
      (country/dob/identifiers all agree or a hard identifier hits).
    - ``potential``  : fuzzy candidate that lacks corroboration — needs an
      investigator, never auto-blocks on its own for PEP/custom lists.
    Sanctions hard-block policy is applied by the orchestrator, not here.
    """
    mt = match.get("match_type") or ""
    score = float(match.get("score") or 0.0)
    sec = match.get("secondary") or {}
    if mt in ("exact", "alias", "country_exact"):
        return "confirmed"
    if sec.get("identifiers") or (sec.get("country") == "match" and sec.get("dob") == "match"):
        return "confirmed"
    if score >= 0.95 and list_type == "sanctions":
        return "confirmed"
    return "potential"


def _evidence(match: dict, list_type: str) -> dict:
    """Build a compact, point-in-time evidence record for the decision snapshot."""
    e = match["entry"]
    return {
        "entry_id": e.get("id"),
        "list_type": list_type,
        "tenant_id": e.get("tenant_id"),
        "value": e.get("value"),
        "matched_on": match.get("matched_on"),
        "match_type": match.get("match_type"),
        "match_result": _classify(match, list_type),
        "score": match.get("score"),
        "source": e.get("source"),
        "external_id": e.get("external_id"),
        "entity_kind": e.get("entity_kind"),
        "secondary": match.get("secondary", {}),
        "list_snapshot_at": e.get("updated_at") or e.get("created_at"),
    }


class AMLService:
    def __init__(self, watchlist_repo: WatchlistRepository, *, fuzzy_threshold: float = 0.87):
        self.watchlist = watchlist_repo
        self.fuzzy_threshold = fuzzy_threshold

    def _screen_countries(self, tx: Transaction, signal: AMLSignal,
                          flags: list[str], evidence: list[dict]) -> float:
        score = 0.0
        beneficiary_country = tx.beneficiary_country or (tx.device.ip_country if tx.device else None)
        if not beneficiary_country:
            return score
        c = beneficiary_country.upper()
        hit = self.watchlist.check("sanctions", c, tx.tenant_id)
        if hit:
            signal.sanctions_hit = True
            score += 0.60
            flags.append(f"SANCTIONS_HIT:{c}")
            evidence.append(_evidence({"entry": hit, "matched_on": c,
                                       "match_type": "country_exact", "score": 1.0}, "sanctions"))
        hr = self.watchlist.check("high_risk_country", c, tx.tenant_id)
        if hr:
            signal.fatf_high_risk_country = True
            score += 0.20
            flags.append(f"HIGH_RISK_COUNTRY:{c}")
            evidence.append(_evidence({"entry": hr, "matched_on": c,
                                       "match_type": "country_exact", "score": 1.0}, "high_risk_country"))
        return score

    def _screen_names(self, tx: Transaction, signal: AMLSignal,
                      flags: list[str], evidence: list[dict]) -> float:
        """Name-based sanctions / PEP / custom screening across sender,
        beneficiary and customer names, with secondary attribute context."""
        score = 0.0
        candidates: list[tuple[str, str, dict]] = []  # (role, name, context)
        base_ctx = {"country": tx.customer_country, "dob": tx.customer_dob,
                    "identifiers": tx.customer_identifiers or {}}
        if tx.sender_name:
            candidates.append(("sender", tx.sender_name, base_ctx))
        if tx.beneficiary_name:
            candidates.append(("beneficiary", tx.beneficiary_name,
                               {"country": tx.beneficiary_country, "dob": None, "identifiers": {}}))
        if tx.customer_name:
            candidates.append(("customer", tx.customer_name, base_ctx))
        if tx.merchant_name:
            candidates.append(("merchant", tx.merchant_name, {"country": None, "dob": None, "identifiers": {}}))

        for list_type, weight, flag in (("sanctions", 0.60, "SANCTIONS_NAME_HIT"),
                                        ("pep", 0.35, "PEP_NAME_HIT"),
                                        ("custom", 0.25, "CUSTOM_LIST_HIT")):
            entries = self.watchlist.list_active(list_type, tx.tenant_id)
            # skip pure country codes (2-letter ISO) — country screening covers those
            entries = [e for e in entries if not (len(e.get("value", "")) == 2 and e["value"].isalpha())]
            if not entries:
                continue
            for role, name, ctx in candidates:
                matches = match_name(name, entries, context=ctx,
                                     fuzzy_threshold=self.fuzzy_threshold, limit=3)
                for m in matches:
                    if list_type == "sanctions":
                        signal.sanctions_hit = True
                    elif list_type == "pep":
                        signal.pep_hit = True
                    score += weight * float(m["score"])
                    flags.append(f"{flag}:{role}:{m['entry'].get('value')}({m['score']})")
                    evidence.append({**_evidence(m, list_type), "role": role})
        return score

    async def screen(self, tx: Transaction, features: dict[str, Any]) -> AMLSignal:
        signal = AMLSignal()
        score = 0.0
        flags: list[str] = []
        evidence: list[dict] = []

        # 1. Country screening (existing behaviour, kept exactly)
        score += self._screen_countries(tx, signal, flags, evidence)

        # 2. Name screening — sanctions / PEP / custom (new, additive)
        score += self._screen_names(tx, signal, flags, evidence)

        # 3. Typology detection (unchanged from previous engine)
        amount = float(tx.amount)
        vel = features.get("velocity", {})
        structuring_count = vel.get("count_9k_10k_30d", 0)
        if 9000 <= amount < 10000 and structuring_count >= 2:
            signal.typology_matches.append("structuring_smurfing")
            score += 0.30
            flags.append("STRUCTURING_PATTERN")
        if vel.get("tx_count_1h", 0) >= 8 and vel.get("amount_1h", 0) > 20000:
            signal.typology_matches.append("rapid_movement_of_funds")
            score += 0.25
            flags.append("RAPID_FUND_MOVEMENT")
        if features.get("amount_flags", {}).get("is_round_1000") and features.get("beneficiary", {}).get("offshore"):
            signal.typology_matches.append("round_amount_offshore")
            score += 0.15
            flags.append("ROUND_AMOUNT_OFFSHORE")
        if features.get("device", {}).get("tor") or features.get("device", {}).get("vpn"):
            if amount > 5000:
                signal.typology_matches.append("anonymity_tool_high_value")
                score += 0.10
                flags.append("ANONYMITY_TOOL_HIGH_VALUE")

        signal.score = min(1.0, score)
        signal.risk_flags = flags
        # Persistable point-in-time evidence (declared on AMLSignal; the
        # orchestrator serializes it into decisions.aml_json for audit).
        signal.watchlist_evidence = evidence
        return signal
