"""Shared state between MCP server and avatar display via multiprocessing.Manager."""

from __future__ import annotations

from multiprocessing import Manager
from multiprocessing.managers import SyncManager
from typing import Any, Literal

AvatarPose = Literal[
    "idle", "thinking", "coding", "angry", "smug",
    "shy", "planning", "speaking", "listening", "drag",
]

VALID_POSES: set[str] = {
    "idle", "thinking", "coding", "angry", "smug",
    "shy", "planning", "speaking", "listening", "drag",
}

VALID_EMOTIONS: set[str] = {
    "neutral", "happy", "sad", "excited", "angry", "shy", "smug", "bratty",
}

# Maps emotion → default pose
EMOTION_POSE_MAP: dict[str, str] = {
    "neutral": "idle",
    "happy": "smug",
    "sad": "shy",
    "excited": "smug",
    "angry": "angry",
    "shy": "shy",
    "smug": "smug",
    "bratty": "angry",
}


class SharedState:
    """Thread/process-safe shared state using multiprocessing.Manager proxies."""

    def __init__(self, manager: SyncManager):
        self._state = manager.dict({
            "pose": "idle",
            "visible": True,
            "position_x": 100,
            "position_y": 100,
            "emotion": "neutral",
            "is_speaking": False,
            "is_listening": False,
        })
        self._command_queue = manager.Queue()

    def get(self, key: str) -> Any:
        return self._state[key]

    def set(self, key: str, value: Any) -> None:
        self._state[key] = value

    def set_many(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            self._state[k] = v

    def snapshot(self) -> dict[str, Any]:
        return dict(self._state)

    def send_command(self, cmd: dict) -> None:
        self._command_queue.put(cmd)

    def poll_command(self) -> dict | None:
        try:
            return self._command_queue.get_nowait()
        except Exception:
            return None
