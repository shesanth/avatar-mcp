"""Injects recognized speech into Claude Code's terminal via clipboard.

Finds the VSCode/terminal window, briefly activates it, pastes, then
returns focus to whatever the user was doing. Cross-platform:
Windows (Win32 API), macOS (AppleScript), Linux (xdotool).
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import time

import pyperclip

log = logging.getLogger("avatar-mcp")

_SYSTEM = platform.system()

# --- platform-specific window management ---


def _find_and_paste_windows(text: str) -> bool:
    """Win32: find VSCode window, activate, paste, restore focus."""
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    target_kw = ("visual studio code", "code -")

    # find VSCode hwnd
    result = []

    @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.lower()
        if any(kw in title for kw in target_kw):
            result.append(hwnd)
            return False
        return True

    user32.EnumWindows(enum_cb, 0)
    if not result:
        return False

    hwnd = result[0]
    prev_hwnd = user32.GetForegroundWindow()
    old_clip = pyperclip.paste()
    pyperclip.copy(text)

    try:
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.08)

        VK_CONTROL, VK_V, VK_RETURN = 0x11, 0x56, 0x0D
        KEYEVENTF_KEYUP = 0x0002

        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.05)

        user32.keybd_event(VK_RETURN, 0, 0, 0)
        user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.05)
        return True
    finally:
        if prev_hwnd and prev_hwnd != hwnd:
            time.sleep(0.05)
            user32.SetForegroundWindow(prev_hwnd)
        time.sleep(0.05)
        pyperclip.copy(old_clip)


def _find_and_paste_macos(text: str) -> bool:
    """macOS: use AppleScript to target VSCode."""
    old_clip = pyperclip.paste()
    pyperclip.copy(text)

    script = """
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
    end tell
    tell application "Visual Studio Code" to activate
    delay 0.1
    tell application "System Events"
        keystroke "v" using command down
        delay 0.05
        key code 36
    end tell
    delay 0.05
    tell application frontApp to activate
    """
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
        return True
    except Exception:
        return False
    finally:
        time.sleep(0.05)
        pyperclip.copy(old_clip)


def _find_and_paste_linux(text: str) -> bool:
    """Linux: use xdotool to target VSCode."""
    if not shutil.which("xdotool"):
        log.error("xdotool not found — install it for voice input on Linux")
        return False

    old_clip = pyperclip.paste()
    pyperclip.copy(text)

    try:
        # remember current window
        prev = subprocess.run(
            ["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=3
        ).stdout.strip()

        # find and activate VSCode
        result = subprocess.run(
            ["xdotool", "search", "--name", "Visual Studio Code"],
            capture_output=True, text=True, timeout=3,
        )
        windows = result.stdout.strip().split("\n")
        if not windows or not windows[0]:
            return False

        target = windows[0]
        subprocess.run(["xdotool", "windowactivate", target], timeout=3)
        time.sleep(0.08)

        subprocess.run(["xdotool", "key", "ctrl+v"], timeout=3)
        time.sleep(0.05)
        subprocess.run(["xdotool", "key", "Return"], timeout=3)
        time.sleep(0.05)

        # restore previous window
        if prev:
            subprocess.run(["xdotool", "windowactivate", prev], timeout=3)
        return True
    except Exception:
        return False
    finally:
        time.sleep(0.05)
        pyperclip.copy(old_clip)


def _find_and_paste(text: str) -> bool:
    if _SYSTEM == "Windows":
        return _find_and_paste_windows(text)
    elif _SYSTEM == "Darwin":
        return _find_and_paste_macos(text)
    elif _SYSTEM == "Linux":
        return _find_and_paste_linux(text)
    else:
        log.error("Unsupported platform: %s", _SYSTEM)
        return False


class ClaudeCodeSender:
    """Sends recognized text to Claude Code by finding its window,
    briefly activating it, pasting, and returning focus.

    Works on Windows, macOS, and Linux.
    """

    def send(self, text: str) -> bool:
        prefixed = f"[VOICE] {text}"
        try:
            ok = _find_and_paste(prefixed)
            if not ok:
                log.warning("Could not find VSCode window, dropping: %s", text[:50])
            return ok
        except Exception as e:
            log.error("Failed to send voice input: %s", e)
            return False
