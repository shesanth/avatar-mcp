"""Standalone avatar display test — run this to verify the overlay window works.

Usage: python -m tests.test_avatar_standalone
(from the avatar-mcp directory)
"""

import multiprocessing
import sys
import time

# add src to path
sys.path.insert(0, "src")

from avatar_mcp.avatar.display import run_avatar_display
from avatar_mcp.avatar.sprites import ensure_all_placeholders
from avatar_mcp.config import AvatarConfig
from avatar_mcp.state import SharedState


def main():
    print("Generating placeholder sprites...")
    sprites = ensure_all_placeholders()
    for pose, path in sprites.items():
        print(f"  {pose}: {path}")

    print("\nStarting avatar display...")
    manager = multiprocessing.Manager()
    state = SharedState(manager)
    config = AvatarConfig(start_visible=True, start_x=200, start_y=200)

    proc = multiprocessing.Process(
        target=run_avatar_display,
        args=(state, config),
        daemon=True,
    )
    proc.start()

    print("Avatar is running! Cycling through poses every 2 seconds...")
    print("Press Ctrl+C to stop.\n")

    poses = ["idle", "thinking", "coding", "angry", "smug", "shy", "planning", "speaking", "listening"]
    try:
        i = 0
        while proc.is_alive():
            pose = poses[i % len(poses)]
            print(f"  -> {pose}")
            state.set("pose", pose)
            time.sleep(2)
            i += 1
    except KeyboardInterrupt:
        print("\nStopping...")
        state.send_command({"action": "quit"})
        proc.join(timeout=3)

    manager.shutdown()
    print("Done.")


if __name__ == "__main__":
    main()
