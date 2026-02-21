"""Tests for lifecycle import ordering and DLL safety."""

from __future__ import annotations

import ast
import sys
import textwrap
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
LIFECYCLE = SRC / "avatar_mcp" / "lifecycle.py"
TTS_KOKORO = SRC / "avatar_mcp" / "voice" / "tts_kokoro.py"


class TestImportOrdering:
    """PyQt6 adds Qt6\\bin to the DLL search path on import, which breaks
    onnxruntime initialization on Windows.  The lifecycle module must
    initialize TTS (which may load onnxruntime) BEFORE importing the
    display module (which loads PyQt6).

    These tests verify the code structure enforces this ordering.
    """

    def test_display_not_imported_at_module_level(self):
        """display.py (which imports PyQt6) must NOT be a top-level import."""
        tree = ast.parse(LIFECYCLE.read_text())
        top_imports = [
            node for node in ast.iter_child_nodes(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        for node in top_imports:
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "display" not in node.module, (
                    "display must be lazily imported inside start_all(), "
                    "not at module level — PyQt6 poisons onnxruntime DLL loading"
                )

    def test_tts_init_before_display_import(self):
        """In start_all(), _init_tts() must be called before display is imported."""
        source = LIFECYCLE.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "start_all":
                lines = {
                    "tts_init": None,
                    "display_import": None,
                }
                for child in ast.walk(node):
                    # Find self._init_tts() call
                    if (isinstance(child, ast.Call)
                            and isinstance(child.func, ast.Attribute)
                            and child.func.attr == "_init_tts"):
                        lines["tts_init"] = child.lineno
                    # Find 'from .avatar.display import ...'
                    if (isinstance(child, ast.ImportFrom)
                            and child.module
                            and "display" in child.module):
                        lines["display_import"] = child.lineno

                assert lines["tts_init"] is not None, "_init_tts() call not found in start_all()"
                assert lines["display_import"] is not None, "display import not found in start_all()"
                assert lines["tts_init"] < lines["display_import"], (
                    f"_init_tts() (line {lines['tts_init']}) must come before "
                    f"display import (line {lines['display_import']})"
                )
                return

        pytest.fail("start_all() method not found in Lifecycle")

    def test_kokoro_branch_imports_onnxruntime_eagerly(self):
        """The kokoro branch in _init_tts() must import onnxruntime eagerly."""
        source = LIFECYCLE.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_init_tts":
                source_lines = source.splitlines()
                func_source = "\n".join(
                    source_lines[node.lineno - 1 : node.end_lineno]
                )
                assert "import onnxruntime" in func_source, (
                    "_init_tts() must eagerly import onnxruntime in the kokoro "
                    "branch to ensure it loads before PyQt6"
                )
                return

        pytest.fail("_init_tts() method not found")


class TestAddOnnxDllDir:
    """Tests for the _add_onnx_dll_dir helper in tts_kokoro."""

    def test_function_exists(self):
        from avatar_mcp.voice.tts_kokoro import _add_onnx_dll_dir
        assert callable(_add_onnx_dll_dir)

    def test_does_not_import_onnxruntime(self):
        """_add_onnx_dll_dir must not trigger onnxruntime import itself."""
        source = TTS_KOKORO.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_add_onnx_dll_dir":
                func_source = source.splitlines()[node.lineno - 1 : node.end_lineno]
                for line in func_source:
                    stripped = line.strip()
                    # Allow importlib.util.find_spec("onnxruntime") but not 'import onnxruntime'
                    if stripped.startswith("import onnxruntime") or stripped.startswith("from onnxruntime"):
                        pytest.fail(
                            "_add_onnx_dll_dir must not import onnxruntime directly — "
                            "it should only locate the package via importlib.util.find_spec"
                        )
                return

        pytest.fail("_add_onnx_dll_dir function not found")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only DLL fix")
    def test_adds_to_path_on_windows(self):
        """On Windows, _add_onnx_dll_dir should add onnxruntime capi to PATH."""
        import os
        from avatar_mcp.voice.tts_kokoro import _add_onnx_dll_dir

        _add_onnx_dll_dir()
        path = os.environ.get("PATH", "")
        # onnxruntime must be installed for this test
        try:
            import importlib.util
            spec = importlib.util.find_spec("onnxruntime")
            if spec and spec.submodule_search_locations:
                capi = os.path.join(list(spec.submodule_search_locations)[0], "capi")
                assert capi in path, f"Expected {capi} in PATH"
        except ImportError:
            pytest.skip("onnxruntime not installed")
