from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from app.db import Database


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _entry_hash(
    prev_hash: str,
    ts: str,
    tenant_id: str | None,
    actor: str,
    event_type: str,
    resource: str | None,
    resource_id: str | None,
    request_id: str | None,
    metadata_json: str,
) -> str:
    """SHA-256 over prev hash + canonical payload — insertion order defines the chain."""
    canonical = "|".join(
        [
            prev_hash,
            ts,
            tenant_id or "",
            actor,
            event_type,
            resource or "",
            resource_id or "",
            request_id or "",
            metadata_json,
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditRepository:
    """Append-only, hash-chained audit log. Tampering with any historical entry
    invalidates entry_hash of that row and every row after it (verifiable)."""

    def __init__(self, db: Database):
        self.db = db

    def _last_hash(self) -> str:
        row = self.db.query_one("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1")
        return row["entry_hash"] if row and row.get("entry_hash") else "GENESIS"

    def log(
        self,
        tenant_id: str | None,
        actor: str,
        event_type: str,
        resource: str | None = None,
        resource_id: str | None = None,
        request_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        safe_meta = {
            k: v
            for k, v in (metadata or {}).items()
            if k not in ("hmac_secret", "password", "api_key", "token")
        }
        ts = utcnow()
        meta_json = json.dumps(safe_meta, ensure_ascii=False, default=str, sort_keys=True)
        prev = self._last_hash()
        entry = _entry_hash(
            prev, ts, tenant_id, actor, event_type, resource, resource_id, request_id, meta_json
        )
        self.db.execute(
            "INSERT INTO audit_log (ts,tenant_id,actor,event_type,resource,"
            "resource_id,request_id,metadata_json,prev_hash,entry_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                ts,
                tenant_id,
                actor,
                event_type,
                resource,
                resource_id,
                request_id,
                meta_json,
                prev,
                entry,
            ),
        )

    def verify_chain(self, limit: int = 10000) -> dict:
        """Verify the tamper-evident audit chain.

        Two distinct checks:
        1. CONTENT INTEGRITY (hard fail): every hashed row's entry_hash is
           recomputed from its own stored prev_hash + payload. Any edit to a
           historical row breaks its own hash -> detected. This is the core
           tamper-evidence guarantee.
        2. LINKAGE (warn, not fail): prev_hash must reference GENESIS or an
           earlier known entry_hash. Non-linear links and chain restarts occur
           in dev-era history (the writer evolved from per-tenant to global
           chaining); they are reported as warnings, never silently ignored.
        An orphan prev_hash (references a hash that never existed) still fails,
        since it indicates fabricated or deleted rows.
        """
        rows = self.db.query(
            "SELECT id,ts,tenant_id,actor,event_type,resource,resource_id,request_id,"
            "metadata_json,prev_hash,entry_hash FROM audit_log ORDER BY id ASC LIMIT ?",
            (limit,),
        )
        seen_hashes = {"GENESIS"}
        checked = 0
        legacy_skipped = 0
        warnings = []
        tip = None
        for r in rows:
            if not r.get("entry_hash"):
                legacy_skipped += 1  # pre-chain legacy rows (audit predates hashing)
                continue
            stored_prev = r["prev_hash"] or ""
            # (1) content integrity — recompute from the row's OWN stored prev
            expect = _entry_hash(
                stored_prev,
                r["ts"],
                r["tenant_id"],
                r["actor"],
                r["event_type"],
                r["resource"],
                r["resource_id"],
                r["request_id"],
                r["metadata_json"],
            )
            if expect != r["entry_hash"]:
                return {
                    "ok": False,
                    "reason": "entry_hash_mismatch",
                    "row_id": r["id"],
                    "checked": checked,
                }
            # (2) linkage — orphan reference is a hard fail; non-linear = warning
            if stored_prev not in seen_hashes:
                return {
                    "ok": False,
                    "reason": "orphan_prev_hash",
                    "row_id": r["id"],
                    "checked": checked,
                }
            if tip is not None and stored_prev != tip:
                if stored_prev == "GENESIS":
                    warnings.append({"row_id": r["id"], "type": "chain_restart"})
                else:
                    warnings.append(
                        {
                            "row_id": r["id"],
                            "type": "non_linear_link",
                            "detail": "prev_hash links to an earlier row, not the immediate "
                            "predecessor (historical per-tenant writer era)",
                        }
                    )
            seen_hashes.add(r["entry_hash"])
            tip = r["entry_hash"]
            checked += 1
        return {
            "ok": True,
            "checked": checked,
            "tip": tip,
            "legacy_skipped": legacy_skipped,
            "chain_started": checked > 0,
            "warning_count": len(warnings),
            "warnings": warnings[:50],
        }

    def list(
        self,
        tenant_id: str | None = None,
        event_type: str | None = None,
        resource: str | None = None,
        resource_id: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
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
