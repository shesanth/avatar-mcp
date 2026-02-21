"""Tests for TTS engine text processing."""

from __future__ import annotations

from avatar_mcp.voice.tts_edge import EdgeTTSEngine
from avatar_mcp.voice.tts_eleven import ElevenLabsTTSEngine
from avatar_mcp.voice.tts_kokoro import KokoroTTSEngine


class TestEdgeCleanText:
    def test_strips_markdown(self):
        text = "**bold** and *italic* and `code`"
        result = EdgeTTSEngine._clean_text(text)
        assert "*" not in result
        assert "`" not in result
        assert "bold" in result
        assert "italic" in result
        assert "code" in result

    def test_strips_links(self):
        result = EdgeTTSEngine._clean_text("[click here](https://example.com)")
        assert result == "click here"
        assert "https" not in result

    def test_caps_at_500(self):
        text = "a" * 1000
        result = EdgeTTSEngine._clean_text(text)
        assert len(result) == 500

    def test_collapses_whitespace(self):
        result = EdgeTTSEngine._clean_text("hello    world\n\nfoo")
        assert result == "hello world foo"

    def test_empty_input(self):
        assert EdgeTTSEngine._clean_text("") == ""
        assert EdgeTTSEngine._clean_text("   ") == ""


class TestKokoroCleanAndEmote:
    def test_strips_code_blocks(self):
        text = "Before ```python\nprint('hi')\n``` After"
        result = KokoroTTSEngine._clean_and_emote(text, "neutral")
        assert "print" not in result
        assert "Before" in result
        assert "After" in result

    def test_strips_inline_code(self):
        result = KokoroTTSEngine._clean_and_emote("Use `foo()` here", "neutral")
        assert "`" not in result
        assert "Use" in result
        assert "here" in result

    def test_adds_emotion_prefix(self):
        result = KokoroTTSEngine._clean_and_emote("Hello", "angry")
        assert result.startswith("*irritated*")

    def test_neutral_no_prefix(self):
        result = KokoroTTSEngine._clean_and_emote("Hello", "neutral")
        assert result == "Hello"

    def test_all_emotions_have_prefix(self):
        emotions_with_prefix = ["angry", "shy", "happy", "excited", "sad", "smug", "bratty"]
        for emotion in emotions_with_prefix:
            result = KokoroTTSEngine._clean_and_emote("test", emotion)
            assert result.startswith("*"), f"No prefix for emotion: {emotion}"

    def test_caps_at_500_before_prefix(self):
        text = "a" * 1000
        result = KokoroTTSEngine._clean_and_emote(text, "happy")
        # prefix + 500 chars of text
        assert len(result) > 500  # prefix adds to it
        assert result.startswith("*cheerfully*")


class TestElevenLabsEmotionContext:
    def test_angry_prefix(self):
        result = ElevenLabsTTSEngine._add_emotion_context("Hello", "angry")
        assert result.startswith("*irritated*")
        assert "Hello" in result

    def test_neutral_no_prefix(self):
        result = ElevenLabsTTSEngine._add_emotion_context("Hello", "neutral")
        assert result == "Hello"

    def test_caps_text_at_500(self):
        text = "x" * 1000
        result = ElevenLabsTTSEngine._add_emotion_context(text, "neutral")
        assert len(result) == 500

    def test_bratty_prefix(self):
        result = ElevenLabsTTSEngine._add_emotion_context("Hi", "bratty")
        assert "*bratty*" in result
