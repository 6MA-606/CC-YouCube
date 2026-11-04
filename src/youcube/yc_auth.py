#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Optional shared-secret authentication.

When YOUCUBE_TOKEN is unset or blank, every client is accepted. The unmodified
official YouCube ComputerCraft client keeps working in that mode. When the
variable is set, a client must present the same secret as the ``token`` query
parameter (``ws://host:5000/?token=...``) or as an ``Authorization: Bearer``
header.
"""

# Built-in modules
import logging
from hmac import compare_digest
from os import getenv
from re import compile as re_compile

_TOKEN_QUERY = re_compile(r"(?i)(token=)[^&\s\"']+")
_BEARER = re_compile(r"(?i)(bearer\s+)\S+")
_REDACTION_INSTALLED = False


def expected_token() -> str:
    """Return the configured shared secret, or an empty string when auth is off."""
    return (getenv("YOUCUBE_TOKEN") or "").strip()


def auth_enabled() -> bool:
    """Return True when a shared secret is configured."""
    return bool(expected_token())


def extract_presented_token(request) -> str:
    """Read the client secret from the query string or a bearer header."""
    args = getattr(request, "args", None)
    query_token = args.get("token") if args is not None else None
    if query_token:
        return str(query_token)

    headers = getattr(request, "headers", None)
    header = headers.get("Authorization", "") if headers is not None else ""
    if str(header).lower().startswith("bearer "):
        return str(header)[7:].strip()
    return ""


def client_authorized(request) -> bool:
    """
    Return True when the request may use the server.

    Open mode (no YOUCUBE_TOKEN) accepts every request.
    """
    expected = expected_token()
    if not expected:
        return True
    presented = extract_presented_token(request)
    return compare_digest(presented, expected)


def _redact_text(text: str) -> str:
    text = _TOKEN_QUERY.sub(r"\1***", text)
    return _BEARER.sub(r"\1***", text)


def _redact_value(value):
    if isinstance(value, str):
        return _redact_text(value)
    try:
        text = str(value)
    except Exception:  # pylint: disable=broad-exception-caught
        return value
    redacted = _redact_text(text)
    return redacted if redacted != text else value


class RedactSecretsFilter(logging.Filter):  # pylint: disable=too-few-public-methods
    """Hide shared secrets that would otherwise land in access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_value(record.msg)
        if isinstance(record.args, dict):
            record.args = {
                key: _redact_value(item) for key, item in record.args.items()
            }
        elif record.args:
            record.args = tuple(_redact_value(item) for item in record.args)
        # Sanic access logs put the URL on the record (extra={"request": url}).
        for key, value in list(record.__dict__.items()):
            if isinstance(value, str) and key not in {"msg", "message"}:
                redacted = _redact_text(value)
                if redacted != value:
                    setattr(record, key, redacted)
        return True


def install_secret_redaction() -> None:
    """Redact tokens on every log handler, including ones Sanic adds later."""
    # pylint: disable=global-statement
    global _REDACTION_INSTALLED
    if _REDACTION_INSTALLED:
        return

    # StreamHandler overrides emit, so patch handle, which subclasses still inherit.
    original_handle = logging.Handler.handle

    def handle(self, record):
        RedactSecretsFilter().filter(record)
        return original_handle(self, record)

    logging.Handler.handle = handle
    _REDACTION_INSTALLED = True
