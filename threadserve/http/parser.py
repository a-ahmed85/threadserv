"""Hand-rolled HTTP/1.x request parser.

Design rules, deliberately strict:
- Never guess on ambiguous framing. Any Transfer-Encoding header is rejected
  outright (chunked decoding isn't implemented). Duplicate or conflicting
  Content-Length headers are rejected. Both rules together mean framing is
  always unambiguous by the time a body is read.
- Every connection is one request, then closed by the caller (no keep-alive),
  so bytes past the declared body length are simply ignored, not
  reinterpreted as a pipelined second request.
- `read_fn` mirrors `socket.recv`: it may return fewer bytes than requested,
  and an empty bytes return means the peer closed the connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs

from threadserve.http.errors import (
    BadRequest,
    ClientDisconnected,
    HttpVersionNotSupported,
    NotImplementedFraming,
    PayloadTooLarge,
)
from threadserve.http.request import ParsedRequest

ReadFn = Callable[[int], bytes]

_SUPPORTED_VERSIONS = {"HTTP/1.0", "HTTP/1.1"}
_HEADER_TERMINATOR = b"\r\n\r\n"


@dataclass(frozen=True)
class ParserLimits:
    max_header_bytes: int = 16_384
    max_headers_count: int = 100
    max_body_bytes: int = 1_000_000
    read_chunk_size: int = 65_536


def parse_request(
    read_fn: ReadFn,
    limits: ParserLimits | None = None,
    client_addr: tuple[str, int] = ("", 0),
) -> ParsedRequest:
    limits = limits or ParserLimits()
    buf = _read_until_headers_complete(read_fn, limits)
    header_block, leftover = _split_headers(buf)
    method, path, query, http_version = _parse_request_line(header_block)
    headers = _parse_headers(header_block, limits)
    content_length = _resolve_content_length(headers, limits)
    body = _read_body(read_fn, leftover, content_length, limits)
    return ParsedRequest(
        method=method,
        path=path,
        query=query,
        http_version=http_version,
        headers=headers,
        body=body,
        client_addr=client_addr,
    )


def _read_until_headers_complete(read_fn: ReadFn, limits: ParserLimits) -> bytearray:
    buf = bytearray()
    while True:
        chunk = read_fn(limits.read_chunk_size)
        if not chunk:
            raise ClientDisconnected("client closed the connection before headers were complete")
        buf += chunk

        idx = buf.find(_HEADER_TERMINATOR)
        if idx != -1:
            if idx > limits.max_header_bytes:
                raise BadRequest(
                    "request headers exceed the configured size limit",
                    error_code="header_too_large",
                )
            return buf
        if len(buf) > limits.max_header_bytes:
            raise BadRequest(
                "request headers exceed the configured size limit",
                error_code="header_too_large",
            )


def _split_headers(buf: bytearray) -> tuple[bytes, bytes]:
    idx = buf.index(_HEADER_TERMINATOR)
    header_block = bytes(buf[:idx])
    leftover = bytes(buf[idx + len(_HEADER_TERMINATOR) :])
    return header_block, leftover


def _parse_request_line(header_block: bytes) -> tuple[str, str, dict[str, list[str]], str]:
    lines = header_block.split(b"\r\n")
    if not lines or not lines[0]:
        raise BadRequest("empty request line")
    try:
        request_line = lines[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise BadRequest("request line is not valid ASCII") from exc

    parts = request_line.split(" ")
    if len(parts) != 3 or not all(parts):
        raise BadRequest("malformed request line")
    method, raw_target, http_version = parts

    if http_version not in _SUPPORTED_VERSIONS:
        raise HttpVersionNotSupported(f"unsupported HTTP version: {http_version!r}")

    if not raw_target.startswith("/"):
        raise BadRequest("request target must be an absolute path")

    path, _, query_string = raw_target.partition("?")
    query = parse_qs(query_string) if query_string else {}
    return method, path, query, http_version


def _parse_headers(header_block: bytes, limits: ParserLimits) -> dict[str, str]:
    lines = header_block.split(b"\r\n")[1:]
    if len(lines) > limits.max_headers_count:
        raise BadRequest("too many header fields", error_code="header_too_large")

    headers: dict[str, str] = {}
    content_length_values: list[str] = []

    for raw_line in lines:
        if not raw_line:
            continue
        try:
            line = raw_line.decode("ascii")
        except UnicodeDecodeError as exc:
            raise BadRequest("header line is not valid ASCII") from exc

        if line[:1] in (" ", "\t"):
            raise BadRequest("obsolete header line folding is not supported")

        name, sep, value = line.partition(":")
        if sep != ":":
            raise BadRequest(f"malformed header line: {line!r}")
        if name != name.strip() or not name.strip():
            raise BadRequest("header name must be non-empty with no whitespace before the colon")

        name = name.strip().lower()
        value = value.strip()

        if name == "transfer-encoding":
            raise NotImplementedFraming("Transfer-Encoding is not supported")
        if name == "content-length":
            content_length_values.append(value)
            continue

        headers[name] = value

    if content_length_values:
        if len(content_length_values) > 1:
            raise BadRequest("duplicate or conflicting Content-Length headers")
        headers["content-length"] = content_length_values[0]

    return headers


def _resolve_content_length(headers: dict[str, str], limits: ParserLimits) -> int:
    raw = headers.get("content-length")
    if raw is None:
        return 0
    if not raw.isdigit():
        raise BadRequest("invalid Content-Length value")
    length = int(raw)
    if length > limits.max_body_bytes:
        raise PayloadTooLarge("request body exceeds the configured size limit")
    return length


def _read_body(read_fn: ReadFn, leftover: bytes, content_length: int, limits: ParserLimits) -> bytes:
    if content_length == 0:
        return b""
    body = bytearray(leftover[:content_length])
    while len(body) < content_length:
        chunk = read_fn(min(limits.read_chunk_size, content_length - len(body)))
        if not chunk:
            raise ClientDisconnected("client closed the connection before the request body was complete")
        body += chunk
    return bytes(body)
