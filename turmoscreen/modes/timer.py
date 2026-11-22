"""Countdown timer with a progress ring, and a stopwatch with laps."""
import math
import time
from datetime import datetime

from PIL import Image, ImageDraw
from PySide6.QtCore import QTimer, Signal, QObject
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
                               QSpinBox, QWidget, QCheckBox)

from ..draw import APPLE_ORANGE, W, H, draw_mono, fmt_clock
from ..fonts import font
from .base import Mode, panel

BG = (16, 16, 16)
TRACK = (48, 48, 48)
FG = (255, 255, 255)
MUTED = (152, 152, 157)
RED = (255, 69, 58)
GREEN = (48, 209, 88)

RING_R = 128      # mid radius of the ring
RING_W = 14
SS = 2


def _ring(frac, color, bg):
    """Progress ring (clockwise from 12 o'clock) as a supersampled image."""
    size = (RING_R * 2 + RING_W + 6)
    n = size * SS
    im = Image.new("RGB", (n, n), bg)
    d = ImageDraw.Draw(im)
    c = n / 2
    rm, w = RING_R * SS, RING_W * SS
    box = (c - rm - w / 2, c - rm - w / 2, c + rm + w / 2, c + rm + w / 2)
    d.ellipse(box, outline=TRACK, width=w)
    if frac > 0.0005:
        end = -90 + 360 * frac
        d.arc(box, -90, end, fill=color, width=w)
        for deg in (-90, end):
            a = math.radians(deg)
            x, y = c + math.cos(a) * rm, c + math.sin(a) * rm
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color)
    return im.resize((size, size), Image.LANCZOS)


class _Notifier(QObject):
    finished = Signal(str)


class TimerMode(Mode):
    id = "timer"
    name = "Timer"
    icon = "⏳"
    description = "Countdown timer with a progress ring. The screen flashes when time is up."
    DEFAULTS = {"duration": 25 * 60, "label": "Focus", "beep": True}

    def __init__(self, settings):
        super().__init__(settings)
        self.running = False
        self.end = 0.0
        self.paused_left = float(self.cfg["duration"])
        self.finished_at = None
        self.notifier = _Notifier()
        self._fired = False

    # --- control (GUI thread)
    def remaining(self):
        if self.running:
            return max(0.0, self.end - time.monotonic())
        return self.paused_left

    def start(self):
        if self.running:
            return
        if self.paused_left <= 0:
            self.paused_left = float(self.cfg["duration"])
        self.finished_at = None
        self._fired = False
        self.end = time.monotonic() + self.paused_left
        self.running = True

    def pause(self):
        if self.running:
            self.paused_left = self.remaining()
            self.running = False

    def reset(self):
        self.running = False
        self.finished_at = None
        self.paused_left = float(self.cfg["duration"])

    def set_duration(self, seconds):
        self.set("duration", int(max(1, seconds)))
        if not self.running:
            self.reset()

    def _check_done(self):
        if self.running and time.monotonic() >= self.end:
            self.running = False
            self.paused_left = 0.0
            self.finished_at = time.monotonic()
            if not self._fired:
                self._fired = True
                self.notifier.finished.emit(self.cfg["label"] or "Timer")

    def fps(self):
        if self.running:
            return 30.0
        if self.finished_at and time.monotonic() - self.finished_at < 60:
            return 4.0
        return 2.0

    def render(self, now):
        self._check_done()
        left = self.remaining()
        total = max(1.0, float(self.cfg["duration"]))
        done = self.finished_at is not None
        flashing = done and time.monotonic() - self.finished_at < 60
        bg = BG
        if flashing and int((time.monotonic() - self.finished_at) * 2) % 2 == 0:
            bg = (90, 20, 16)
        w, h = self.size
        cx, cy = w // 2, h // 2
        img = Image.new("RGB", (w, h), bg)
        color = RED if done else (APPLE_ORANGE if self.running else MUTED)
        ring = _ring(1.0 if done else left / total, color, bg)
        img.paste(ring, (cx - ring.width // 2, cy - ring.height // 2))
        d = ImageDraw.Draw(img)
        d.text((cx, cy - 44), (self.cfg["label"] or "Timer").upper(), font=font(16, "semibold"), fill=MUTED,
               anchor="ms")
        if done:
            d.text((cx, cy + 24), "Time's up", font=font(44, "bold"), fill=FG, anchor="ms")
        else:
            txt = fmt_clock(math.ceil(left))
            size = 64 if len(txt) <= 5 else 50
            draw_mono(d, (cx, cy + 26), txt, font(size, "bold"), FG, anchor="ms")
        if self.running:
            sub = "ends " + datetime.fromtimestamp(time.time() + left).strftime("%H:%M")
        elif done:
            sub = fmt_clock(total) + " done"
        elif left < total:
            sub = "paused"
        else:
            sub = fmt_clock(total)
        d.text((cx, cy + 60), sub, font=font(16), fill=MUTED, anchor="ms")
        return img

    def build_settings(self):
        w, form = panel(self)

        label = QLineEdit(self.cfg["label"])
        label.textChanged.connect(lambda v: self.set("label", v))
        form.addRow("Label:", label)

        dur = int(self.cfg["duration"])
        boxes = []
        row = QHBoxLayout()
        for maximum, value, suffix in ((23, dur // 3600, " h"), (59, dur % 3600 // 60, " m"), (59, dur % 60, " s")):
            sb = QSpinBox()
            sb.setRange(0, maximum)
            sb.setValue(value)
            sb.setSuffix(suffix)
            boxes.append(sb)
            row.addWidget(sb)

        def apply_duration():
            self.set_duration(boxes[0].value() * 3600 + boxes[1].value() * 60 + boxes[2].value())

        for sb in boxes:
            sb.valueChanged.connect(apply_duration)
        form.addRow("Duration:", row)

        presets = QGridLayout()
        for i, m in enumerate((1, 3, 5, 10, 15, 25, 30, 60)):
            b = QPushButton(f"{m} min")

            def pick(_=False, m=m):
                for sb, v in zip(boxes, (m // 60, m % 60, 0)):
                    sb.blockSignals(True)
                    sb.setValue(v)
                    sb.blockSignals(False)
                self.set_duration(m * 60)

            b.clicked.connect(pick)
            presets.addWidget(b, i // 4, i % 4)
        form.addRow("Presets:", presets)

        beep = QCheckBox("Beep and notify when done")
        beep.setChecked(bool(self.cfg["beep"]))
        beep.toggled.connect(lambda v: self.set("beep", v))
        form.addRow("", beep)

        controls = QHBoxLayout()
        start = QPushButton("Start")
        start.setDefault(True)
        reset = QPushButton("Reset")
        controls.addWidget(start)
        controls.addWidget(reset)
        form.addRow("", controls)
        status = QLabel()
        form.addRow("Remaining:", status)

        def toggle():
            self.pause() if self.running else self.start()
            update()

        def update():
            self._check_done()
            start.setText("Pause" if self.running else ("Resume" if 0 < self.remaining() < self.cfg["duration"]
                                                        else "Start"))
            status.setText(fmt_clock(math.ceil(self.remaining())))

        start.clicked.connect(toggle)
        reset.clicked.connect(lambda: (self.reset(), update()))
        t = QTimer(w)
        t.timeout.connect(update)
        t.start(250)
        update()
        return w


class StopwatchMode(Mode):
    id = "stopwatch"
    name = "Stopwatch"
    icon = "⏱"
    description = "Stopwatch with laps."

    def __init__(self, settings):
        super().__init__(settings)
        self.running = False
        self.start_t = 0.0
        self.acc = 0.0
        self.laps = []  # cumulative times

    def elapsed(self):
        return self.acc + (time.monotonic() - self.start_t if self.running else 0.0)

    def start_stop(self):
        if self.running:
            self.acc = self.elapsed()
            self.running = False
        else:
            self.start_t = time.monotonic()
            self.running = True

    def lap_reset(self):
        if self.running:
            self.laps.append(self.elapsed())
        else:
            self.acc = 0.0
            self.laps = []

    def fps(self):
        return 60.0 if self.running else 2.0

    def render(self, now):
        w, h = self.size
        p = self.portrait
        img = Image.new("RGB", (w, h), BG)
        d = ImageDraw.Draw(img)
        e = self.elapsed()
        d.text((w / 2, 56 if p else 40), "STOPWATCH", font=font(16, "semibold"), fill=MUTED, anchor="ms")
        txt = fmt_clock(e, hundredths=True)
        big = (58 if len(txt) <= 8 else 46) if p else (76 if len(txt) <= 8 else 60)
        draw_mono(d, (w / 2, 150 if p else 128), txt, font(big, "bold"),
                  FG if self.running or e == 0 else APPLE_ORANGE, anchor="ms")
        if not self.laps:
            d.text((w / 2, 240 if p else 200), "Start/Lap from the app", font=font(17), fill=MUTED, anchor="ms")
            return img
        laps = [(i + 1, t - (self.laps[i - 1] if i else 0.0), t) for i, t in enumerate(self.laps)]
        splits = [l[1] for l in laps]
        best, worst = min(splits), max(splits)
        y = 222 if p else 178
        m = 20 if p else 40
        d.line((m, y - 20, w - m, y - 20), fill=TRACK, width=1)
        f = font(18 if p else 19)
        for n, split, cum in reversed(laps[-(6 if p else 4):]):
            col = FG
            if len(laps) > 1 and split == best:
                col = GREEN
            elif len(laps) > 1 and split == worst:
                col = RED
            d.text((m + 4, y), f"Lap {n}", font=f, fill=col, anchor="ls")
            draw_mono(d, (w * 0.62, y), fmt_clock(split, hundredths=True), f, col, anchor="rs")
            draw_mono(d, (w - m - 4, y), fmt_clock(cum, hundredths=True), f, MUTED, anchor="rs")
            y += 38 if p else 34
        return img

    def build_settings(self):
        w, form = panel(self)
        row = QHBoxLayout()
        ss = QPushButton("Start")
        lr = QPushButton("Reset")
        row.addWidget(ss)
        row.addWidget(lr)
        form.addRow("", row)
        laps = QListWidget()
        laps.setMaximumHeight(140)
        form.addRow("Laps:", laps)

        def update():
            ss.setText("Stop" if self.running else ("Resume" if self.elapsed() else "Start"))
            lr.setText("Lap" if self.running else "Reset")
            if laps.count() != len(self.laps):
                laps.clear()
                prev = 0.0
                for i, t in enumerate(self.laps):
                    laps.insertItem(0, f"Lap {i + 1}   {fmt_clock(t - prev, hundredths=True)}"
                                       f"   ({fmt_clock(t, hundredths=True)})")
                    prev = t

        ss.clicked.connect(lambda: (self.start_stop(), update()))
        lr.clicked.connect(lambda: (self.lap_reset(), update()))
        t = QTimer(w)
        t.timeout.connect(update)
        t.start(200)
        update()
        return w
