"""HTTP error hierarchy shared by the parser, router, and handlers."""

from __future__ import annotations


class HttpError(Exception):
    """Base class for errors that map directly to an HTTP response."""

    status: int = 500
    default_error_code: str = "error"

    def __init__(self, message: str, *, error_code: str | None = None, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.default_error_code
        self.extra = extra or {}


class BadRequest(HttpError):
    status = 400
    default_error_code = "bad_request"


class NotFound(HttpError):
    status = 404
    default_error_code = "not_found"


class MethodNotAllowed(HttpError):
    status = 405
    default_error_code = "method_not_allowed"

    def __init__(self, message: str, allowed_methods: list[str], **kwargs):
        super().__init__(message, **kwargs)
        self.allowed_methods = allowed_methods


class LengthRequired(HttpError):
    status = 411
    default_error_code = "length_required"


class PayloadTooLarge(HttpError):
    status = 413
    default_error_code = "payload_too_large"


class UnprocessableEntity(HttpError):
    status = 422
    default_error_code = "invalid_field"


class NotImplementedFraming(HttpError):
    """Raised for framing mechanisms we deliberately don't support (e.g. chunked)."""

    status = 501
    default_error_code = "not_implemented"


class HttpVersionNotSupported(HttpError):
    status = 505
    default_error_code = "http_version_not_supported"


class ClientDisconnected(Exception):
    """Raised when the client closes the connection before a full request
    was received. Not an HttpError: there is no socket left to respond on.
    """
