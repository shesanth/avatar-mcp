"""Tests for process cleanup: Job Objects, parent watchdog, atexit, signal handlers."""

from __future__ import annotations

import multiprocessing
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _clean_stale_temp_dirs
# ---------------------------------------------------------------------------

class TestCleanStaleTempDirs:
    def test_removes_matching_dirs(self, tmp_path):
        from avatar_mcp.lifecycle import _clean_stale_temp_dirs

        # create fake stale dirs in the real temp dir
        tmp = Path(tempfile.gettempdir())
        dirs = []
        for prefix in ("avatar_mcp_tts_", "avatar_mcp_kokoro_", "avatar_mcp_eleven_"):
            d = tmp / f"{prefix}test_cleanup"
            d.mkdir(exist_ok=True)
            (d / "junk.wav").write_bytes(b"\x00")
            dirs.append(d)

        _clean_stale_temp_dirs()

        for d in dirs:
            assert not d.exists(), f"{d} should have been removed"

    def test_ignores_unrelated_dirs(self):
        from avatar_mcp.lifecycle import _clean_stale_temp_dirs

        tmp = Path(tempfile.gettempdir())
        unrelated = tmp / "some_other_temp_dir_12345"
        unrelated.mkdir(exist_ok=True)
        try:
            _clean_stale_temp_dirs()
            assert unrelated.exists(), "unrelated dirs should not be touched"
        finally:
            unrelated.rmdir()


# ---------------------------------------------------------------------------
# _create_job_object
# ---------------------------------------------------------------------------

class TestCreateJobObject:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_returns_handle_on_windows(self):
        from avatar_mcp.lifecycle import _create_job_object
        handle = _create_job_object()
        assert handle is not None and handle != 0, "should return a valid job handle"
        # clean up
        import ctypes
        ctypes.windll.kernel32.CloseHandle(handle)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")
    def test_returns_none_on_unix(self):
        from avatar_mcp.lifecycle import _create_job_object
        assert _create_job_object() is None


# ---------------------------------------------------------------------------
# _assign_to_job
# ---------------------------------------------------------------------------

class TestAssignToJob:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_assigns_child_process(self):
        """Spawn a real child process, assign it to a job, verify it gets killed on close."""
        import ctypes
        from avatar_mcp.lifecycle import _create_job_object, _assign_to_job, _job_handle
        import avatar_mcp.lifecycle as lc_mod

        job = _create_job_object()
        assert job is not None

        # temporarily set the module-level handle
        old_handle = lc_mod._job_handle
        lc_mod._job_handle = job

        try:
            # spawn a harmless child that sleeps
            proc = multiprocessing.Process(
                target=_sleep_forever, daemon=True,
            )
            proc.start()
            assert proc.is_alive()

            _assign_to_job(proc.pid)

            # close the job handle — should kill the child
            ctypes.windll.kernel32.CloseHandle(job)
            proc.join(timeout=5)
            assert not proc.is_alive(), "child should have been killed by Job Object"
        finally:
            lc_mod._job_handle = old_handle
            if proc.is_alive():
                proc.kill()

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")
    def test_noop_on_unix(self):
        from avatar_mcp.lifecycle import _assign_to_job
        # should not raise
        _assign_to_job(os.getpid())

    def test_noop_when_no_job(self):
        """If _job_handle is None, _assign_to_job should silently do nothing."""
        import avatar_mcp.lifecycle as lc_mod
        old = lc_mod._job_handle
        lc_mod._job_handle = None
        try:
            lc_mod._assign_to_job(os.getpid())  # should not raise
        finally:
            lc_mod._job_handle = old


# ---------------------------------------------------------------------------
# _is_parent_alive (display.py)
# ---------------------------------------------------------------------------

class TestIsParentAlive:
    def test_current_process_is_alive(self):
        from avatar_mcp.lifecycle import _is_parent_alive
        assert _is_parent_alive(os.getpid()) is True

    def test_dead_pid_returns_false(self):
        from avatar_mcp.lifecycle import _is_parent_alive
        # spawn and immediately kill a process to get a dead PID
        proc = multiprocessing.Process(target=_noop)
        proc.start()
        proc.join(timeout=5)
        dead_pid = proc.pid
        assert _is_parent_alive(dead_pid) is False

    def test_bogus_pid_returns_false(self):
        from avatar_mcp.lifecycle import _is_parent_alive
        # very high PID unlikely to exist
        assert _is_parent_alive(99999999) is False


# ---------------------------------------------------------------------------
# Lifecycle.stop_all idempotency
# ---------------------------------------------------------------------------

class TestStopAllIdempotent:
    def test_double_stop_does_not_raise(self):
        """Calling stop_all() twice should be safe (guarded by _stopped flag)."""
        from avatar_mcp.config import AppConfig
        from avatar_mcp.lifecycle import Lifecycle

        mgr = multiprocessing.Manager()
        try:
            from avatar_mcp.state import SharedState
            state = SharedState(mgr)
            config = AppConfig.load()
            lc = Lifecycle(config, state)
            # don't start_all — just verify double-stop is safe
            lc.stop_all()
            lc.stop_all()  # second call should not raise
        finally:
            mgr.shutdown()


# ---------------------------------------------------------------------------
# server.py _force_cleanup
# ---------------------------------------------------------------------------

class TestForceCleanup:
    def test_calls_stop_all_and_shutdown(self):
        from avatar_mcp.server import _force_cleanup, _cleanup_refs

        mock_lc = MagicMock()
        mock_mgr = MagicMock()

        _cleanup_refs["lifecycle"] = mock_lc
        _cleanup_refs["manager"] = mock_mgr

        _force_cleanup()

        mock_lc.stop_all.assert_called_once()
        mock_mgr.shutdown.assert_called_once()
        assert "lifecycle" not in _cleanup_refs
        assert "manager" not in _cleanup_refs

    def test_tolerates_exceptions(self):
        from avatar_mcp.server import _force_cleanup, _cleanup_refs

        mock_lc = MagicMock()
        mock_lc.stop_all.side_effect = RuntimeError("boom")
        mock_mgr = MagicMock()

        _cleanup_refs["lifecycle"] = mock_lc
        _cleanup_refs["manager"] = mock_mgr

        # should not raise even if stop_all throws
        _force_cleanup()
        mock_mgr.shutdown.assert_called_once()

    def test_noop_when_empty(self):
        from avatar_mcp.server import _force_cleanup, _cleanup_refs
        _cleanup_refs.clear()
        _force_cleanup()  # should not raise


# ---------------------------------------------------------------------------
# AudioQueue.shutdown
# ---------------------------------------------------------------------------

class TestAudioQueueShutdown:
    def test_shutdown_calls_mixer_quit(self):
        with patch("pygame.mixer") as mock_mixer:
            mock_mixer.init = MagicMock()
            mock_mixer.music = MagicMock()
            from avatar_mcp.voice.audio import AudioQueue
            aq = AudioQueue()
            aq.shutdown()
            mock_mixer.quit.assert_called_once()

    def test_double_shutdown_safe(self):
        with patch("pygame.mixer") as mock_mixer:
            mock_mixer.init = MagicMock()
            mock_mixer.music = MagicMock()
            from avatar_mcp.voice.audio import AudioQueue
            aq = AudioQueue()
            aq.shutdown()
            aq.shutdown()  # should not raise


# ---------------------------------------------------------------------------
# Display watchdog poll logic
# ---------------------------------------------------------------------------

class TestDisplayWatchdog:
    """Test the poll counter and failure counter logic in AvatarWindow._poll."""

    def test_parent_check_interval(self):
        """Parent alive check happens every 40th poll (roughly 2 seconds at 50ms)."""
        # verify the check is at poll_count % 40 == 0 by reading the source
        import ast
        display_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "avatar" / "display.py"
        )
        source = display_path.read_text()
        assert "self._poll_count % 40 == 0" in source, (
            "Parent alive check should happen every 40th poll"
        )

    def test_state_failure_threshold(self):
        """After 100+ consecutive state failures, display should self-terminate."""
        import ast
        display_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "avatar" / "display.py"
        )
        source = display_path.read_text()
        assert "self._state_failures > 100" in source, (
            "State failure threshold should be 100 (roughly 5 seconds)"
        )


# ---------------------------------------------------------------------------
# Cross-platform structure tests
# ---------------------------------------------------------------------------

class TestCrossPlatformStructure:
    """Verify the code has proper platform branching for all OS-specific paths."""

    def test_is_parent_alive_has_windows_and_unix_branches(self):
        """Both lifecycle.py and display.py have _is_parent_alive with platform branches."""
        for rel_path in ("lifecycle.py", "avatar/display.py"):
            src_path = (
                Path(__file__).resolve().parent.parent
                / "src" / "avatar_mcp" / rel_path
            )
            source = src_path.read_text()
            assert 'sys.platform == "win32"' in source, (
                f"_is_parent_alive in {rel_path} must have a Windows branch"
            )
            assert "os.kill(pid, 0)" in source, (
                f"_is_parent_alive in {rel_path} must have a Unix branch"
            )

    def test_kill_stale_holder_has_windows_and_unix_branches(self):
        display_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "avatar" / "display.py"
        )
        source = display_path.read_text()
        # find the _kill_stale_holder function
        assert "TerminateProcess" in source, (
            "_kill_stale_holder must use TerminateProcess on Windows"
        )
        assert "signal.SIGTERM" in source, (
            "_kill_stale_holder must use SIGTERM on Unix"
        )

    def test_job_object_returns_none_on_non_windows(self):
        from avatar_mcp.lifecycle import _create_job_object
        if sys.platform != "win32":
            assert _create_job_object() is None

    def test_assign_to_job_is_noop_without_handle(self):
        """_assign_to_job should be safe to call even when _job_handle is None."""
        import avatar_mcp.lifecycle as lc_mod
        old = lc_mod._job_handle
        lc_mod._job_handle = None
        try:
            lc_mod._assign_to_job(12345)
        finally:
            lc_mod._job_handle = old


# ---------------------------------------------------------------------------
# _assign_all_children / _kill_stale_pids (PID file)
# ---------------------------------------------------------------------------

class TestPidFile:
    def test_assign_all_children_creates_pid_file(self):
        """_assign_all_children writes child PIDs to the PID file."""
        import avatar_mcp.lifecycle as lc_mod
        from avatar_mcp.lifecycle import _assign_all_children, _PID_FILE

        # spawn a child so active_children() has something
        proc = multiprocessing.Process(target=_sleep_forever, daemon=True)
        proc.start()
        try:
            _assign_all_children()
            assert _PID_FILE.exists(), "PID file should be created"
            content = _PID_FILE.read_text()
            assert str(proc.pid) in content, "child PID should be in the file"
        finally:
            proc.kill()
            proc.join(timeout=3)
            _PID_FILE.unlink(missing_ok=True)

    def test_kill_stale_pids_kills_processes_from_file(self):
        """_kill_stale_pids reads the PID file and kills listed processes."""
        from avatar_mcp.lifecycle import _kill_stale_pids, _PID_FILE

        proc = multiprocessing.Process(target=_sleep_forever, daemon=True)
        proc.start()
        assert proc.is_alive()

        # write its PID to the file
        _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PID_FILE.write_text(str(proc.pid))

        try:
            _kill_stale_pids()
            proc.join(timeout=5)
            assert not proc.is_alive(), "stale process should have been killed"
            assert not _PID_FILE.exists(), "PID file should be deleted after cleanup"
        finally:
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=3)
            _PID_FILE.unlink(missing_ok=True)

    def test_kill_stale_pids_noop_without_file(self):
        """No PID file = nothing to kill, no error."""
        from avatar_mcp.lifecycle import _kill_stale_pids, _PID_FILE
        _PID_FILE.unlink(missing_ok=True)
        _kill_stale_pids()  # should not raise

    def test_kill_stale_pids_handles_dead_pids(self):
        """PID file with already-dead processes should not error."""
        from avatar_mcp.lifecycle import _kill_stale_pids, _PID_FILE

        _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PID_FILE.write_text("99999999\n88888888")

        _kill_stale_pids()  # should not raise
        assert not _PID_FILE.exists()


# ---------------------------------------------------------------------------
# Signal handler registration
# ---------------------------------------------------------------------------

class TestParentWatchdog:
    def test_watchdog_function_exists(self):
        from avatar_mcp.server import _start_parent_watchdog
        assert callable(_start_parent_watchdog)

    def test_server_calls_watchdog_in_main(self):
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "server.py"
        )
        source = server_path.read_text()
        assert "_start_parent_watchdog()" in source, (
            "main() must call _start_parent_watchdog()"
        )

    def test_force_cleanup_kills_active_children(self):
        """_force_cleanup should call .kill() on active children."""
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "server.py"
        )
        source = server_path.read_text()
        assert "active_children()" in source, (
            "_force_cleanup must iterate active_children()"
        )
        assert "child.kill()" in source, (
            "_force_cleanup must kill surviving children"
        )


# ---------------------------------------------------------------------------
# Hook-triggered pose changes
# ---------------------------------------------------------------------------

class TestHookPose:
    def _make_lifecycle(self):
        """Create a minimal Lifecycle with mocked state for testing."""
        from avatar_mcp.lifecycle import Lifecycle
        lc = object.__new__(Lifecycle)
        lc._pose_gen = 0
        lc._pending_hook_pose = None
        lc._stopped = False
        lc.state = MagicMock()
        lc.state.get = MagicMock(return_value="idle")
        return lc

    def test_set_hook_pose_immediate_when_not_speaking(self):
        """set_hook_pose should call set_pose immediately if not speaking."""
        lc = self._make_lifecycle()
        lc.state.get.return_value = False  # is_speaking = False
        lc.set_hook_pose("coding")
        lc.state.set.assert_called_with("pose", "coding")
        assert lc._pending_hook_pose is None

    def test_set_hook_pose_deferred_when_speaking(self):
        """set_hook_pose should defer if is_speaking is True."""
        lc = self._make_lifecycle()
        lc.state.get.return_value = True  # is_speaking = True
        lc.set_hook_pose("listening")
        assert lc._pending_hook_pose == "listening"
        # state.set should NOT have been called with "pose" for listening
        # (it was called with "pose", "coding" would not be here)

    def test_set_pose_clears_pending_hook(self):
        """Explicit set_pose should clear pending hook pose."""
        lc = self._make_lifecycle()
        lc._pending_hook_pose = "listening"
        lc.set_pose("coding")
        assert lc._pending_hook_pose is None
        assert lc._pose_gen == 1

    def test_speak_emotion_pose_mapping(self):
        """speak() should show emotion-mapped pose, not 'speaking', for non-neutral emotions."""
        lifecycle_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "lifecycle.py"
        )
        source = lifecycle_path.read_text()
        # Check that speak() uses EMOTION_POSE_MAP
        assert "EMOTION_POSE_MAP.get(emotion" in source, (
            "speak() must use EMOTION_POSE_MAP to determine pose during speech"
        )
        # Check the fallback to "speaking" for neutral
        assert 'emotion_pose = "speaking"' in source, (
            "speak() must fall back to 'speaking' sprite for neutral emotion"
        )

    def test_pose_watcher_exists_in_server(self):
        """server.py must have a pose file watcher."""
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "server.py"
        )
        source = server_path.read_text()
        assert "_start_pose_watcher" in source
        assert "avatar-pose" in source
        assert "pose-watcher" in source

    def test_pose_watcher_validates_poses(self):
        """Pose watcher should check against VALID_POSES."""
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "server.py"
        )
        source = server_path.read_text()
        assert "VALID_POSES" in source

    def test_set_pose_and_set_emotion_tools_removed(self):
        """set_pose and set_emotion MCP tools should not exist in server.py."""
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "server.py"
        )
        source = server_path.read_text()
        # The @mcp.tool() decorated functions should not exist
        assert "async def set_pose(" not in source, (
            "set_pose MCP tool should be removed"
        )
        assert "async def set_emotion(" not in source, (
            "set_emotion MCP tool should be removed"
        )

    def test_lifecycle_methods_still_exist(self):
        """Lifecycle.set_pose() and set_emotion() methods must remain (used internally)."""
        from avatar_mcp.lifecycle import Lifecycle
        assert hasattr(Lifecycle, "set_pose"), "Lifecycle.set_pose must exist"
        assert hasattr(Lifecycle, "set_emotion"), "Lifecycle.set_emotion must exist"


class TestSignalHandlerRegistration:
    def test_server_registers_sigint(self):
        """server.py main() must register SIGINT handler."""
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "server.py"
        )
        source = server_path.read_text()
        assert "signal.signal(signal.SIGINT" in source

    def test_server_registers_sigterm(self):
        """server.py main() must register SIGTERM handler (with hasattr guard)."""
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "server.py"
        )
        source = server_path.read_text()
        assert 'hasattr(signal, "SIGTERM")' in source

    def test_server_registers_atexit(self):
        """server.py main() must register atexit handler."""
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "avatar_mcp" / "server.py"
        )
        source = server_path.read_text()
        assert "atexit.register(_force_cleanup)" in source


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _noop():
    """Target for test child process — exits immediately."""
    pass


def _sleep_forever():
    """Target for test child process — sleeps until killed."""
    import time
    while True:
        time.sleep(1)
