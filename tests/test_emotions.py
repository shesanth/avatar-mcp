"""Tests for emotion/pose consistency."""

from __future__ import annotations

from avatar_mcp.state import EMOTION_POSE_MAP, VALID_EMOTIONS, VALID_POSES
from avatar_mcp.voice.emotions import EMOTION_PROSODY, ProsodyParams


class TestEmotionConsistency:
    def test_every_emotion_has_prosody(self):
        for emotion in VALID_EMOTIONS:
            assert emotion in EMOTION_PROSODY, f"Missing prosody for emotion: {emotion}"

    def test_every_emotion_has_pose_mapping(self):
        for emotion in VALID_EMOTIONS:
            assert emotion in EMOTION_POSE_MAP, f"Missing pose mapping for emotion: {emotion}"

    def test_pose_mappings_are_valid_poses(self):
        for emotion, pose in EMOTION_POSE_MAP.items():
            assert pose in VALID_POSES, f"Emotion '{emotion}' maps to invalid pose '{pose}'"

    def test_prosody_params_are_well_formed(self):
        for emotion, params in EMOTION_PROSODY.items():
            assert isinstance(params, ProsodyParams)
            assert params.pitch.endswith("Hz"), f"Bad pitch format for {emotion}: {params.pitch}"
            assert params.rate.endswith("%"), f"Bad rate format for {emotion}: {params.rate}"
            assert params.volume.endswith("%"), f"Bad volume format for {emotion}: {params.volume}"

    def test_valid_emotions_set_matches_prosody_keys(self):
        assert VALID_EMOTIONS == set(EMOTION_PROSODY.keys())

    def test_valid_emotions_set_matches_pose_map_keys(self):
        assert VALID_EMOTIONS == set(EMOTION_POSE_MAP.keys())
