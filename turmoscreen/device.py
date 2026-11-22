"""Driver for 3.5" Turing-style USB smart screens (revision A protocol, 320x480 panel).

Frames are drawn at the logical size of the chosen orientation (480x320 landscape or
320x480 portrait) and rotated in software. The panel's firmware accepts only ~220 KB/s
(measured: independent of baud rate, flow control, write size and pixel content), and each
command costs about as much as 13 pixels. So only 4x4 tiles that visibly changed are sent,
nearby runs are merged, and a writer thread transmits while the next frame is being drawn.

Protocol rule learned the hard way: the firmware reads each command from its own USB
packet and drops anything else in that packet, so a command is always a separate write.
"""
import queue
import sys
import threading

import numpy as np
import serial
from serial.tools import list_ports

PANEL_W, PANEL_H = 320, 480
TILE = 4
MERGE_GAP_TILES = 3  # gaps up to 12 px are cheaper to resend than to start a new command
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


# 4x4 Bayer matrix, as fractions in [0, 1): ordered dithering spreads the rounding error of the
# panel's 5/6/5-bit colour into a fixed fine pattern, so dark gradients don't show bands.
_BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) + 0.5) / 16
_bayer_cache = {}


def _threshold(h, w):
    if (h, w) not in _bayer_cache:
        _bayer_cache[(h, w)] = np.tile(_BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w]
    return _bayer_cache[(h, w)]


def to_rgb565(img, dither=False):
    """RGB888 -> RGB565. With dither, values between two panel shades are mixed in a fixed pattern;
    colours the panel can show exactly stay exactly the same (no noise on flat areas)."""
    if not dither:
        a = np.asarray(img.convert("RGB"), dtype=np.uint16)
        return ((a[..., 0] & 0xF8) << 8) | ((a[..., 1] & 0xFC) << 3) | (a[..., 2] >> 3)
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    t = _threshold(a.shape[0], a.shape[1])
    r = np.minimum(np.floor(a[..., 0] / 8 + t), 31).astype(np.uint16)
    g = np.minimum(np.floor(a[..., 1] / 4 + t), 63).astype(np.uint16)
    b = np.minimum(np.floor(a[..., 2] / 8 + t), 31).astype(np.uint16)
    return (r << 11) | (g << 5) | b


def changed_mask(px, shadow, tolerance):
    """Pixels that differ from what the panel shows. tolerance = colour steps (RGB565 units) to ignore:
    0 = exact; 1 = skip ±1-step changes (dithering noise, invisible on this panel)."""
    mask = px != shadow
    if tolerance <= 0 or not mask.any():
        return mask
    # only look at pixels that changed at all (usually a small fraction of the frame)
    a = px[mask].astype(np.int32)
    b = shadow[mask].astype(np.int32)
    visible = ((np.abs((a >> 11) - (b >> 11)) > tolerance)
               | (np.abs(((a >> 5) & 63) - ((b >> 5) & 63)) > 2 * tolerance)
               | (np.abs((a & 31) - (b & 31)) > tolerance))
    mask[mask] = visible
    return mask


class TuringScreen:
    """All serial writes go through one background writer thread, so the next frame can be drawn and
    compared while the current one is still being transmitted (the panel itself is the bottleneck)."""

    def __init__(self, port, orientation="reverse_landscape"):
        self.port = port
        self.orientation = orientation
        self.tolerance = 1
        self.dither = True
        self.ser = None
        self._shadow = None
        self._last = None
        self.bytes_sent = 0
        self.model = ""
        self._q = None
        self._writer = None
        self._error = None

    # ------------------------------------------------------------ connection
    def open(self):
        self.ser = serial.Serial(self.port, 115200, timeout=1, write_timeout=10, rtscts=True)
        self._shadow = None
        self.model = self.identify()
        self._error = None
        self._q = queue.Queue(maxsize=2)  # at most ~1 frame queued ahead of the one being sent
        self._writer = threading.Thread(target=self._write_loop, name="screen-writer", daemon=True)
        self._writer.start()

    def close(self):
        if self._q is not None:
            try:
                self._q.put(None, timeout=3)  # let queued data finish, then stop
            except queue.Full:
                pass
            if self._writer is not None:
                self._writer.join(timeout=5)
        self._q = self._writer = None
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def _write_loop(self):
        while True:
            item = self._q.get()
            if item is None:
                return
            try:
                for chunk in item:
                    self.ser.write(chunk)
            except Exception as e:  # reported to the engine on its next call
                self._error = e
                return

    def _enqueue(self, chunks):
        if self._error is not None:
            raise serial.SerialException(f"screen write failed: {self._error}")
        while True:
            try:
                self._q.put(chunks, timeout=0.5)
                return
            except queue.Full:
                if self._error is not None or not self._writer.is_alive():
                    raise serial.SerialException(f"screen write failed: {self._error}")

    @staticmethod
    def _packet(cmd, x=0, y=0, ex=0, ey=0):
        return bytes([
            (x >> 2) & 0xFF,
            (((x & 3) << 6) + (y >> 4)) & 0xFF,
            (((y & 15) << 4) + (ex >> 6)) & 0xFF,
            (((ex & 63) << 2) + (ey >> 8)) & 0xFF,
            ey & 0xFF,
            cmd,
        ])

    def _cmd(self, cmd, x=0, y=0, ex=0, ey=0):
        # A command must be its own write: the firmware reads each command from its own USB packet
        # and drops anything else in that packet.
        self._enqueue([self._packet(cmd, x, y, ex, ey)])

    def identify(self):
        """Ask the screen what it is (HELLO). Older Turing units don't answer. Runs before the writer starts."""
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

    # ------------------------------------------------------------ commands
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

    # ------------------------------------------------------------ pixels
    def _region(self, px, x, y, w, h):
        """Command + pixel chunks for one logical rectangle, mapped onto the panel."""
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
        data = np.ascontiguousarray(dev).astype("<u2").tobytes()
        self.bytes_sent += len(data) + 6
        return [self._packet(CMD_DISPLAY_BITMAP, dx, dy, dx + dw - 1, dy + dh - 1)] + \
               [data[o:o + CHUNK] for o in range(0, len(data), CHUNK)]

    def show(self, img):
        """Queue a PIL image of the orientation's logical size, sending only the changed 4x4 tiles."""
        px = to_rgb565(img, self.dither)
        h, w = px.shape
        if (w, h) != logical_size(self.orientation):
            return  # frame rendered for the previous orientation
        last, self._last = self._last, px
        if self._shadow is None or self._shadow.shape != px.shape:
            self._enqueue(self._region(px, 0, 0, w, h))
            self._shadow = px
            return
        diff = changed_mask(px, self._shadow, self.tolerance)
        if self.tolerance > 0 and last is not None and last.shape == px.shape:
            # Small differences are only skipped while that area keeps changing (e.g. GIF noise).
            # Once it holds still, repaint it exactly, so no slightly-off blocks are left behind.
            leftover = (px != self._shadow) & ~diff & (px == last)
            diff |= leftover
        tiles = diff.reshape(h // TILE, TILE, w // TILE, TILE).any(axis=(1, 3))
        chunks = []
        shadow = self._shadow.copy()
        for ty in np.nonzero(tiles.any(axis=1))[0]:
            row = np.concatenate(([False], tiles[ty], [False]))
            edges = np.flatnonzero(row[1:] != row[:-1])
            runs = []
            for s, e in zip(edges[::2], edges[1::2]):
                if runs and s - runs[-1][1] <= MERGE_GAP_TILES:  # a command costs ~13 px: bridge small gaps
                    runs[-1][1] = e
                else:
                    runs.append([s, e])
            y0 = int(ty) * TILE
            for s, e in runs:
                x0, x1 = int(s) * TILE, int(e) * TILE
                chunks += self._region(px, x0, y0, x1 - x0, TILE)
                shadow[y0:y0 + TILE, x0:x1] = px[y0:y0 + TILE, x0:x1]
        if chunks:
            self._enqueue(chunks)
        self._shadow = shadow  # untouched tiles keep what the panel really shows
