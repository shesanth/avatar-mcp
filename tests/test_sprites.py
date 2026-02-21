"""Tests for sprite loading and placeholder generation."""

from __future__ import annotations

from avatar_mcp.avatar.sprites import POSE_COLORS, POSE_KAOMOJI, generate_placeholder, load_sprite_paths
from avatar_mcp.state import VALID_POSES


class TestPoseData:
    def test_every_pose_has_color(self):
        for pose in VALID_POSES:
            if pose == "drag":
                continue  # drag is a transient state, having a color is optional
            assert pose in POSE_COLORS, f"Missing color for pose: {pose}"

    def test_every_pose_has_kaomoji(self):
        for pose in VALID_POSES:
            if pose == "drag":
                continue
            assert pose in POSE_KAOMOJI, f"Missing kaomoji for pose: {pose}"

    def test_colors_are_hex(self):
        for pose, color in POSE_COLORS.items():
            assert color.startswith("#"), f"Color for {pose} is not hex: {color}"
            assert len(color) == 7, f"Color for {pose} wrong length: {color}"


class TestPlaceholderGeneration:
    def test_generate_creates_file(self, tmp_path):
        import avatar_mcp.avatar.sprites as sprites_mod
        original = sprites_mod.ASSETS_DIR
        sprites_mod.ASSETS_DIR = tmp_path
        try:
            path = generate_placeholder("idle", size=100)
            assert path.exists()
            assert path.suffix == ".png"
        finally:
            sprites_mod.ASSETS_DIR = original

    def test_generate_returns_existing(self, tmp_path):
        import avatar_mcp.avatar.sprites as sprites_mod
        original = sprites_mod.ASSETS_DIR
        sprites_mod.ASSETS_DIR = tmp_path
        try:
            path1 = generate_placeholder("idle", size=100)
            path2 = generate_placeholder("idle", size=100)
            assert path1 == path2
        finally:
            sprites_mod.ASSETS_DIR = original


class TestLoadSpritePaths:
    def test_empty_custom_dir_generates_placeholders(self):
        sprites = load_sprite_paths("")
        assert len(sprites) > 0
        assert "idle" in sprites

    def test_custom_dir_with_pngs(self, tmp_path):
        (tmp_path / "idle.png").write_bytes(b"fake")
        (tmp_path / "thinking.png").write_bytes(b"fake")
        sprites = load_sprite_paths(str(tmp_path))
        assert "idle" in sprites
        assert "thinking" in sprites
