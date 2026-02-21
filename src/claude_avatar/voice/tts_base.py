"""Abstract TTS engine interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSEngine(ABC):
    @abstractmethod
    async def synthesize(self, text: str, emotion: str, output_path: Path | None = None) -> Path:
        """Generate audio file from text with emotional prosody. Returns path to file."""
        ...

    @abstractmethod
    async def list_voices(self) -> list[dict[str, str]]:
        """Return available voices as list of {id, name, language} dicts."""
        ...

    @abstractmethod
    def set_voice(self, voice_id: str) -> None:
        ...

    @abstractmethod
    def get_current_voice(self) -> str:
        ...
