"""GIF mode: plays animated GIF / WebP / APNG files with their own frame timing."""
import bisect
import threading
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageSequence
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QSpinBox)

from ..draw import message_image
from .base import Mode, panel

GIF_EXTS = {".gif", ".webp", ".png", ".apng"}
MAX_FRAMES = 400


def is_animated(path):
    try:
        with Image.open(path) as im:
            return bool(getattr(im, "is_animated", False))
    except Exception:
        return False


class Clip:
    """Decoded frames already scaled to the screen, plus their timing."""

    def __init__(self, frames, durations):
        self.frames = frames
        self.ends = []
        t = 0
        for d in durations:
            t += d
            self.ends.append(t)
        self.total = t
        self.min_duration = min(durations)

    def frame_at(self, ms):
        return self.frames[bisect.bisect_right(self.ends, ms % self.total) % len(self.frames)]


def _scale(frame, fit, size, bg):
    w, h = size
    if fit == "fill":
        return ImageOps.fit(frame, size, Image.LANCZOS)
    if fit == "fit":
        out = bg.copy()
        fg = ImageOps.contain(frame, size, Image.LANCZOS)
        out.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
        return out
    # "original": as-is (shrunk only if bigger than the screen), centered on black
    fg = frame if frame.width <= w and frame.height <= h else ImageOps.contain(frame, size, Image.LANCZOS)
    out = Image.new("RGB", size, (0, 0, 0))
    out.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return out


# Measured on the panel: ~4.21 us per pixel byte, ~107 us per update command (see device.py).
BYTE_US, CMD_US = 4.21, 107.0
SMOOTH_FPS = 8           # default target for "Smooth video" (best size/smoothness balance)
SMOOTH_HEADROOM = 0.8    # use 80% of the link so frames arrive on time


def _centered(frame, scale, size):
    """The frame fitted to the screen, shrunk by `scale`, centered on black."""
    w, h = size
    fg = ImageOps.contain(frame, (max(8, int(w * scale)), max(8, int(h * scale))), Image.LANCZOS)
    out = Image.new("RGB", size, (0, 0, 0))
    out.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return out


def _send_ms(frames):
    """Average time the panel needs per frame change, from the same 4x4-tile diff the driver uses."""
    from ..device import TILE, changed_mask, to_rgb565
    px = [to_rgb565(f) for f in frames]
    h, w = px[0].shape
    total = 0.0
    for a, b in zip(px, px[1:] + px[:1]):
        tiles = changed_mask(b, a, 1).reshape(h // TILE, TILE, w // TILE, TILE).any(axis=(1, 3))
        rows = tiles.any(axis=1).sum()
        total += tiles.sum() * TILE * TILE * 2 * BYTE_US + rows * 1.5 * CMD_US
    return total / len(px) / 1000


def load_clip(path, fit, size, speed=1.0, target_fps=SMOOTH_FPS):
    with Image.open(path) as im:
        first = im.convert("RGB")
        bg = None
        if fit == "fit":  # a still, blurred backdrop: only the GIF area changes, so it plays faster
            bg = ImageOps.fit(first, size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(18))
            bg = ImageEnhance.Brightness(bg).enhance(0.5)
        raw, durations = [], []
        for i, fr in enumerate(ImageSequence.Iterator(im)):
            if i >= MAX_FRAMES:
                break
            durations.append(max(20, int(fr.info.get("duration", im.info.get("duration", 100)) or 100)))
            raw.append(fr.convert("RGB"))
    if fit != "smooth":
        return Clip([_scale(f, fit, size, bg) for f in raw], durations)

    # Smooth video: the biggest size whose frame changes the panel can deliver in time.
    clip_fps = 1000.0 / (sum(durations) / len(durations)) * speed
    target = min(float(target_fps), clip_fps)
    budget_ms = 1000.0 / target * SMOOTH_HEADROOM
    sample = raw[:: max(1, len(raw) // 24)]  # enough frames to judge, quick to compute
    chosen, est_ms = 0.2, None
    for scale in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2):
        ms = _send_ms([_centered(f, scale, size) for f in sample])
        if ms <= budget_ms:
            chosen, est_ms = scale, ms
            break
        est_ms = ms
    clip = Clip([_centered(f, chosen, size) for f in raw], durations)
    clip.info = (f"{int(chosen * 100)}% size · ~{min(clip_fps, 1000.0 / max(est_ms, 1e-3)):.0f} fps "
                 f"(clip runs at {clip_fps:.0f} fps)")
    return clip


class GifMode(Mode):
    id = "gif"
    name = "GIF"
    icon = "🎞"
    description = ("Play animated GIFs (also animated WebP/PNG). The screen can only take about 220 KB/s, "
                   "so full-screen video plays at about 1 fps. \"Smooth video\" measures each GIF and "
                   "picks the biggest size that still plays fluidly.")
    DEFAULTS = {"paths": [], "fit": "smooth", "speed": 1.0, "switch": 30, "smooth_fps": 8}

    def __init__(self, settings):
        super().__init__(settings)
        self._clips = {}
        self._loading = set()
        self._lock = threading.Lock()
        self._list_widget = None
        self._status = None

    def set_gifs(self, paths, append=False):
        paths = [str(p) for p in paths if Path(p).suffix.lower() in GIF_EXTS]
        new = (list(self.cfg["paths"]) + paths) if append else paths
        self.set("paths", list(dict.fromkeys(new)))
        with self._lock:
            self._clips.clear()
        if self._list_widget is not None:
            self._refresh_list()

    def _current(self, now):
        paths = [p for p in self.cfg["paths"] if Path(p).exists()]
        if not paths:
            return None
        return paths[int(now // max(1, self.cfg["switch"])) % len(paths)]

    def _key(self, path):
        smooth_speed = (float(self.cfg["speed"]), int(self.cfg["smooth_fps"])) if self.cfg["fit"] == "smooth" else None
        return (path, self.cfg["fit"], self.size, smooth_speed)

    def smooth_info(self):
        """What "Smooth video" picked for the current GIF, for the settings panel."""
        path = self._current(getattr(self, "_last_now", 0))
        clip = self._clips.get(self._key(path)) if path else None
        if self.cfg["fit"] != "smooth":
            return ""
        if isinstance(clip, Clip):
            return getattr(clip, "info", "")
        return "Measuring the best size…" if path else ""

    def _clip(self, path):
        key = self._key(path)
        with self._lock:
            clip = self._clips.get(key)
            if clip is not None or key in self._loading:
                return clip
            self._loading.add(key)

        def work():
            try:
                c = load_clip(path, key[1], key[2], float(self.cfg["speed"]), int(self.cfg["smooth_fps"]))
            except Exception as e:
                c = e
            with self._lock:
                if len(self._clips) > 6:
                    self._clips.clear()
                self._clips[key] = c
                self._loading.discard(key)

        threading.Thread(target=work, name="gif-loader", daemon=True).start()
        return None

    def fps(self):
        path = self._current(self._last_now) if hasattr(self, "_last_now") else None
        clip = self._clips.get(self._key(path)) if path else None
        if isinstance(clip, Clip):
            return max(1.0, min(60.0, 1000.0 / clip.min_duration * float(self.cfg["speed"])))
        return 4.0

    def render(self, now):
        self._last_now = now
        path = self._current(now)
        if path is None:
            return message_image("No GIF selected", "Add GIFs in the app or drop them on the preview",
                                 size=self.size)
        clip = self._clip(path)
        if clip is None:
            return message_image("Loading GIF…", Path(path).name, size=self.size)
        if isinstance(clip, Exception):
            return message_image("Can't play GIF", f"{Path(path).name}: {clip}"[:80], size=self.size)
        return clip.frame_at(now * 1000 * float(self.cfg["speed"]))

    def _refresh_list(self):
        lw = self._list_widget
        lw.clear()
        for p in self.cfg["paths"]:
            item = QListWidgetItem(Path(p).name)
            item.setToolTip(p)
            item.setData(256, p)
            lw.addItem(item)

    def build_settings(self):
        w, form = panel(self)
        lw = QListWidget()
        lw.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        lw.setMinimumHeight(100)
        self._list_widget = lw
        self._refresh_list()
        form.addRow(lw)

        buttons = QHBoxLayout()
        add = QPushButton("Add GIFs…")
        remove = QPushButton("Remove")
        clear = QPushButton("Clear")
        for b in (add, remove, clear):
            buttons.addWidget(b)
        form.addRow(buttons)

        def on_add():
            files, _ = QFileDialog.getOpenFileNames(w, "Choose animated images", str(Path.home()),
                                                    "Animated images (*.gif *.webp *.png *.apng)")
            if files:
                self.set_gifs(files, append=True)

        def on_remove():
            gone = {i.data(256) for i in lw.selectedItems()}
            self.set_gifs([p for p in self.cfg["paths"] if p not in gone])

        add.clicked.connect(on_add)
        remove.clicked.connect(on_remove)
        clear.clicked.connect(lambda: self.set_gifs([]))

        fit = QComboBox()
        fit.addItem("Smooth video (auto size)", "smooth")
        fit.addItem("Fit, on blurred background", "fit")
        fit.addItem("Original size, centered", "original")
        fit.addItem("Fill screen (crop, slowest)", "fill")
        fit.setCurrentIndex(max(0, fit.findData(self.cfg["fit"])))
        fit.currentIndexChanged.connect(lambda: self.set("fit", fit.currentData()))
        form.addRow("Scaling:", fit)
        smooth = QSpinBox()
        smooth.setRange(3, 30)
        smooth.setSuffix(" fps")
        smooth.setValue(int(self.cfg["smooth_fps"]))
        smooth.setToolTip("Higher = more fluid but smaller picture; lower = bigger picture but choppier.\n"
                          "Only used by \"Smooth video\".")
        smooth.valueChanged.connect(lambda v: self.set("smooth_fps", v))
        form.addRow("Target smoothness:", smooth)
        info = QLabel()
        info.setStyleSheet("color: palette(placeholder-text);")
        form.addRow("", info)
        timer = QTimer(w)
        timer.timeout.connect(lambda: info.setText(self.smooth_info()))
        timer.start(500)

        speed = QDoubleSpinBox()
        speed.setRange(0.25, 4.0)
        speed.setSingleStep(0.25)
        speed.setSuffix("×")
        speed.setValue(float(self.cfg["speed"]))
        speed.valueChanged.connect(lambda v: self.set("speed", v))
        form.addRow("Speed:", speed)

        switch = QSpinBox()
        switch.setRange(3, 3600)
        switch.setSuffix(" s")
        switch.setValue(int(self.cfg["switch"]))
        switch.valueChanged.connect(lambda v: self.set("switch", v))
        form.addRow("Next GIF every:", switch)
        return w
