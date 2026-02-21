"""Config loader — parses config.toml into typed dataclasses."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AvatarConfig:
    start_visible: bool = True
    start_x: int = 100
    start_y: int = 100
    sprite_scale: float = 1.0
    sprite_directory: str = ""
    poll_interval_ms: int = 50


@dataclass
class TTSConfig:
    engine: str = "edge"
    voice: str = "ja-JP-NanamiNeural"
    kokoro_lang: str = ""  # override auto-detected lang for kokoro (e.g. "en-us" with a Japanese voice)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_flash_v2_5"


@dataclass
class STTConfig:
    enabled: bool = False
    language: str = "en-US"
    cooldown_seconds: float = 1.0
    energy_threshold: int = 150
    pause_threshold: float = 2.0       # seconds of silence before phrase is considered complete
    phrase_threshold: float = 0.1       # minimum seconds of speech to register as a phrase
    non_speaking_duration: float = 1.0  # seconds of silence to keep on both sides of recording
    wake_words: list[str] = field(default_factory=lambda: ["claude", "hey claude"])


@dataclass
class BehaviorConfig:
    auto_speak: bool = True


@dataclass
class AppConfig:
    avatar: AvatarConfig = field(default_factory=AvatarConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> AppConfig:
        """Load config from TOML. Search order: explicit path, ./config.toml, defaults."""
        search_paths = [
            path,
            Path.cwd() / "config.toml",
            Path(__file__).resolve().parent.parent.parent / "config.toml",
        ]

        for p in search_paths:
            if p and p.is_file():
                with open(p, "rb") as f:
                    raw = tomllib.load(f)
                return cls._from_dict(raw)

        return cls()

    @classmethod
    def _from_dict(cls, raw: dict) -> AppConfig:
        return cls(
            avatar=AvatarConfig(**{k: v for k, v in raw.get("avatar", {}).items() if k in AvatarConfig.__dataclass_fields__}),
            tts=TTSConfig(**{k: v for k, v in raw.get("tts", {}).items() if k in TTSConfig.__dataclass_fields__}),
            stt=STTConfig(**{k: v for k, v in raw.get("stt", {}).items() if k in STTConfig.__dataclass_fields__}),
            behavior=BehaviorConfig(**{k: v for k, v in raw.get("behavior", {}).items() if k in BehaviorConfig.__dataclass_fields__}),
        )
