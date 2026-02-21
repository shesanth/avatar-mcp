"""RealtimeSTT engine — local Whisper-based streaming speech-to-text.

Uses faster-whisper via the RealtimeSTT library for GPU-accelerated,
low-latency transcription with built-in Silero VAD. No network calls,
no API keys, no truncation of long utterances.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from ..config import STTConfig
from .stt_base import STTEngine, check_wake_word

log = logging.getLogger("avatar-mcp")


class RealtimeSTTEngine(STTEngine):
    def __init__(self, config: STTConfig, on_text: Callable[[str], None]):
        self._config = config
        self._on_text = on_text
        self._recorder = None  # lazy — created in start()
        self._thread: threading.Thread | None = None
        self._running = False
        self._muted = False
        self._lock = threading.Lock()
        self._last_time = 0.0
        self._last_text = ""

    def start(self) -> None:
        from RealtimeSTT import AudioToTextRecorder

        # "en-US" -> "en" for whisper
        lang = self._config.language.split("-")[0] if self._config.language else ""

        self._recorder = AudioToTextRecorder(
            model=self._config.realtime_model,
            language=lang or "en",
            device=self._config.realtime_device,
            post_speech_silence_duration=self._config.pause_threshold,
            silero_sensitivity=self._config.realtime_silero_sensitivity,
            enable_realtime_transcription=False,
            spinner=False,
        )

        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        log.info(
            "RealtimeSTT started (model=%s, device=%s, lang=%s)",
            self._config.realtime_model,
            self._config.realtime_device,
            lang,
        )

    def stop(self) -> None:
        self._running = False
        if self._recorder:
            try:
                self._recorder.shutdown()
            except Exception:
                pass
            self._recorder = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def toggle_mute(self) -> None:
        self._muted = not self._muted

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def _listen_loop(self) -> None:
        while self._running:
            try:
                text = self._recorder.text()
            except Exception as e:
                if self._running:
                    log.error("RealtimeSTT recognition error: %s", e)
                    time.sleep(0.5)
                continue

            if not text or not text.strip():
                continue

            if self._muted:
                continue

            message = check_wake_word(text.strip(), self._config.wake_words)
            if message is None:
                log.debug("No wake word, ignoring: %s", text[:60])
                continue

            with self._lock:
                now = time.time()
                if now - self._last_time < self._config.cooldown_seconds:
                    continue
                if message == self._last_text and now - self._last_time < 15.0:
                    log.debug("Dropping duplicate: %s", message[:50])
                    continue
                self._last_time = now
                self._last_text = message

            log.info("Voice input accepted: %s", message[:80])
            self._on_text(message)
