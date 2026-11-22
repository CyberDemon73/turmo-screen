"""Photo mode: one photo, or a slideshow of several."""
import random
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QSpinBox)

from ..draw import W, H, message_image
from .base import Mode, panel

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".apng", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


def prepare(path, fit, size=(W, H)):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = size
    if fit == "fill":
        return ImageOps.fit(img, size, Image.LANCZOS)
    # "fit": whole photo on a blurred, darkened copy of itself
    bg = ImageOps.fit(img, size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(18))
    bg = ImageEnhance.Brightness(bg).enhance(0.55)
    fg = ImageOps.contain(img, size, Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return bg


class PhotoMode(Mode):
    id = "photo"
    name = "Photo"
    icon = "🖼"
    description = ("Show a photo, or several as a slideshow. You can also drag images "
                   "onto the preview to show them right away.")
    DEFAULTS = {"paths": [], "interval": 10, "fit": "fill", "shuffle": False}

    def __init__(self, settings):
        super().__init__(settings)
        self._cache = {}
        self._order = []
        self._list_widget = None

    def fps(self):
        return 1.0

    def set_photos(self, paths, append=False):
        paths = [str(p) for p in paths if Path(p).suffix.lower() in IMAGE_EXTS]
        new = (list(self.cfg["paths"]) + paths) if append else paths
        self.set("paths", list(dict.fromkeys(new)))
        self._order = []
        self._cache.clear()
        if self._list_widget is not None:
            self._refresh_list()

    def _current(self, now):
        paths = [p for p in self.cfg["paths"] if Path(p).exists()]
        if not paths:
            return None
        if len(self._order) != len(paths) or set(self._order) != set(paths):
            self._order = list(paths)
            if self.cfg["shuffle"]:
                random.shuffle(self._order)
        idx = int(now // max(1, self.cfg["interval"])) % len(self._order)
        return self._order[idx]

    def render(self, now):
        path = self._current(now)
        if path is None:
            return message_image("No photo selected", "Add photos in the app or drop them on the preview",
                                 size=self.size)
        key = (path, self.cfg["fit"], self.size)
        if key not in self._cache:
            try:
                if len(self._cache) > 24:
                    self._cache.clear()
                self._cache[key] = prepare(path, self.cfg["fit"], self.size)
            except Exception as e:
                return message_image("Can't open photo", f"{Path(path).name}: {e}"[:80], size=self.size)
        return self._cache[key]

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
        lw.setMinimumHeight(110)
        self._list_widget = lw
        self._refresh_list()
        form.addRow(lw)

        buttons = QHBoxLayout()
        add = QPushButton("Add photos…")
        add_dir = QPushButton("Add folder…")
        remove = QPushButton("Remove")
        clear = QPushButton("Clear")
        for b in (add, add_dir, remove, clear):
            buttons.addWidget(b)
        form.addRow(buttons)

        exts = " ".join("*" + e for e in sorted(IMAGE_EXTS))

        def on_add():
            files, _ = QFileDialog.getOpenFileNames(w, "Choose photos", str(Path.home()), f"Images ({exts})")
            if files:
                self.set_photos(files, append=True)

        def on_add_dir():
            d = QFileDialog.getExistingDirectory(w, "Choose a folder of photos", str(Path.home()))
            if d:
                self.set_photos(sorted(str(p) for p in Path(d).iterdir() if p.suffix.lower() in IMAGE_EXTS),
                                append=True)

        def on_remove():
            gone = {i.data(256) for i in lw.selectedItems()}
            self.set_photos([p for p in self.cfg["paths"] if p not in gone])

        add.clicked.connect(on_add)
        add_dir.clicked.connect(on_add_dir)
        remove.clicked.connect(on_remove)
        clear.clicked.connect(lambda: self.set_photos([]))

        fit = QComboBox()
        fit.addItem("Fill screen (crop)", "fill")
        fit.addItem("Fit whole photo", "fit")
        fit.setCurrentIndex(max(0, fit.findData(self.cfg["fit"])))
        fit.currentIndexChanged.connect(lambda: (self.set("fit", fit.currentData()), self._cache.clear()))
        form.addRow("Scaling:", fit)

        interval = QSpinBox()
        interval.setRange(2, 3600)
        interval.setSuffix(" s")
        interval.setValue(int(self.cfg["interval"]))
        interval.valueChanged.connect(lambda v: self.set("interval", v))
        form.addRow("Slideshow every:", interval)

        shuffle = QCheckBox("Shuffle")
        shuffle.setChecked(bool(self.cfg["shuffle"]))
        shuffle.toggled.connect(lambda v: (self.set("shuffle", v), self._order.clear()))
        form.addRow("", shuffle)
        return w
