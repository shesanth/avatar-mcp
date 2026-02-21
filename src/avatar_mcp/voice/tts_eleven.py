"""ElevenLabs TTS implementation — premium voices."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .tts_base import TTSEngine


class ElevenLabsTTSEngine(TTSEngine):
    def __init__(self, api_key: str, voice_id: str, model: str = "eleven_flash_v2_5"):
        from elevenlabs.client import AsyncElevenLabs

        self._client = AsyncElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._model = model
        self._temp_dir = Path(tempfile.mkdtemp(prefix="avatar_mcp_eleven_"))
        self._counter = 0

    async def synthesize(self, text: str, emotion: str, output_path: Path | None = None) -> Path:
        emotional_text = self._add_emotion_context(text, emotion)

        if output_path is None:
            self._counter += 1
            output_path = self._temp_dir / f"eleven_{self._counter}.mp3"

        audio_gen = await self._client.text_to_speech.convert(
            text=emotional_text,
            voice_id=self._voice_id,
            model_id=self._model,
            output_format="mp3_44100_128",
        )

        with open(output_path, "wb") as f:
            async for chunk in audio_gen:
                f.write(chunk)

        return output_path

    async def list_voices(self) -> list[dict[str, str]]:
        response = await self._client.voices.get_all()
        return [
            {"id": v.voice_id, "name": v.name, "language": "multi"}
            for v in response.voices
        ]

    def set_voice(self, voice_id: str) -> None:
        self._voice_id = voice_id

    def get_current_voice(self) -> str:
        return self._voice_id

    @staticmethod
    def _add_emotion_context(text: str, emotion: str) -> str:
        """ElevenLabs infers emotion from text context — prepend stage directions."""
        prefixes = {
            "angry": "*irritated* ",
            "shy": "*quietly, embarrassed* ",
            "happy": "*cheerfully* ",
            "excited": "*excitedly* ",
            "sad": "*sadly* ",
            "smug": "*smugly* ",
            "bratty": "*bratty* ",
        }
        return prefixes.get(emotion, "") + text[:500]
