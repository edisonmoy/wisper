#!/usr/bin/env python3
"""
Generate assets/wisper.icns from scratch using Pillow.

Creates a 1024x1024 PNG with a solid blue (#2563EB) circle and a white
microphone emoji in the centre, then resizes to all required iconset sizes
and runs `iconutil` to produce assets/wisper.icns.

Run: python3 make_icon.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow is not installed. Run: pip install pillow")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
OUTPUT_ICNS = os.path.join(ASSETS_DIR, "wisper.icns")

# Iconset sizes: (icon_size, scale) -> filename
ICONSET_SIZES = [
    (16,   1, "icon_16x16.png"),
    (16,   2, "icon_16x16@2x.png"),
    (32,   1, "icon_32x32.png"),
    (32,   2, "icon_32x32@2x.png"),
    (128,  1, "icon_128x128.png"),
    (128,  2, "icon_128x128@2x.png"),
    (256,  1, "icon_256x256.png"),
    (256,  2, "icon_256x256@2x.png"),
    (512,  1, "icon_512x512.png"),
    (512,  2, "icon_512x512@2x.png"),
]

APPLE_EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
BG_COLOR = (37, 99, 235, 255)   # #2563EB fully opaque
CANVAS_SIZE = 1024
EMOJI = "\U0001f3a4"            # microphone emoji


def make_base_image() -> Image.Image:
    """Create the 1024x1024 base icon image."""
    img = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw solid blue circle (slight inset so edges don't clip)
    margin = 32
    draw.ellipse(
        [margin, margin, CANVAS_SIZE - margin, CANVAS_SIZE - margin],
        fill=BG_COLOR,
    )

    # Try to draw emoji with Apple Color Emoji font
    emoji_drawn = False
    if os.path.exists(APPLE_EMOJI_FONT):
        try:
            font_size = 580
            font = ImageFont.truetype(APPLE_EMOJI_FONT, font_size, index=0)
            # Measure bounding box so we can centre it
            bbox = draw.textbbox((0, 0), EMOJI, font=font, embedded_color=True)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = (CANVAS_SIZE - text_w) // 2 - bbox[0]
            y = (CANVAS_SIZE - text_h) // 2 - bbox[1]
            draw.text((x, y), EMOJI, font=font, embedded_color=True)
            emoji_drawn = True
        except Exception as exc:
            print(f"  Warning: could not render emoji with Apple font: {exc}")

    if not emoji_drawn:
        # Fallback: draw a simple white circle (mic body) + rectangle (stand)
        cx, cy = CANVAS_SIZE // 2, CANVAS_SIZE // 2
        white = (255, 255, 255, 255)
        # Mic capsule
        draw.ellipse([cx - 110, cy - 200, cx + 110, cy + 60], fill=white)
        # Mic body
        draw.rectangle([cx - 70, cy - 130, cx + 70, cy + 60], fill=white)
        # Stand arc approximation (three rectangles)
        draw.rectangle([cx - 150, cy + 60, cx + 150, cy + 100], fill=white)
        draw.rectangle([cx - 150, cy + 60, cx - 110, cy + 200], fill=white)
        draw.rectangle([cx + 110, cy + 60, cx + 150, cy + 200], fill=white)
        draw.rectangle([cx - 40, cy + 200, cx + 40, cy + 240], fill=white)

    return img


def main() -> None:
    os.makedirs(ASSETS_DIR, exist_ok=True)

    print("Generating base 1024x1024 icon…")
    base = make_base_image()

    with tempfile.TemporaryDirectory() as tmpdir:
        iconset_dir = os.path.join(tmpdir, "wisper.iconset")
        os.makedirs(iconset_dir)

        for icon_size, scale, filename in ICONSET_SIZES:
            pixel_size = icon_size * scale
            resized = base.resize((pixel_size, pixel_size), Image.LANCZOS)
            dest = os.path.join(iconset_dir, filename)
            resized.save(dest, "PNG")
            print(f"  Wrote {filename} ({pixel_size}x{pixel_size})")

        # iconutil is macOS-only; check for it
        if shutil.which("iconutil") is None:
            print(
                "ERROR: `iconutil` not found. This script must run on macOS."
            )
            sys.exit(1)

        print("Running iconutil…")
        result = subprocess.run(
            ["iconutil", "-c", "icns", iconset_dir, "-o", OUTPUT_ICNS],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"ERROR: iconutil failed:\n{result.stderr}")
            sys.exit(1)

    print(f"Success: {OUTPUT_ICNS}")


if __name__ == "__main__":
    main()
