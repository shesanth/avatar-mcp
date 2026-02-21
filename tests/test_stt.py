"""Tests for speech-to-text wake word logic and engine structure."""

from __future__ import annotations

from avatar_mcp.voice.stt_base import check_wake_word, STTEngine
from avatar_mcp.voice.stt_google import GoogleSTTEngine


class TestCheckWakeWord:
    def test_wake_word_detected(self):
        result = check_wake_word("claude what is the weather", ["claude"])
        assert result == "what is the weather"

    def test_wake_word_case_insensitive(self):
        result = check_wake_word("Claude do something", ["claude"])
        assert result == "do something"

    def test_wake_word_with_comma(self):
        result = check_wake_word("claude, help me", ["claude"])
        assert result == "help me"

    def test_multi_word_wake(self):
        result = check_wake_word("hey claude tell me a joke", ["hey claude"])
        assert result == "tell me a joke"

    def test_no_wake_word_returns_none(self):
        result = check_wake_word("what is the weather", ["claude", "hey claude"])
        assert result is None

    def test_wake_word_only_returns_none(self):
        result = check_wake_word("claude", ["claude"])
        assert result is None

    def test_empty_wake_words_passes_all(self):
        result = check_wake_word("anything goes here", [])
        assert result == "anything goes here"

    def test_multiple_wake_words(self):
        words = ["claude", "hey claude", "assistant"]
        assert check_wake_word("assistant do this", words) == "do this"
        assert check_wake_word("hey claude do that", words) == "do that"
        assert check_wake_word("claude do it", words) == "do it"

    def test_whitespace_in_remainder(self):
        result = check_wake_word("claude  tell me ", ["claude"])
        assert result == "tell me"


class TestEngineInterface:
    """Both engines must implement the STTEngine ABC."""

    def test_google_is_stt_engine(self):
        assert issubclass(GoogleSTTEngine, STTEngine)

    def test_realtime_is_stt_engine(self):
        from avatar_mcp.voice.stt_realtime import RealtimeSTTEngine
        assert issubclass(RealtimeSTTEngine, STTEngine)
