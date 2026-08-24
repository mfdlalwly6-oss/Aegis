from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db import Database


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TransactionRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, row: dict, features: dict, raw: dict) -> dict:
        self.db.execute(
            "INSERT OR IGNORE INTO transactions "
            "(tx_id,tenant_id,ts,channel,amount,currency,sender_account_id,"
            "sender_user_id,beneficiary_account_id,beneficiary_user_id,"
            "beneficiary_country,merchant_id,merchant_name,device_id,ip,"
            "ip_country,raw_json,features_json,created_at,"
            "reference_amount,reference_currency,fx_snapshot_id,fx_status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["tx_id"], row["tenant_id"], row["timestamp"], row["channel"],
             row["amount"], row["currency"], row["sender_account_id"],
             row.get("sender_user_id"), row["beneficiary_account_id"],
             row.get("beneficiary_user_id"), row.get("beneficiary_country"),
             row.get("merchant_id"), row.get("merchant_name"),
             row.get("device_id"), row.get("ip"), row.get("ip_country"),
             json.dumps(raw, default=str), json.dumps(features, default=str), utcnow(),
             row.get("reference_amount"), row.get("reference_currency"),
             row.get("fx_snapshot_id"), row.get("fx_status")),
        )
        return row

    def get(self, tx_id: str, tenant_id: str | None = None) -> dict | None:
        if tenant_id:
            return self.db.query_one(
                "SELECT * FROM transactions WHERE tx_id=? AND tenant_id=?",
                (tx_id, tenant_id))
        return self.db.query_one("SELECT * FROM transactions WHERE tx_id=?", (tx_id,))

    def list_recent(self, tenant_id: str | None = None, limit: int = 100) -> list[dict]:
        if tenant_id:
            return self.db.query(
                "SELECT * FROM transactions WHERE tenant_id=? ORDER BY ts DESC LIMIT ?",
                (tenant_id, limit))
        return self.db.query(
            "SELECT * FROM transactions ORDER BY ts DESC LIMIT ?", (limit,))

    def velocity(self, tenant_id: str, sender: str, window_sec: int) -> dict:
        """Count + sum of transactions from this sender in the last window."""
        rows = self.db.query(
            "SELECT amount, ts FROM transactions "
            "WHERE tenant_id=? AND sender_account_id=? "
            "ORDER BY ts DESC LIMIT 200",
            (tenant_id, sender),
        )
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - window_sec
        count, total = 0, 0.0
        for r in rows:
            try:
                ts = datetime.fromisoformat(r["ts"]).timestamp()
            except Exception:
                continue
            if ts >= cutoff:
                count += 1
                total += float(r["amount"])
        return {"count": count, "total_amount": total}

    def distinct_devices(self, tenant_id: str, sender: str) -> int:
        row = self.db.query_one(
            "SELECT COUNT(DISTINCT device_id) AS c FROM transactions "
            "WHERE tenant_id=? AND sender_account_id=? AND device_id IS NOT NULL",
            (tenant_id, sender),
        )
        return row["c"] if row else 0

    def shared_device_accounts(self, tenant_id: str, device_id: str) -> list[str]:
        rows = self.db.query(
            "SELECT DISTINCT sender_account_id FROM transactions "
            "WHERE tenant_id=? AND device_id=?", (tenant_id, device_id))
        return [r["sender_account_id"] for r in rows]

    def shared_ip_accounts(self, tenant_id: str, ip: str) -> list[str]:
        rows = self.db.query(
            "SELECT DISTINCT sender_account_id FROM transactions "
            "WHERE tenant_id=? AND ip=?", (tenant_id, ip))
        return [r["sender_account_id"] for r in rows]

    def known_beneficiary(self, tenant_id: str, sender: str, beneficiary: str) -> bool:
        row = self.db.query_one(
            "SELECT 1 FROM transactions WHERE tenant_id=? AND sender_account_id=? "
            "AND beneficiary_account_id=? LIMIT 1",
            (tenant_id, sender, beneficiary))
        return row is not None

    def structuring_count(self, tenant_id: str, sender: str,
                           low: float = 9000, high: float = 10000,
                           days: int = 30) -> int:
        rows = self.db.query(
            "SELECT COUNT(*) AS c FROM transactions "
            "WHERE tenant_id=? AND sender_account_id=? AND amount>=? AND amount<?",
            (tenant_id, sender, low, high))
        return rows[0]["c"] if rows else 0
