from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import pytest

from threadserve.http.errors import BadRequest, UnprocessableEntity
from threadserve.http.request import ParsedRequest
from threadserve.http.routing.handlers import list_events, submit_event
from threadserve.http.routing.router import RequestContext


@dataclass(frozen=True)
class FakeEvent:
    id: str
    type: str
    severity: str
    message: str
    timestamp: float
    received_at: float


class FakeEventStore:
    """Minimal local double for the EventStore contract, backed by a list."""

    def __init__(self) -> None:
        self._events: list[FakeEvent] = []

    def add(self, type: str, severity: str, message: str, timestamp: float | None) -> FakeEvent:
        now = 1_000_000.0 + len(self._events)
        event = FakeEvent(
            id=str(uuid.uuid4()),
            type=type,
            severity=severity,
            message=message,
            timestamp=timestamp if timestamp is not None else now,
            received_at=now,
        )
        self._events.append(event)
        return event

    def list_recent(self, limit: int = 50, severity: str | None = None) -> list[FakeEvent]:
        events = self._events
        if severity is not None:
            events = [e for e in events if e.severity == severity]
        return list(reversed(events))[:limit]


def make_request(method: str, path: str, body: bytes = b"", query: dict | None = None) -> ParsedRequest:
    return ParsedRequest(
        method=method,
        path=path,
        query=query or {},
        http_version="HTTP/1.1",
        headers={},
        body=body,
        client_addr=("127.0.0.1", 12345),
    )


def make_ctx(store: FakeEventStore) -> RequestContext:
    return RequestContext(
        event_store=store,
        stats_cache=None,
        telemetry=None,
        request_id="test",
        received_at=0.0,
    )


# --- submit_event ---


def test_submit_event_valid_returns_201_with_fields():
    store = FakeEventStore()
    ctx = make_ctx(store)
    body = json.dumps({"type": "login", "severity": "info", "message": "user logged in"}).encode()
    request = make_request("POST", "/events", body=body)

    response = submit_event(request, ctx)

    assert response.status == 201
    payload = json.loads(response.body)
    assert payload["type"] == "login"
    assert payload["severity"] == "info"
    assert payload["message"] == "user logged in"
    assert "id" in payload and payload["id"]
    assert "timestamp" in payload
    assert "received_at" in payload


@pytest.mark.parametrize("missing_field", ["type", "severity", "message"])
def test_submit_event_missing_required_field(missing_field):
    store = FakeEventStore()
    ctx = make_ctx(store)
    data = {"type": "login", "severity": "info", "message": "hi"}
    del data[missing_field]
    request = make_request("POST", "/events", body=json.dumps(data).encode())

    with pytest.raises(UnprocessableEntity) as exc_info:
        submit_event(request, ctx)

    assert exc_info.value.error_code == "missing_field"


def test_submit_event_invalid_json_body():
    store = FakeEventStore()
    ctx = make_ctx(store)
    request = make_request("POST", "/events", body=b"not json")

    with pytest.raises(BadRequest):
        submit_event(request, ctx)


@pytest.mark.parametrize("body", [b"[1,2,3]", b'"a string"', b"42", b"true"])
def test_submit_event_non_object_json_body(body):
    store = FakeEventStore()
    ctx = make_ctx(store)
    request = make_request("POST", "/events", body=body)

    with pytest.raises(BadRequest):
        submit_event(request, ctx)


def test_submit_event_invalid_severity_value():
    store = FakeEventStore()
    ctx = make_ctx(store)
    data = {"type": "login", "severity": "urgent", "message": "hi"}
    request = make_request("POST", "/events", body=json.dumps(data).encode())

    with pytest.raises(UnprocessableEntity) as exc_info:
        submit_event(request, ctx)

    assert exc_info.value.error_code == "invalid_field"


@pytest.mark.parametrize("field_name", ["type", "message"])
def test_submit_event_non_string_field(field_name):
    store = FakeEventStore()
    ctx = make_ctx(store)
    data = {"type": "login", "severity": "info", "message": "hi"}
    data[field_name] = 123
    request = make_request("POST", "/events", body=json.dumps(data).encode())

    with pytest.raises(UnprocessableEntity) as exc_info:
        submit_event(request, ctx)

    assert exc_info.value.error_code == "invalid_field"


def test_submit_event_empty_string_field():
    store = FakeEventStore()
    ctx = make_ctx(store)
    data = {"type": "login", "severity": "info", "message": ""}
    request = make_request("POST", "/events", body=json.dumps(data).encode())

    with pytest.raises(UnprocessableEntity) as exc_info:
        submit_event(request, ctx)

    assert exc_info.value.error_code == "invalid_field"


def test_submit_event_valid_numeric_timestamp_passed_through():
    store = FakeEventStore()
    ctx = make_ctx(store)
    data = {"type": "login", "severity": "info", "message": "hi", "timestamp": 1234.5}
    request = make_request("POST", "/events", body=json.dumps(data).encode())

    response = submit_event(request, ctx)

    payload = json.loads(response.body)
    assert payload["timestamp"] == 1234.5


def test_submit_event_non_numeric_timestamp_rejected():
    store = FakeEventStore()
    ctx = make_ctx(store)
    data = {"type": "login", "severity": "info", "message": "hi", "timestamp": "not-a-number"}
    request = make_request("POST", "/events", body=json.dumps(data).encode())

    with pytest.raises(UnprocessableEntity) as exc_info:
        submit_event(request, ctx)

    assert exc_info.value.error_code == "invalid_field"


def test_submit_event_boolean_timestamp_rejected():
    store = FakeEventStore()
    ctx = make_ctx(store)
    data = {"type": "login", "severity": "info", "message": "hi", "timestamp": True}
    request = make_request("POST", "/events", body=json.dumps(data).encode())

    with pytest.raises(UnprocessableEntity) as exc_info:
        submit_event(request, ctx)

    assert exc_info.value.error_code == "invalid_field"


# --- list_events ---


def _seed(store: FakeEventStore, count_by_severity: dict[str, int]) -> None:
    for severity, count in count_by_severity.items():
        for i in range(count):
            store.add(type="t", severity=severity, message=f"msg {i}", timestamp=None)


def test_list_events_no_query_params_returns_all_up_to_default_limit():
    store = FakeEventStore()
    ctx = make_ctx(store)
    _seed(store, {"info": 3, "warning": 2})
    request = make_request("GET", "/events", query={})

    response = list_events(request, ctx)

    assert response.status == 200
    payload = json.loads(response.body)
    assert payload["count"] == 5
    assert len(payload["events"]) == 5


def test_list_events_severity_filter():
    store = FakeEventStore()
    ctx = make_ctx(store)
    _seed(store, {"info": 3, "warning": 2, "critical": 1})
    request = make_request("GET", "/events", query={"severity": ["warning"]})

    response = list_events(request, ctx)

    payload = json.loads(response.body)
    assert payload["count"] == 2
    assert all(e["severity"] == "warning" for e in payload["events"])


def test_list_events_limit_caps_results():
    store = FakeEventStore()
    ctx = make_ctx(store)
    _seed(store, {"info": 10})
    request = make_request("GET", "/events", query={"limit": ["3"]})

    response = list_events(request, ctx)

    payload = json.loads(response.body)
    assert payload["count"] == 3
    assert len(payload["events"]) == 3


def test_list_events_invalid_severity_query_param():
    store = FakeEventStore()
    ctx = make_ctx(store)
    request = make_request("GET", "/events", query={"severity": ["urgent"]})

    with pytest.raises(BadRequest) as exc_info:
        list_events(request, ctx)

    assert exc_info.value.error_code == "invalid_query_param"


@pytest.mark.parametrize("limit_value", ["abc", "0", "-1", "99999"])
def test_list_events_invalid_limit_query_param(limit_value):
    store = FakeEventStore()
    ctx = make_ctx(store)
    request = make_request("GET", "/events", query={"limit": [limit_value]})

    with pytest.raises(BadRequest) as exc_info:
        list_events(request, ctx)

    assert exc_info.value.error_code == "invalid_query_param"
