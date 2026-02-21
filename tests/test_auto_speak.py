"""Tests for the auto_speak hook script text extraction."""

from __future__ import annotations

import sys
from pathlib import Path

# auto_speak.py is a standalone script, not a package module — add scripts/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from auto_speak import extract_speakable_text


class TestExtractSpeakableText:
    def test_string_content(self):
        hook = {"last_assistant_message": "Hello, how are you?"}
        assert extract_speakable_text(hook) == "Hello, how are you?"

    def test_list_content_blocks(self):
        hook = {
            "last_assistant_message": [
                {"type": "text", "text": "First part."},
                {"type": "text", "text": "Second part."},
            ]
        }
        result = extract_speakable_text(hook)
        assert "First part." in result
        assert "Second part." in result

    def test_list_with_non_text_blocks(self):
        hook = {
            "last_assistant_message": [
                {"type": "tool_use", "name": "read_file"},
                {"type": "text", "text": "Here is the result."},
            ]
        }
        result = extract_speakable_text(hook)
        assert "Here is the result." in result

    def test_empty_content(self):
        assert extract_speakable_text({}) == ""
        assert extract_speakable_text({"last_assistant_message": ""}) == ""
        assert extract_speakable_text({"last_assistant_message": "   "}) == ""

    def test_strips_code_blocks(self):
        text = "Here is code:\n```python\nprint('hi')\n```\nDone."
        hook = {"last_assistant_message": text}
        result = extract_speakable_text(hook)
        assert "print" not in result
        assert "Done." in result

    def test_strips_inline_code(self):
        hook = {"last_assistant_message": "Use `foo()` to call it."}
        result = extract_speakable_text(hook)
        assert "`" not in result
        assert "foo()" not in result

    def test_strips_markdown_formatting(self):
        hook = {"last_assistant_message": "**bold** and *italic* and # heading"}
        result = extract_speakable_text(hook)
        assert "*" not in result
        assert "#" not in result

    def test_strips_links(self):
        hook = {"last_assistant_message": "See [docs](https://example.com) for more."}
        result = extract_speakable_text(hook)
        assert "docs" in result
        assert "https" not in result
        assert "[" not in result

    def test_caps_at_500(self):
        hook = {"last_assistant_message": "a" * 1000}
        result = extract_speakable_text(hook)
        assert len(result) == 500

    def test_collapses_whitespace(self):
        hook = {"last_assistant_message": "hello    world\n\nfoo"}
        result = extract_speakable_text(hook)
        assert result == "hello world foo"
