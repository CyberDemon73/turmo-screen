"""System monitor: CPU, memory, network and disk with sparklines."""
import os
import time
from collections import deque

from PIL import Image, ImageDraw

from ..draw import W, H, blend, fmt_span
from ..fonts import font
from .base import Mode

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

BG = (16, 16, 16)
TILE = (32, 32, 32)
FG = (245, 245, 247)
MUTED = (152, 152, 157)
COLORS = {"cpu": (255, 159, 10), "mem": (100, 160, 255), "net": (48, 209, 88), "disk": (191, 90, 242)}


def _bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class SystemMode(Mode):
    id = "system"
    name = "System"
    icon = "📊"
    description = "CPU, memory, network and disk usage of this computer."

    def __init__(self, settings):
        super().__init__(settings)
        self.hist = {k: deque([0.0] * 60, maxlen=60) for k in COLORS}
        self._last_sample = 0.0
        self._net = None
        self._vals = {}
        self._frame = None

    def fps(self):
        return 2.0

    def _sample(self, now):
        cpu = psutil.cpu_percent(None)
        mem = psutil.virtual_memory()
        net = psutil.net_io_counters()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        down = up = 0.0
        if self._net is not None:
            dt = max(0.001, now - self._net[0])
            down = (net.bytes_recv - self._net[1]) / dt
            up = (net.bytes_sent - self._net[2]) / dt
        first = self._net is None
        self._net = (now, net.bytes_recv, net.bytes_sent)
        if first:  # start the graphs flat at the current level instead of zero
            self.hist["cpu"].extend([cpu] * 60)
            self.hist["mem"].extend([mem.percent] * 60)
            self.hist["disk"].extend([disk.percent] * 60)
        self.hist["cpu"].append(cpu)
        self.hist["mem"].append(mem.percent)
        self.hist["net"].append(down)
        self.hist["disk"].append(disk.percent)
        self._vals = dict(cpu=cpu, mem=mem, down=down, up=up, disk=disk)

    def render(self, now):
        if psutil is None:
            from ..draw import message_image
            return message_image("psutil not installed", "pip install psutil", size=self.size)
        if now - self._last_sample >= 1.0 or self._frame is None or self._frame.size != self.size:
            if now - self._last_sample >= 1.0 or self._frame is None:
                self._sample(now)
                self._last_sample = now
            self._frame = self._draw(now)
        return self._frame

    def _tile(self, d, x, y, w, h, key, label, value, sub, scale_max=None):
        d.rounded_rectangle((x, y, x + w, y + h), radius=14, fill=TILE)
        col = COLORS[key]
        d.text((x + 14, y + 24), label, font=font(14, "semibold"), fill=MUTED, anchor="ls")
        if self.portrait:  # narrow tile: subtitle under the value
            d.text((x + 12, y + 60), value, font=font(28, "bold"), fill=FG, anchor="ls")
            d.text((x + 14, y + 82), sub, font=font(14), fill=MUTED, anchor="ls")
            gy = y + 96
        else:
            d.text((x + 12, y + 62), value, font=font(32, "bold"), fill=FG, anchor="ls")
            d.text((x + w - 14, y + 24), sub, font=font(14), fill=MUTED, anchor="rs")
            gy = y + 74
        # sparkline
        vals = list(self.hist[key])
        top = scale_max or max(1.0, max(vals))
        gx, gw, gh = x + 10, w - 20, y + h - 10 - gy
        pts = [(gx + gw * i / (len(vals) - 1), gy + gh - gh * min(v, top) / top) for i, v in enumerate(vals)]
        d.polygon(pts + [(gx + gw, gy + gh), (gx, gy + gh)], fill=blend(TILE, col, 0.25))
        d.line(pts, fill=col, width=2)

    def _draw(self, now):
        w, h = self.size
        img = Image.new("RGB", (w, h), BG)
        d = ImageDraw.Draw(img)
        v = self._vals
        tw, th = (w - 24) // 2, (h - 24) // 2
        x2, y2 = 16 + tw, 16 + th
        self._tile(d, 8, 8, tw, th, "cpu", "CPU", f"{v['cpu']:.0f}%", f"{psutil.cpu_count()} cores", 100)
        mem = v["mem"]
        self._tile(d, x2, 8, tw, th, "mem", "MEMORY", f"{mem.percent:.0f}%",
                   f"{mem.used / 2**30:.1f}/{mem.total / 2**30:.0f} GB", 100)
        self._tile(d, 8, y2, tw, th, "net", "NETWORK ↓", _bytes(v["down"]) + "/s", "↑ " + _bytes(v["up"]) + "/s")
        disk = v["disk"]
        self._tile(d, x2, y2, tw, th, "disk", "DISK", f"{disk.percent:.0f}%",
                   f"{disk.free / 2**30:.0f} GB free", 100)
        return img
