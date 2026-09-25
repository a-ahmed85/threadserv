from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

REASON_PHRASES: dict[int, str] = {
    200: "OK",
    201: "Created",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    411: "Length Required",
    413: "Payload Too Large",
    422: "Unprocessable Entity",
    500: "Internal Server Error",
    501: "Not Implemented",
    503: "Service Unavailable",
    505: "HTTP Version Not Supported",
}


@dataclass
class HttpResponse:
    status: int
    reason: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def __post_init__(self) -> None:
        if self.reason is None:
            self.reason = REASON_PHRASES.get(self.status, "")

    @classmethod
    def json(cls, status: int, payload: Any, headers: dict[str, str] | None = None) -> "HttpResponse":
        body = json.dumps(payload).encode("utf-8")
        merged_headers = {"Content-Type": "application/json"}
        merged_headers.update(headers or {})
        return cls(status=status, headers=merged_headers, body=body)


def error_envelope(error_code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": error_code, "message": message}
    payload.update(extra)
    return payload
