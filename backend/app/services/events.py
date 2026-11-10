"""In-process pub/sub used for server-sent events (SSE). Thread-safe; bounded queues; slow clients are dropped
rather than allowed to block publishers. Single-process only: with several API replicas, clients fall back to the
polling they already do (documented in docs/architecture.md)."""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Iterator
from itertools import count

_MAX_QUEUE = 100
_ids = count(1)


class EventBus:
    def __init__(self) -> None:
        self._subs: set[queue.Queue] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=_MAX_QUEUE)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subs.discard(q)

    @property
    def subscribers(self) -> int:
        with self._lock:
            return len(self._subs)

    def publish(self, event: str, data: dict) -> int:
        msg = {"id": next(_ids), "event": event, "data": data, "ts": time.time()}
        delivered = 0
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(msg)
                delivered += 1
            except queue.Full:
                self.unsubscribe(q)  # a stalled client must never block ingestion
        return delivered


def format_sse(msg: dict) -> str:
    """One SSE frame. Newlines inside data are impossible because it is JSON-encoded on a single line."""
    return f"id: {msg['id']}\nevent: {msg['event']}\ndata: {json.dumps(msg['data'], separators=(',', ':'))}\n\n"


def stream(bus: EventBus, heartbeat_s: float = 15.0, max_events: int | None = None) -> Iterator[str]:
    """Generator for a StreamingResponse. Always unsubscribes when the client disconnects (GeneratorExit)."""
    q = bus.subscribe()
    sent = 0
    try:
        yield "retry: 3000\n\n"  # browser reconnect delay
        yield format_sse({"id": 0, "event": "hello", "data": {"subscribers": bus.subscribers}})
        while max_events is None or sent < max_events:
            try:
                yield format_sse(q.get(timeout=heartbeat_s))
            except queue.Empty:
                yield ": heartbeat\n\n"
            sent += 1
    finally:
        bus.unsubscribe(q)


_bus = EventBus()


def get_bus() -> EventBus:
    return _bus
