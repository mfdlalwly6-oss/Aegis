"""Audit module — thin wrapper over AuditRepository for service-level use."""
from __future__ import annotations

from typing import Any

from app.repositories.audit_repo import AuditRepository


class AuditService:
    def __init__(self, repo: AuditRepository):
        self.repo = repo

    def log(self, tenant_id: str | None, actor: str, event_type: str,
            resource: str | None = None, resource_id: str | None = None,
            request_id: str | None = None, metadata: dict | None = None) -> None:
        self.repo.log(tenant_id, actor, event_type, resource, resource_id,
                      request_id, metadata)
