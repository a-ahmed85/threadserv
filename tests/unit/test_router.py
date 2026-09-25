import pytest

from threadserve.http.errors import BadRequest, MethodNotAllowed, NotFound
from threadserve.http.request import ParsedRequest
from threadserve.http.response import HttpResponse
from threadserve.http.routing.router import RequestContext, Router


def make_request(method: str, path: str) -> ParsedRequest:
    return ParsedRequest(
        method=method,
        path=path,
        query={},
        http_version="HTTP/1.1",
        headers={},
        body=b"",
        client_addr=("127.0.0.1", 5000),
    )


def make_ctx() -> RequestContext:
    return RequestContext(
        event_store=None,
        stats_cache=None,
        telemetry=None,
        request_id="test",
        received_at=0.0,
    )


def ok_handler(request: ParsedRequest, ctx: RequestContext) -> HttpResponse:
    return HttpResponse(status=200, body=b"ok")


def boom_handler(request: ParsedRequest, ctx: RequestContext) -> HttpResponse:
    raise BadRequest("boom")


# --- happy path ---------------------------------------------------------

def test_dispatch_returns_matching_handler_response():
    router = Router()
    router.register("GET", "/events", ok_handler)

    response = router.dispatch(make_request("GET", "/events"), make_ctx())

    assert response.status == 200
    assert response.body == b"ok"


# --- 404 ------------------------------------------------------------------

def test_dispatch_unregistered_path_raises_not_found():
    router = Router()
    router.register("GET", "/events", ok_handler)

    with pytest.raises(NotFound):
        router.dispatch(make_request("GET", "/nope"), make_ctx())


# --- 405 ------------------------------------------------------------------

def test_dispatch_unregistered_method_raises_method_not_allowed_with_allowed_methods():
    router = Router()
    router.register("GET", "/events", ok_handler)
    router.register("POST", "/events", ok_handler)

    with pytest.raises(MethodNotAllowed) as exc_info:
        router.dispatch(make_request("DELETE", "/events"), make_ctx())

    assert exc_info.value.allowed_methods == ["GET", "POST"]


# --- case insensitivity ----------------------------------------------------

def test_register_lowercase_method_matches_uppercase_dispatch():
    router = Router()
    router.register("post", "/events", ok_handler)

    response = router.dispatch(make_request("POST", "/events"), make_ctx())

    assert response.status == 200


def test_register_uppercase_method_matches_lowercase_dispatch():
    router = Router()
    router.register("POST", "/events", ok_handler)

    response = router.dispatch(make_request("post", "/events"), make_ctx())

    assert response.status == 200


# --- exception propagation --------------------------------------------------

def test_dispatch_does_not_swallow_handler_http_errors():
    router = Router()
    router.register("GET", "/events", boom_handler)

    with pytest.raises(BadRequest):
        router.dispatch(make_request("GET", "/events"), make_ctx())
