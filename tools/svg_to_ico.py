"""Convert app-icon.svg to app.ico using Edge headless for rendering."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

REPO_ROOT = Path(__file__).parent.parent
SVG_PATH  = REPO_ROOT / "img" / "app-icon.svg"
ICO_OUT   = REPO_ROOT / "img" / "app.ico"

EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not Path(EDGE_EXE).exists():
    EDGE_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

SIZES      = [16, 32, 48, 64, 128, 256]
ICON_COLOR = (0xFF, 0xD7, 0x00)  # yellow #FFD700

svg_data = SVG_PATH.read_text(encoding="utf-8")
# Remove fixed width/height so the SVG scales to the CSS container
svg_data = re.sub(r'\s+width="[^"]*"',  '', svg_data)
svg_data = re.sub(r'\s+height="[^"]*"', '', svg_data)

PAD = 20  # padding so the icon edges don't get clipped
SVG_SIZE = 256 - PAD * 2

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width: 256px; height: 256px;
  background: black;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}}
svg {{
  width: {SVG_SIZE}px;
  height: {SVG_SIZE}px;
  display: block;
  fill: white;
}}
</style>
</head>
<body>
{svg_data}
</body>
</html>"""

tmpdir    = Path(tempfile.mkdtemp())
html_file = tmpdir / "icon.html"
screenshot = tmpdir / "screenshot.png"
html_file.write_text(html, encoding="utf-8")

subprocess.run([
    EDGE_EXE,
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--hide-scrollbars",
    "--window-size=256,256",
    f"--screenshot={screenshot}",
    html_file.as_uri(),
], check=True, capture_output=True)

img = Image.open(screenshot).convert("RGBA")
img = img.crop((0, 0, 256, 256))

# Black background + white icon: R channel = brightness.
# Use R as alpha (white icon → opaque, black bg → transparent).
# Then tint with ICON_COLOR.
r, g, b, a = img.split()
alpha = r
cr = Image.new("L", img.size, ICON_COLOR[0])
cg = Image.new("L", img.size, ICON_COLOR[1])
cb = Image.new("L", img.size, ICON_COLOR[2])
final = Image.merge("RGBA", (cr, cg, cb, alpha))

final.save(ICO_OUT, format="ICO", sizes=[(s, s) for s in SIZES])
shutil.rmtree(tmpdir)
print(f"Saved: {ICO_OUT}")
