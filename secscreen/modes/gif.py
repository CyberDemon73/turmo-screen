"""GIF mode: plays animated GIF / WebP / APNG files with their own frame timing."""
import bisect
import threading
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageSequence
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


def load_clip(path, fit, size):
    with Image.open(path) as im:
        first = im.convert("RGB")
        bg = None
        if fit == "fit":  # a still, blurred backdrop: only the GIF area changes, so it plays faster
            bg = ImageOps.fit(first, size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(18))
            bg = ImageEnhance.Brightness(bg).enhance(0.5)
        frames, durations = [], []
        for i, fr in enumerate(ImageSequence.Iterator(im)):
            if i >= MAX_FRAMES:
                break
            durations.append(max(20, int(fr.info.get("duration", im.info.get("duration", 100)) or 100)))
            frames.append(_scale(fr.convert("RGB"), fit, size, bg))
    return Clip(frames, durations)


class GifMode(Mode):
    id = "gif"
    name = "GIF"
    icon = "🎞"
    description = ("Play animated GIFs (also animated WebP/PNG). The screen can take about 220 KB/s, "
                   "so GIFs where only part of the picture moves play smoothest; "
                   "full-screen motion plays at a few frames per second.")
    DEFAULTS = {"paths": [], "fit": "fit", "speed": 1.0, "switch": 30}

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

    def _clip(self, path):
        key = (path, self.cfg["fit"], self.size)
        with self._lock:
            clip = self._clips.get(key)
            if clip is not None or key in self._loading:
                return clip
            self._loading.add(key)

        def work():
            try:
                c = load_clip(path, key[1], key[2])
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
        clip = self._clips.get((path, self.cfg["fit"], self.size)) if path else None
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
        fit.addItem("Fit, on blurred background (smoother)", "fit")
        fit.addItem("Original size, centered (smoothest)", "original")
        fit.addItem("Fill screen (crop, slowest)", "fill")
        fit.setCurrentIndex(max(0, fit.findData(self.cfg["fit"])))
        fit.currentIndexChanged.connect(lambda: self.set("fit", fit.currentData()))
        form.addRow("Scaling:", fit)

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
