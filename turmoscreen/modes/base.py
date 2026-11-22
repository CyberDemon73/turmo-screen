"""Base class for display modes.

A mode renders a 480x320 PIL image (render) on the engine thread and builds a Qt
settings panel (build_settings) on the GUI thread. Simple attribute writes from the
GUI are picked up by the next rendered frame.
"""
from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget


class Mode:
    id = "base"
    name = "Base"
    icon = "•"
    description = ""
    DEFAULTS = {}
    # Logical canvas size, set by the engine before each render: (480, 320) or (320, 480).
    size = (480, 320)

    @property
    def portrait(self):
        return self.size[1] > self.size[0]

    def __init__(self, settings):
        self.settings = settings
        self.cfg = settings.section(self.id)
        for k, v in self.DEFAULTS.items():
            self.cfg.setdefault(k, v)

    def set(self, key, value):
        self.cfg[key] = value
        self.settings.save()

    def fps(self):
        return 2.0

    def activate(self):
        pass

    def deactivate(self):
        pass

    def render(self, now):
        raise NotImplementedError

    def build_settings(self):
        w, _ = panel(self)
        return w


def panel(mode):
    """A settings panel with a title and description; returns (widget, form layout)."""
    w = QWidget()
    outer = QVBoxLayout(w)
    outer.setContentsMargins(4, 4, 4, 4)
    title = QLabel(f"<b style='font-size:15px'>{mode.name}</b>")
    outer.addWidget(title)
    if mode.description:
        desc = QLabel(mode.description)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: palette(placeholder-text);")
        outer.addWidget(desc)
    form = QFormLayout()
    form.setContentsMargins(0, 8, 0, 0)
    outer.addLayout(form)
    outer.addStretch(1)
    return w, form
