"""MCP server entry point — exposes avatar/voice tools to Claude Code."""

from __future__ import annotations

import atexit
import logging
import multiprocessing
import os
import signal
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import AppConfig
from .lifecycle import Lifecycle, _assign_all_children, _is_parent_alive
from .state import VALID_EMOTIONS, VALID_POSES, SharedState

# Log to both stderr and a file for post-mortem debugging
_log_file = Path.home() / ".claude" / "avatar-mcp.log"
_log_file.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(_log_file), mode="a"),
    ],
)
log = logging.getLogger("avatar-mcp")

# Module-level refs so atexit/signal handlers can reach them
_cleanup_refs: dict = {}


def _force_cleanup() -> None:
    """Last-resort cleanup — called by atexit, signal handlers, and parent watchdog.

    Tries graceful shutdown first, then scorched-earth kills every child process.
    """
    lc = _cleanup_refs.pop("lifecycle", None)
    mgr = _cleanup_refs.pop("manager", None)
    if lc:
        try:
            lc.stop_all()
        except Exception:
            pass
    if mgr:
        try:
            mgr.shutdown()
        except Exception:
            pass

    # clean up pose signal file
    try:
        _POSE_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    # nuclear option: kill every remaining child process
    for child in multiprocessing.active_children():
        try:
            log.info("Force-killing surviving child pid=%s", child.pid)
            child.kill()
            child.join(timeout=2)
        except Exception:
            pass


def _signal_handler(signum, frame) -> None:
    log.info("Received signal %s, cleaning up", signum)
    _force_cleanup()
    sys.exit(0)


def _start_parent_watchdog() -> None:
    """Start a daemon thread that monitors the parent process (Claude Code).

    When the parent dies (VSCode closed, Claude Code killed, etc.), this
    thread runs _force_cleanup() and then os._exit() to ensure ALL child
    processes are terminated.  This is the most reliable cleanup mechanism
    because it doesn't depend on signals, atexit, or Job Objects.
    """
    ppid = os.getppid()
    log.info("Parent watchdog started (parent pid=%d)", ppid)

    def _watchdog():
        while True:
            time.sleep(2)
            if not _is_parent_alive(ppid):
                log.info("Parent process (pid=%d) is dead — force cleaning up", ppid)
                _force_cleanup()
                # os._exit bypasses atexit, finally blocks, etc. — scorched earth
                os._exit(0)

    t = threading.Thread(target=_watchdog, daemon=True, name="parent-watchdog")
    t.start()


_POSE_FILE = Path.home() / ".claude" / "avatar-pose"


def _start_pose_watcher(lifecycle: Lifecycle) -> None:
    """Watch ~/.claude/avatar-pose for hook-triggered pose changes.

    Claude Code hooks write a pose name to this file:
    - UserPromptSubmit → thinking
    - PreToolUse → coding/thinking/planning (by tool matcher)
    - PermissionRequest → listening (approval needed)
    - Stop → listening (turn done)

    No debounce needed — "listening" only comes from PermissionRequest and Stop,
    not from a spammy catch-all PostToolUse.
    """
    def _watcher():
        last_mtime = 0.0
        while True:
            time.sleep(0.1)
            try:
                if _POSE_FILE.exists():
                    mtime = _POSE_FILE.stat().st_mtime
                    if mtime != last_mtime:
                        last_mtime = mtime
                        pose = _POSE_FILE.read_text().strip()
                        if pose in VALID_POSES:
                            lifecycle.set_hook_pose(pose)
            except Exception:
                pass

    t = threading.Thread(target=_watcher, daemon=True, name="pose-watcher")
    t.start()
    log.info("Pose file watcher started (%s)", _POSE_FILE)


@dataclass
class AppContext:
    config: AppConfig
    state: SharedState
    lifecycle: Lifecycle


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    config = AppConfig.load()
    manager = multiprocessing.Manager()
    state = SharedState(manager)

    state.set_many(
        visible=config.avatar.start_visible,
        position_x=config.avatar.start_x,
        position_y=config.avatar.start_y,
    )

    lifecycle = Lifecycle(config, state)
    lifecycle.start_all()

    # assign ALL child processes (Manager, display, STT workers) to
    # Job Object + PID file — must run after start_all() so libraries
    # like RealtimeSTT have finished spawning their workers
    _assign_all_children()

    # watch for hook-triggered pose changes
    _start_pose_watcher(lifecycle)

    # store refs for atexit/signal cleanup
    _cleanup_refs["lifecycle"] = lifecycle
    _cleanup_refs["manager"] = manager

    log.info("avatar-mcp started")

    try:
        yield AppContext(config=config, state=state, lifecycle=lifecycle)
    finally:
        _cleanup_refs.clear()
        lifecycle.stop_all()
        manager.shutdown()
        log.info("avatar-mcp stopped")


mcp = FastMCP("avatar-mcp", lifespan=app_lifespan)


# --- Tools ---


@mcp.tool()
async def speak(text: str, emotion: str = "neutral") -> str:
    """Speak text aloud with TTS. Emotion affects voice prosody and avatar pose.
    Valid emotions: neutral, happy, sad, excited, angry, shy, smug, bratty."""
    ctx = mcp.get_context()
    lc: Lifecycle = ctx.request_context.lifespan_context.lifecycle
    emotion = emotion if emotion in VALID_EMOTIONS else "neutral"
    return await lc.speak(text, emotion)


@mcp.tool()
async def show_avatar() -> str:
    """Make the avatar visible on screen."""
    ctx = mcp.get_context()
    lc: Lifecycle = ctx.request_context.lifespan_context.lifecycle
    return lc.show_avatar()


@mcp.tool()
async def hide_avatar() -> str:
    """Hide the avatar from screen."""
    ctx = mcp.get_context()
    lc: Lifecycle = ctx.request_context.lifespan_context.lifecycle
    return lc.hide_avatar()


@mcp.tool()
async def start_listening() -> str:
    """Start speech recognition. Recognized text is injected into Claude Code as [VOICE] messages."""
    ctx = mcp.get_context()
    lc: Lifecycle = ctx.request_context.lifespan_context.lifecycle
    return lc.start_listening()


@mcp.tool()
async def stop_listening() -> str:
    """Stop speech recognition."""
    ctx = mcp.get_context()
    lc: Lifecycle = ctx.request_context.lifespan_context.lifecycle
    return lc.stop_listening()


@mcp.tool()
async def set_voice(voice_id: str, engine: str | None = None) -> str:
    """Change the TTS voice. Optionally switch engine ('edge' or 'elevenlabs').
    Use list_voices to see available voice IDs."""
    ctx = mcp.get_context()
    lc: Lifecycle = ctx.request_context.lifespan_context.lifecycle
    return await lc.set_voice(voice_id, engine)


@mcp.tool()
async def list_voices(engine: str | None = None) -> str:
    """List available TTS voices for the current or specified engine ('edge' or 'elevenlabs')."""
    ctx = mcp.get_context()
    lc: Lifecycle = ctx.request_context.lifespan_context.lifecycle
    return await lc.list_voices(engine)


def main():
    import multiprocessing
    multiprocessing.freeze_support()

    # safety net: atexit fires on normal interpreter shutdown
    atexit.register(_force_cleanup)

    # catch SIGINT (Ctrl+C); SIGTERM on Unix (Windows ignores it but costs nothing)
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    # monitor parent (Claude Code) — if it dies, force-kill everything
    _start_parent_watchdog()

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
