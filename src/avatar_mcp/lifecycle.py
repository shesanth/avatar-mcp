"""Process lifecycle — spawns avatar display, initializes TTS/STT, tears down cleanly."""

from __future__ import annotations

import logging
import multiprocessing
from pathlib import Path

from .config import AppConfig
from .input.sender import ClaudeCodeSender
from .state import EMOTION_POSE_MAP, SharedState
from .voice.audio import AudioQueue
from .voice.tts_base import TTSEngine
from .voice.tts_edge import EdgeTTSEngine

log = logging.getLogger("avatar-mcp")


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

    def start_all(self) -> None:
        # guard against double-spawn
        if self._avatar_proc is not None and self._avatar_proc.is_alive():
            log.warning("Avatar process already running, skipping spawn")
            return

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
        if self._stt:
            try:
                self._stt.stop()
            except Exception:
                pass

        if self._audio:
            self._audio.clear()

        if self._avatar_proc and self._avatar_proc.is_alive():
            self.state.send_command({"action": "quit"})
            self._avatar_proc.join(timeout=3)
            if self._avatar_proc.is_alive():
                self._avatar_proc.terminate()
                self._avatar_proc.join(timeout=2)

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
        emotion_pose = EMOTION_POSE_MAP.get(emotion, "idle")
        self.state.set_many(pose="speaking", emotion=emotion, is_speaking=True)

        path = await self._tts.synthesize(text, emotion)

        gen_at_speak = self._pose_gen

        def on_done():
            self.state.set("is_speaking", False)
            # only restore emotion pose if no explicit set_pose happened since speak started
            if self._pose_gen == gen_at_speak:
                self.state.set("pose", emotion_pose)

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
        self.state.set("pose", pose)
        return f"Pose set to {pose}"

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
