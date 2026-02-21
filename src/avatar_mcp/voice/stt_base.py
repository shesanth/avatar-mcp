"""Abstract STT engine interface + shared wake word filter."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable

log = logging.getLogger("avatar-mcp")


def check_wake_word(text: str, wake_words: list[str]) -> str | None:
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


class STTEngine(ABC):
    """Common interface for all speech-to-text backends."""

    @abstractmethod
    def __init__(self, config, on_text: Callable[[str], None]) -> None: ...

    @abstractmethod
    def start(self) -> None:
        """Begin listening for speech."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop listening and release resources."""
        ...

    @abstractmethod
    def toggle_mute(self) -> None:
        """Toggle mute — when muted, audio is captured but ignored."""
        ...

    @property
    @abstractmethod
    def is_running(self) -> bool: ...
