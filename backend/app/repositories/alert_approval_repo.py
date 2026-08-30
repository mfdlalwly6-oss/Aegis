"""Four-eyes alert approvals — a high/critical alert is resolved only after a
SECOND, DIFFERENT investigator approves the first investigator's resolution.

The pending request is unique per alert (partial unique index in 018), so two
investigators cannot race two separate approvals for the same alert; the
approver-must-differ rule is enforced here AND in the API layer (defense in
depth), never in the UI.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from app.security import generate_id


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class AlertApprovalRepository:
    def __init__(self, db):
        self.db = db

    def create_request(
        self, tenant_id: str, alert_id: str, resolution: str, note: str, requested_by: str
    ) -> dict:
        aid = generate_id("apr")
        self.db.execute(
            "INSERT INTO alert_approvals "
            "(approval_id,tenant_id,alert_id,resolution,note,requested_by,status,created_at) "
            "VALUES (?,?,?,?,?,?,'pending',?)",
            (aid, tenant_id, alert_id, resolution, note, requested_by, utcnow()),
        )
        return self.get(aid)

    def get(self, approval_id: str) -> dict | None:
        r = self.db.query_one(
            "SELECT * FROM alert_approvals WHERE approval_id=?", (approval_id,)
        )
        return dict(r) if r else None

    def pending_for_alert(self, alert_id: str) -> dict | None:
        r = self.db.query_one(
            "SELECT * FROM alert_approvals WHERE alert_id=? AND status='pending' "
            "ORDER BY created_at DESC LIMIT 1",
            (alert_id,),
        )
        return dict(r) if r else None

    def decide(self, approval_id: str, status: str, approved_by: str) -> dict | None:
        if status not in ("approved", "rejected"):
            raise ValueError("invalid_status")
        self.db.execute(
            "UPDATE alert_approvals SET status=?, approved_by=?, decided_at=? WHERE approval_id=?",
            (status, approved_by, utcnow(), approval_id),
        )
        return self.get(approval_id)

    def list_for(self, tenant_id: str, status: str | None = None, limit: int = 100) -> list[dict]:
        if status:
            rows = self.db.query(
                "SELECT * FROM alert_approvals WHERE tenant_id=? AND status=? "
                "ORDER BY created_at DESC LIMIT ?",
                (tenant_id, status, limit),
            )
        else:
            rows = self.db.query(
                "SELECT * FROM alert_approvals WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, limit),
            )
        return [dict(r) for r in rows]
