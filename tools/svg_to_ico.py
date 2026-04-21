"""Convert app-icon.svg to app.ico using Edge headless for rendering."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

REPO_ROOT = Path(__file__).parent.parent
SVG_PATH  = REPO_ROOT / "img" / "app-icon.svg"
ICO_OUT   = REPO_ROOT / "img" / "app.ico"

EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not Path(EDGE_EXE).exists():
    EDGE_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

SIZES      = [16, 32, 48, 64, 128, 256]
BG_COLOR   = (0xFF, 0xD7, 0x00, 255)   # yellow #FFD700
ICON_COLOR = (0x1A, 0x1A, 0x1A, 255)   # near-black
RADIUS     = 52   # rounded corner radius (out of 256px)
PAD        = 28   # icon padding inside the rounded rect

# ── Step 1: render SVG to get icon shape mask ─────────────────────────────────
svg_data = SVG_PATH.read_text(encoding="utf-8")
svg_data = re.sub(r'\s+width="[^"]*"',  '', svg_data)
svg_data = re.sub(r'\s+height="[^"]*"', '', svg_data)

RENDER_SIZE = 256 - 2 * PAD   # size of the actual SVG content area

html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:{RENDER_SIZE}px; height:{RENDER_SIZE}px; background:white; overflow:hidden; }}
svg {{ width:{RENDER_SIZE}px; height:{RENDER_SIZE}px; display:block; fill:black; }}
</style>
</head>
<body>{svg_data}</body>
</html>"""

tmpdir     = Path(tempfile.mkdtemp())
html_file  = tmpdir / "icon.html"
screenshot = tmpdir / "screenshot.png"
html_file.write_text(html, encoding="utf-8")

subprocess.run([
    EDGE_EXE,
    "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
    f"--window-size={RENDER_SIZE},{RENDER_SIZE}",
    f"--screenshot={screenshot}",
    html_file.as_uri(),
], check=True, capture_output=True)

# ── Step 2: extract mask (black SVG paths → opaque, white bg → transparent) ───
raw = Image.open(screenshot).convert("L")
raw = raw.crop((0, 0, RENDER_SIZE, RENDER_SIZE))
mask = ImageOps.invert(raw)                 # black→255, white→0
mask = mask.filter(ImageFilter.SMOOTH_MORE) # smooth anti-aliasing

# ── Step 3: compose icon on yellow rounded-rect background ────────────────────
bg = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(bg)
draw.rounded_rectangle([(0, 0), (255, 255)], radius=RADIUS, fill=BG_COLOR)

# Place dark icon centered inside the rounded rect
icon_layer = Image.new("RGBA", (RENDER_SIZE, RENDER_SIZE), ICON_COLOR)
icon_layer.putalpha(mask)

canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
canvas.paste(icon_layer, (PAD, PAD))

final = Image.alpha_composite(bg, canvas)

# ── Step 4: save multi-size ICO ───────────────────────────────────────────────
final.save(ICO_OUT, format="ICO", sizes=[(s, s) for s in SIZES])
shutil.rmtree(tmpdir)
print(f"Saved: {ICO_OUT}")
