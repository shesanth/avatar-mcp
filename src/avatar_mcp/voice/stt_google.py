"""Google Speech API STT engine (speech_recognition package).

Fallback engine — works without GPU but has high latency and drops
long utterances. Prefer RealtimeSTT for conversational voice input.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import speech_recognition as sr

from ..config import STTConfig
from .stt_base import STTEngine, check_wake_word

log = logging.getLogger("avatar-mcp")


class GoogleSTTEngine(STTEngine):
    def __init__(self, config: STTConfig, on_text: Callable[[str], None]):
        self._config = config
        self._recognizer = sr.Recognizer()
        self._recognizer.pause_threshold = config.pause_threshold
        self._recognizer.phrase_threshold = config.phrase_threshold
        self._recognizer.non_speaking_duration = config.non_speaking_duration
        self._recognizer.dynamic_energy_threshold = False
        self._mic = sr.Microphone()
        self._on_text = on_text
        self._stop_fn: Callable | None = None
        self._muted = False
        self._lock = threading.Lock()
        self._last_time = 0.0
        self._last_text = ""

    def start(self) -> None:
        with self._mic as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=1)

        calibrated = self._recognizer.energy_threshold
        final = max(self._config.energy_threshold, calibrated)
        self._recognizer.energy_threshold = final
        log.info(
            "STT energy_threshold: config=%s, calibrated=%s, using=%s",
            self._config.energy_threshold, calibrated, final,
        )

        self._stop_fn = self._recognizer.listen_in_background(
            self._mic,
            self._on_audio,
            phrase_time_limit=30,
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

        try:
            text = recognizer.recognize_google(audio, language=self._config.language)
            if not text or not text.strip():
                return

            message = check_wake_word(text.strip(), self._config.wake_words)
            if message is None:
                return

            with self._lock:
                now = time.time()
                if now - self._last_time < self._config.cooldown_seconds:
                    return
                if message == self._last_text and now - self._last_time < 15.0:
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
