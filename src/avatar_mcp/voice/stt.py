"""Speech-to-text via Google Speech API (speech_recognition package).

Supports wake word activation — listens to everything but only forwards
text that starts with a wake word (e.g. 'claude'). This way
STT can stay hot while the user talks to friends on Discord etc.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

import speech_recognition as sr

from ..config import STTConfig

log = logging.getLogger("avatar-mcp")


def _check_wake_word(text: str, wake_words: list[str]) -> str | None:
    """If text starts with a wake word, return the text after it. Otherwise None."""
    if not wake_words:
        return text  # no wake words configured = everything passes through

    lower = text.lower().strip()
    for word in wake_words:
        w = word.lower().strip()
        if lower.startswith(w):
            remainder = text[len(w):].strip().lstrip(",").strip()
            return remainder if remainder else None
    return None


class SpeechListener:
    def __init__(self, config: STTConfig, on_text: Callable[[str], None]):
        self._config = config
        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = config.energy_threshold
        self._recognizer.pause_threshold = config.pause_threshold
        self._recognizer.phrase_threshold = config.phrase_threshold
        self._recognizer.non_speaking_duration = config.non_speaking_duration
        self._mic = sr.Microphone()
        self._on_text = on_text
        self._stop_fn: Callable | None = None
        self._muted = False
        self._last_time = 0.0
        self._last_text = ""

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
            if not text or not text.strip():
                return

            # wake word filtering
            message = _check_wake_word(text.strip(), self._config.wake_words)
            if message is None:
                return  # not talking to us

            # deduplicate — Google Speech sometimes fires twice for the same phrase
            if message == self._last_text and now - self._last_time < 5.0:
                log.debug("Dropping duplicate voice input: %s", message[:50])
                return

            self._last_time = now
            self._last_text = message

            log.info("Voice input accepted: %s", message[:80])
            self._on_text(message)
        except sr.UnknownValueError:
            log.debug("Speech not understood")
        except sr.RequestError as e:
            log.warning("Google Speech API error: %s", e)
