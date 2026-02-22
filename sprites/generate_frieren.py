"""Generate Frieren avatar sprites using NoobAI-XL Cyberfix.

Two batches:
  1. artist:abe_tsukasa -- manga-accurate style
  2. artist:nat_the_lich + artist:morry -- stylized alt

Usage:
    python sprites/generate_frieren.py
    python sprites/generate_frieren.py --style abe       # abe_tsukasa only
    python sprites/generate_frieren.py --style natmorry   # nat_the_lich/morry only
"""

from __future__ import annotations

import argparse
import gc
from pathlib import Path

import torch
from diffusers import EulerDiscreteScheduler, StableDiffusionXLPipeline
from huggingface_hub import hf_hub_download

# --- Character prompt: Frieren (Sousou no Frieren) ---
# Danbooru tags sourced from the character's 13k+ post corpus.
FRIEREN_BASE = (
    "masterpiece, best quality, "
    "{artist_tags}"
    "1girl, solo, upper body, "
    "frieren, sousou no frieren, elf, pointy ears, "
    "white hair, twintails, green eyes, white capelet, "
    "simple background, white background, "
    "{pose_tags}"
)

NEGATIVE_PROMPT = (
    "nsfw, worst quality, old, early, low quality, lowres, "
    "signature, username, logo, bad hands, mutated hands, "
    "bad anatomy, deformed, ugly, blurry, multiple girls, "
    "3d, realistic, photorealistic"
)

ARTIST_TAGS = {
    "abe": "artist:abe_tsukasa, ",
    "natmorry": "artist:nat_the_lich, artist:morry, ",
}

POSE_PROMPTS: dict[str, str] = {
    "idle":      "relaxed, gentle smile, hands clasped, looking at viewer",
    "thinking":  "finger on chin, looking up, tilted head, curious expression",
    "coding":    "holding staff, both hands, casting spell, magic circle, concentrated",
    "angry":     "angry, clenched fist, furrowed brows, pouting, blush",
    "smug":      "smug, closed eyes, hand on hip, smirk, confident",
    "shy":       "blushing, hands covering face, looking away, embarrassed",
    "planning":  "reading book, holding book, focused, looking down",
    "speaking":  "open mouth, pointing finger, gesturing, energetic",
    "listening": "hand to ear, cupping ear, head tilted, attentive, curious",
    "drag":      "arms raised, startled, wide eyes, open mouth, flailing",
}

DEFAULT_STEPS = 28
DEFAULT_CFG = 5
DEFAULT_WIDTH = 832
DEFAULT_HEIGHT = 1216
CYBERFIX_REPO = "Panchovix/noobai-XL-Vpred-1.0-cyberfix"
CYBERFIX_FILE = "NoobAI-XL-Vpred-v1.0-cyberfix.safetensors"
FP16_VAE_REPO = "madebyollin/sdxl-vae-fp16-fix"


def load_pipeline(model_path: str | None = None) -> StableDiffusionXLPipeline:
    if not torch.cuda.is_available():
        print("ERROR: CUDA is required for sprite generation.")
        print("Install PyTorch with CUDA: https://pytorch.org/get-started/locally/")
        raise SystemExit(1)

    if model_path:
        local_path = model_path
    else:
        print(f"Downloading {CYBERFIX_FILE} from {CYBERFIX_REPO}...")
        print("(~6.9GB, cached after first download)")
        local_path = hf_hub_download(repo_id=CYBERFIX_REPO, filename=CYBERFIX_FILE)

    print(f"Loading model: {local_path}")
    from diffusers import AutoencoderKL  # lazy: avoid import if CUDA check fails above
    vae = AutoencoderKL.from_pretrained(FP16_VAE_REPO, torch_dtype=torch.float16)

    pipe = StableDiffusionXLPipeline.from_single_file(
        local_path, vae=vae, use_safetensors=True, torch_dtype=torch.float16,
    )
    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config,
        prediction_type="v_prediction",
        rescale_betas_zero_snr=True,
    )
    pipe = pipe.to("cuda")
    try:
        pipe.enable_xformers_memory_efficient_attention()
    except Exception:
        pass
    return pipe


def generate_batch(pipe, style: str, seed: int, output_dir: Path) -> None:
    artist_tags = ARTIST_TAGS[style]
    style_dir = output_dir / style
    style_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Generating Frieren ({style}) ===")
    print(f"Artist tags: {artist_tags.strip()}")
    print(f"Output: {style_dir}\n")

    for i, (pose, pose_tags) in enumerate(POSE_PROMPTS.items()):
        prompt = FRIEREN_BASE.format(artist_tags=artist_tags, pose_tags=pose_tags)
        pose_seed = seed + i
        gen = torch.Generator(device="cuda").manual_seed(pose_seed)

        print(f"  {pose} (seed={pose_seed})...", end=" ", flush=True)
        image = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT,
            width=DEFAULT_WIDTH,
            height=DEFAULT_HEIGHT,
            num_inference_steps=DEFAULT_STEPS,
            guidance_scale=DEFAULT_CFG,
            generator=gen,
        ).images[0]

        path = style_dir / f"{pose}.png"
        image.save(path, "PNG")
        print(f"saved")

        gc.collect()
        torch.cuda.empty_cache()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Frieren avatar sprites")
    parser.add_argument("--seed", type=int, default=42, help="Base seed")
    parser.add_argument("--style", type=str, default=None,
                        choices=["abe", "natmorry"],
                        help="Generate one style only (default: both)")
    parser.add_argument("--model", type=str, default=None, help="Local model path")
    parser.add_argument("--output", type=str, default="sprites/frieren", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    pipe = load_pipeline(args.model)

    styles = [args.style] if args.style else ["abe", "natmorry"]
    for style in styles:
        generate_batch(pipe, style, args.seed, output_dir)

    print(f"\nDone! Process with: python sprites/process_sprites.py sprites/frieren/<style> <output_dir> --rembg")


if __name__ == "__main__":
    main()
