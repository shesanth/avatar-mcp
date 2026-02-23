"""Process lifecycle — spawns avatar display, initializes TTS/STT, tears down cleanly."""

from __future__ import annotations

import logging
import multiprocessing
import os
import shutil
import sys
import tempfile
from pathlib import Path

from .config import AppConfig
from .input.sender import ClaudeCodeSender
from .state import EMOTION_POSE_MAP, SharedState
from .voice.audio import AudioQueue
from .voice.tts_base import TTSEngine
from .voice.tts_edge import EdgeTTSEngine

log = logging.getLogger("avatar-mcp")


def _is_parent_alive(pid: int) -> bool:
    """Check if a process is alive. Cross-platform.

    On Windows, uses ctypes OpenProcess + GetExitCodeProcess (safe).
    On Unix, uses os.kill(pid, 0) (signal 0 = existence check).
    """
    if sys.platform == "win32":
        try:
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
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _clean_stale_temp_dirs() -> None:
    """Remove leftover avatar_mcp temp dirs from previous sessions."""
    tmp = Path(tempfile.gettempdir())
    for prefix in ("avatar_mcp_tts_", "avatar_mcp_kokoro_", "avatar_mcp_eleven_"):
        for d in tmp.glob(f"{prefix}*"):
            try:
                shutil.rmtree(d)
            except OSError:
                pass


_job_handle = None  # Windows Job Object handle, kept alive for process lifetime


def _create_job_object():
    """Create a Windows Job Object that kills all assigned processes on close.

    Returns the job handle, or None on non-Windows / failure.
    """
    if sys.platform != "win32":
        return None

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        ok = kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(info), ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(job)
            return None

        log.info("Job Object created for child process cleanup")
        return job
    except Exception:
        return None


_PID_FILE = Path.home() / ".claude" / "avatar-mcp.pids"


def _assign_to_job(pid: int) -> None:
    """Assign a process to the kill-on-close Job Object by PID."""
    global _job_handle
    if _job_handle is None or sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_SET_QUOTA = 0x0100
        PROCESS_TERMINATE = 0x0001
        handle = kernel32.OpenProcess(
            PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid,
        )
        if handle:
            ok = kernel32.AssignProcessToJobObject(_job_handle, handle)
            err = kernel32.GetLastError() if not ok else 0
            kernel32.CloseHandle(handle)
            if ok:
                log.info("Assigned pid=%d to Job Object", pid)
            else:
                log.warning("Failed to assign pid=%d to Job Object (error=%d)", pid, err)
        else:
            log.warning("OpenProcess failed for pid=%d (error=%d)", pid, kernel32.GetLastError())
    except Exception as e:
        log.warning("Job Object assignment exception for pid=%d: %s", pid, e)


def _assign_all_children() -> None:
    """Assign ALL child processes to the Job Object and record PIDs to a file.

    Called after start_all() so RealtimeSTT and other libraries have finished
    spawning their workers. Uses multiprocessing.active_children() to catch
    everything — Manager, avatar display, STT workers, etc.
    """
    children = multiprocessing.active_children()
    pids = [c.pid for c in children if c.pid is not None]

    # assign each to the Windows Job Object (noop on Unix)
    for pid in pids:
        _assign_to_job(pid)

    # write PID file as cross-platform fallback
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text("\n".join(str(p) for p in pids))
    log.info("Tracking %d child processes: %s", len(pids), pids)


def _kill_stale_pids() -> None:
    """Kill leftover child processes from a previous session using the PID file.

    Called on startup BEFORE spawning new processes.
    """
    if not _PID_FILE.exists():
        log.info("No stale PID file found — clean start")
        return

    raw = _PID_FILE.read_text()
    log.info("Found stale PID file with contents: %s", raw.strip())
    killed = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue

        if pid == os.getpid():
            continue

        alive = _is_parent_alive(pid)
        if not alive:
            log.info("Stale pid=%d already dead, skipping", pid)
            continue

        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
                if handle:
                    ok = kernel32.TerminateProcess(handle, 1)
                    kernel32.CloseHandle(handle)
                    if ok:
                        log.info("Killed stale pid=%d", pid)
                        killed += 1
                    else:
                        log.warning("TerminateProcess failed for pid=%d", pid)
                else:
                    log.warning("OpenProcess(TERMINATE) failed for pid=%d", pid)
            except Exception as e:
                log.warning("Exception killing stale pid=%d: %s", pid, e)
        else:
            try:
                import signal
                os.kill(pid, signal.SIGTERM)
                log.info("Sent SIGTERM to stale pid=%d", pid)
                killed += 1
            except OSError as e:
                log.warning("Failed to kill stale pid=%d: %s", pid, e)

    _PID_FILE.unlink(missing_ok=True)
    if killed:
        log.info("Killed %d stale processes from previous session", killed)


class Lifecycle:
    def __init__(self, config: AppConfig, state: SharedState):
        self.config = config
        self.state = state
        self._avatar_proc: multiprocessing.Process | None = None
        self._audio: AudioQueue | None = None
        self._tts: TTSEngine | None = None
        self._stt = None  # SpeechListener, lazily imported
        self._sender: ClaudeCodeSender | None = None
        self._pose_gen: int = 0  # incremented on explicit set_pose, prevents speak on_done from clobbering
        self._pending_hook_pose: str | None = None  # deferred hook pose when is_speaking
        self._stopped = False

    def start_all(self) -> None:
        # guard against double-spawn
        if self._avatar_proc is not None and self._avatar_proc.is_alive():
            log.warning("Avatar process already running, skipping spawn")
            return

        _kill_stale_pids()
        _clean_stale_temp_dirs()

        global _job_handle
        _job_handle = _create_job_object()

        # audio queue
        self._audio = AudioQueue()

        # TTS engine — must init before PyQt6 is imported, as Qt6's DLLs
        # on Windows poison the loader and break onnxruntime initialization
        self._init_tts()

        # avatar display in child process (lazy import keeps PyQt6 out until needed)
        from .avatar.display import run_avatar_display

        self._avatar_proc = multiprocessing.Process(
            target=run_avatar_display,
            args=(self.state, self.config.avatar),
            daemon=True,
        )
        self._avatar_proc.start()
        log.info("Avatar display started (pid=%s)", self._avatar_proc.pid)

        # STT sender (always init, listener started on demand)
        self._sender = ClaudeCodeSender()

        # auto-start listening if configured — wrapped so STT failure doesn't kill the server
        if self.config.stt.enabled:
            try:
                self.start_listening()
            except Exception as e:
                log.error("STT auto-start failed (server continues without voice): %s", e)

    def stop_all(self) -> None:
        if self._stopped:
            return
        self._stopped = True

        # STT first — may have non-daemon threads (RealtimeSTT internals)
        if self._stt:
            try:
                self._stt.stop()
            except Exception:
                pass
            self._stt = None

        # stop audio playback and pygame mixer
        if self._audio:
            try:
                self._audio.shutdown()
            except Exception:
                pass
            self._audio = None

        # avatar display: graceful quit → terminate → kill
        if self._avatar_proc and self._avatar_proc.is_alive():
            self.state.send_command({"action": "quit"})
            self._avatar_proc.join(timeout=3)
            if self._avatar_proc.is_alive():
                self._avatar_proc.terminate()
                self._avatar_proc.join(timeout=2)
            if self._avatar_proc.is_alive():
                log.warning("Avatar process didn't terminate, force killing")
                self._avatar_proc.kill()
                self._avatar_proc.join(timeout=1)
        self._avatar_proc = None

    def _init_tts(self) -> None:
        engine = self.config.tts.engine
        if engine == "elevenlabs" and self.config.tts.elevenlabs_api_key:
            from .voice.tts_eleven import ElevenLabsTTSEngine
            self._tts = ElevenLabsTTSEngine(
                api_key=self.config.tts.elevenlabs_api_key,
                voice_id=self.config.tts.elevenlabs_voice_id,
                model=self.config.tts.elevenlabs_model,
            )
            log.info("Using ElevenLabs TTS")
        elif engine == "kokoro":
            from .voice.tts_kokoro import KokoroTTSEngine, _add_onnx_dll_dir
            _add_onnx_dll_dir()
            import onnxruntime  # noqa: F401 — must load before PyQt6 poisons DLL search
            self._tts = KokoroTTSEngine(
                voice=self.config.tts.voice,
                lang_override=self.config.tts.kokoro_lang,
            )
            log.info("Using Kokoro TTS (voice=%s, lang=%s)", self.config.tts.voice, self.config.tts.kokoro_lang or "auto")
        else:
            self._tts = EdgeTTSEngine(voice=self.config.tts.voice)
            log.info("Using Edge TTS (voice=%s)", self.config.tts.voice)

    # --- public API for MCP tools ---

    async def speak(self, text: str, emotion: str) -> str:
        pre_speak_pose = self.state.get("pose")

        # Show emotion-mapped pose while speaking (angry, shy, smug, etc.)
        # Only fall back to "speaking" sprite for neutral emotion
        emotion_pose = EMOTION_POSE_MAP.get(emotion, "idle")
        if emotion_pose == "idle":
            emotion_pose = "speaking"
        self.state.set_many(pose=emotion_pose, emotion=emotion, is_speaking=True)

        path = await self._tts.synthesize(text, emotion)

        gen_at_speak = self._pose_gen
        self._pending_hook_pose = None  # clear any stale pending

        def on_done():
            self.state.set("is_speaking", False)
            if self._pending_hook_pose:
                # a hook fired during speech — apply the deferred pose
                pose = self._pending_hook_pose
                self._pending_hook_pose = None
                self.state.set("pose", pose)
            elif self._pose_gen == gen_at_speak:
                # no explicit set_pose during speech — restore pre-speak
                self.state.set("pose", pre_speak_pose)
            # else: explicit set_pose() was called, don't overwrite

        self._audio.set_on_complete(on_done)
        self._audio.add(path)

        preview = text[:80] + ("..." if len(text) > 80 else "")
        return f"Speaking ({emotion}): {preview}"

    def set_emotion(self, emotion: str) -> str:
        pose = EMOTION_POSE_MAP.get(emotion, "idle")
        self.state.set_many(emotion=emotion, pose=pose)
        return f"Emotion set to {emotion} (pose: {pose})"

    def set_pose(self, pose: str) -> str:
        self._pose_gen += 1
        self._pending_hook_pose = None  # explicit pose overrides pending hook
        self.state.set("pose", pose)
        return f"Pose set to {pose}"

    def set_hook_pose(self, pose: str) -> None:
        """Apply a pose from the hook file watcher. Defers if currently speaking."""
        if self.state.get("is_speaking"):
            self._pending_hook_pose = pose
        else:
            self._pending_hook_pose = None
            self.set_pose(pose)

    def show_avatar(self) -> str:
        self.state.set("visible", True)
        return "Avatar shown"

    def hide_avatar(self) -> str:
        self.state.set("visible", False)
        return "Avatar hidden"

    def start_listening(self) -> str:
        if self._stt and self._stt.is_running:
            return "Already listening"

        self._stt = self._init_stt()
        self._stt.start()
        self.state.set("is_listening", True)
        return "Listening started — speak into your microphone. Text will be injected as [VOICE] messages."

    def _init_stt(self):
        engine = self.config.stt.engine
        if engine == "realtime":
            from .voice.stt_realtime import RealtimeSTTEngine
            log.info("Using RealtimeSTT (model=%s, device=%s)", self.config.stt.realtime_model, self.config.stt.realtime_device)
            return RealtimeSTTEngine(self.config.stt, self._sender.send)
        else:
            from .voice.stt_google import GoogleSTTEngine
            log.info("Using Google Speech STT")
            return GoogleSTTEngine(self.config.stt, self._sender.send)

    def stop_listening(self) -> str:
        if self._stt:
            self._stt.stop()
            self._stt = None
        self.state.set("is_listening", False)
        return "Listening stopped"

    async def set_voice(self, voice_id: str, engine: str | None = None) -> str:
        if engine and engine != self.config.tts.engine:
            self.config.tts.engine = engine
            self._init_tts()

        self._tts.set_voice(voice_id)
        return f"Voice set to {voice_id} (engine: {self.config.tts.engine})"

    async def list_voices(self, engine: str | None = None) -> str:
        if engine and engine != self.config.tts.engine:
            if engine == "elevenlabs":
                from .voice.tts_eleven import ElevenLabsTTSEngine
                tmp = ElevenLabsTTSEngine(
                    api_key=self.config.tts.elevenlabs_api_key,
                    voice_id="",
                    model=self.config.tts.elevenlabs_model,
                )
                voices = await tmp.list_voices()
            elif engine == "kokoro":
                from .voice.tts_kokoro import KokoroTTSEngine
                tmp = KokoroTTSEngine()
                voices = await tmp.list_voices()
            else:
                tmp = EdgeTTSEngine()
                voices = await tmp.list_voices()
        else:
            voices = await self._tts.list_voices()

        lines = [f"- {v['id']} ({v['name']}, {v['language']})" for v in voices[:30]]
        header = f"Voices for {engine or self.config.tts.engine} ({len(voices)} total, showing first 30):\n"
        return header + "\n".join(lines)
