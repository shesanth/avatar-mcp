"""Audio playback queue — sequential, non-blocking, cleans up temp files."""

from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Callable

import pygame

log = logging.getLogger("avatar-mcp")


class AudioQueue:
    def __init__(self):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        self._queue: queue.Queue[Path] = queue.Queue()
        self._playing = False
        self._on_complete: Callable[[], None] | None = None
        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._worker.start()

    def set_on_complete(self, callback: Callable[[], None]) -> None:
        self._on_complete = callback

    def add(self, audio_path: Path) -> None:
        self._queue.put(audio_path)

    @property
    def is_playing(self) -> bool:
        return self._playing

    def clear(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        pygame.mixer.music.stop()
        self._playing = False

    def shutdown(self) -> None:
        """Stop playback and release pygame mixer resources."""
        self.clear()
        try:
            pygame.mixer.quit()
        except Exception:
            pass

    def _loop(self) -> None:
        while True:
            path = self._queue.get()
            self._playing = True
            try:
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(50)
                # small gap between consecutive clips
                pygame.time.wait(200)
            except Exception:
                log.debug("Audio playback failed for %s", path, exc_info=True)
            finally:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    log.debug("Failed to delete temp audio file %s", path)
                if self._queue.empty():
                    self._playing = False
                    if self._on_complete:
                        self._on_complete()
