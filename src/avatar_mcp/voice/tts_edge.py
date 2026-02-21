"""Edge TTS implementation — free, no API key, neural voices."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import edge_tts

from .emotions import EMOTION_PROSODY
from .tts_base import TTSEngine


class EdgeTTSEngine(TTSEngine):
    def __init__(self, voice: str = "ja-JP-NanamiNeural"):
        self._voice = voice
        self._temp_dir = Path(tempfile.mkdtemp(prefix="avatar_mcp_tts_"))
        self._counter = 0

    async def synthesize(self, text: str, emotion: str, output_path: Path | None = None) -> Path:
        prosody = EMOTION_PROSODY.get(emotion, EMOTION_PROSODY["neutral"])
        cleaned = self._clean_text(text)
        if not cleaned:
            cleaned = "..."

        if output_path is None:
            self._counter += 1
            output_path = self._temp_dir / f"tts_{self._counter}.mp3"

        communicate = edge_tts.Communicate(
            text=cleaned,
            voice=self._voice,
            rate=prosody.rate,
            volume=prosody.volume,
            pitch=prosody.pitch,
        )
        await communicate.save(str(output_path))
        return output_path

    async def list_voices(self) -> list[dict[str, str]]:
        voices = await edge_tts.list_voices()
        return [
            {"id": v["ShortName"], "name": v["FriendlyName"], "language": v["Locale"]}
            for v in voices
        ]

    def set_voice(self, voice_id: str) -> None:
        self._voice = voice_id

    def get_current_voice(self) -> str:
        return self._voice

    @staticmethod
    def _clean_text(text: str) -> str:
        """Strip markdown and excess whitespace, cap length."""
        text = re.sub(r"[*_~`#>]", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [text](url) → text
        text = re.sub(r"\s+", " ", text).strip()
        return text[:500]
