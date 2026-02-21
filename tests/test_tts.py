"""TTS test — synthesize and play a few lines with different emotions.

Usage: python -m tests.test_tts
(from the claude-avatar directory)
"""

import asyncio
import sys
import time

sys.path.insert(0, "src")

from claude_avatar.voice.tts_edge import EdgeTTSEngine
from claude_avatar.voice.audio import AudioQueue


async def main():
    print("Initializing Edge TTS (ja-JP-NanamiNeural)...")
    tts = EdgeTTSEngine(voice="ja-JP-NanamiNeural")
    audio = AudioQueue()

    lines = [
        ("Mou, nani yo! I was in the middle of something!", "angry"),
        ("Ehhhh, you actually did it right for once...", "smug"),
        ("I-it's not like I wanted to help you or anything, baka!", "shy"),
        ("Yatta! That code actually compiled!", "excited"),
    ]

    for text, emotion in lines:
        print(f"\n  [{emotion}] {text}")
        path = await tts.synthesize(text, emotion)
        audio.add(path)
        # wait for playback to finish
        while audio.is_playing:
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.3)

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
