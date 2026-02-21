"""Speech-to-text via Google Speech API (speech_recognition package)."""

from __future__ import annotations

import time
from typing import Callable

import speech_recognition as sr

from ..config import STTConfig


class SpeechListener:
    def __init__(self, config: STTConfig, on_text: Callable[[str], None]):
        self._config = config
        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = config.energy_threshold
        self._mic = sr.Microphone()
        self._on_text = on_text
        self._stop_fn: Callable | None = None
        self._muted = False
        self._last_time = 0.0

    def start(self) -> None:
        with self._mic as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=1)

        self._stop_fn = self._recognizer.listen_in_background(
            self._mic,
            self._on_audio,
        )

    def stop(self) -> None:
        if self._stop_fn:
            self._stop_fn(wait_for_stop=True)
            self._stop_fn = None

    def toggle_mute(self) -> None:
        self._muted = not self._muted

    @property
    def is_running(self) -> bool:
        return self._stop_fn is not None

    def _on_audio(self, recognizer: sr.Recognizer, audio: sr.AudioData) -> None:
        if self._muted:
            return

        now = time.time()
        if now - self._last_time < self._config.cooldown_seconds:
            return

        try:
            text = recognizer.recognize_google(audio, language=self._config.language)
            if text and text.strip():
                self._last_time = now
                self._on_text(text.strip())
        except sr.UnknownValueError:
            pass
        except sr.RequestError:
            pass
