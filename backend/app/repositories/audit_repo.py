from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db import Database


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditRepository:
    def __init__(self, db: Database):
        self.db = db

    def log(self, tenant_id: str | None, actor: str, event_type: str,
            resource: str | None = None, resource_id: str | None = None,
            request_id: str | None = None, metadata: dict | None = None) -> None:
        safe_meta = {k: v for k, v in (metadata or {}).items()
                     if k not in ("hmac_secret", "password", "api_key", "token")}
        self.db.execute(
            "INSERT INTO audit_log (ts,tenant_id,actor,event_type,resource,"
            "resource_id,request_id,metadata_json) VALUES (?,?,?,?,?,?,?,?)",
            (utcnow(), tenant_id, actor, event_type, resource, resource_id,
             request_id, json.dumps(safe_meta, ensure_ascii=False, default=str)))

    def list(self, tenant_id: str | None = None, event_type: str | None = None,
             resource: str | None = None, resource_id: str | None = None,
             limit: int = 200) -> list[dict]:
        sql, params = "SELECT * FROM audit_log WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            params.append(tenant_id)
        if event_type:
            sql += " AND event_type=?"
            params.append(event_type)
        if resource:
            sql += " AND resource=?"
            params.append(resource)
        if resource_id:
            sql += " AND resource_id=?"
            params.append(resource_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return self.db.query(sql, tuple(params))
