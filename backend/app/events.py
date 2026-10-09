"""In-process pub/sub for live run events (one uvicorn worker by design)."""

from __future__ import annotations

import asyncio
from collections import defaultdict


class RunBus:
    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, run_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subs[run_id].add(q)
        return q

    def unsubscribe(self, run_id: int, q: asyncio.Queue) -> None:
        self._subs[run_id].discard(q)
        if not self._subs[run_id]:
            self._subs.pop(run_id, None)

    def publish(self, run_id: int, event: dict) -> None:
        for q in list(self._subs.get(run_id, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow client; it will catch up from the DB on reconnect


bus = RunBus()
