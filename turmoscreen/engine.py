"""Render loop: runs the active mode, applies screen settings, pushes frames to the screen and preview.

All serial I/O happens on this one thread; the GUI talks to it through a command queue.
"""
import queue
import threading
import time
import traceback
from datetime import datetime

import serial
from PIL import Image, ImageEnhance, ImageOps
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from .device import TuringScreen, auto_port, logical_size
from .draw import message_image

PICTURE_DEFAULTS = {"warmth": 0, "contrast": 100, "saturation": 100, "grayscale": False, "invert": False,
                    "mirror": False}
NIGHT_DEFAULTS = {"enabled": False, "start": "22:00", "end": "07:00", "action": "dim", "brightness": 10}


def pil_to_qimage(img):
    data = img.tobytes("raw", "RGB")
    return QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888).copy()


def picture(settings):
    p = dict(PICTURE_DEFAULTS)
    p.update(settings.data.get("picture") or {})
    return p


def night(settings):
    n = dict(NIGHT_DEFAULTS)
    n.update(settings.data.get("night") or {})
    return n


_lut_cache = {}


def adjust(img, p):
    """Software picture controls (the panel itself only has brightness)."""
    w = int(p["warmth"])
    if w:
        if w not in _lut_cache:
            k = abs(w) / 100
            r, g, b = (1, 1 - 0.12 * k, 1 - 0.40 * k) if w > 0 else (1 - 0.40 * k, 1 - 0.12 * k, 1)
            _lut_cache[w] = [int(i * r) for i in range(256)] + [int(i * g) for i in range(256)] + \
                            [int(i * b) for i in range(256)]
        img = img.point(_lut_cache[w])
    if p["contrast"] != 100:
        img = ImageEnhance.Contrast(img).enhance(p["contrast"] / 100)
    if p["saturation"] != 100:
        img = ImageEnhance.Color(img).enhance(p["saturation"] / 100)
    if p["grayscale"]:
        img = ImageOps.grayscale(img).convert("RGB")
    if p["invert"]:
        img = ImageOps.invert(img)
    if p["mirror"]:
        img = ImageOps.mirror(img)
    return img


def in_window(start, end, now):
    """True if the time of day `now` is within [start, end), handling windows across midnight."""
    def mins(s):
        h, m = (int(x) for x in s.split(":"))
        return h * 60 + m
    s, e, n = mins(start), mins(end), now.hour * 60 + now.minute
    return s <= n < e if s <= e else (n >= s or n < e)


class Engine(QObject):
    frameReady = Signal(QImage)
    statusChanged = Signal(str, str)   # state: disconnected | connecting | connected | error ; message
    fpsChanged = Signal(float)
    statsChanged = Signal(dict)        # fps, kbps, total_mb, model, port, paused, night, power

    def __init__(self, modes, settings):
        super().__init__()
        self.modes = modes
        self.settings = settings
        self.mode = modes.get(settings["mode"]) or next(iter(modes.values()))
        self.screen = None
        self.want_port = None      # None = stay disconnected; "auto" or a device path
        self.orientation = settings["orientation"]
        self.brightness = settings["brightness"]
        self.user_power = True
        self.paused = False
        self._applied = None       # (power_on, brightness) currently on the panel
        self._last_full = time.monotonic()
        self._q = queue.Queue()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="engine", daemon=True)

    # ---------------------------------------------------------------- GUI API
    def start(self):
        self.mode.activate()
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=10)

    def _post(self, *cmd):
        self._q.put(cmd)
        self._wake.set()

    def set_mode(self, mode_id):
        self._post("mode", mode_id)

    def connect_port(self, port):
        self._post("connect", port or "auto")

    def disconnect(self):
        self._post("disconnect")

    def set_brightness(self, value):
        self._post("brightness", int(value))

    def set_orientation(self, orientation):
        self._post("orientation", orientation)

    def screen_power(self, on):
        self._post("power", bool(on))

    def set_paused(self, paused):
        self._post("pause", bool(paused))

    def redraw(self):
        self._post("redraw")

    def show_black(self):
        self._post("black")

    def reboot_screen(self):
        self._post("reboot")

    # ---------------------------------------------------------------- thread
    def _close(self):
        if self.screen is not None:
            self.screen.close()
            self.screen = None
        self._applied = None

    def _handle(self, cmd):
        kind = cmd[0]
        if kind == "mode":
            new = self.modes.get(cmd[1])
            if new is not None and new is not self.mode:
                self.mode.deactivate()
                self.mode = new
                new.activate()
        elif kind == "connect":
            self._close()
            self.want_port = cmd[1]
            self._next_try = 0.0
        elif kind == "disconnect":
            self.want_port = None
            self._close()
            self.statusChanged.emit("disconnected", "Not connected")
        elif kind == "brightness":
            self.brightness = cmd[1]
        elif kind == "orientation":
            self.orientation = cmd[1]
            if self.screen:
                self.screen.set_orientation(self.orientation)
        elif kind == "power":
            self.user_power = cmd[1]
        elif kind == "pause":
            self.paused = cmd[1]
        elif kind == "redraw":
            if self.screen:
                self.screen.invalidate()
        elif kind == "black":
            if self.screen:
                self.screen.show(Image.new("RGB", logical_size(self.orientation), (0, 0, 0)))
        elif kind == "reboot":
            if self.screen:
                self.screen.reboot()
                self._close()
                self.statusChanged.emit("connecting", "Screen rebooting…")
                self._next_try = time.monotonic() + 6.0

    def _apply_power(self, now):
        """Keep panel power/brightness in line with the user's choice and the night schedule."""
        n = night(self.settings)
        is_night = n["enabled"] and in_window(n["start"], n["end"], now)
        on = self.user_power and not (is_night and n["action"] == "off")
        bright = min(self.brightness, int(n["brightness"])) if is_night and n["action"] == "dim" else self.brightness
        want = (on, bright)
        if self.screen is not None and want != self._applied:
            if on:
                if not self._applied or not self._applied[0]:
                    self.screen.screen_on()
                self.screen.set_brightness(bright)
            else:
                self.screen.screen_off()
            self._applied = want
        return on, is_night

    def _try_open(self):
        port = auto_port() if self.want_port == "auto" else self.want_port
        if not port:
            self.statusChanged.emit("connecting", "Looking for the screen… (is it plugged in?)")
            return
        self.statusChanged.emit("connecting", f"Connecting to {port}…")
        scr = TuringScreen(port, self.orientation)
        try:
            scr.open()
        except (serial.SerialException, OSError) as e:
            scr.close()
            msg = str(e)
            if "denied" in msg.lower() or "busy" in msg.lower() or "permission" in msg.lower():
                msg = f"{port} is busy or not permitted (another program using it?)"
            self.statusChanged.emit("error", msg)
            return
        self.screen = scr
        self._applied = None
        self._last_full = time.monotonic()
        self.statusChanged.emit("connected", f"Connected · {port}")

    def _run(self):
        self._next_try = 0.0
        frames, mark, sent_mark = 0, time.monotonic(), 0
        self.statusChanged.emit("disconnected", "Not connected")
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                while True:
                    self._handle(self._q.get_nowait())
            except queue.Empty:
                pass
            except (serial.SerialException, OSError) as e:
                self._close()
                self.statusChanged.emit("error", str(e))

            if self.want_port and self.screen is None and t0 >= self._next_try:
                self._try_open()
                if self.screen is None:
                    self._next_try = t0 + 3.0

            mode = self.mode
            size = logical_size(self.orientation)
            mode.size = size
            try:
                img = mode.render(time.time())
                if img.size != size:
                    img = img.resize(size)
                img = adjust(img, picture(self.settings))
            except Exception as e:
                traceback.print_exc()
                img = message_image(f"{mode.name} failed", str(e)[:80], size=size)

            on, is_night = True, False
            if self.screen is not None:
                try:
                    on, is_night = self._apply_power(datetime.now())
                    refresh = float(self.settings["refresh_minutes"] or 0)
                    if refresh and t0 - self._last_full >= refresh * 60:
                        self.screen.invalidate()
                        self._last_full = t0
                    if on and not self.paused:
                        self.screen.tolerance = 1 if self.settings["skip_invisible"] else 0
                        self.screen.show(img)
                except (serial.SerialException, OSError) as e:
                    self._close()
                    self.statusChanged.emit("error", f"Screen lost: {e}. Retrying…")
                    self._next_try = time.monotonic() + 2.0

            self.frameReady.emit(pil_to_qimage(img))
            frames += 1
            now = time.monotonic()
            if now - mark >= 2.0:
                fps = frames / (now - mark) if self.screen else 0.0
                total = self.screen.bytes_sent if self.screen else 0
                self.fpsChanged.emit(fps)
                self.statsChanged.emit({
                    "fps": fps,
                    "kbps": max(0, total - sent_mark) / 1024 / (now - mark) if self.screen else 0.0,
                    "total_mb": total / 2**20,
                    "model": self.screen.model if self.screen else "",
                    "port": self.screen.port if self.screen else "",
                    "paused": self.paused, "night": is_night, "power": on,
                })
                frames, mark, sent_mark = 0, now, total

            try:
                cap = max(1, int(self.settings["max_fps"] or 60))
                period = max(1.0 / max(0.5, mode.fps()), 1.0 / cap)
            except Exception:
                period = 0.5
            remaining = period - (time.monotonic() - t0)
            if remaining > 0:
                self._wake.wait(remaining)
            self._wake.clear()
        self._close()
