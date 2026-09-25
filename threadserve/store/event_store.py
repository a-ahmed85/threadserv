"""Thread-safe, in-memory, capacity-bounded store for events.

Backed by a `collections.deque(maxlen=capacity)`, which gives O(1) bounded
storage and silently evicts the oldest event once capacity is exceeded.
Severity counts are maintained incrementally rather than recomputed on every
read, so `add()` must detect an impending eviction (deque is already full)
*before* appending, and decrement the counter for whatever is about to be
pushed out.

Locking is a single plain `threading.Lock`, held only around the deque
mutation/read and the counter update. Anything that can be computed without
touching shared state (id generation, timestamps) is done before the lock is
acquired.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque

from threadserve.store.models import Event


class EventStore:
    def __init__(self, capacity: int):
        self._events: deque[Event] = deque(maxlen=capacity)
        self._counts_by_severity: dict[str, int] = {}
        self._lock = threading.Lock()

    def add(self, type: str, severity: str, message: str, timestamp: float | None) -> Event:
        event_id = uuid.uuid4().hex
        received_at = time.time()
        event = Event(
            id=event_id,
            type=type,
            severity=severity,
            message=message,
            timestamp=received_at if timestamp is None else timestamp,
            received_at=received_at,
        )

        with self._lock:
            if self._events and len(self._events) == self._events.maxlen:
                evicted = self._events[0]
                self._counts_by_severity[evicted.severity] -= 1
            self._events.append(event)
            self._counts_by_severity[severity] = self._counts_by_severity.get(severity, 0) + 1

        return event

    def list_recent(self, limit: int = 50, severity: str | None = None) -> list[Event]:
        result: list[Event] = []
        with self._lock:
            for event in reversed(self._events):
                if severity is not None and event.severity != severity:
                    continue
                result.append(event)
                if len(result) >= limit:
                    break
        return result

    def count(self) -> int:
        with self._lock:
            return len(self._events)

    def counts_by_severity(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts_by_severity)
