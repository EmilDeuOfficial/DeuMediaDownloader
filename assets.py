from functools import lru_cache
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import aggdraw
from PIL import Image
import customtkinter as ctk

_IMG_DIR = Path(__file__).parent / "img"


def _parse_translate(t: str):
    m = re.search(r'translate\(\s*([+-]?[\d.]+)[\s,]+([+-]?[\d.]+)\s*\)', t)
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)


def _transform_path(d: str, tx: float, ty: float,
                    vx: float, vy: float, vw: float, vh: float, size: int) -> str:
    sx = size / vw
    sy = size / vh

    def tp(x, y):
        return (x + tx - vx) * sx, (y + ty - vy) * sy

    out = []
    for seg in re.findall(r'[MLCZmlcz][^MLCZmlcz]*', d):
        cmd = seg[0]
        nums = [float(n) for n in re.findall(
            r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', seg[1:])]
        out.append(cmd)
        if cmd in 'ML':
            for i in range(0, len(nums), 2):
                out.append('{:.3f},{:.3f}'.format(*tp(nums[i], nums[i + 1])))
        elif cmd == 'C':
            for i in range(0, len(nums), 2):
                out.append('{:.3f},{:.3f}'.format(*tp(nums[i], nums[i + 1])))
    return ' '.join(out)


def _svg_to_pil(svg_path: Path, fill: str, size: int) -> Image.Image:
    tree = ET.parse(str(svg_path))
    root = tree.getroot()

    vb = root.get('viewBox', '0 0 20 20').split()
    vx, vy, vw, vh = float(vb[0]), float(vb[1]), float(vb[2]), float(vb[3])

    def tagname(e):
        return e.tag.split('}')[-1]

    paths = []

    def walk(elem, tx=0.0, ty=0.0):
        if tagname(elem) == 'g':
            dtx, dty = _parse_translate(elem.get('transform', ''))
            tx += dtx
            ty += dty
        if tagname(elem) == 'path':
            paths.append((elem.get('d', ''), tx, ty))
        for child in elem:
            walk(child, tx, ty)

    walk(root)

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    canvas = aggdraw.Draw(img)
    brush = aggdraw.Brush(fill, 255)

    for d, tx, ty in paths:
        transformed = _transform_path(d, tx, ty, vx, vy, vw, vh, size)
        try:
            canvas.symbol((0, 0), aggdraw.Symbol(transformed), brush)
        except Exception:
            pass

    canvas.flush()
    return img


# Cache the expensive SVG→PIL render; create CTkImage fresh each call
# so it's always bound to the current live Tk root.
@lru_cache(maxsize=None)
def _spotify_pil(size: int) -> Image.Image:
    return _svg_to_pil(_IMG_DIR / "spotify-icon.svg", "#1DB954", size)


@lru_cache(maxsize=None)
def _youtube_pil(size: int) -> Image.Image:
    return _svg_to_pil(_IMG_DIR / "youtube-icon.svg", "#FF0000", size)


@lru_cache(maxsize=None)
def _tiktok_pil(size: int) -> Image.Image:
    return _svg_to_pil(_IMG_DIR / "tiktok-icon.svg", "#EE1D52", size)


def spotify_icon(size: int = 20) -> ctk.CTkImage:
    pil = _spotify_pil(size)
    return ctk.CTkImage(light_image=pil, dark_image=pil, size=(size, size))


def youtube_icon(size: int = 20) -> ctk.CTkImage:
    pil = _youtube_pil(size)
    return ctk.CTkImage(light_image=pil, dark_image=pil, size=(size, size))


def tiktok_icon(size: int = 20) -> ctk.CTkImage:
    pil = _tiktok_pil(size)
    return ctk.CTkImage(light_image=pil, dark_image=pil, size=(size, size))


def warmup_icons() -> None:
    """Pre-render all PIL bitmaps used by the UI into the lru_cache.
    Call this in a background thread right after the launcher appears."""
    for size in (18, 22, 44):
        _spotify_pil(size)
        _youtube_pil(size)
        _tiktok_pil(size)
