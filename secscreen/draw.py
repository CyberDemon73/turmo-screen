"""Shared drawing helpers: canvas size, colors, number formatting, fixed-width digits, Claude spark."""
import math

import numpy as np
from PIL import Image, ImageDraw

W, H = 480, 320  # logical (landscape) canvas

ORANGE = (217, 119, 87)          # Claude orange
APPLE_ORANGE = (255, 159, 10)
BG = (24, 24, 22)
PANEL = (44, 44, 40)
TEXT = (245, 244, 238)
MUTED = (165, 162, 154)
BLUE = (106, 155, 204)
PURPLE = (185, 162, 224)
GREEN = (127, 182, 133)


def canvas(color=BG, size=(W, H)):
    img = Image.new("RGB", size, color)
    return img, ImageDraw.Draw(img)


def fmt_tokens(v):
    v = int(v)
    if v >= 1_000_000_000:
        return f"{v / 1e9:.2f}B"
    if v >= 1_000_000:
        return f"{v / 1e6:.0f}M" if v >= 100_000_000 else f"{v / 1e6:.1f}M"
    if v >= 1_000:
        return f"{v / 1e3:.0f}K" if v >= 100_000 else f"{v / 1e3:.1f}K"
    return str(v)


def fmt_span(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "<1m"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m"


def fmt_clock(seconds, tenths=False, hundredths=False):
    """mm:ss or h:mm:ss, optionally with fractional digits."""
    whole = int(seconds)
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    out = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    if hundredths:
        out += f".{int((seconds - whole) * 100):02d}"
    elif tenths:
        out += f".{int((seconds - whole) * 10)}"
    return out


def bar(d, x, y, w, h, color):
    if w <= 0:
        return
    w = max(w, h)
    d.rounded_rectangle((x, y, x + w, y + h), radius=h / 2, fill=color)


def capsule(d, p1, p2, width, color):
    """Thick line with round caps."""
    d.line([p1, p2], fill=color, width=max(1, int(round(width))))
    r = width / 2
    for x, y in (p1, p2):
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)


_digit_w = {}


def mono_width(f, text):
    key = id(f)
    if key not in _digit_w:
        _digit_w[key] = max(f.getlength(c) for c in "0123456789")
    dw = _digit_w[key]
    return sum(dw if c.isdigit() else f.getlength(c) for c in text), dw


def draw_mono(d, xy, text, f, fill, anchor="ms"):
    """Draw text with fixed-width digits so changing numbers don't jitter.
    anchor[0] in l/m/r (horizontal), anchor[1] is passed through for vertical."""
    total, dw = mono_width(f, text)
    x, y = xy
    if anchor[0] == "m":
        x -= total / 2
    elif anchor[0] == "r":
        x -= total
    for c in text:
        w = dw if c.isdigit() else f.getlength(c)
        d.text((x + w / 2, y), c, font=f, fill=fill, anchor="m" + anchor[1])
        x += w


def blend(c1, c2, a):
    return tuple(int(c1[i] * (1 - a) + c2[i] * a) for i in range(3))


# ---------------------------------------------------------------- Claude spark

RAY_LEN = [1.0, 0.70, 0.90, 0.64, 0.97, 0.76, 0.93, 0.68, 0.88, 0.79, 1.0, 0.72]
RAY_JIT = [0, 5, -4, 2, -5, 3, 0, -3, 4, -4, 2, -1]
_glow_cache = {}


def _glow(n, bg, color):
    key = (n, bg, color)
    if key not in _glow_cache:
        yy, xx = np.mgrid[0:n, 0:n]
        c = (n - 1) / 2
        dist = np.hypot(xx - c, yy - c) / (n * 0.49)
        a = (np.clip(1 - dist, 0, 1) ** 2 * 0.22)[..., None]
        arr = np.array(bg, float) * (1 - a) + np.array(color, float) * a
        _glow_cache[key] = Image.fromarray(arr.astype(np.uint8), "RGB")
    return _glow_cache[key]


def spark(size, t, active, bg=BG, color=ORANGE, ss=3):
    """Claude-style starburst. Active: rays ripple and glow; idle: gentle breathing.
    Rays pulse in place (no rotation) so few pixels change per frame on the slow USB link."""
    n = size * ss
    im = _glow(n, bg, color).copy() if active else Image.new("RGB", (n, n), bg)
    d = ImageDraw.Draw(im)
    c = n / 2
    R = n * 0.40
    w = R * 0.17
    r = w / 2
    step = max(1.0, w * 0.2)
    wave = (t * 9.0) % 12  # active: a bump that travels around the rays (~1.3 s per turn)
    for i in range(12):
        ang = math.radians(i * 30 + RAY_JIT[i])
        cs, sn = math.cos(ang), math.sin(ang)
        base = R * RAY_LEN[i]
        if active:
            # only the 2-3 rays near the wave move; the others stay pixel-identical
            dist = min(abs(i - wave), 12 - abs(i - wave))
            bump = (1 - (dist / 1.6) ** 2) ** 2 if dist < 1.6 else 0.0
            shortest = base
            length = base * (1 + 0.22 * bump)
        else:
            shortest = base * 0.95
            length = base * (1 + 0.05 * math.sin(t * 1.8 + i * 1.3))
        # Fixed body (pixel-identical every frame) + disks stamped on a fixed grid up to the tip,
        # so only the pixels around the tip change between frames (keeps USB traffic tiny).
        capsule(d, (c + cs * R * 0.14, c + sn * R * 0.14), (c + cs * shortest, c + sn * shortest), w, color)
        s = shortest + step
        while s < length:
            x, y = c + cs * s, c + sn * s
            d.ellipse((x - r, y - r, x + r, y + r), fill=color)
            s += step
        x, y = c + cs * length, c + sn * length
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)
    return im.resize((size, size), Image.LANCZOS)


def app_icon_image(size):
    """App icon: a main monitor with a small second screen in front showing a mini chart,
    on an orange-to-pink gradient tile (RGBA)."""
    ss = 4
    n = size * ss
    small = size <= 32

    # gradient tile
    yy, xx = np.mgrid[0:n, 0:n]
    a = ((xx + yy) / (2 * n))[..., None]
    grad = np.array((255, 138, 76), float) * (1 - a) + np.array((222, 54, 110), float) * a
    tile = Image.fromarray(grad.astype(np.uint8), "RGB").convert("RGBA")
    mask = Image.new("L", (n, n), 0)
    m = n * 0.04
    ImageDraw.Draw(mask).rounded_rectangle((m, m, n - m, n - m), radius=n * 0.22, fill=255)
    tile.putalpha(mask)

    layer = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    white = (255, 255, 255, 255)
    if not small:
        # main monitor behind: outline + stand
        bx = (n * 0.16, n * 0.20, n * 0.70, n * 0.56)
        d.rounded_rectangle(bx, radius=n * 0.05, outline=(255, 255, 255, 140), width=int(n * 0.035))
        d.rounded_rectangle((n * 0.38, n * 0.56, n * 0.48, n * 0.66), radius=n * 0.01, fill=(255, 255, 255, 140))
    # the second screen in front
    fx = (n * 0.36, n * 0.42, n * 0.86, n * 0.80) if not small else (n * 0.16, n * 0.26, n * 0.84, n * 0.74)
    d.rounded_rectangle(fx, radius=n * 0.06, fill=white)
    inset = n * (0.035 if not small else 0.06)
    ix0, iy0, ix1, iy1 = fx[0] + inset, fx[1] + inset, fx[2] - inset, fx[3] - inset
    d.rounded_rectangle((ix0, iy0, ix1, iy1), radius=n * 0.03, fill=(30, 27, 38, 255))
    # mini bar chart on the second screen
    heights = (0.45, 0.8, 0.6, 1.0) if not small else (0.5, 0.95, 0.7)
    gap = (ix1 - ix0) * 0.12
    bw = ((ix1 - ix0) - gap * (len(heights) + 1)) / len(heights)
    base = iy1 - (iy1 - iy0) * 0.16
    top = iy0 + (iy1 - iy0) * 0.16
    colors = [(255, 160, 90, 255), (255, 120, 110, 255), (240, 90, 130, 255), (255, 190, 100, 255)]
    for i, h in enumerate(heights):
        x0 = ix0 + gap + i * (bw + gap)
        d.rounded_rectangle((x0, base - (base - top) * h, x0 + bw, base), radius=bw * 0.3, fill=colors[i])
    tile.alpha_composite(layer)
    return tile.resize((size, size), Image.LANCZOS)


def message_image(title, subtitle="", bg=BG, size=(W, H)):
    from .fonts import font
    img, d = canvas(bg, size)
    w, h = size
    d.text((w / 2, h / 2 - 6), title, font=font(26 if w > 400 else 22, "semibold"), fill=TEXT, anchor="ms")
    if subtitle:
        f = font(16 if w > 400 else 14)
        lines, line = [], ""
        for word in subtitle.split():  # wrap to the screen width
            test = (line + " " + word).strip()
            if f.getlength(test) > w - 24 and line:
                lines.append(line)
                line = word
            else:
                line = test
        lines.append(line)
        for i, ln in enumerate(lines[:3]):
            d.text((w / 2, h / 2 + 24 + i * 20), ln, font=f, fill=MUTED, anchor="ms")
    return img
