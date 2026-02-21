# avatar-mcp

Desktop avatar companion for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Gives Claude a visible on-screen presence with text-to-speech, speech-to-text, and an interactive avatar overlay.

Runs as an [MCP server](https://modelcontextprotocol.io/) — Claude Code connects to it automatically and gets access to voice/avatar tools.

## What it does

- **Avatar overlay** — A draggable, always-on-top transparent window that displays poses and emotions (PyQt6)
- **Text-to-speech** — Claude can speak aloud with emotional prosody. Three engines:
  - **Kokoro** (default) — Free, local, runs via ONNX runtime. Auto-downloads ~350MB model on first use
  - **Edge TTS** — Free, uses Microsoft's neural voices, requires internet
  - **ElevenLabs** — Premium quality, requires API key
- **Speech-to-text** — Voice input via Google Speech API. Supports wake words so it can stay hot while you talk to other people
- **Emotion system** — 8 emotions (neutral, happy, sad, excited, angry, shy, smug, bratty) that affect avatar pose and voice prosody

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

### Auto-allow tools (optional)

To skip approval prompts, add to `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__avatar-mcp__speak",
      "mcp__avatar-mcp__set_emotion",
      "mcp__avatar-mcp__set_pose"
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
enabled = false
language = "en-US"
cooldown_seconds = 1.0
energy_threshold = 150
pause_threshold = 2.0
phrase_threshold = 0.1
non_speaking_duration = 1.0
wake_words = ["claude", "hey claude"]

[behavior]
auto_speak = true
```

## MCP Tools

Once connected, Claude Code has access to these tools:

| Tool | Description |
|------|-------------|
| `speak(text, emotion)` | Speak text aloud with emotional prosody |
| `set_emotion(emotion)` | Set avatar emotion (changes pose) |
| `set_pose(pose)` | Directly set avatar pose |
| `show_avatar()` | Show the avatar window |
| `hide_avatar()` | Hide the avatar window |
| `start_listening()` | Start speech recognition |
| `stop_listening()` | Stop speech recognition |
| `set_voice(voice_id, engine)` | Change TTS voice or engine |
| `list_voices(engine)` | List available voices |

### Emotions
`neutral`, `happy`, `sad`, `excited`, `angry`, `shy`, `smug`, `bratty`

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

Configure wake words in `config.toml` under `[stt]`. Set `wake_words = []` to disable filtering (all speech passes through).

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Architecture

```
src/avatar_mcp/
  server.py          # MCP server entry point
  lifecycle.py       # Process lifecycle, TTS/STT initialization
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
    stt.py           # Speech-to-text with wake words
  input/
    sender.py        # Injects voice text into Claude Code via clipboard
```

## License

MIT
