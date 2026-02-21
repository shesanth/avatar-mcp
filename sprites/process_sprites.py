"""Process raw SD-generated sprites into game-ready transparent PNGs.

Usage:
    python sprites/process_sprites.py [raw_dir] [output_dir] [--rembg]

Options:
    --rembg   Use rembg (neural network) for background removal instead of
              simple thresholding. Much better results, needs `pip install rembg`.

Defaults:
    raw_dir   = sprites/raw/
    output_dir = src/avatar_mcp/assets/sprites/
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

# Target size for all sprites (square, transparency-padded)
TARGET_SIZE = 400

# Valid pose names — files must be named {pose}.png
VALID_POSES = {
    "idle", "thinking", "coding", "angry", "smug",
    "shy", "planning", "speaking", "listening", "drag",
}


def remove_background_rembg(img: Image.Image) -> Image.Image:
    """Remove background using rembg with isnet-anime model."""
    from rembg import new_session, remove
    session = new_session("isnet-anime")
    return remove(img, session=session)


def remove_background_threshold(img: Image.Image, threshold: int = 240) -> Image.Image:
    """Remove near-white backgrounds via simple color thresholding.

    Fallback when rembg isn't installed. Works okay for clean white backgrounds
    but struggles with shadows, gradients, and anti-aliased edges.
    """
    img = img.convert("RGBA")

    # Check if image already has meaningful transparency
    alpha = img.getchannel("A")
    transparent_pixels = sum(1 for p in alpha.getdata() if p < 128)
    total_pixels = img.width * img.height
    if transparent_pixels > total_pixels * 0.05:
        return img

    data = img.getdata()
    new_data = []
    for r, g, b, a in data:
        if r > threshold and g > threshold and b > threshold:
            new_data.append((r, g, b, 0))
        else:
            new_data.append((r, g, b, a))
    img.putdata(new_data)
    return img


def remove_background(img: Image.Image, use_rembg: bool = False) -> Image.Image:
    """Remove background — dispatch to rembg or threshold."""
    if use_rembg:
        return remove_background_rembg(img)
    return remove_background_threshold(img)


def auto_crop(img: Image.Image, padding: int = 10) -> Image.Image:
    """Crop to the bounding box of non-transparent content, with padding."""
    bbox = img.getbbox()
    if bbox is None:
        return img

    left, upper, right, lower = bbox
    left = max(0, left - padding)
    upper = max(0, upper - padding)
    right = min(img.width, right + padding)
    lower = min(img.height, lower + padding)

    return img.crop((left, upper, right, lower))


def pad_to_square(img: Image.Image, target: int) -> Image.Image:
    """Center the image on a transparent square canvas of target size."""
    # Scale to fit within target, preserving aspect ratio
    ratio = min(target / img.width, target / img.height)
    if ratio < 1.0:
        new_w = int(img.width * ratio)
        new_h = int(img.height * ratio)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Center on transparent canvas
    canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    offset_x = (target - img.width) // 2
    offset_y = (target - img.height) // 2
    canvas.paste(img, (offset_x, offset_y), img)
    return canvas


def process_sprite(input_path: Path, output_path: Path, use_rembg: bool = False) -> None:
    """Full pipeline: remove bg → crop → pad to square → save."""
    img = Image.open(input_path).convert("RGBA")
    img = remove_background(img, use_rembg=use_rembg)
    img = auto_crop(img)
    img = pad_to_square(img, TARGET_SIZE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG", optimize=True)
    print(f"  {input_path.name} -> {output_path} ({img.size[0]}x{img.size[1]})")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_rembg = "--rembg" in sys.argv

    raw_dir = Path(args[0]) if len(args) > 0 else Path("sprites/raw")
    output_dir = Path(args[1]) if len(args) > 1 else Path("src/avatar_mcp/assets/sprites")

    if use_rembg:
        try:
            import rembg  # noqa: F401
            print("Using rembg for background removal (neural network)")
        except ImportError:
            print("rembg not installed. Install with: pip install rembg")
            print("Falling back to threshold-based removal.")
            use_rembg = False

    if not raw_dir.is_dir():
        print(f"Raw directory not found: {raw_dir}")
        print(f"Create it and place your SD-generated PNGs there.")
        print(f"Files should be named: idle.png, thinking.png, coding.png, etc.")
        sys.exit(1)

    png_files = list(raw_dir.glob("*.png"))
    if not png_files:
        print(f"No PNG files found in {raw_dir}")
        sys.exit(1)

    processed = 0
    skipped = []

    for png in sorted(png_files):
        pose = png.stem.lower()
        if pose not in VALID_POSES:
            skipped.append(png.name)
            continue
        process_sprite(png, output_dir / f"{pose}.png", use_rembg=use_rembg)
        processed += 1

    print(f"\nProcessed: {processed}/{len(VALID_POSES)} poses")
    if skipped:
        print(f"Skipped (unknown pose names): {', '.join(skipped)}")

    missing = VALID_POSES - {p.stem.lower() for p in png_files if p.stem.lower() in VALID_POSES}
    if missing:
        print(f"Missing poses: {', '.join(sorted(missing))}")


if __name__ == "__main__":
    main()
