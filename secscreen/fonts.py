"""Cross-platform font lookup for Pillow (Windows: Segoe UI, macOS: SF/Helvetica, Linux: DejaVu/Noto)."""
import os
import subprocess
import sys
from functools import lru_cache

from PIL import ImageFont

_WIN = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

# weight -> list of candidates. A candidate is (path, ttc_index, variation_name).
_CANDIDATES = {
    "light": [
        (os.path.join(_WIN, "segoeuil.ttf"), 0, None),
        ("/System/Library/Fonts/SFNS.ttf", 0, "Light"),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 7, None),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-ExtraLight.ttf", 0, None),
        ("/usr/share/fonts/TTF/DejaVuSans-ExtraLight.ttf", 0, None),
    ],
    "regular": [
        (os.path.join(_WIN, "segoeui.ttf"), 0, None),
        ("/System/Library/Fonts/SFNS.ttf", 0, "Regular"),
        ("/System/Library/Fonts/Helvetica.ttc", 0, None),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", 0, None),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0, None),
        ("/usr/share/fonts/TTF/DejaVuSans.ttf", 0, None),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf", 0, None),
        ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 0, None),
    ],
    "semibold": [
        (os.path.join(_WIN, "seguisb.ttf"), 0, None),
        ("/System/Library/Fonts/SFNS.ttf", 0, "Semibold"),
        ("/System/Library/Fonts/Helvetica.ttc", 1, None),
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0, None),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0, None),
        ("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", 0, None),
        ("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", 0, None),
        ("/usr/share/fonts/truetype/noto/NotoSans-SemiBold.ttf", 0, None),
    ],
    "bold": [
        (os.path.join(_WIN, "segoeuib.ttf"), 0, None),
        ("/System/Library/Fonts/SFNS.ttf", 0, "Bold"),
        ("/System/Library/Fonts/Helvetica.ttc", 1, None),
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0, None),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0, None),
        ("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", 0, None),
        ("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", 0, None),
        ("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", 0, None),
    ],
}

_FC_PATTERN = {"light": "sans-serif:light", "regular": "sans-serif",
               "semibold": "sans-serif:semibold", "bold": "sans-serif:bold"}


@lru_cache(maxsize=None)
def _fc_match(weight):
    if not sys.platform.startswith("linux"):
        return None
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", _FC_PATTERN[weight]],
                             capture_output=True, text=True, timeout=3).stdout.strip()
        return out or None
    except Exception:
        return None


@lru_cache(maxsize=None)
def font(size, weight="regular"):
    """Return a Pillow font of the given pixel size and weight (light/regular/semibold/bold)."""
    size = int(round(size))
    cands = list(_CANDIDATES.get(weight, _CANDIDATES["regular"]))
    fc = _fc_match(weight)
    if fc:
        cands.append((fc, 0, None))
    for path, index, variation in cands:
        if not os.path.exists(path):
            continue
        try:
            f = ImageFont.truetype(path, size, index=index)
            if variation:
                try:
                    f.set_variation_by_name(variation)
                except Exception:
                    pass
            return f
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()
