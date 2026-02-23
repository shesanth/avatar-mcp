# avatar-mcp

Desktop avatar companion for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Gives Claude a visible on-screen presence with text-to-speech, speech-to-text, and an interactive avatar overlay.

Runs as an [MCP server](https://modelcontextprotocol.io/) — Claude Code connects to it automatically and gets access to voice/avatar tools.

## What it does

- **Avatar overlay** — A draggable, always-on-top transparent window that displays poses and emotions (PyQt6)
- **Text-to-speech** — Claude can speak aloud with emotional prosody. Three engines:
  - **Kokoro** (default) — Free, local, runs via ONNX runtime. Auto-downloads ~350MB model on first use
  - **Edge TTS** — Free, uses Microsoft's neural voices, requires internet
  - **ElevenLabs** — Premium quality, requires API key
- **Speech-to-text** — Voice input with two engines:
  - **RealtimeSTT** (recommended) — Local Whisper model via faster-whisper, GPU-accelerated, real-time streaming, no API keys
  - **Google Speech API** — Cloud-based fallback, no GPU required, higher latency
- **Emotion system** — 7 emotions (neutral, happy, sad, excited, angry, shy, smug) that affect avatar pose and voice prosody
- **Automatic pose changes** — Avatar reacts to what Claude is doing (coding, thinking, planning, listening) via Claude Code hooks. No manual tool calls needed

## Why?

Claude Code runs in a terminal — if you alt-tab away, switch monitors, or just glance at another screen, you lose all visual feedback. The avatar sits on top of everything so you always know what Claude is doing: coding, thinking, speaking, or waiting for input. Useful for multi-monitor setups, long-running tasks, and voice-driven workflows where the terminal isn't in focus.

## Setup

### Requirements

- Python 3.11+
- A microphone (for STT)
- Speakers/headphones (for TTS)

### Install

```bash
git clone <this-repo>
cd avatar-mcp
pip install -e .
```

For RealtimeSTT (local Whisper, recommended if you have a GPU):
```bash
pip install -e ".[realtime-stt]"
# For CUDA acceleration (replace cu128 with your CUDA version):
pip install --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

For ElevenLabs support:
```bash
pip install -e ".[premium]"
```

For development:
```bash
pip install -e ".[dev]"
```

### Configure Claude Code

Add to your project's `.mcp.json` (or global MCP config):

```json
{
  "mcpServers": {
    "avatar-mcp": {
      "command": "python",
      "args": ["-m", "avatar_mcp.server"],
      "cwd": "/path/to/avatar-mcp"
    }
  }
}
```

Restart Claude Code. The avatar window should appear and tools will be available.

### Automatic Poses via Hooks (recommended)

The avatar can change poses automatically based on what Claude is doing — no manual `set_pose()` calls needed. Add hooks to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [{ "type": "command", "command": "echo thinking > \"$HOME/.claude/avatar-pose\"" }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit|Bash",
        "hooks": [{ "type": "command", "command": "echo coding > \"$HOME/.claude/avatar-pose\"" }]
      },
      {
        "matcher": "Read|Grep|Glob",
        "hooks": [{ "type": "command", "command": "echo thinking > \"$HOME/.claude/avatar-pose\"" }]
      },
      {
        "matcher": "Task|EnterPlanMode",
        "hooks": [{ "type": "command", "command": "echo planning > \"$HOME/.claude/avatar-pose\"" }]
      }
    ],
    "PermissionRequest": [
      {
        "hooks": [{ "type": "command", "command": "echo listening > \"$HOME/.claude/avatar-pose\"" }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "echo listening > \"$HOME/.claude/avatar-pose\"" }]
      }
    ]
  }
}
```

This maps avatar poses to Claude's activity:
- **User sends message** → thinking pose (UserPromptSubmit)
- **Edit/Write/Bash** → coding pose (PreToolUse)
- **Read/Grep/Glob** → thinking pose (PreToolUse)
- **Task/Plan mode** → planning pose (PreToolUse)
- **Waiting for approval** → listening pose (PermissionRequest)
- **Turn complete** → listening pose (Stop)
- **speak(text, emotion)** → emotion-matched pose while speaking (built-in, no hook needed)

The MCP server watches the `~/.claude/avatar-pose` file for changes and updates the avatar automatically.

### Auto-allow tools (optional)

To skip approval prompts, add to `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__avatar-mcp__speak",
      "mcp__avatar-mcp__show_avatar",
      "mcp__avatar-mcp__hide_avatar"
    ]
  }
}
```

## Configuration

Edit `config.toml` in the project root:

```toml
[avatar]
start_visible = true
start_x = 100          # initial window position
start_y = 100
sprite_scale = 1.0
sprite_directory = ""   # empty = use built-in placeholders; set a path to use custom PNGs
poll_interval_ms = 50

[tts]
engine = "kokoro"       # "edge", "kokoro", or "elevenlabs"
voice = "jf_alpha"      # voice ID (run list_voices tool to see options)
kokoro_lang = "en-us"   # language override for Kokoro (auto-detected from voice prefix if empty)
elevenlabs_api_key = ""
elevenlabs_voice_id = ""
elevenlabs_model = "eleven_flash_v2_5"

[stt]
enabled = true
engine = "realtime"            # "google" or "realtime" (local whisper)
language = "en-US"
cooldown_seconds = 3.0
pause_threshold = 1.2
wake_words = ["claude", "hey claude"]
# realtime engine (faster-whisper via RealtimeSTT)
realtime_model = "base"        # tiny / base / small / medium / large-v3
realtime_device = "cuda"       # "cuda" or "cpu"
realtime_silero_sensitivity = 0.4
# google engine (fallback)
energy_threshold = 150
phrase_threshold = 0.1
non_speaking_duration = 0.5

[behavior]
auto_speak = true
```

## MCP Tools

Once connected, Claude Code has access to these tools:

| Tool | Description |
|------|-------------|
| `speak(text, emotion)` | Speak text aloud with emotional prosody. Shows emotion-matched pose while speaking |
| `show_avatar()` | Show the avatar window |
| `hide_avatar()` | Hide the avatar window |
| `start_listening()` | Start speech recognition |
| `stop_listening()` | Stop speech recognition |
| `set_voice(voice_id, engine)` | Change TTS voice or engine |
| `list_voices(engine)` | List available voices |

### Emotions
`neutral`, `happy`, `sad`, `excited`, `angry`, `shy`, `smug`

### Poses
`idle`, `thinking`, `coding`, `angry`, `smug`, `shy`, `planning`, `speaking`, `listening`, `drag`

## Custom Sprites

To use your own avatar sprites, create a directory with PNG files named after poses:

```
my-sprites/
  idle.png
  thinking.png
  coding.png
  angry.png
  smug.png
  shy.png
  planning.png
  speaking.png
  listening.png
  drag.png
```

Then set `sprite_directory = "path/to/my-sprites"` in `config.toml`.

## Voice Input

Speech-to-text uses wake word activation by default. Say **"Claude"** or **"Hey Claude"** followed by your message. Text is injected into Claude Code's input as `[VOICE]` messages.

### STT Engines

**RealtimeSTT** (recommended) — Uses faster-whisper for local, GPU-accelerated transcription. Streams results in real-time with built-in Silero VAD. No network calls, no API keys, no truncation. Requires `pip install -e ".[realtime-stt]"` and CUDA-enabled PyTorch.

**Google Speech API** (fallback) — Cloud-based, works without a GPU but has higher latency and may drop long utterances. Set `engine = "google"` in config to use.

Configure wake words in `config.toml` under `[stt]`. Set `wake_words = []` to disable filtering (all speech passes through).

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Process Cleanup

The MCP server spawns several child processes (avatar display, multiprocessing Manager, STT workers). Multiple mechanisms ensure these are cleaned up when Claude Code exits:

1. **Parent watchdog** — A daemon thread polls every 2s to check if the parent process (Claude Code) is alive. If the parent dies, all children are force-killed immediately. This is the most reliable mechanism since it doesn't depend on signals or atexit.
2. **Job Objects** (Windows) — All child processes are assigned to a Win32 Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so the OS kills them when the MCP server exits.
3. **Display self-monitoring** — The avatar window checks its parent PID every ~2s and self-terminates if the parent is gone.
4. **atexit + signal handlers** — Standard cleanup on normal interpreter shutdown and SIGINT/SIGTERM.
5. **PID file** — `~/.claude/avatar-mcp-children.pid` tracks child PIDs for stale process cleanup on next startup.

## Architecture

```
src/avatar_mcp/
  server.py          # MCP server, pose file watcher, parent watchdog
  lifecycle.py       # Process lifecycle, TTS/STT init, hook pose logic
  config.py          # TOML config parsing
  state.py           # Shared state (multiprocessing.Manager)
  avatar/
    display.py       # PyQt6 overlay window (child process)
    sprites.py       # Sprite loading and placeholder generation
  voice/
    tts_base.py      # Abstract TTS engine interface
    tts_edge.py      # Edge TTS (free, cloud)
    tts_kokoro.py    # Kokoro TTS (free, local ONNX)
    tts_eleven.py    # ElevenLabs TTS (premium)
    audio.py         # Playback queue
    emotions.py      # Emotion → prosody mapping
    stt_base.py      # Abstract STT engine interface
    stt_google.py    # Google Speech API (cloud fallback)
    stt_realtime.py  # RealtimeSTT / faster-whisper (local, GPU)
  input/
    sender.py        # Injects voice text into Claude Code via clipboard
```

## License

MIT
