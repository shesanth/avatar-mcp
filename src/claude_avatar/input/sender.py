"""Injects recognized speech into Claude Code's terminal via clipboard."""

from __future__ import annotations

import time

import pyautogui
import pyperclip


class ClaudeCodeSender:
    """Pastes recognized text into the active terminal window."""

    def send(self, text: str) -> bool:
        try:
            prefixed = f"[VOICE] {text}"
            old_clip = pyperclip.paste()
            pyperclip.copy(prefixed)
            time.sleep(0.05)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.05)
            pyautogui.press("enter")
            # restore previous clipboard contents
            time.sleep(0.1)
            pyperclip.copy(old_clip)
            return True
        except Exception:
            return False
