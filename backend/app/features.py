"""Feature extraction — computes signals from transaction + historical data.
All features are real: they query the actual transaction history in SQLite.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from app.models.schemas import Transaction
from app.repositories.decision_repo import DecisionRepository
from app.repositories.transaction_repo import TransactionRepository


class FeatureExtractor:
    def __init__(self, tx_repo: TransactionRepository, dec_repo: DecisionRepository):
        self.tx_repo = tx_repo
        self.dec_repo = dec_repo

    def extract(self, tx: Transaction) -> dict[str, Any]:
        tid = tx.tenant_id
        sender = tx.sender_account_id

        vel_1m = self.tx_repo.velocity(tid, sender, 60)
        vel_5m = self.tx_repo.velocity(tid, sender, 300)
        vel_1h = self.tx_repo.velocity(tid, sender, 3600)

        device_id = tx.device.device_id if tx.device else None
        ip = str(tx.device.ip) if tx.device and tx.device.ip else None

        shared_dev = self.tx_repo.shared_device_accounts(tid, device_id) if device_id else []
        shared_ip = self.tx_repo.shared_ip_accounts(tid, ip) if ip else []
        # device is 'new' when this sender never used it before (extraction runs before persist)
        new_device = bool(device_id) and sender not in shared_dev

        known_benef = self.tx_repo.known_beneficiary(tid, sender, tx.beneficiary_account_id)
        structuring = self.tx_repo.structuring_count(tid, sender)

        hist = self.dec_repo.count_by_tenant(tid)
        suspicious = hist["by_decision"].get("block", 0) + hist["by_decision"].get("review", 0)

        meta = tx.metadata or {}
        hour = tx.timestamp.hour if tx.timestamp else datetime.now(UTC).hour

        return {
            "amount": float(tx.amount),
            "hour_sin": math.sin((hour / 24) * 2 * math.pi),
            "hour_cos": math.cos((hour / 24) * 2 * math.pi),
            "velocity": {
                "tx_per_min_card": vel_1m["count"],
                "amount_5min_account": vel_5m["total_amount"],
                "tx_count_5min": vel_5m["count"],
                "tx_count_1h": vel_1h["count"],
                "amount_1h": vel_1h["total_amount"],
                "distinct_merchants_1h": meta.get("distinct_merchants_1h", 0),
                "card_declines_1h": meta.get("card_declines_1h", 0),
                "count_9k_10k_30d": structuring,
            },
            "device": {
                "device_id": device_id,
                "first_seen_today": new_device,
                "shared_device_count": len(shared_dev),
                "shared_ip_count": len(shared_ip),
                "vpn": bool(tx.device and tx.device.vpn),
                "tor": bool(tx.device and tx.device.tor),
                "proxy": bool(tx.device and tx.device.proxy),
                "emulator": bool(meta.get("emulator", False)),
                "rooted": bool(meta.get("rooted", False)),
            },
            "geo": {
                "impossible_travel": bool(meta.get("impossible_travel", False)),
                "fatf_high_risk": bool(meta.get("fatf_high_risk", False)),
                "ip_country": tx.device.ip_country if tx.device else None,
            },
            "account": {
                "seconds_since_password_change": meta.get("seconds_since_password_change", 999999),
                "account_age_days": meta.get("account_age_days", 0),
                "mfa_recently_disabled": bool(meta.get("mfa_recently_disabled", False)),
            },
            "beneficiary": {
                "new": not known_benef,
                "offshore": bool(meta.get("offshore", False)),
                "country": tx.beneficiary_country,
                "scam_list_hit": False,
            },
            "crypto": {
                "beneficiary_mixer": False,
                "beneficiary_sanctioned": False,
            },
            "amount_flags": {
                "is_round_1000": float(tx.amount) % 1000 == 0 and float(tx.amount) >= 1000,
            },
            "history": {
                "suspicious_events_30d": suspicious,
                "previous_declines": meta.get("previous_declines", 0),
                "previous_chargebacks": meta.get("previous_chargebacks", 0),
            },
            "customer": {
                "billing_country": meta.get("billing_country"),
            },
        }

    def vector(self, tx: Transaction, features: dict) -> list[float]:
        f = features
        v = [
            float(tx.amount),
            f["hour_sin"],
            f["hour_cos"],
            float(f["velocity"]["tx_per_min_card"]),
            float(f["velocity"]["amount_5min_account"]),
            float(f["velocity"]["distinct_merchants_1h"]),
            float(f["device"]["first_seen_today"]),
            float(f["device"]["shared_device_count"]),
            float(f["device"]["shared_ip_count"]),
            float(f["geo"]["impossible_travel"]),
            float(f["geo"]["fatf_high_risk"]),
            float(f["beneficiary"]["new"]),
            float(f["account"]["seconds_since_password_change"]),
            float(f["history"]["previous_declines"]),
            float(f["history"]["previous_chargebacks"]),
            float(bool(tx.metadata.get("high_risk_merchant"))),
            float(tx.timestamp.hour < 6 or tx.timestamp.hour > 22 if tx.timestamp else False),
            float(f["amount_flags"]["is_round_1000"]),
            float(f["velocity"]["count_9k_10k_30d"] > 2),
            float(f["history"]["suspicious_events_30d"]),
        ]
        return v
