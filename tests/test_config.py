"""Tests for config loading and defaults."""

from __future__ import annotations

from avatar_mcp.config import AppConfig, AvatarConfig, BehaviorConfig, STTConfig, TTSConfig


class TestDefaults:
    def test_avatar_defaults(self):
        c = AvatarConfig()
        assert c.start_visible is True
        assert c.start_x == 100
        assert c.start_y == 100
        assert c.sprite_scale == 1.0
        assert c.sprite_directory == ""
        assert c.poll_interval_ms == 50

    def test_tts_defaults(self):
        c = TTSConfig()
        assert c.engine == "edge"
        assert c.voice == "ja-JP-NanamiNeural"
        assert c.kokoro_lang == ""
        assert c.elevenlabs_api_key == ""

    def test_stt_defaults(self):
        c = STTConfig()
        assert c.enabled is False
        assert c.engine == "google"
        assert c.language == "en-US"
        assert c.pause_threshold == 1.2
        assert c.phrase_threshold == 0.1
        assert c.non_speaking_duration == 0.5
        assert "claude" in c.wake_words
        assert c.realtime_model == "base"
        assert c.realtime_device == "cuda"
        assert c.realtime_silero_sensitivity == 0.4

    def test_behavior_defaults(self):
        c = BehaviorConfig()
        assert c.auto_speak is True


class TestFromDict:
    def test_full_config(self):
        raw = {
            "avatar": {"start_visible": False, "start_x": 500, "start_y": 300},
            "tts": {"engine": "kokoro", "voice": "af_heart"},
            "stt": {"enabled": True, "language": "ja-JP"},
            "behavior": {"auto_speak": False},
        }
        cfg = AppConfig._from_dict(raw)
        assert cfg.avatar.start_visible is False
        assert cfg.avatar.start_x == 500
        assert cfg.tts.engine == "kokoro"
        assert cfg.tts.voice == "af_heart"
        assert cfg.stt.enabled is True
        assert cfg.stt.language == "ja-JP"
        assert cfg.behavior.auto_speak is False

    def test_unknown_keys_ignored(self):
        raw = {
            "avatar": {"start_visible": True, "nonexistent_key": 42},
            "tts": {"engine": "edge", "fake_field": "hello"},
        }
        cfg = AppConfig._from_dict(raw)
        assert cfg.avatar.start_visible is True
        assert cfg.tts.engine == "edge"
        assert not hasattr(cfg.avatar, "nonexistent_key")

    def test_empty_dict_uses_defaults(self):
        cfg = AppConfig._from_dict({})
        assert cfg.avatar.start_visible is True
        assert cfg.tts.engine == "edge"
        assert cfg.stt.enabled is False

    def test_partial_sections(self):
        raw = {"tts": {"engine": "kokoro"}}
        cfg = AppConfig._from_dict(raw)
        assert cfg.tts.engine == "kokoro"
        assert cfg.tts.voice == "ja-JP-NanamiNeural"  # default preserved
        assert cfg.avatar.start_x == 100  # entire section defaulted


class TestLoad:
    def test_no_file_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Patch the module-level __file__ fallback so it doesn't find the real config.toml
        import avatar_mcp.config as config_mod
        monkeypatch.setattr(config_mod, "__file__", str(tmp_path / "fake" / "config.py"))
        cfg = AppConfig.load(tmp_path / "nonexistent.toml")
        assert cfg.avatar.start_visible is True
        assert cfg.tts.engine == "edge"

    def test_load_from_toml(self, tmp_path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(
            '[avatar]\nstart_visible = false\nstart_x = 999\n'
            '[tts]\nengine = "kokoro"\n'
        )
        cfg = AppConfig.load(toml_file)
        assert cfg.avatar.start_visible is False
        assert cfg.avatar.start_x == 999
        assert cfg.tts.engine == "kokoro"
