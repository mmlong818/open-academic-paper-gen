"""Secrets stay out of printed settings and out of logs.

A failing monkeypatch printed repr(settings) with every API key in it, and httpx logged each
OpenAlex request URL with its api_key query parameter.
"""
import logging

import pytest

from backend.core.config import Settings
from backend.core.log_redaction import RedactSecrets

SECRETS = {
    "openai_api_key": "sk-test-openai-123456",
    "zhipu_api_key": "zhipu-test-abcdef",
    "openalex_api_key": "openalex-test-xyz",
    "semantic_scholar_api_key": "s2-test-789",
    "secret_key": "app-secret-000",
    "database_url": "postgresql+asyncpg://u:db-pass-111@host:5432/db",
    "redis_url": "redis://:redis-pass-222@host:6379/0",
}


def _settings() -> Settings:
    return Settings(_env_file=None, **SECRETS)


def test_printed_settings_hold_no_secret():
    s = _settings()
    for text in (repr(s), str(s)):
        assert not [v for v in SECRETS.values() if v in text]
    assert "gpt" in repr(s)  # the rest is still there to debug with


def test_a_failed_monkeypatch_does_not_print_secrets(monkeypatch):
    s = _settings()
    with pytest.raises(AttributeError) as err:
        monkeypatch.setattr(s, "no_such_field", "x")
    assert not [v for v in SECRETS.values() if v in str(err.value)]


def _render(msg, *args) -> str:
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1, msg, args, None)
    assert RedactSecrets().filter(record)
    return record.getMessage()


def test_api_keys_in_logged_urls_are_masked():
    url = "https://api.openalex.org/works?search=rag&mailto=a%40b.org&api_key=openalex-test-xyz&page=2"
    line = _render('HTTP Request: %s %s "%s %d %s"', "GET", url, "HTTP/1.1", 200, "OK")
    assert "openalex-test-xyz" not in line
    assert "api_key=***&page=2" in line and "search=rag" in line


def test_other_log_lines_are_unchanged():
    assert _render("screened %d papers", 8) == "screened 8 papers"
