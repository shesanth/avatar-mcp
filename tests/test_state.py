"""Tests for SharedState."""

from __future__ import annotations


class TestSharedState:
    def test_get_set(self, shared_state):
        shared_state.set("pose", "thinking")
        assert shared_state.get("pose") == "thinking"

    def test_set_many(self, shared_state):
        shared_state.set_many(pose="coding", visible=False, emotion="happy")
        assert shared_state.get("pose") == "coding"
        assert shared_state.get("visible") is False
        assert shared_state.get("emotion") == "happy"

    def test_snapshot(self, shared_state):
        snap = shared_state.snapshot()
        assert isinstance(snap, dict)
        assert "pose" in snap
        assert "visible" in snap
        assert "emotion" in snap
        assert snap["pose"] == "idle"
        assert snap["visible"] is True

    def test_snapshot_is_copy(self, shared_state):
        snap = shared_state.snapshot()
        snap["pose"] = "angry"
        assert shared_state.get("pose") == "idle"  # original unchanged

    def test_defaults(self, shared_state):
        assert shared_state.get("pose") == "idle"
        assert shared_state.get("visible") is True
        assert shared_state.get("emotion") == "neutral"
        assert shared_state.get("is_speaking") is False
        assert shared_state.get("is_listening") is False


class TestCommandQueue:
    def test_send_and_poll(self, shared_state):
        shared_state.send_command({"action": "quit"})
        cmd = shared_state.poll_command()
        assert cmd == {"action": "quit"}

    def test_poll_empty_returns_none(self, shared_state):
        assert shared_state.poll_command() is None

    def test_fifo_order(self, shared_state):
        shared_state.send_command({"action": "first"})
        shared_state.send_command({"action": "second"})
        assert shared_state.poll_command()["action"] == "first"
        assert shared_state.poll_command()["action"] == "second"
        assert shared_state.poll_command() is None
