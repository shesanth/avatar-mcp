"""Sprite loading and placeholder generation."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Placeholder colors per pose — vibrant enough to be visually distinct
POSE_COLORS: dict[str, str] = {
    "idle":      "#7B68EE",  # medium slate blue
    "thinking":  "#FFD700",  # gold
    "coding":    "#00CED1",  # dark turquoise
    "angry":     "#FF4500",  # orange-red
    "smug":      "#FF69B4",  # hot pink
    "shy":       "#FFC0CB",  # pink
    "planning":  "#9370DB",  # medium purple
    "speaking":  "#32CD32",  # lime green
    "listening": "#87CEEB",  # sky blue
    "drag":      "#FFA500",  # orange
}

POSE_KAOMOJI: dict[str, str] = {
    "idle":      "(  -_-)",
    "thinking":  "( ._.?)",
    "coding":    "( >_<)b",
    "angry":     "(`Д´ )",
    "smug":      "( ̄ω ̄)",
    "shy":       "(*/ω＼)",
    "planning":  "( ¬‿¬)",
    "speaking":  "( °▽°)",
    "listening": "( ・ω・)",
    "drag":      "(ﾉ´ヮ`)ﾉ",
}

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "sprites"


def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def generate_placeholder(pose: str, size: int = 200) -> Path:
    """Generate a colored circle placeholder sprite with pose label and kaomoji."""
    output = ASSETS_DIR / f"{pose}.png"
    if output.exists():
        return output

    output.parent.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = _hex_to_rgba(POSE_COLORS.get(pose, "#FFFFFF"))

    # draw filled circle
    margin = 10
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
        outline=(255, 255, 255, 200),
        width=3,
    )

    # draw pose label
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        font_small = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
        font_small = font

    label = pose.upper()
    bbox = draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2, size / 2 - th - 5),
        label,
        fill=(255, 255, 255, 255),
        font=font,
    )

    # draw kaomoji
    kao = POSE_KAOMOJI.get(pose, "")
    if kao:
        bbox2 = draw.textbbox((0, 0), kao, font=font_small)
        kw = bbox2[2] - bbox2[0]
        draw.text(
            ((size - kw) / 2, size / 2 + 5),
            kao,
            fill=(255, 255, 255, 220),
            font=font_small,
        )

    img.save(output, "PNG")
    return output


def ensure_all_placeholders(size: int = 200) -> dict[str, Path]:
    """Generate placeholder sprites for all poses. Returns {pose: path} map."""
    return {pose: generate_placeholder(pose, size) for pose in POSE_COLORS}


def load_sprite_paths(custom_dir: str = "") -> dict[str, Path]:
    """Load sprite paths from custom directory or generate placeholders."""
    if custom_dir:
        custom = Path(custom_dir)
        if custom.is_dir():
            sprites = {}
            for png in custom.glob("*.png"):
                sprites[png.stem] = png
            if sprites:
                return sprites

    return ensure_all_placeholders()
