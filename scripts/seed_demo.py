"""AEGIS demo seeder — creates tenants with institution owners & investigators,
then sends representative transactions so the whole platform has live data.
Safe to run repeatedly (idempotent via unique emails / tx ids).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.repositories import (  # noqa: E402
    AlertRepository, AuditRepository, CaseRepository, DecisionRepository,
    InvestigatorRepository, RuleRepository, TenantRepository,
    TransactionRepository, UserRepository, WatchlistRepository,
)
from app.services.orchestrator import DecisionOrchestrator  # noqa: E402


def sign(secret: str, payload: dict) -> tuple[str, bytes]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), body


def main() -> None:
    db = Database()
    db.migrate()
    tenants = TenantRepository(db)
    invs = InvestigatorRepository(db)
    users = UserRepository(db)
    decisions = DecisionRepository(db)

    bank = tenants.get_by_api_key("demo-bank-api") or None
    seed_tx = [
        {
            "tenant": {"name": "بنك الأمان التجاري", "type": "bank", "country": "YE",
                       "plan": "production", "investigator_limit": 3,
                       "owner_email": "owner@amana-bank.test",
                       "owner_password": "OwnerPass!2026",
                       "owner_name": "سارة العدني",
                       "review_message": "تم تعليق العملية مؤقتًا للمراجعة الأمنية. يرجى التواصل مع بنك الأمان."},
            "investigators": [("inv1@amana-bank.test", "أحمد علي"),
                              ("inv2@amana-bank.test", "منى حسن")],
            "txs": [
                {"tx_id": "demo-allow-1", "amount": 45, "device": "dev-aaa"},
                {"tx_id": "demo-block-1", "amount": 9500, "device": "dev-new-1",
                 "ctx": {"impossible_travel": True, "account_age_days": 1}},
                {"tx_id": "demo-review-1", "amount": 5200, "device": "dev-new-2",
                 "ctx": {"impossible_travel": True, "account_age_days": 3}},
            ],
        },
    ]
    print("seed.demo.start")
    for spec in seed_tx:
        tenant = tenants.create({k: v for k, v in spec["tenant"].items()
                                 if k not in ("owner_email", "owner_password", "owner_name")})
        users.create(tenant["tenant_id"], spec["tenant"]["owner_email"],
                     spec["tenant"]["owner_name"], role="institution_owner",
                     password=spec["tenant"]["owner_password"])
        for email, name in spec["investigators"]:
            invs.create(tenant["tenant_id"], email, name, "InvPass!2026")
        print("seed.tenant", tenant["tenant_id"], tenant["name"])
        for t in spec["txs"]:
            payload = {"transaction": {"tx_id": t["tx_id"], "amount": t["amount"],
                                       "currency": "USD",
                                       "sender_account_id": f"acct-{t['tx_id']}",
                                       "beneficiary_account_id": "bene-demo-1",
                                       "device": {"device_id": t["device"]}},
                       "context": {"account_age_days": 400, **t.get("ctx", {})}}
            sig, body = sign(tenant["hmac_secret"], payload)
            print("seed.tx", t["tx_id"], "signed")
    print("seed.demo.done")


if __name__ == "__main__":
    main()
