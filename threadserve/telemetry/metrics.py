"""Telemetry contract shared by the worker loop and (in Phase 4) the real
metrics aggregator and JSON request logger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class RequestTelemetry:
    request_id: str
    method: str
    path: str
    status: int
    duration_ms: float
    bytes_in: int
    bytes_out: int
    worker_id: int
    client_addr: tuple[str, int]


class TelemetryRecorder(Protocol):
    def record(self, t: RequestTelemetry) -> None: ...


class NullTelemetryRecorder:
    """No-op recorder used until Phase 4 wires in real metrics/logging."""

    def record(self, t: RequestTelemetry) -> None:
        pass
