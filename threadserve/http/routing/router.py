"""Route registration and dispatch.

Contract frozen for parallel Phase 2 work: RequestContext and Handler are
final; Router's method bodies are left for implementation (see the build
plan, Phase 2, Agent B) but its public signature and error behavior below
are fixed so routing/handlers.py (Agent C) can be written against it
without waiting on this file to be finished.

Behavior Router.dispatch must implement:
- No route registered for the request path at all -> raise NotFound.
- Route registered for the path, but not for this method -> raise
  MethodNotAllowed with allowed_methods set to the sorted list of methods
  that ARE registered for that path (used to build the Allow header).
- Otherwise -> call the matching handler and return its HttpResponse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from threadserve.http.errors import MethodNotAllowed, NotFound
from threadserve.http.request import ParsedRequest
from threadserve.http.response import HttpResponse

if TYPE_CHECKING:
    from threadserve.cache.stats_cache import StatsCache
    from threadserve.store.event_store import EventStore
    from threadserve.telemetry.metrics import TelemetryRecorder


@dataclass
class RequestContext:
    event_store: "EventStore"
    stats_cache: "StatsCache"
    telemetry: "TelemetryRecorder"
    request_id: str
    received_at: float


Handler = Callable[[ParsedRequest, RequestContext], HttpResponse]


class Router:
    def __init__(self) -> None:
        self._routes: dict[str, dict[str, Handler]] = {}

    def register(self, method: str, path: str, handler: Handler) -> None:
        self._routes.setdefault(path, {})[method.upper()] = handler

    def dispatch(self, request: ParsedRequest, ctx: RequestContext) -> HttpResponse:
        methods = self._routes.get(request.path)
        if methods is None:
            raise NotFound(f"no route registered for path {request.path!r}")

        handler = methods.get(request.method.upper())
        if handler is None:
            raise MethodNotAllowed(
                f"method {request.method!r} not allowed for path {request.path!r}",
                allowed_methods=sorted(methods),
            )

        return handler(request, ctx)
