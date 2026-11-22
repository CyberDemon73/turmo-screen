"""Regenerate the README images from demo data (no real usage data, files or devices needed).

    python docs/make_screenshots.py

Writes into docs/images/.
"""
import math
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "images"
TMP = Path(tempfile.mkdtemp(prefix="secscreen-docs-"))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402
from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
app.setStyle("Fusion")

from secscreen.draw import app_icon_image  # noqa: E402
from secscreen.fonts import font  # noqa: E402
from secscreen.modes import create_modes  # noqa: E402
from secscreen.settings import Settings  # noqa: E402
from secscreen.usage import Stats  # noqa: E402

BASE = datetime(2026, 11, 22, 10, 9, 32).timestamp()  # a nice time for clock hands


# ---------------------------------------------------------------- demo data
class FakeWatcher:
    def __init__(self, stats):
        self.stats = stats
        self.store = type("S", (), {"roots": [Path("~/.claude/projects")], "entries": [0] * 17311})()

    def start(self):
        pass


def demo_stats(active=True):
    return Stats(t_in=4_210, t_out=1_620_000, t_cw=6_400_000, t_cr=412_000_000, t_msgs=1458,
                 block_tokens=38_400_000, block_end=BASE + 3 * 3600 + 12 * 60, block_active=True,
                 burn_per_min=1_150_000, last_context=96_000, model="claude-opus-5-5",
                 last_time=BASE if active else BASE - 7 * 60,
                 days=[210e6, 168e6, 32e6, 41e6, 12e6, 9e6, 424e6],
                 day_names=["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"], loaded=True)


def demo_photo():
    w, h = 1200, 800
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        a = y / h
        d.line((0, y, w, y), fill=(int(40 + 215 * a), int(30 + 110 * a), int(90 + 20 * a)))
    d.ellipse((520, 380, 760, 620), fill=(255, 214, 140))
    d.polygon([(0, 640), (260, 430), (480, 600), (700, 400), (960, 620), (1200, 470), (1200, 800), (0, 800)],
              fill=(46, 26, 60))
    d.polygon([(0, 720), (300, 600), (620, 730), (900, 610), (1200, 700), (1200, 800), (0, 800)],
              fill=(24, 14, 34))
    p = TMP / "sunset.jpg"
    im.save(p, quality=92)
    return str(p)


def demo_gif():
    frames = []
    for i in range(24):
        im = Image.new("RGB", (220, 160), (18, 24, 48))
        d = ImageDraw.Draw(im)
        x = 110 + 70 * math.cos(i / 24 * 2 * math.pi)
        y = 80 + 40 * math.sin(i / 24 * 2 * math.pi)
        d.ellipse((x - 22, y - 22, x + 22, y + 22), fill=(255, 150, 80))
        frames.append(im)
    p = TMP / "orbit.gif"
    frames[0].save(p, save_all=True, append_images=frames[1:], duration=50, loop=0)
    return str(p)


def setup_modes():
    st = Settings(TMP / "settings.json")
    st.data["autoconnect"] = False
    modes = create_modes(st)
    modes["tokens"].watcher = FakeWatcher(demo_stats())
    tasks = ["Reply to client emails", "Ship SecScreen v1.0", "Buy groceries", "Call mom", "Gym at 7pm",
             "Review pull request #42", "Book dentist appointment"]
    modes["tasks"].cfg["tasks"] = [{"id": i, "text": t, "done": i in (1, 3)} for i, t in enumerate(tasks)]
    modes["photo"].cfg["paths"] = [demo_photo()]
    modes["gif"].cfg["paths"] = [demo_gif()]
    tm = modes["timer"]
    tm.cfg["duration"] = 25 * 60
    tm.start()
    tm.end = time.monotonic() + 15 * 60 + 42
    sw = modes["stopwatch"]
    sw.acc, sw.laps = 137.06, [75.4, 106.6, 135.5]
    modes["message"].cfg.update(text="In a meeting", theme="claude")
    return st, modes


# ---------------------------------------------------------------- framing
def bezel(img, pad=16, radius=28, shadow=26):
    w, h = img.size
    W, H = w + 2 * pad + 2 * shadow, h + 2 * pad + 2 * shadow
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((shadow, shadow + 8, W - shadow, H - shadow + 8), radius=radius,
                                         fill=(0, 0, 0, 120))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(shadow / 2)))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((shadow, shadow, W - shadow, H - shadow), radius=radius, fill=(14, 14, 16, 255),
                        outline=(70, 70, 76, 255), width=2)
    out.paste(img, (shadow + pad, shadow + pad))
    return out


def render(mode, size, now=BASE):
    mode.size = size
    if mode.id in ("photo", "gif"):  # these load in the background
        mode.render(now)
        time.sleep(1.0)
    return mode.render(now).convert("RGB")


def grid(images, cols, bg=(0, 0, 0, 0), gap=8):
    w, h = images[0].size
    rows = math.ceil(len(images) / cols)
    out = Image.new("RGBA", (cols * w + (cols - 1) * gap, rows * h + (rows - 1) * gap), bg)
    for i, im in enumerate(images):
        out.alpha_composite(im, ((i % cols) * (w + gap), (i // cols) * (h + gap)))
    return out


# ---------------------------------------------------------------- outputs
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "modes").mkdir(exist_ok=True)
    st, modes = setup_modes()

    app_icon_image(512).save(OUT / "logo.png")

    landscape = {}
    for mid, m in modes.items():
        landscape[mid] = render(m, (480, 320))
        bezel(landscape[mid]).save(OUT / "modes" / f"{mid}.png")
    clock = modes["clock"]
    clock.cfg["style"] = "digital"
    landscape["clock_digital"] = render(clock, (480, 320))
    bezel(landscape["clock_digital"]).save(OUT / "modes" / "clock_digital.png")
    clock.cfg.update(style="analog", theme="light")
    bezel(render(clock, (480, 320))).save(OUT / "modes" / "clock_light.png")
    clock.cfg["theme"] = "dark"

    order = ["tokens", "clock", "tasks", "clock_digital", "timer", "system", "photo", "stopwatch", "message"]
    grid([bezel(landscape[k]) for k in order], 3).save(OUT / "modes-landscape.png")

    portrait = []
    for mid in ("tokens", "clock", "tasks", "timer"):
        portrait.append(bezel(render(modes[mid], (320, 480))))
    clock.cfg["style"] = "digital"
    portrait.append(bezel(render(clock, (320, 480))))
    clock.cfg["style"] = "analog"
    grid(portrait, 5).save(OUT / "modes-portrait.png")

    # animated spark (one full turn of the "working" wave = 32 frames at 24 fps)
    tok = modes["tokens"]
    tok.size = (480, 320)
    frames = []
    for k in range(32):
        frames.append(bezel(tok.render(BASE + k / 24)).convert("RGB")
                      .quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    frames[0].save(OUT / "tokens-live.gif", save_all=True, append_images=frames[1:], duration=42, loop=0,
                   optimize=True)

    hero(landscape["tokens"], render(clock, (320, 480)))
    window_shots(st, modes)
    print("Images written to", OUT)


def hero(screen_l, screen_p):
    W, H = 1280, 640
    bg = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        a = y / H
        d.line((0, y, W, y), fill=(int(22 + 20 * a), int(20 + 8 * a), int(31 + 14 * a), 255))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((700, 60, 1260, 620), fill=(255, 120, 90, 60))
    bg.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90)))
    bg.alpha_composite(app_icon_image(120), (80, 150))
    d = ImageDraw.Draw(bg)
    d.text((80, 340), "SecScreen", font=font(76, "bold"), fill=(255, 255, 255, 255), anchor="ls")
    for i, line in enumerate(("Turn a 3.5″ USB smart screen into a live", "Claude Code dashboard, clock, to-do list,",
                              "photo frame and more.")):
        d.text((82, 392 + i * 36), line, font=font(26), fill=(200, 196, 210, 255), anchor="ls")
    d.text((82, 520), "Windows  ·  macOS  ·  Linux", font=font(20, "semibold"), fill=(255, 150, 100, 255),
           anchor="ls")
    bl = bezel(screen_l)
    bg.alpha_composite(bl, (W - bl.width - 30, 60))
    bp = bezel(screen_p.resize((240, 360), Image.LANCZOS), pad=12, radius=22)
    bg.alpha_composite(bp, (W - bl.width - 90, H - bp.height + 10))
    bg.save(OUT / "hero.png")


def window_shots(st, modes):
    from secscreen.engine import Engine
    from secscreen.gui import MainWindow, SCREEN_PAGE

    engine = Engine(modes, st)
    win = MainWindow(engine, modes, st)
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    win.resize(1180, 760)
    win.show()
    engine.start()
    win._on_status("connected", "Connected · COM6")
    win.set_connected_ui(True)
    shots = [("clock", "app-clock.png"), ("tasks", "app-tasks.png"), (SCREEN_PAGE, "app-screen-settings.png")]

    def step(i=0):
        if i > 0:
            win._on_status("connected", "Connected · COM6")
            win.fps_label.setText("58.1 fps")
            win.grab().save(str(OUT / shots[i - 1][1]))
        if i == len(shots):
            engine.stop()
            win.tray.hide()
            app.quit()
            return
        target = shots[i][0]
        if target == SCREEN_PAGE:
            win.sidebar.setCurrentRow(win.sidebar.count() - 1)
        else:
            win.select_mode(target)
        QTimer.singleShot(1500, lambda: step(i + 1))

    QTimer.singleShot(800, step)
    app.exec()


if __name__ == "__main__":
    main()
