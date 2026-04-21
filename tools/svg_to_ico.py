"""Convert img/app-icon.svg to img/app.ico using aggdraw (no Edge/browser needed)."""
import sys
from pathlib import Path

# Make sure we can import assets.py from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw
from assets import _svg_to_pil

REPO_ROOT  = Path(__file__).parent.parent
SVG_PATH   = REPO_ROOT / "img" / "app-icon.svg"
ICO_OUT    = REPO_ROOT / "img" / "app.ico"

SIZES      = [16, 32, 48, 64, 128, 256]
BG_COLOR   = (0xFF, 0xD7, 0x00, 255)   # yellow #FFD700
ICON_COLOR = "#1A1A1A"                  # near-black
PAD        = 26   # padding inside the rounded rect
RADIUS     = 52   # rounded corner radius (at 256px)


def make_icon(size: int) -> Image.Image:
    pad    = max(2, round(PAD * size / 256))
    radius = max(2, round(RADIUS * size / 256))
    icon_s = size - 2 * pad

    # 1. Render SVG paths onto transparent background
    icon = _svg_to_pil(SVG_PATH, ICON_COLOR, icon_s)  # RGBA, transparent bg

    # 2. Yellow rounded-rect background
    bg   = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bg)
    draw.rounded_rectangle([(0, 0), (size - 1, size - 1)], radius=radius, fill=BG_COLOR)

    # 3. Composite icon centred on background
    bg.paste(icon, (pad, pad), mask=icon.split()[3])
    return bg


# Build the 256×256 master and let Pillow resize for smaller frames
master = make_icon(256)
master.save(ICO_OUT, format="ICO", sizes=[(s, s) for s in SIZES])
print(f"Saved: {ICO_OUT}")
