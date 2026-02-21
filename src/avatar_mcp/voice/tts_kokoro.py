"""Kokoro TTS via ONNX runtime — free, local, Python 3.13 compatible."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
import soundfile as sf

from .tts_base import TTSEngine

log = logging.getLogger("avatar-mcp")

_MODEL_DIR = Path.home() / ".cache" / "avatar-mcp" / "kokoro"
_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
_MODEL_FILE = _MODEL_DIR / "kokoro-v1.0.onnx"
_VOICES_FILE = _MODEL_DIR / "voices-v1.0.bin"

_VOICES: dict[str, list[str]] = {
    "a": [
        "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica",
        "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
        "am_michael", "am_onyx", "am_puck", "am_santa",
    ],
    "b": [
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    ],
    "j": [
        "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    ],
}

_LANG_NAMES = {
    "a": "American English", "b": "British English", "j": "Japanese",
    "e": "Spanish", "f": "French", "h": "Hindi",
    "i": "Italian", "p": "Brazilian Portuguese", "z": "Mandarin Chinese",
}

_VOICE_TO_LANG = {
    "a": "en-us", "b": "en-gb", "j": "ja",
    "e": "es", "f": "fr", "h": "hi",
    "i": "it", "p": "pt-br", "z": "zh",
}


def _download_safe(url: str, dest: Path, label: str) -> None:
    """Download to a temp file, then atomically rename. Prevents corrupt partial downloads."""
    import socket
    from urllib.request import urlopen

    partial = dest.with_suffix(dest.suffix + ".partial")
    try:
        log.info("Downloading %s...", label)
        # 5-minute timeout per connection — generous but not infinite
        with urlopen(url, timeout=300) as resp, open(partial, "wb") as f:
            while chunk := resp.read(1 << 20):  # 1MB chunks
                f.write(chunk)
        partial.rename(dest)
        log.info("Downloaded %s to %s", label, dest)
    except (OSError, socket.timeout) as e:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download {label}: {e}") from e


def _ensure_models() -> tuple[str, str]:
    """Download model files on first use. Returns (model_path, voices_path)."""
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if not _MODEL_FILE.exists():
        _download_safe(_MODEL_URL, _MODEL_FILE, "Kokoro ONNX model (~300MB)")

    if not _VOICES_FILE.exists():
        _download_safe(_VOICES_URL, _VOICES_FILE, "Kokoro voices file (~28MB)")

    return str(_MODEL_FILE), str(_VOICES_FILE)


class KokoroTTSEngine(TTSEngine):
    def __init__(self, voice: str = "af_heart", speed: float = 1.0, lang_override: str = ""):
        self._voice = voice
        self._speed = speed
        self._lang_override = lang_override  # force this lang regardless of voice prefix
        self._temp_dir = Path(tempfile.mkdtemp(prefix="avatar_mcp_kokoro_"))
        self._counter = 0
        self._kokoro = None  # lazy init — model loads on first speak

    def _get_kokoro(self):
        if self._kokoro is None:
            from kokoro_onnx import Kokoro
            model_path, voices_path = _ensure_models()
            self._kokoro = Kokoro(model_path, voices_path)
            log.info("Kokoro ONNX engine ready")
        return self._kokoro

    async def synthesize(self, text: str, emotion: str, output_path: Path | None = None) -> Path:
        cleaned = self._clean_and_emote(text, emotion)
        if not cleaned:
            cleaned = "..."

        if output_path is None:
            self._counter += 1
            output_path = self._temp_dir / f"kokoro_{self._counter}.wav"

        if self._lang_override:
            lang = self._lang_override
        else:
            lang_code = self._voice[0] if self._voice else "a"
            lang = _VOICE_TO_LANG.get(lang_code, "en-us")

        kokoro = self._get_kokoro()
        samples, sample_rate = kokoro.create(
            cleaned, voice=self._voice, speed=self._speed, lang=lang,
        )
        sf.write(str(output_path), samples, sample_rate)
        return output_path

    async def list_voices(self) -> list[dict[str, str]]:
        result = []
        for lang_code, voices in _VOICES.items():
            lang_name = _LANG_NAMES.get(lang_code, lang_code)
            for v in voices:
                result.append({"id": v, "name": v, "language": lang_name})
        return result

    def set_voice(self, voice_id: str) -> None:
        self._voice = voice_id

    def get_current_voice(self) -> str:
        return self._voice

    @staticmethod
    def _clean_and_emote(text: str, emotion: str) -> str:
        """Strip markdown, add stage directions for emotion."""
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`[^`]+`", "", text)
        text = re.sub(r"[*_~#>|]", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = text[:500]

        prefixes = {
            "angry": "*irritated* ",
            "shy": "*quietly, embarrassed* ",
            "happy": "*cheerfully* ",
            "excited": "*excitedly* ",
            "sad": "*sadly, softly* ",
            "smug": "*smugly, confidently* ",
            "bratty": "*bratty* ",
        }
        return prefixes.get(emotion, "") + text
