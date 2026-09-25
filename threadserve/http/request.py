from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedRequest:
    method: str
    path: str
    query: dict[str, list[str]]
    http_version: str
    headers: dict[str, str]
    body: bytes
    client_addr: tuple[str, int]
