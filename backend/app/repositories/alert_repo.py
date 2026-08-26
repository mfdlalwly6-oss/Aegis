from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db import Database
from app.security import generate_id


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class AlertRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        tenant_id: str,
        tx_id: str,
        severity: str,
        title: str,
        description: str = "",
        decision_id: str | None = None,
    ) -> dict:
        aid = generate_id("alr")
        now = utcnow()
        self.db.execute(
            "INSERT INTO alerts (alert_id,tenant_id,tx_id,decision_id,severity,title,"
            "description,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (aid, tenant_id, tx_id, decision_id, severity, title, description, "open", now, now),
        )
        return self.get(aid)

    def _parse(self, row: dict) -> dict:
        row["notes"] = json.loads(row.pop("notes_json", "[]") or "[]")
        return row

    def get(self, alert_id: str) -> dict | None:
        row = self.db.query_one("SELECT * FROM alerts WHERE alert_id=?", (alert_id,))
        return self._parse(row) if row else None

    def list(
        self, tenant_id: str | None = None, status: str | None = None, limit: int = 100
    ) -> list[dict]:
        sql, params = "SELECT * FROM alerts WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            params.append(tenant_id)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [self._parse(r) for r in self.db.query(sql, tuple(params))]

    def update_status(self, alert_id: str, status: str, assignee: str | None = None) -> dict | None:
        self.db.execute(
            "UPDATE alerts SET status=?, assignee=COALESCE(?,assignee), updated_at=? WHERE alert_id=?",
            (status, assignee, utcnow(), alert_id),
        )
        return self.get(alert_id)

    def add_note(self, alert_id: str, author: str, text: str) -> dict | None:
        alert = self.get(alert_id)
        if not alert:
            return None
        notes = alert["notes"]
        notes.append({"author": author, "text": text, "at": utcnow()})
        self.db.execute(
            "UPDATE alerts SET notes_json=?, updated_at=? WHERE alert_id=?",
            (json.dumps(notes, ensure_ascii=False), utcnow(), alert_id),
        )
        return self.get(alert_id)

    def resolve(
        self,
        alert_id: str,
        resolution: str,
        note: str = "",
        author: str = "investigator",
        actor_type: str = "investigator",
    ) -> dict | None:
        """Lifecycle terminal state: resolved_true_positive / resolved_false_positive.
        actor_type is STORED EXPLICITLY in the note (never inferred from email)."""
        alert = self.get(alert_id)
        if not alert:
            return None
        notes = alert["notes"]
        if note:
            notes.append({"author": author, "actor_type": actor_type, "text": note, "at": utcnow()})
        self.db.execute(
            "UPDATE alerts SET status=?, resolution=?, notes_json=?, updated_at=? WHERE alert_id=?",
            (resolution, resolution, json.dumps(notes, ensure_ascii=False), utcnow(), alert_id),
        )
        return self.get(alert_id)
