"""Server configuration: dataclass + env/CLI parsing.

Precedence: CLI args > environment variables (THREADSERVE_*) > defaults.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    num_workers: int = 4
    queue_capacity: int = 64
    listen_backlog: int = 128
    max_request_bytes: int = 1_000_000
    event_store_capacity: int = 10_000
    stats_cache_ttl_s: float = 2.0
    drain_timeout_s: float = 10.0
    log_path: str | None = None

    @classmethod
    def from_env_and_args(cls, argv: list[str] | None = None) -> "ServerConfig":
        defaults = cls()
        env = _env_defaults(defaults)
        parser = _build_arg_parser(env)
        args = parser.parse_args(argv)
        return cls(
            host=args.host,
            port=args.port,
            num_workers=args.workers,
            queue_capacity=args.queue_capacity,
            listen_backlog=args.listen_backlog,
            max_request_bytes=args.max_request_bytes,
            event_store_capacity=args.event_store_capacity,
            stats_cache_ttl_s=args.stats_cache_ttl,
            drain_timeout_s=args.drain_timeout,
            log_path=args.log_path,
        )


def _env_defaults(defaults: ServerConfig) -> dict[str, object]:
    def _get(name: str, cast, fallback):
        raw = os.environ.get(name)
        if not raw:
            return fallback
        try:
            return cast(raw)
        except ValueError:
            return fallback

    return {
        "host": _get("THREADSERVE_HOST", str, defaults.host),
        "port": _get("THREADSERVE_PORT", int, defaults.port),
        "workers": _get("THREADSERVE_WORKERS", int, defaults.num_workers),
        "queue_capacity": _get("THREADSERVE_QUEUE_CAPACITY", int, defaults.queue_capacity),
        "listen_backlog": _get("THREADSERVE_LISTEN_BACKLOG", int, defaults.listen_backlog),
        "max_request_bytes": _get("THREADSERVE_MAX_REQUEST_BYTES", int, defaults.max_request_bytes),
        "event_store_capacity": _get("THREADSERVE_EVENT_STORE_CAPACITY", int, defaults.event_store_capacity),
        "stats_cache_ttl": _get("THREADSERVE_STATS_CACHE_TTL", float, defaults.stats_cache_ttl_s),
        "drain_timeout": _get("THREADSERVE_DRAIN_TIMEOUT", float, defaults.drain_timeout_s),
        "log_path": os.environ.get("THREADSERVE_LOG_PATH", defaults.log_path),
    }


def _build_arg_parser(env: dict[str, object]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="threadserve",
        description="ThreadServe: a thread-per-connection HTTP server.",
    )
    parser.add_argument("--host", default=env["host"])
    parser.add_argument("--port", type=int, default=env["port"])
    parser.add_argument("--workers", type=int, default=env["workers"])
    parser.add_argument("--queue-capacity", dest="queue_capacity", type=int, default=env["queue_capacity"])
    parser.add_argument("--listen-backlog", dest="listen_backlog", type=int, default=env["listen_backlog"])
    parser.add_argument(
        "--max-request-bytes", dest="max_request_bytes", type=int, default=env["max_request_bytes"]
    )
    parser.add_argument(
        "--event-store-capacity",
        dest="event_store_capacity",
        type=int,
        default=env["event_store_capacity"],
    )
    parser.add_argument("--stats-cache-ttl", dest="stats_cache_ttl", type=float, default=env["stats_cache_ttl"])
    parser.add_argument("--drain-timeout", dest="drain_timeout", type=float, default=env["drain_timeout"])
    parser.add_argument("--log-path", dest="log_path", default=env["log_path"])
    return parser
