import sys
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.ai import _fmt, stream_chat, stream_insights


# ── _fmt ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("b,expected", [
    (0,           "0.0 B"),
    (1023,        "1023.0 B"),
    (1024,        "1.0 KB"),
    (1024 * 1024, "1.0 MB"),
    (1024 ** 3,   "1.0 GB"),
    (1024 ** 4,   "1.0 TB"),
    (1024 ** 5,   "1.0 PB"),
])
def test_fmt_boundaries(b, expected):
    assert _fmt(b) == expected


# ── stream_insights — guard clauses ──────────────────────────────────────────

def test_stream_insights_no_api_key(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    chunks = list(stream_insights(db, []))

    assert len(chunks) > 0
    combined = "".join(chunks)
    assert "ANTHROPIC_API_KEY" in combined


def test_stream_insights_no_anthropic_package(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setitem(sys.modules, "anthropic", None)

    chunks = list(stream_insights(db, []))

    combined = "".join(chunks)
    assert "anthropic" in combined.lower()


def test_stream_insights_api_error_yields_graceful_message(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")

    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_client.messages.stream.side_effect = Exception("network error")

    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    chunks = list(stream_insights(db, []))

    combined = "".join(chunks)
    assert "unavailable" in combined.lower() or "error" in combined.lower()


# ── stream_chat — guard clauses ───────────────────────────────────────────────

def test_stream_chat_no_api_key(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    chunks = list(stream_chat(db, "how many files do I have?"))

    combined = "".join(chunks)
    assert "ANTHROPIC_API_KEY" in combined


def test_stream_chat_no_anthropic_package(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setitem(sys.modules, "anthropic", None)

    chunks = list(stream_chat(db, "test question"))

    combined = "".join(chunks)
    assert "anthropic" in combined.lower()


def test_stream_chat_api_error_yields_graceful_message(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")

    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_client.messages.stream.side_effect = Exception("timeout")

    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    chunks = list(stream_chat(db, "what is my largest file?"))

    combined = "".join(chunks)
    assert "error" in combined.lower() or "unavailable" in combined.lower()
