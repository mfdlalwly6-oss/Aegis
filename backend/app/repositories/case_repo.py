from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db import Database
from app.security import generate_id


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class CaseRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        tenant_id: str,
        title: str,
        priority: str = "medium",
        narrative: str = "",
        tx_ids: list[str] | None = None,
        alert_ids: list[str] | None = None,
    ) -> dict:
        cid = generate_id("case")
        now = utcnow()
        self.db.execute(
            "INSERT INTO cases (case_id,tenant_id,title,status,priority,narrative,"
            "tx_ids_json,alert_ids_json,notes_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid,
                tenant_id,
                title,
                "open",
                priority,
                narrative,
                json.dumps(tx_ids or []),
                json.dumps(alert_ids or []),
                json.dumps([]),
                now,
                now,
            ),
        )
        return self.get(cid)

    def _parse(self, row: dict) -> dict:
        row["tx_ids"] = json.loads(row.pop("tx_ids_json", "[]"))
        row["alert_ids"] = json.loads(row.pop("alert_ids_json", "[]"))
        row["notes"] = json.loads(row.pop("notes_json", "[]"))
        return row

    def get(self, case_id: str) -> dict | None:
        row = self.db.query_one("SELECT * FROM cases WHERE case_id=?", (case_id,))
        return self._parse(row) if row else None

    def list(
        self, tenant_id: str | None = None, status: str | None = None, limit: int = 100
    ) -> list[dict]:
        sql, params = "SELECT * FROM cases WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            params.append(tenant_id)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [self._parse(r) for r in self.db.query(sql, tuple(params))]

    def add_note(self, case_id: str, author: str, text: str) -> dict | None:
        case = self.get(case_id)
        if not case:
            return None
        notes = case["notes"]
        notes.append({"author": author, "text": text, "at": utcnow()})
        self.db.execute(
            "UPDATE cases SET notes_json=?, updated_at=? WHERE case_id=?",
            (json.dumps(notes, ensure_ascii=False), utcnow(), case_id),
        )
        return self.get(case_id)

    def update_status(self, case_id: str, status: str, assignee: str | None = None) -> dict | None:
        self.db.execute(
            "UPDATE cases SET status=?, assignee=COALESCE(?,assignee), updated_at=? WHERE case_id=?",
            (status, assignee, utcnow(), case_id),
        )
        return self.get(case_id)

    def resolve(
        self, case_id: str, resolution: str, note: str = "", author: str = "investigator"
    ) -> dict | None:
        """Close a case with a resolution: confirmed_fraud / false_positive / inconclusive."""
        case = self.get(case_id)
        if not case:
            return None
        notes = case["notes"]
        if note:
            notes.append({"author": author, "text": note, "at": utcnow()})
        self.db.execute(
            "UPDATE cases SET status='closed', resolution=?, notes_json=?, updated_at=? WHERE case_id=?",
            (resolution, json.dumps(notes, ensure_ascii=False), utcnow(), case_id),
        )
        return self.get(case_id)
