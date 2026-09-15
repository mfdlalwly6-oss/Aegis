"""Event bus — async pub/sub for real-time dashboard updates via SSE.

A2 fix — TENANT ISOLATION: subscribers declare a tenant scope
(None = platform, sees everything; a tenant id = only that tenant's
events). publish() tags each item with its tenant (payload.tenant_id)
and delivers only to matching subscribers, so one institution's
decision stream never leaks into another's SSE connection.
"""

from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    def __init__(self):
        self._subscribers: list[tuple[str | None, asyncio.Queue]] = []

    def subscribe(self, tenant_id: str | None = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.append((tenant_id, q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers = [(s, sq) for s, sq in self._subscribers if sq is not q]

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        item = {"event_type": event_type, "payload": payload}
        ev_tenant = payload.get("tenant_id") if isinstance(payload, dict) else None
        for scope, q in self._subscribers:
            # platform scope (None) sees all; tenant scope sees only its own
            if scope is not None and scope != ev_tenant:
                continue
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                pass
