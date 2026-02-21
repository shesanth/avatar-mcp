"""Animation sequence definitions — lists of (pose, duration_ms) frames."""

from __future__ import annotations

ANIMATIONS: dict[str, dict] = {
    "thinking_loop": {
        "frames": [("thinking", 600), ("idle", 300), ("thinking", 600)],
        "loop": True,
    },
    "angry_reaction": {
        "frames": [("angry", 1000), ("idle", 300)],
        "loop": False,
    },
    "coding_session": {
        "frames": [("coding", 1000), ("thinking", 400), ("coding", 1000)],
        "loop": True,
    },
    "smug_wiggle": {
        "frames": [("smug", 500), ("idle", 200), ("smug", 500)],
        "loop": False,
    },
    "shy_peek": {
        "frames": [("shy", 800), ("idle", 200), ("shy", 400)],
        "loop": False,
    },
    "planning_mode": {
        "frames": [("planning", 800), ("thinking", 400), ("planning", 800)],
        "loop": True,
    },
}
