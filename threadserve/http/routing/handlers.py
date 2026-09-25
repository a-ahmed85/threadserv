"""Route handlers for the /events resource.

Handlers never catch HttpError themselves: they raise on failure and let
the caller (the Phase 3 worker loop) convert it into an error response.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from threadserve.http.errors import BadRequest, UnprocessableEntity
from threadserve.http.request import ParsedRequest
from threadserve.http.response import HttpResponse
from threadserve.http.routing.router import RequestContext

_VALID_SEVERITIES = {"info", "warning", "error", "critical"}
_REQUIRED_FIELDS = ("type", "severity", "message")
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 1000


def submit_event(request: ParsedRequest, ctx: RequestContext) -> HttpResponse:
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError as exc:
        raise BadRequest("request body must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise BadRequest("request body must be a JSON object")

    for field_name in _REQUIRED_FIELDS:
        if field_name not in payload:
            raise UnprocessableEntity(
                f"missing required field: {field_name}", error_code="missing_field"
            )
        value = payload[field_name]
        if not isinstance(value, str) or not value:
            raise UnprocessableEntity(
                f"field {field_name!r} must be a non-empty string", error_code="invalid_field"
            )

    event_type = payload["type"]
    severity = payload["severity"]
    message = payload["message"]

    if severity not in _VALID_SEVERITIES:
        raise UnprocessableEntity(f"invalid severity: {severity!r}", error_code="invalid_field")

    timestamp: float | int | None = None
    if "timestamp" in payload:
        raw_timestamp = payload["timestamp"]
        if isinstance(raw_timestamp, bool) or not isinstance(raw_timestamp, (int, float)):
            raise UnprocessableEntity(
                "field 'timestamp' must be a number", error_code="invalid_field"
            )
        timestamp = raw_timestamp

    event = ctx.event_store.add(
        type=event_type, severity=severity, message=message, timestamp=timestamp
    )

    return HttpResponse.json(
        201,
        {
            "id": event.id,
            "type": event.type,
            "severity": event.severity,
            "message": event.message,
            "timestamp": event.timestamp,
            "received_at": event.received_at,
        },
    )


def list_events(request: ParsedRequest, ctx: RequestContext) -> HttpResponse:
    severity: str | None = None
    severity_values = request.query.get("severity")
    if severity_values:
        severity = severity_values[0]
        if severity not in _VALID_SEVERITIES:
            raise BadRequest(
                f"invalid severity filter: {severity!r}", error_code="invalid_query_param"
            )

    limit_values = request.query.get("limit")
    raw_limit = limit_values[0] if limit_values else str(_DEFAULT_LIMIT)
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise BadRequest(f"invalid limit: {raw_limit!r}", error_code="invalid_query_param") from exc
    if limit < 1 or limit > _MAX_LIMIT:
        raise BadRequest(f"invalid limit: {raw_limit!r}", error_code="invalid_query_param")

    events = ctx.event_store.list_recent(limit=limit, severity=severity)
    serialized: list[dict[str, Any]] = [asdict(event) for event in events]

    return HttpResponse.json(200, {"events": serialized, "count": len(serialized)})
