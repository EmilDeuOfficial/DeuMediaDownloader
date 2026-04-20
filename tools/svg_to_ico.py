"""Convert app-icon.svg to app.ico using Edge headless for rendering."""
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from PIL import Image

REPO_ROOT = Path(__file__).parent.parent
SVG_PATH  = REPO_ROOT / "img" / "app-icon.svg"
ICO_OUT   = REPO_ROOT / "img" / "app.ico"

EDGE_EXE  = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not Path(EDGE_EXE).exists():
    EDGE_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

SIZES = [16, 32, 48, 64, 128, 256]

import xml.etree.ElementTree as ET
import re

svg_data = SVG_PATH.read_text(encoding="utf-8")

# Make the SVG square by expanding viewBox horizontally with equal padding
tree = ET.parse(SVG_PATH)
root = tree.getroot()
ns   = "http://www.w3.org/2000/svg"

vb_str  = root.get("viewBox") or f"0 0 {root.get('width','784').replace('pt','')} {root.get('height','1168').replace('pt','')}"
vb      = [float(v) for v in vb_str.split()]
vb_w, vb_h = vb[2], vb[3]
pad     = (vb_h - vb_w) / 2 if vb_h > vb_w else 0
new_vb  = f"{vb[0] - pad} {vb[1]} {vb_w + 2*pad} {vb_h}"

# Patch SVG string for new square viewBox and remove width/height attrs
svg_data = re.sub(r'viewBox="[^"]*"', f'viewBox="{new_vb}"', svg_data)
svg_data = re.sub(r'\s+width="[^"]*"', '', svg_data)
svg_data = re.sub(r'\s+height="[^"]*"', '', svg_data)

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width: 256px; height: 256px;
  background: transparent;
  overflow: hidden;
}}
svg {{
  width: 256px;
  height: 256px;
  display: block;
}}
</style>
</head>
<body>
{svg_data}
</body>
</html>"""

tmpdir = Path(tempfile.mkdtemp())
html_file   = tmpdir / "icon.html"
screenshot  = tmpdir / "screenshot.png"
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
# Crop to 256x256 (Edge may add extra height for browser chrome)
img = img.crop((0, 0, 256, 256))

# Edge renders the SVG as: white logo shapes on black background.
# We want: white logo shapes on transparent background.
# Use the R channel directly as alpha (white=opaque, black=transparent).
r, g, b, a = img.split()
alpha = r  # white logo pixels → alpha=255 (opaque); black bg → alpha=0 (transparent)
white_ch = Image.new("L", img.size, 255)
final = Image.merge("RGBA", (white_ch, white_ch, white_ch, alpha))

final.save(ICO_OUT, format="ICO", sizes=[(s, s) for s in SIZES])

shutil.rmtree(tmpdir)
print(f"Saved: {ICO_OUT}")
