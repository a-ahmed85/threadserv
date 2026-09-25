"""Data model for a single stored event."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    id: str
    type: str
    severity: str  # one of: "info", "warning", "error", "critical" — not enforced here;
    # the caller (a route handler) validates this before calling EventStore.add().
    message: str
    timestamp: float  # epoch seconds — the event's own "when it happened" time
    received_at: float  # epoch seconds — when the store received/recorded it
