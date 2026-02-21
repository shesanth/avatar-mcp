"""Tests for speech-to-text wake word logic."""

from __future__ import annotations

from avatar_mcp.voice.stt import _check_wake_word


class TestCheckWakeWord:
    def test_wake_word_detected(self):
        result = _check_wake_word("claude what is the weather", ["claude"])
        assert result == "what is the weather"

    def test_wake_word_case_insensitive(self):
        result = _check_wake_word("Claude do something", ["claude"])
        assert result == "do something"

    def test_wake_word_with_comma(self):
        result = _check_wake_word("claude, help me", ["claude"])
        assert result == "help me"

    def test_multi_word_wake(self):
        result = _check_wake_word("hey claude tell me a joke", ["hey claude"])
        assert result == "tell me a joke"

    def test_no_wake_word_returns_none(self):
        result = _check_wake_word("what is the weather", ["claude", "hey claude"])
        assert result is None

    def test_wake_word_only_returns_none(self):
        result = _check_wake_word("claude", ["claude"])
        assert result is None

    def test_empty_wake_words_passes_all(self):
        result = _check_wake_word("anything goes here", [])
        assert result == "anything goes here"

    def test_multiple_wake_words(self):
        words = ["claude", "hey claude", "assistant"]
        assert _check_wake_word("assistant do this", words) == "do this"
        assert _check_wake_word("hey claude do that", words) == "do that"
        assert _check_wake_word("claude do it", words) == "do it"

    def test_whitespace_in_remainder(self):
        # recognizer output is pre-trimmed, so test trimmed input
        result = _check_wake_word("claude  tell me ", ["claude"])
        assert result == "tell me"
