"""Main window, live preview and tray icon."""
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QPushButton, QScrollArea, QSizePolicy,
                               QSlider, QSplitter, QStackedWidget, QSystemTrayIcon, QToolButton, QVBoxLayout,
                               QWidget)

from . import APP_NAME
from .device import ORIENTATIONS, find_ports
from .draw import app_icon_image
from .icons import icon
from .engine import pil_to_qimage
from .modes.gif import is_animated
from .modes.photo import IMAGE_EXTS
from .screen_panel import ScreenPanel

SCREEN_PAGE = "__screen__"


_icon = None


def app_icon():
    global _icon
    if _icon is None:
        from PySide6.QtGui import QImage
        _icon = QIcon()
        for size in (16, 20, 24, 32, 40, 48, 64, 128, 256, 512):
            img = app_icon_image(size)
            q = QImage(img.tobytes("raw", "RGBA"), size, size, size * 4, QImage.Format.Format_RGBA8888).copy()
            _icon.addPixmap(QPixmap.fromImage(q))
    return _icon


class PreviewWidget(QWidget):
    """Shows the current frame inside a screen bezel; accepts dropped photos."""
    filesDropped = Signal(list)

    def __init__(self):
        super().__init__()
        self._img = None
        self.setAcceptDrops(True)
        self.setMinimumSize(300, 210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._drag = False

    def set_image(self, img):
        self._img = img
        self.update()

    def sizeHint(self):
        return QSize(560, 390)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pad, bezel = 14, 14
        iw, ih = (self._img.width(), self._img.height()) if self._img is not None else (480, 320)
        aw, ah = self.width() - 2 * pad - 2 * bezel, self.height() - 2 * pad - 2 * bezel
        scale = min(aw / iw, ah / ih)
        w, h = iw * scale, ih * scale
        x, y = (self.width() - w) / 2, (self.height() - h) / 2
        outer = QRectF(x - bezel, y - bezel, w + 2 * bezel, h + 2 * bezel)
        path = QPainterPath()
        path.addRoundedRect(outer, 18, 18)
        p.fillPath(path, QColor(16, 16, 16))
        p.setPen(QColor(60, 60, 60))
        p.drawPath(path)
        if self._img is not None:
            p.drawImage(QRectF(x, y, w, h), self._img)
        if self._drag:
            p.fillRect(QRectF(x, y, w, h), QColor(217, 119, 87, 110))
            p.setPen(QColor(255, 255, 255))
            f = p.font()
            f.setPointSize(16)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, "Drop to show on screen")

    def _paths(self, event):
        md = event.mimeData()
        if not md.hasUrls():
            return []
        out = []
        for u in md.urls():
            p = Path(u.toLocalFile())
            if p.is_dir():
                out += sorted(str(f) for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS)
            elif p.suffix.lower() in IMAGE_EXTS:
                out.append(str(p))
        return out

    def dragEnterEvent(self, event):
        if self._paths(event):
            self._drag = True
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, _):
        self._drag = False
        self.update()

    def dropEvent(self, event):
        self._drag = False
        self.update()
        paths = self._paths(event)
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)


class MainWindow(QMainWindow):
    def __init__(self, engine, modes, settings):
        super().__init__()
        self.engine = engine
        self.modes = modes
        self.settings = settings
        self._quitting = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1060, 700)

        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setIconSize(QSize(20, 20))
        self.sidebar.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setStyleSheet(
            "QListWidget { padding: 10px 6px; background: rgba(128,128,128,0.10); }"
            "QListWidget::item { padding: 9px 10px; border-radius: 8px; margin: 1px 0; }"
            "QListWidget::item:selected { background: #D97757; color: white; }")
        for m in modes.values():
            item = QListWidgetItem(icon(m.id), m.name)
            item.setData(Qt.ItemDataRole.UserRole, m.id)
            self.sidebar.addItem(item)
        sep = QListWidgetItem("")
        sep.setFlags(Qt.ItemFlag.NoItemFlags)
        sep.setSizeHint(QSize(10, 14))
        self.sidebar.addItem(sep)
        item = QListWidgetItem(icon("screen"), "Screen")
        item.setData(Qt.ItemDataRole.UserRole, SCREEN_PAGE)
        self.sidebar.addItem(item)
        lay.addWidget(self.sidebar)

        # ---- main column
        main = QWidget()
        col = QVBoxLayout(main)
        col.setContentsMargins(16, 12, 16, 12)
        col.setSpacing(10)
        lay.addWidget(main, 1)

        col.addWidget(self._device_bar())

        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        self.preview = PreviewWidget()
        self.preview.filesDropped.connect(self._photos_dropped)
        split.addWidget(self.preview)

        self.stack = QStackedWidget()
        self.panels = {}
        for m in modes.values():
            w = m.build_settings()
            self.panels[m.id] = w
            self.stack.addWidget(w)
        self.panels[SCREEN_PAGE] = ScreenPanel(engine, settings)
        self.stack.addWidget(self.panels[SCREEN_PAGE])
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.stack)
        split.addWidget(scroll)
        self.split = split
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        col.addWidget(split, 1)

        self.sidebar.currentRowChanged.connect(self._select_mode)
        ids = list(modes)
        self.sidebar.setCurrentRow(ids.index(engine.mode.id) if engine.mode.id in ids else 0)

        engine.frameReady.connect(self.preview.set_image)
        engine.statusChanged.connect(self._on_status)
        engine.fpsChanged.connect(lambda f: self.fps_label.setText(f"{f:.1f} fps" if f else ""))

        timer = modes.get("timer")
        if timer is not None:
            timer.notifier.finished.connect(self._timer_done)

        self._setup_tray()

    # ------------------------------------------------------------ device bar
    def _device_bar(self):
        bar = QFrame()
        bar.setObjectName("devicebar")
        bar.setStyleSheet("#devicebar { background: rgba(128,128,128,0.12); border-radius: 10px; }")
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(8)

        self.status_dot = QLabel("●")
        self.status_label = QLabel("Not connected")
        self.status_label.setMinimumWidth(150)
        self.fps_label = QLabel("")
        self.fps_label.setStyleSheet("color: palette(placeholder-text);")
        h.addWidget(self.status_dot)
        h.addWidget(self.status_label, 1)
        h.addWidget(self.fps_label)

        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(190)
        h.addWidget(self.port_combo)
        refresh = QToolButton()
        refresh.setIcon(icon("refresh", 16))
        refresh.setToolTip("Rescan ports")
        refresh.clicked.connect(self._fill_ports)
        h.addWidget(refresh)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setCheckable(True)
        self.connect_btn.toggled.connect(self._toggle_connect)
        h.addWidget(self.connect_btn)

        h.addSpacing(10)
        sun = QLabel()
        sun.setPixmap(icon("sun", 18).pixmap(18, 18))
        sun.setToolTip("Brightness")
        h.addWidget(sun)
        self.brightness = QSlider(Qt.Orientation.Horizontal)
        self.brightness.setRange(5, 100)
        self.brightness.setFixedWidth(110)
        self.brightness.setValue(int(self.settings["brightness"]))
        self.brightness.valueChanged.connect(self._brightness_changed)
        h.addWidget(self.brightness)

        self.orient = QComboBox()
        for k, v in ORIENTATIONS.items():
            self.orient.addItem(v, k)
        self.orient.setCurrentIndex(max(0, self.orient.findData(self.settings["orientation"])))
        self.orient.currentIndexChanged.connect(self._orientation_changed)
        h.addWidget(self.orient)

        self.power = QCheckBox("Screen on")
        self.power.setChecked(True)
        self.power.toggled.connect(self.engine.screen_power)
        h.addWidget(self.power)

        self._fill_ports()
        self._on_status("disconnected", "Not connected")
        return bar

    def _fill_ports(self):
        current = self.port_combo.currentData() or self.settings["port"]
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        self.port_combo.addItem("Auto-detect", "auto")
        for dev, desc, ok in find_ports():
            label = f"{dev} — {'Smart screen' if ok else desc}"
            self.port_combo.addItem(("✓ " if ok else "") + label, dev)
        idx = self.port_combo.findData(current)
        self.port_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.port_combo.blockSignals(False)

    def _toggle_connect(self, on):
        if on:
            port = self.port_combo.currentData() or "auto"
            self.settings["port"] = port
            self.settings["autoconnect"] = True
            self.engine.connect_port(port)
            self.connect_btn.setText("Disconnect")
        else:
            self.settings["autoconnect"] = False
            self.engine.disconnect()
            self.connect_btn.setText("Connect")

    def set_connected_ui(self, on):
        self.connect_btn.blockSignals(True)
        self.connect_btn.setChecked(on)
        self.connect_btn.setText("Disconnect" if on else "Connect")
        self.connect_btn.blockSignals(False)

    def _on_status(self, state, msg):
        colors = {"connected": "#30D158", "connecting": "#FF9F0A", "error": "#FF453A", "disconnected": "#8E8E93"}
        self.status_dot.setStyleSheet(f"color: {colors.get(state, '#8E8E93')}; font-size: 16px;")
        self.status_label.setText(msg)
        self.status_label.setToolTip(msg)
        if hasattr(self, "tray"):
            self.tray.setToolTip(f"{APP_NAME} — {msg}")

    def _brightness_changed(self, v):
        self.settings["brightness"] = v
        self.engine.set_brightness(v)

    def _orientation_changed(self):
        o = self.orient.currentData()
        self.settings["orientation"] = o
        self.engine.set_orientation(o)

    # ------------------------------------------------------------ modes
    def _select_mode(self, row):
        if row < 0:
            return
        mode_id = self.sidebar.item(row).data(Qt.ItemDataRole.UserRole)
        if mode_id not in self.panels:
            return
        self.stack.setCurrentWidget(self.panels[mode_id])
        total = sum(self.split.sizes()) or 600
        if mode_id == SCREEN_PAGE:
            self.split.setSizes([int(total * 0.35), int(total * 0.65)])
            return  # settings page; the screen keeps showing the current mode
        self.split.setSizes([int(total * 0.6), int(total * 0.4)])
        self.settings["mode"] = mode_id
        self.engine.set_mode(mode_id)

    def select_mode(self, mode_id):
        ids = list(self.modes)
        if mode_id in ids:
            self.sidebar.setCurrentRow(ids.index(mode_id))

    def _photos_dropped(self, paths):
        animated = [p for p in paths if is_animated(p)]
        stills = [p for p in paths if p not in animated]
        if stills:
            self.modes["photo"].set_photos(stills)
        if animated:
            self.modes["gif"].set_gifs(animated)
        self.select_mode("gif" if animated else "photo")

    def _timer_done(self, label):
        if self.modes["timer"].cfg.get("beep", True):
            QApplication.beep()
            if self.tray.isVisible():
                self.tray.showMessage(APP_NAME, f"{label}: time's up!", QSystemTrayIcon.MessageIcon.Information,
                                      5000)

    # ------------------------------------------------------------ tray
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        menu = QMenu()
        show = QAction("Show window", self)
        show.triggered.connect(self.show_normal)
        menu.addAction(show)
        modes_menu = menu.addMenu("Mode")
        for m in self.modes.values():
            a = QAction(icon(m.id, 16), m.name, self)
            a.triggered.connect(lambda _=False, mid=m.id: self.select_mode(mid))
            modes_menu.addAction(a)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_normal() if reason == QSystemTrayIcon.ActivationReason.Trigger
            and sys.platform != "darwin" else None)
        self._tray_menu = menu
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def show_normal(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def quit(self):
        self._quitting = True
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if not self._quitting and self.settings["tray"] and self.tray.isVisible():
            event.ignore()
            self.hide()
            if not self.settings["tray_hint_shown"]:
                self.tray.showMessage(APP_NAME, "Still running in the background. Use the tray icon to quit.",
                                      QSystemTrayIcon.MessageIcon.Information, 4000)
                self.settings["tray_hint_shown"] = True
            return
        self._quitting = True
        event.accept()
        QApplication.quit()
