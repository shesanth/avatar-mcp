"""PyQt6 transparent overlay window — runs in a child process."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QPoint, QTimer, Qt

log = logging.getLogger("avatar-mcp")
from PyQt6.QtGui import QAction, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QWidget

from ..avatar.sprites import load_sprite_paths
from ..config import AvatarConfig
from ..state import SharedState


def _is_parent_alive(pid: int) -> bool:
    """Check if a process is alive. Works on Windows, Linux, macOS.

    NOTE: os.kill(pid, 0) is NOT safe on Windows — signal 0 == CTRL_C_EVENT,
    so it broadcasts Ctrl+C to the process group and kills Claude Code.

    Duplicated here (also in lifecycle.py) to avoid importing the heavy
    lifecycle module into the lightweight display child process.
    """
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        result = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return result != 0 and exit_code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class AvatarWindow(QWidget):
    def __init__(self, shared_state: SharedState, config: AvatarConfig):
        super().__init__()
        self._state = shared_state
        self._config = config
        self._current_pose = "idle"
        self._drag_offset = QPoint()
        self._dragging = False
        self._sprites: dict[str, QPixmap] = {}
        self._parent_pid = os.getppid()
        self._poll_count = 0
        self._state_failures = 0

        self._setup_window()
        self._load_sprites()
        self._set_pose("idle")
        self._start_polling()

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("avatar-mcp")

        self._label = QLabel(self)
        self._label.setStyleSheet("background: transparent;")

        self.move(self._config.start_x, self._config.start_y)

    def _load_sprites(self) -> None:
        paths = load_sprite_paths(self._config.sprite_directory)
        for pose, path in paths.items():
            pm = QPixmap(str(path))
            if not pm.isNull():
                self._sprites[pose] = pm

    def _start_polling(self) -> None:
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(self._config.poll_interval_ms)

    def _poll(self) -> None:
        """Read shared state and update display."""
        self._poll_count += 1

        # check if parent (MCP server) is alive every ~2 seconds
        if self._poll_count % 40 == 0:
            if not _is_parent_alive(self._parent_pid):
                log.info("Parent process (pid=%s) is gone, shutting down", self._parent_pid)
                QApplication.quit()
                return

        try:
            snap = self._state.snapshot()
            self._state_failures = 0
        except Exception:
            self._state_failures += 1
            # shared state dead for 5+ seconds — parent/Manager is gone
            if self._state_failures > 100:
                log.info("Shared state unreachable, shutting down")
                QApplication.quit()
                return
            return

        # visibility
        if snap["visible"] and not self.isVisible():
            self.show()
        elif not snap["visible"] and self.isVisible():
            self.hide()

        # pose
        if not self._dragging:
            new_pose = snap["pose"]
            if new_pose != self._current_pose:
                self._set_pose(new_pose)

        # commands
        cmd = self._state.poll_command()
        if cmd:
            self._handle_command(cmd)

    def _set_pose(self, pose: str) -> None:
        pixmap = self._sprites.get(pose, self._sprites.get("idle"))
        if pixmap is None:
            return

        scale = self._config.sprite_scale
        w = int(pixmap.width() * scale)
        h = int(pixmap.height() * scale)
        scaled = pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())
        self.resize(scaled.size())
        self._current_pose = pose

    def _handle_command(self, cmd: dict) -> None:
        action = cmd.get("action")
        if action == "quit":
            QApplication.quit()

    # --- drag handling ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._dragging = True
            self._set_pose("drag")

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self._dragging = False
            pos = self.pos()
            self._state.set_many(position_x=pos.x(), position_y=pos.y())
            # restore pose from state
            try:
                self._set_pose(self._state.get("pose"))
            except Exception:
                log.debug("Failed to restore pose after drag", exc_info=True)
                self._set_pose("idle")

    # --- context menu ---

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        hide_action = QAction("Hide", self)
        hide_action.triggered.connect(lambda: self._state.set("visible", False))
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(hide_action)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())


_LOCK_FILE = Path.home() / ".claude" / "avatar-mcp.lock"
_lock_fh = None  # held open for the process lifetime


def _lock_file(fh) -> bool:
    """Acquire a non-blocking exclusive lock. Returns True on success."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return True


def _unlock_file(fh) -> None:
    """Release the lock held on a file handle."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _read_stale_pid() -> int | None:
    """Read the PID from the lock file without truncating it."""
    try:
        text = _LOCK_FILE.read_text().strip()
        return int(text) if text else None
    except (ValueError, OSError, FileNotFoundError):
        return None


def _kill_stale_holder(pid: int | None) -> None:
    """Kill a stale avatar display process by PID.

    Uses TerminateProcess directly on Windows to avoid os.kill signal pitfalls.
    """
    if pid is None:
        return
    import time
    try:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_TERMINATE = 0x0001
            handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if handle:
                kernel32.TerminateProcess(handle, 1)
                kernel32.CloseHandle(handle)
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
    except OSError:
        pass


def _acquire_lock() -> bool:
    """Ensure only one avatar display runs at a time using OS-level file locking.

    If a stale process holds the lock, kill it and retry.
    """
    global _lock_fh
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    # read stale PID BEFORE opening with "w" (which truncates the file)
    stale_pid = _read_stale_pid()

    for attempt in range(2):
        try:
            _lock_fh = open(_LOCK_FILE, "w")
            _lock_file(_lock_fh)
            _lock_fh.write(str(os.getpid()))
            _lock_fh.flush()
            return True
        except (OSError, IOError):
            if _lock_fh:
                _lock_fh.close()
                _lock_fh = None
            if attempt == 0:
                _kill_stale_holder(stale_pid)
            else:
                return False
    return False


def _release_lock() -> None:
    global _lock_fh
    try:
        if _lock_fh:
            try:
                _unlock_file(_lock_fh)
            except OSError:
                pass
            _lock_fh.close()
            _lock_fh = None
            _LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def run_avatar_display(shared_state: SharedState, config: AvatarConfig) -> None:
    """Entry point for the avatar child process."""
    if not _acquire_lock():
        print("avatar-mcp: another instance is already running", file=sys.stderr)
        return
    try:
        app = QApplication(sys.argv)
        window = AvatarWindow(shared_state, config)
        if config.start_visible:
            window.show()
        sys.exit(app.exec())
    finally:
        _release_lock()
