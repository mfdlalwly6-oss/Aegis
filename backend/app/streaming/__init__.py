"""Event bus — async pub/sub for real-time dashboard updates via SSE."""
from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        item = {"event_type": event_type, "payload": payload}
        for q in self._subscribers:
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                pass
