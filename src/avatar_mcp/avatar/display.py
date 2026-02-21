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


class AvatarWindow(QWidget):
    def __init__(self, shared_state: SharedState, config: AvatarConfig):
        super().__init__()
        self._state = shared_state
        self._config = config
        self._current_pose = "idle"
        self._drag_offset = QPoint()
        self._dragging = False
        self._sprites: dict[str, QPixmap] = {}

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
        try:
            snap = self._state.snapshot()
        except Exception:
            log.debug("Failed to read shared state", exc_info=True)
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


def _acquire_lock() -> bool:
    """Ensure only one avatar display runs at a time using OS-level file locking."""
    import msvcrt

    global _lock_fh
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        _lock_fh = open(_LOCK_FILE, "w")
        msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
        return True
    except (OSError, IOError):
        # another instance holds the lock
        if _lock_fh:
            _lock_fh.close()
            _lock_fh = None
        return False


def _release_lock() -> None:
    global _lock_fh
    try:
        if _lock_fh:
            import msvcrt
            try:
                msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
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
