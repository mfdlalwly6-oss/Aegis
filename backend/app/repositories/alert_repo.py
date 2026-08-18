from __future__ import annotations

from datetime import datetime, timezone

from app.db import Database
from app.security import generate_id


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AlertRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id: str, tx_id: str, severity: str,
               title: str, description: str = "", decision_id: str | None = None) -> dict:
        aid = generate_id("alr")
        now = utcnow()
        self.db.execute(
            "INSERT INTO alerts (alert_id,tenant_id,tx_id,decision_id,severity,title,"
            "description,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (aid, tenant_id, tx_id, decision_id, severity, title, description,
             "open", now, now))
        return self.get(aid)

    def get(self, alert_id: str) -> dict | None:
        return self.db.query_one("SELECT * FROM alerts WHERE alert_id=?", (alert_id,))

    def list(self, tenant_id: str | None = None, status: str | None = None,
             limit: int = 100) -> list[dict]:
        sql, params = "SELECT * FROM alerts WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            params.append(tenant_id)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return self.db.query(sql, tuple(params))

    def update_status(self, alert_id: str, status: str,
                      assignee: str | None = None) -> dict | None:
        self.db.execute(
            "UPDATE alerts SET status=?, assignee=COALESCE(?,assignee), updated_at=? "
            "WHERE alert_id=?", (status, assignee, utcnow(), alert_id))
        return self.get(alert_id)
