"""Shared-secret auth stays open unless YOUCUBE_TOKEN is set."""

import logging
from io import StringIO

from yc_auth import (
    client_authorized,
    extract_presented_token,
    install_secret_redaction,
)


class _Request:
    def __init__(self, args=None, headers=None):
        self.args = {} if args is None else args
        self.headers = {} if headers is None else headers


def test_open_when_token_unset(monkeypatch):
    monkeypatch.delenv("YOUCUBE_TOKEN", raising=False)
    assert client_authorized(_Request()) is True


def test_blank_token_is_open(monkeypatch):
    monkeypatch.setenv("YOUCUBE_TOKEN", "   ")
    assert client_authorized(_Request()) is True


def test_query_token_matches(monkeypatch):
    monkeypatch.setenv("YOUCUBE_TOKEN", "s3cret")
    assert client_authorized(_Request(args={"token": "s3cret"})) is True
    assert client_authorized(_Request(args={"token": "nope"})) is False
    assert client_authorized(_Request()) is False


def test_bearer_header(monkeypatch):
    monkeypatch.setenv("YOUCUBE_TOKEN", "s3cret")
    request = _Request(headers={"Authorization": "Bearer s3cret"})
    assert extract_presented_token(request) == "s3cret"
    assert client_authorized(request) is True


def test_logs_redact_query_tokens():
    install_secret_redaction()
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("youcube-redact-test")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.info("GET /?token=supersecret HTTP/1.1")
    logger.info("Authorization: %s", "Bearer supersecret")
    handler.setFormatter(logging.Formatter("%(message)s %(request)s"))
    logger.info("OPEN", extra={"request": "ws://127.0.0.1/?token=supersecret"})
    output = stream.getvalue()
    assert "supersecret" not in output
    assert "token=***" in output
    assert "Bearer ***" in output
