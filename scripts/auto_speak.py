"""Stop hook script — reads assistant response from stdin, speaks it aloud.

Reads config.toml to determine TTS engine (edge, kokoro, etc).
Runs async in background so it never blocks Claude Code.
Strips markdown/code blocks to only speak the conversational text.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import pygame

_LOCK_FILE = Path.home() / ".claude" / "auto-speak.lock"

# find config.toml relative to this script
_SCRIPT_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = _SCRIPT_DIR.parent / "config.toml"


def _load_tts_config() -> dict:
    """Read [tts] section from config.toml, or return defaults."""
    try:
        import tomllib
        with open(_CONFIG_PATH, "rb") as f:
            raw = tomllib.load(f)
        return raw.get("tts", {})
    except Exception:
        return {}


_lock_fh = None


def _acquire_lock() -> bool:
    """Acquire file lock so only one auto_speak runs at a time."""
    import msvcrt

    global _lock_fh
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        _lock_fh = open(_LOCK_FILE, "w")
        msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
        return True
    except (OSError, IOError):
        if _lock_fh:
            _lock_fh.close()
            _lock_fh = None
        return False


def _release_lock() -> None:
    global _lock_fh
    try:
        if _lock_fh:
            import msvcrt
            try:
                msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            _lock_fh.close()
            _lock_fh = None
            _LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def extract_speakable_text(hook_input: dict) -> str:
    """Pull the assistant's text from the Stop hook JSON."""
    content = hook_input.get("last_assistant_message", "")

    # content can be a string or list of content blocks
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        text = "\n".join(parts)
    elif isinstance(content, str):
        text = content
    else:
        return ""

    if not text.strip():
        return ""

    # strip code blocks — nobody wants to hear code read aloud
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"[*_~#>|]", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\|.*\|", "", text)
    text = re.sub(r"[-:]{3,}", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


async def speak_edge(text: str, voice: str) -> None:
    import edge_tts
    tmp = Path(tempfile.mktemp(suffix=".mp3", prefix="auto_speak_"))
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice, volume="-30%")
        await communicate.save(str(tmp))
        _play_file(str(tmp), frequency=44100)
    finally:
        tmp.unlink(missing_ok=True)


def speak_kokoro(text: str, voice: str, lang_override: str = "") -> None:
    import soundfile as sf
    from kokoro_onnx import Kokoro

    model_dir = Path.home() / ".cache" / "avatar-mcp" / "kokoro"
    model_path = str(model_dir / "kokoro-v1.0.onnx")
    voices_path = str(model_dir / "voices-v1.0.bin")

    if lang_override:
        lang = lang_override
    else:
        lang_code = voice[0] if voice else "a"
        lang_map = {"a": "en-us", "b": "en-gb", "j": "ja", "e": "es", "f": "fr"}
        lang = lang_map.get(lang_code, "en-us")

    kokoro = Kokoro(model_path, voices_path)
    tmp = Path(tempfile.mktemp(suffix=".wav", prefix="auto_speak_"))

    try:
        samples, sample_rate = kokoro.create(text, voice=voice, speed=1.0, lang=lang)
        sf.write(str(tmp), samples, sample_rate)
        _play_file(str(tmp), frequency=sample_rate)
    finally:
        tmp.unlink(missing_ok=True)


def _play_file(path: str, frequency: int = 44100) -> None:
    pygame.mixer.init(frequency=frequency, size=-16, channels=2, buffer=2048)
    pygame.mixer.music.load(path)
    pygame.mixer.music.set_volume(0.5)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(50)
    pygame.mixer.quit()


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return

    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        return

    text = extract_speakable_text(hook_input)
    if not text:
        return

    if not _acquire_lock():
        return  # another instance is speaking

    try:
        tts_cfg = _load_tts_config()
        engine = tts_cfg.get("engine", "edge")
        voice = tts_cfg.get("voice", "ja-JP-NanamiNeural")

        if engine == "kokoro":
            kokoro_lang = tts_cfg.get("kokoro_lang", "")
            speak_kokoro(text, voice, lang_override=kokoro_lang)
        else:
            asyncio.run(speak_edge(text, voice))
    finally:
        _release_lock()


if __name__ == "__main__":
    main()
