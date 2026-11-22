"""The "Screen" page: picture, updates, night schedule, device and app options."""
from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QSlider, QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

from . import autostart
from .engine import PICTURE_DEFAULTS, night, picture


def _slider(lo, hi, value, on_change, suffix=""):
    row = QHBoxLayout()
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(lo, hi)
    s.setValue(int(value))
    lbl = QLabel()
    lbl.setMinimumWidth(44)

    def changed(v):
        lbl.setText(f"{v}{suffix}")
        on_change(v)

    s.valueChanged.connect(changed)
    lbl.setText(f"{int(value)}{suffix}")
    row.addWidget(s, 1)
    row.addWidget(lbl)
    return row, s


class ScreenPanel(QWidget):
    def __init__(self, engine, settings):
        super().__init__()
        self.engine = engine
        self.settings = settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.addWidget(QLabel("<b style='font-size:15px'>Screen</b>"))
        hint = QLabel("Deeper control of the display. Brightness, orientation and power are in the top bar.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(placeholder-text);")
        outer.addWidget(hint)

        cols = QHBoxLayout()
        left, right = QVBoxLayout(), QVBoxLayout()
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        outer.addLayout(cols)
        left.addWidget(self._picture_box())
        left.addWidget(self._updates_box())
        left.addStretch(1)
        right.addWidget(self._night_box())
        right.addWidget(self._device_box())
        right.addWidget(self._app_box())
        right.addStretch(1)
        outer.addStretch(1)
        engine.statsChanged.connect(self._on_stats)

    # ------------------------------------------------------------ picture
    def _set_picture(self, key, value):
        p = self.settings.data.setdefault("picture", {})
        p[key] = value
        self.settings.save()

    def _picture_box(self):
        box = QGroupBox("Picture")
        form = QFormLayout(box)
        p = picture(self.settings)
        self._pic_widgets = {}
        for key, label, lo, hi, suffix in (("warmth", "Warmth", -100, 100, ""),
                                           ("contrast", "Contrast", 50, 150, "%"),
                                           ("saturation", "Saturation", 0, 200, "%")):
            row, s = _slider(lo, hi, p[key], lambda v, k=key: self._set_picture(k, v), suffix)
            self._pic_widgets[key] = s
            form.addRow(label + ":", row)
        for key, label in (("grayscale", "Black && white"), ("invert", "Invert colors"),
                           ("mirror", "Mirror image")):
            cb = QCheckBox(label)
            cb.setChecked(bool(p[key]))
            cb.toggled.connect(lambda v, k=key: self._set_picture(k, v))
            self._pic_widgets[key] = cb
            form.addRow("", cb)
        reset = QPushButton("Reset picture")
        reset.clicked.connect(self._reset_picture)
        form.addRow("", reset)
        return box

    def _reset_picture(self):
        for key, default in PICTURE_DEFAULTS.items():
            w = self._pic_widgets[key]
            if isinstance(w, QCheckBox):
                w.setChecked(default)
            else:
                w.setValue(default)

    # ------------------------------------------------------------ updates
    def _updates_box(self):
        box = QGroupBox("Updates")
        form = QFormLayout(box)
        fps = QSpinBox()
        fps.setRange(1, 60)
        fps.setSuffix(" fps")
        fps.setValue(int(self.settings["max_fps"] or 60))
        fps.valueChanged.connect(lambda v: self.settings.__setitem__("max_fps", v))
        form.addRow("Max frame rate:", fps)

        refresh = QSpinBox()
        refresh.setRange(0, 120)
        refresh.setSpecialValueText("Never")
        refresh.setSuffix(" min")
        refresh.setValue(int(self.settings["refresh_minutes"] or 0))
        refresh.valueChanged.connect(lambda v: self.settings.__setitem__("refresh_minutes", v))
        refresh.setToolTip("Resend the whole picture regularly; clears any leftover glitches.")
        form.addRow("Full refresh every:", refresh)

        self.pause = QCheckBox("Freeze screen (stop sending updates)")
        self.pause.toggled.connect(self.engine.set_paused)
        form.addRow("", self.pause)

        row = QHBoxLayout()
        redraw = QPushButton("Redraw now")
        redraw.setToolTip("Resend the whole picture")
        redraw.clicked.connect(self.engine.redraw)
        black = QPushButton("Black screen")
        black.setToolTip("Show black (combine with Freeze to keep it black)")
        black.clicked.connect(lambda: (self.pause.setChecked(True), self.engine.show_black()))
        row.addWidget(redraw)
        row.addWidget(black)
        form.addRow("", row)
        return box

    # ------------------------------------------------------------ night
    def _set_night(self, key, value):
        n = self.settings.data.setdefault("night", {})
        n[key] = value
        self.settings.save()

    def _night_box(self):
        box = QGroupBox("Night schedule")
        form = QFormLayout(box)
        n = night(self.settings)
        on = QCheckBox("Enabled")
        on.setChecked(bool(n["enabled"]))
        on.toggled.connect(lambda v: self._set_night("enabled", v))
        form.addRow("", on)
        times = QHBoxLayout()
        for key in ("start", "end"):
            te = QTimeEdit(QTime.fromString(n[key], "HH:mm"))
            te.setDisplayFormat("HH:mm")
            te.timeChanged.connect(lambda t, k=key: self._set_night(k, t.toString("HH:mm")))
            times.addWidget(QLabel("from" if key == "start" else "to"))
            times.addWidget(te)
        form.addRow("Time:", times)
        action = QComboBox()
        action.addItem("Dim the screen", "dim")
        action.addItem("Turn the screen off", "off")
        action.setCurrentIndex(max(0, action.findData(n["action"])))
        action.currentIndexChanged.connect(lambda: self._set_night("action", action.currentData()))
        form.addRow("Action:", action)
        row, _ = _slider(1, 100, n["brightness"], lambda v: self._set_night("brightness", v), "%")
        form.addRow("Dim to:", row)
        return box

    # ------------------------------------------------------------ device
    def _device_box(self):
        box = QGroupBox("Device")
        form = QFormLayout(box)
        self.model = QLabel("—")
        self.port = QLabel("—")
        self.rate = QLabel("—")
        self.state = QLabel("—")
        form.addRow("Model:", self.model)
        form.addRow("Port:", self.port)
        form.addRow("Data rate:", self.rate)
        form.addRow("State:", self.state)
        reboot = QPushButton("Reboot screen")
        reboot.setToolTip("Restarts the screen's firmware. Use it if the picture gets stuck or garbled.")
        reboot.clicked.connect(self._reboot)
        form.addRow("", reboot)
        return box

    def _reboot(self):
        if QMessageBox.question(self, "Reboot screen",
                                "Restart the screen? It disconnects for a few seconds and then reconnects.") \
                == QMessageBox.StandardButton.Yes:
            self.engine.reboot_screen()

    def _on_stats(self, s):
        self.model.setText(s["model"] or "—")
        self.port.setText(s["port"] or "—")
        self.rate.setText(f"{s['kbps']:.0f} KB/s · {s['fps']:.1f} fps · {s['total_mb']:.1f} MB sent"
                          if s["port"] else "—")
        parts = []
        if not s["power"]:
            parts.append("off (night)" if s["night"] else "off")
        elif s["night"]:
            parts.append("night dimming")
        if s["paused"]:
            parts.append("frozen")
        self.state.setText(", ".join(parts) if parts else ("showing live" if s["port"] else "—"))

    # ------------------------------------------------------------ app
    def _app_box(self):
        box = QGroupBox("App")
        form = QFormLayout(box)
        login = QCheckBox("Start at login (in the tray)")
        try:
            login.setChecked(autostart.is_enabled())
        except Exception:
            login.setEnabled(False)

        def set_login(v):
            try:
                autostart.set_enabled(v)
            except Exception as e:
                QMessageBox.warning(self, "Start at login", f"Couldn't change it: {e}")

        login.toggled.connect(set_login)
        form.addRow("", login)
        for key, label in (("tray", "Keep running in the tray when the window is closed"),
                           ("autoconnect", "Connect to the screen when the app starts")):
            cb = QCheckBox(label)
            cb.setChecked(bool(self.settings[key]))
            cb.toggled.connect(lambda v, k=key: self.settings.__setitem__(k, v))
            form.addRow("", cb)
        return box
