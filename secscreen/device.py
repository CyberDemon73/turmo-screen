"""Driver for 3.5" Turing-style USB smart screens (revision A protocol, 320x480 panel).

Frames are drawn at the logical size of the chosen orientation (480x320 landscape or
320x480 portrait) and rotated in software. The panel accepts only ~220 KB/s, so only
8x8 tiles that changed since the last frame are sent.

Protocol rule learned the hard way: the firmware reads each command from its own USB
packet and drops anything else in that packet, so a command is always a separate write.
"""
import sys

import numpy as np
import serial
from serial.tools import list_ports

PANEL_W, PANEL_H = 320, 480
TILE = 8
CHUNK = PANEL_W * 8 * 2  # pixel bytes per write, as in the original working driver
VID, PID = 0x1A86, 0x5722

CMD_HELLO = 69
CMD_RESET = 101
CMD_SCREEN_OFF = 108
CMD_SCREEN_ON = 109
CMD_BRIGHTNESS = 110
CMD_DISPLAY_BITMAP = 197

ORIENTATIONS = {
    "reverse_landscape": "Landscape",
    "landscape": "Landscape (flipped)",
    "portrait": "Portrait",
    "reverse_portrait": "Portrait (flipped)",
}

MODELS = {1: 'UsbMonitor 3.5"', 2: 'UsbMonitor 5"', 3: 'UsbMonitor 7"'}


def logical_size(orientation):
    return (PANEL_W, PANEL_H) if "portrait" in orientation else (PANEL_H, PANEL_W)


def is_screen(p):
    return (p.vid == VID and p.pid == PID) or (p.serial_number or "").upper().startswith("USB35INCH")


def find_ports():
    """[(device, description, is_screen)], likely screens first."""
    out = []
    for p in list_ports.comports():
        if sys.platform == "darwin" and p.device.startswith("/dev/tty."):
            continue  # macOS lists each port twice; /dev/cu.* is the one to open
        out.append((p.device, p.description or p.device, is_screen(p)))
    out.sort(key=lambda x: (not x[2], x[0]))
    return out


def auto_port():
    for dev, _, ok in find_ports():
        if ok:
            return dev
    return None


def to_rgb565(img):
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    return ((a[..., 0] & 0xF8) << 8) | ((a[..., 1] & 0xFC) << 3) | (a[..., 2] >> 3)


class TuringScreen:
    def __init__(self, port, orientation="reverse_landscape"):
        self.port = port
        self.orientation = orientation
        self.ser = None
        self._shadow = None
        self.bytes_sent = 0
        self.model = ""

    def open(self):
        self.ser = serial.Serial(self.port, 115200, timeout=1, write_timeout=10, rtscts=True)
        self._shadow = None
        self.model = self.identify()

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def _cmd(self, cmd, x=0, y=0, ex=0, ey=0):
        self.ser.write(bytes([
            (x >> 2) & 0xFF,
            (((x & 3) << 6) + (y >> 4)) & 0xFF,
            (((y & 15) << 4) + (ex >> 6)) & 0xFF,
            (((ex & 63) << 2) + (ey >> 8)) & 0xFF,
            ey & 0xFF,
            cmd,
        ]))

    def identify(self):
        """Ask the screen what it is (HELLO). Older Turing units don't answer."""
        try:
            self.ser.reset_input_buffer()
            self.ser.write(bytes([CMD_HELLO] * 6))
            self.ser.timeout = 0.5
            reply = self.ser.read(6)
        except serial.SerialException:
            reply = b""
        finally:
            self.ser.timeout = 1
        if len(reply) == 6 and reply[0] in MODELS:
            return MODELS[reply[0]] + " (rev A)"
        return 'Turing 3.5" (rev A)'

    def reboot(self):
        """Restart the screen's firmware; it disconnects from USB for a few seconds."""
        self._cmd(CMD_RESET)

    def screen_on(self):
        self._cmd(CMD_SCREEN_ON)
        self._shadow = None  # redraw everything after waking up

    def screen_off(self):
        self._cmd(CMD_SCREEN_OFF)

    def set_brightness(self, pct):
        pct = max(0, min(100, int(pct)))
        self._cmd(CMD_BRIGHTNESS, int(255 - pct / 100 * 255))  # device scale is inverted

    def set_orientation(self, orientation):
        self.orientation = orientation
        self._shadow = None

    def invalidate(self):
        self._shadow = None

    def _send(self, px, x, y, w, h):
        """Send one logical rectangle mapped onto the panel: command first, then pixels in chunks."""
        sub = px[y:y + h, x:x + w]
        o = self.orientation
        if o == "landscape":
            dev, dx, dy, dw, dh = np.rot90(sub, -1), PANEL_W - y - h, x, h, w
        elif o == "reverse_landscape":
            dev, dx, dy, dw, dh = np.rot90(sub, 1), y, PANEL_H - x - w, h, w
        elif o == "reverse_portrait":
            dev, dx, dy, dw, dh = sub[::-1, ::-1], PANEL_W - x - w, PANEL_H - y - h, w, h
        else:  # portrait
            dev, dx, dy, dw, dh = sub, x, y, w, h
        self._cmd(CMD_DISPLAY_BITMAP, dx, dy, dx + dw - 1, dy + dh - 1)
        data = np.ascontiguousarray(dev).astype("<u2").tobytes()
        for off in range(0, len(data), CHUNK):
            self.ser.write(data[off:off + CHUNK])
        self.bytes_sent += len(data) + 6

    def show(self, img):
        """Send a PIL image of the orientation's logical size, transmitting only changed tiles."""
        px = to_rgb565(img)
        h, w = px.shape
        if (w, h) != logical_size(self.orientation):
            return  # frame rendered for the previous orientation
        if self._shadow is None or self._shadow.shape != px.shape:
            self._send(px, 0, 0, w, h)
        else:
            diff = (px != self._shadow).reshape(h // TILE, TILE, w // TILE, TILE).any(axis=(1, 3))
            for ty in np.nonzero(diff.any(axis=1))[0]:
                row = np.concatenate(([False], diff[ty], [False]))
                edges = np.flatnonzero(row[1:] != row[:-1])
                for s, e in zip(edges[::2], edges[1::2]):
                    self._send(px, int(s) * TILE, int(ty) * TILE, int(e - s) * TILE, TILE)
        self._shadow = px
