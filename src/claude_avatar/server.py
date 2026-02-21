"""MCP server entry point — exposes avatar/voice tools to Claude Code."""

from __future__ import annotations

import logging
import multiprocessing
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from .config import AppConfig
from .lifecycle import Lifecycle
from .state import VALID_EMOTIONS, VALID_POSES, SharedState

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
log = logging.getLogger("claude-avatar")


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
    log.info("claude-avatar started")

    try:
        yield AppContext(config=config, state=state, lifecycle=lifecycle)
    finally:
        lifecycle.stop_all()
        manager.shutdown()
        log.info("claude-avatar stopped")


mcp = FastMCP("claude-avatar", lifespan=app_lifespan)


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
async def set_emotion(emotion: str) -> str:
    """Set the avatar's emotional state. Changes the displayed pose to match.
    Valid emotions: neutral, happy, sad, excited, angry, shy, smug, bratty."""
    ctx = mcp.get_context()
    lc: Lifecycle = ctx.request_context.lifespan_context.lifecycle
    if emotion not in VALID_EMOTIONS:
        return f"Invalid emotion '{emotion}'. Valid: {', '.join(sorted(VALID_EMOTIONS))}"
    return lc.set_emotion(emotion)


@mcp.tool()
async def set_pose(pose: str) -> str:
    """Directly set the avatar's displayed pose.
    Valid poses: idle, thinking, coding, angry, smug, shy, planning, speaking, listening, drag."""
    ctx = mcp.get_context()
    lc: Lifecycle = ctx.request_context.lifespan_context.lifecycle
    if pose not in VALID_POSES:
        return f"Invalid pose '{pose}'. Valid: {', '.join(sorted(VALID_POSES))}"
    return lc.set_pose(pose)


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
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
