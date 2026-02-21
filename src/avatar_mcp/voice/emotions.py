"""Emotion → prosody mapping for TTS engines."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProsodyParams:
    pitch: str
    rate: str
    volume: str


EMOTION_PROSODY: dict[str, ProsodyParams] = {
    "neutral": ProsodyParams(pitch="+0Hz",  rate="+0%",   volume="+0%"),
    "happy":   ProsodyParams(pitch="+10Hz", rate="+5%",   volume="+0%"),
    "sad":     ProsodyParams(pitch="-5Hz",  rate="-10%",  volume="-10%"),
    "excited": ProsodyParams(pitch="+15Hz", rate="+10%",  volume="+5%"),
    "angry":   ProsodyParams(pitch="-10Hz", rate="+5%",   volume="+5%"),
    "shy":     ProsodyParams(pitch="+5Hz",  rate="-5%",   volume="-20%"),
    "smug":    ProsodyParams(pitch="+5Hz",  rate="-3%",   volume="+0%"),
    "bratty":  ProsodyParams(pitch="+8Hz",  rate="+8%",   volume="+5%"),
}
