import pytest

from threadserve.http.errors import (
    BadRequest,
    ClientDisconnected,
    HttpVersionNotSupported,
    NotImplementedFraming,
    PayloadTooLarge,
)
from threadserve.http.parser import ParserLimits, parse_request


class ScriptedReader:
    """A read_fn double that mimics socket.recv: hands back at most the
    requested number of bytes per call, splitting/queuing pre-defined chunks
    as needed, and returns b"" once the scripted chunks are exhausted.
    """

    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    def __call__(self, n: int) -> bytes:
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if len(chunk) > n:
            self._chunks.insert(0, chunk[n:])
            return chunk[:n]
        return chunk


def one_byte_at_a_time(payload: bytes) -> ScriptedReader:
    return ScriptedReader([bytes([b]) for b in payload])


# --- happy path -------------------------------------------------------

def test_parses_simple_get_request():
    raw = b"GET /events HTTP/1.1\r\nHost: localhost\r\n\r\n"
    req = parse_request(ScriptedReader([raw]), client_addr=("127.0.0.1", 5000))

    assert req.method == "GET"
    assert req.path == "/events"
    assert req.http_version == "HTTP/1.1"
    assert req.headers["host"] == "localhost"
    assert req.body == b""
    assert req.client_addr == ("127.0.0.1", 5000)


def test_parses_post_with_body_single_chunk():
    body = b'{"type": "x"}'
    raw = (
        b"POST /events HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"\r\n" + body
    )
    req = parse_request(ScriptedReader([raw]))

    assert req.method == "POST"
    assert req.body == body


def test_query_string_is_parsed():
    raw = b"GET /events?severity=warning&limit=10 HTTP/1.1\r\nHost: h\r\n\r\n"
    req = parse_request(ScriptedReader([raw]))

    assert req.path == "/events"
    assert req.query == {"severity": ["warning"], "limit": ["10"]}


def test_header_names_are_lowercased():
    raw = b"GET / HTTP/1.1\r\nX-Custom-Header: Value\r\n\r\n"
    req = parse_request(ScriptedReader([raw]))

    assert req.headers["x-custom-header"] == "Value"


def test_ignores_bytes_after_declared_body_length():
    raw = b"POST / HTTP/1.1\r\nContent-Length: 2\r\n\r\nABEXTRA-GARBAGE"
    req = parse_request(ScriptedReader([raw]))

    assert req.body == b"AB"


# --- fragmentation ------------------------------------------------------

def test_headers_fragmented_across_many_reads():
    raw = b"GET /events HTTP/1.1\r\nHost: localhost\r\n\r\n"
    req = parse_request(one_byte_at_a_time(raw))

    assert req.method == "GET"
    assert req.path == "/events"


def test_body_fragmented_across_many_reads():
    body = b"0123456789"
    raw = (
        b"POST /events HTTP/1.1\r\nContent-Length: 10\r\n\r\n"
    )
    reader = ScriptedReader([raw[:10], raw[10:], body[:3], body[3:7], body[7:]])
    req = parse_request(reader)

    assert req.body == body


def test_headers_and_body_split_at_arbitrary_byte_boundary():
    body = b"hello-world"
    raw = b"POST / HTTP/1.1\r\nContent-Length: 11\r\n\r\n" + body
    # split in the middle of the header terminator itself
    split_at = raw.index(b"\r\n\r\n") + 2
    reader = ScriptedReader([raw[:split_at], raw[split_at:]])
    req = parse_request(reader)

    assert req.body == body


# --- early disconnect -----------------------------------------------------

def test_raises_client_disconnected_on_immediate_eof():
    with pytest.raises(ClientDisconnected):
        parse_request(ScriptedReader([]))


def test_raises_client_disconnected_mid_headers():
    raw = b"GET /events HTTP/1.1\r\nHost: loc"
    with pytest.raises(ClientDisconnected):
        parse_request(ScriptedReader([raw]))


def test_raises_client_disconnected_mid_body():
    raw = b"POST / HTTP/1.1\r\nContent-Length: 10\r\n\r\nabc"
    with pytest.raises(ClientDisconnected):
        parse_request(ScriptedReader([raw]))


# --- invalid Content-Length / framing ambiguity ----------------------------

def test_rejects_non_numeric_content_length():
    raw = b"POST / HTTP/1.1\r\nContent-Length: abc\r\n\r\n"
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]))


def test_rejects_negative_content_length():
    raw = b"POST / HTTP/1.1\r\nContent-Length: -5\r\n\r\n"
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]))


def test_rejects_duplicate_content_length_even_if_matching():
    raw = b"POST / HTTP/1.1\r\nContent-Length: 5\r\nContent-Length: 5\r\n\r\nhello"
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]))


def test_rejects_conflicting_content_length_values():
    raw = b"POST / HTTP/1.1\r\nContent-Length: 5\r\nContent-Length: 10\r\n\r\nhello"
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]))


def test_rejects_transfer_encoding_header():
    raw = b"POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
    with pytest.raises(NotImplementedFraming):
        parse_request(ScriptedReader([raw]))


def test_rejects_content_length_and_transfer_encoding_together():
    raw = (
        b"POST / HTTP/1.1\r\n"
        b"Content-Length: 5\r\n"
        b"Transfer-Encoding: chunked\r\n\r\nhello"
    )
    with pytest.raises(NotImplementedFraming):
        parse_request(ScriptedReader([raw]))


# --- size limits ------------------------------------------------------

def test_rejects_oversized_headers():
    raw = b"GET / HTTP/1.1\r\nX-Big: " + (b"a" * 100) + b"\r\n\r\n"
    limits = ParserLimits(max_header_bytes=32)
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]), limits=limits)


def test_rejects_oversized_body_before_reading_it():
    raw = b"POST / HTTP/1.1\r\nContent-Length: 1000\r\n\r\n"
    limits = ParserLimits(max_body_bytes=100)
    with pytest.raises(PayloadTooLarge):
        parse_request(ScriptedReader([raw]), limits=limits)


# --- malformed request line / version -----------------------------------

def test_rejects_malformed_request_line_missing_parts():
    raw = b"GET /events\r\nHost: h\r\n\r\n"
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]))


def test_rejects_malformed_request_line_double_space():
    raw = b"GET  /events HTTP/1.1\r\nHost: h\r\n\r\n"
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]))


def test_rejects_unsupported_http_version():
    raw = b"GET / HTTP/2.0\r\nHost: h\r\n\r\n"
    with pytest.raises(HttpVersionNotSupported):
        parse_request(ScriptedReader([raw]))


def test_rejects_non_absolute_request_target():
    raw = b"GET http://example.com/ HTTP/1.1\r\nHost: h\r\n\r\n"
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]))


# --- malformed headers --------------------------------------------------

def test_rejects_obsolete_header_line_folding():
    raw = b"GET / HTTP/1.1\r\nX-A: 1\r\n continuation\r\n\r\n"
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]))


def test_rejects_header_line_without_colon():
    raw = b"GET / HTTP/1.1\r\nNotAHeader\r\n\r\n"
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]))


def test_rejects_whitespace_before_colon():
    raw = b"GET / HTTP/1.1\r\nX-A : 1\r\n\r\n"
    with pytest.raises(BadRequest):
        parse_request(ScriptedReader([raw]))
