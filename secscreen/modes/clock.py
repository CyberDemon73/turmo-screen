"""Clock mode: macOS-widget-style analog face, or a big lock-screen-style digital clock."""
import math
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QCheckBox, QComboBox

from ..draw import APPLE_ORANGE, W, H, capsule, draw_mono
from ..fonts import font
from .base import Mode, panel

THEMES = {
    "dark": dict(bg=(10, 10, 12), face=(28, 28, 30), num=(255, 255, 255), tick=(99, 99, 102),
                 hand=(255, 255, 255), text=(255, 255, 255), muted=(152, 152, 157),
                 grad=((22, 30, 64), (74, 36, 88))),
    "light": dict(bg=(229, 229, 234), face=(255, 255, 255), num=(0, 0, 0), tick=(174, 174, 178),
                  hand=(28, 28, 30), text=(28, 28, 30), muted=(110, 110, 115),
                  grad=((178, 208, 246), (247, 232, 240))),
}

SS = 2           # supersampling for the analog face
CX, CY, R = 162, 160, 146


class ClockMode(Mode):
    id = "clock"
    name = "Clock"
    icon = "🕐"
    description = "An analog clock styled like the macOS Clock widget, or a big lock-screen digital clock."
    DEFAULTS = {"style": "analog", "theme": "dark", "h24": True, "seconds": True, "smooth": True}

    def __init__(self, settings):
        super().__init__(settings)
        self._cache = {}

    def fps(self):
        c = self.cfg
        if c["style"] == "analog" and c["seconds"] and c["smooth"]:
            return 60.0
        return 4.0

    # ------------------------------------------------------------ analog
    def _face(self, theme):
        key = ("face", theme)
        if key not in self._cache:
            t = THEMES[theme]
            n = (R * 2 + 8) * SS
            im = Image.new("RGB", (n, n), t["bg"])
            d = ImageDraw.Draw(im)
            c, r = n / 2, R * SS
            d.ellipse((c - r, c - r, c + r, c + r), fill=t["face"])
            for i in range(60):
                a = math.radians(i * 6)
                r1, r2 = r * 0.955, r * (0.90 if i % 5 == 0 else 0.925)
                d.line((c + math.sin(a) * r1, c - math.cos(a) * r1, c + math.sin(a) * r2, c - math.cos(a) * r2),
                       fill=t["num"] if i % 5 == 0 else t["tick"], width=int(SS * (2.2 if i % 5 == 0 else 1.2)))
            f = font(r * 0.20, "semibold")
            for h in range(1, 13):
                a = math.radians(h * 30)
                d.text((c + math.sin(a) * r * 0.74, c - math.cos(a) * r * 0.74), str(h), font=f,
                       fill=t["num"], anchor="mm")
            self._cache[key] = im
        return self._cache[key]

    def _bg(self, theme):
        key = ("bg", theme, self.size)
        if key not in self._cache:
            self._cache[key] = Image.new("RGB", self.size, THEMES[theme]["bg"])
        return self._cache[key]

    def _render_analog(self, now):
        c = self.cfg
        t = THEMES[c["theme"]]
        dt = datetime.fromtimestamp(now)
        sec = dt.second + (dt.microsecond / 1e6 if c["smooth"] else 0)
        minute = dt.minute + sec / 60
        hour = dt.hour % 12 + minute / 60

        face = self._face(c["theme"]).copy()
        d = ImageDraw.Draw(face)
        n = face.width
        cx = cy = n / 2
        r = R * SS

        def pt(deg, length):
            a = math.radians(deg)
            return cx + math.sin(a) * length, cy - math.cos(a) * length

        # hour & minute hands: thin stem, then a wide rounded bar
        for deg, length in ((hour * 30, 0.52), (minute * 6, 0.84)):
            capsule(d, (cx, cy), pt(deg, r * 0.16), r * 0.028, t["hand"])
            capsule(d, pt(deg, r * 0.16), pt(deg, r * length), r * 0.072, t["hand"])
        d.ellipse((cx - r * 0.05, cy - r * 0.05, cx + r * 0.05, cy + r * 0.05), fill=t["hand"])
        if c["seconds"]:
            capsule(d, pt(sec * 6 + 180, r * 0.16), pt(sec * 6, r * 0.90), r * 0.014, APPLE_ORANGE)
            d.ellipse((cx - r * 0.036, cy - r * 0.036, cx + r * 0.036, cy + r * 0.036), fill=APPLE_ORANGE)
            d.ellipse((cx - r * 0.014, cy - r * 0.014, cx + r * 0.014, cy + r * 0.014), fill=t["face"])

        img = self._bg(c["theme"]).copy()
        size = n // SS
        cx, cy = (160, 164) if self.portrait else (CX, CY)
        img.paste(face.resize((size, size), Image.LANCZOS), (cx - size // 2, cy - size // 2))

        dd = ImageDraw.Draw(img)
        if c["h24"]:
            hm = dt.strftime("%H:%M")
        else:
            hm = dt.strftime("%I:%M").lstrip("0")
        if self.portrait:
            dd.text((160, 350), dt.strftime("%A").upper(), font=font(17, "semibold"), fill=APPLE_ORANGE,
                    anchor="ms")
            draw_mono(dd, (160, 412), hm + ("" if c["h24"] else " " + dt.strftime("%p")), font(52, "bold"),
                      t["text"], anchor="ms")
            dd.text((160, 448), f"{dt.day} {dt.strftime('%B')} {dt.year}", font=font(19), fill=t["muted"],
                    anchor="ms")
            return img
        x = 330
        dd.text((x, 104), dt.strftime("%A").upper(), font=font(17, "semibold"), fill=APPLE_ORANGE, anchor="ls")
        draw_mono(dd, (x - 2, 164), hm, font(50, "bold"), t["text"], anchor="ls")
        if not c["h24"]:
            dd.text((x, 190), dt.strftime("%p"), font=font(17, "semibold"), fill=t["muted"], anchor="ls")
        dd.text((x, 216 if not c["h24"] else 196), f"{dt.day} {dt.strftime('%B')}", font=font(19),
                fill=t["muted"], anchor="ls")
        dd.text((x, 240 if not c["h24"] else 220), str(dt.year), font=font(19), fill=t["muted"], anchor="ls")
        return img

    # ------------------------------------------------------------ digital
    def _gradient(self, theme):
        key = ("grad", theme, self.size)
        if key not in self._cache:
            top, bottom = THEMES[theme]["grad"]
            w, h = self.size
            yy, xx = np.mgrid[0:h, 0:w]
            a = ((yy / h) * 0.75 + (xx / w) * 0.25)[..., None]
            arr = np.array(top, float) * (1 - a) + np.array(bottom, float) * a
            self._cache[key] = Image.fromarray(arr.astype(np.uint8), "RGB")
        return self._cache[key]

    def _render_digital(self, now):
        c = self.cfg
        t = THEMES[c["theme"]]
        dt = datetime.fromtimestamp(now)
        img = self._gradient(c["theme"]).copy()
        d = ImageDraw.Draw(img)
        fg = (255, 255, 255) if c["theme"] == "dark" else (28, 28, 30)
        if self.portrait:  # hours stacked over minutes
            d.text((160, 64), dt.strftime("%A"), font=font(24, "semibold"), fill=fg, anchor="ms")
            d.text((160, 94), f"{dt.day} {dt.strftime('%B')}", font=font(20), fill=fg, anchor="ms")
            hh = dt.strftime("%H") if c["h24"] else dt.strftime("%I")
            f = font(170, "bold")
            draw_mono(d, (160, 258), hh, f, fg, anchor="ms")
            draw_mono(d, (160, 418), dt.strftime("%M"), f, fg, anchor="ms")
            if c["seconds"]:
                frac = (dt.second + dt.microsecond / 1e6) / 60
                d.rounded_rectangle((70, 444, 250, 448), radius=2, fill=t["muted"])
                d.rounded_rectangle((70, 444, 70 + max(4, 180 * frac), 448), radius=2, fill=fg)
            if not c["h24"]:
                d.text((160, 472), dt.strftime("%p"), font=font(16, "semibold"), fill=fg, anchor="ms")
            return img
        d.text((W / 2, 74), f"{dt.strftime('%A')}, {dt.day} {dt.strftime('%B')}", font=font(24, "semibold"),
               fill=fg, anchor="ms")
        hm = dt.strftime("%H:%M") if c["h24"] else dt.strftime("%I:%M").lstrip("0")
        draw_mono(d, (W / 2, 228), hm, font(148, "bold"), fg, anchor="ms")
        if c["seconds"]:
            frac = (dt.second + dt.microsecond / 1e6) / 60
            d.rounded_rectangle((140, 268, 340, 272), radius=2, fill=t["muted"])
            d.rounded_rectangle((140, 268, 140 + max(4, 200 * frac), 272), radius=2, fill=fg)
        if not c["h24"]:
            d.text((W / 2, 304), dt.strftime("%p"), font=font(18, "semibold"), fill=fg, anchor="ms")
        return img

    def render(self, now):
        if self.cfg["style"] == "digital":
            return self._render_digital(now)
        return self._render_analog(now)

    def build_settings(self):
        w, form = panel(self)

        style = QComboBox()
        style.addItem("Analog (macOS widget)", "analog")
        style.addItem("Digital (lock screen)", "digital")
        style.setCurrentIndex(max(0, style.findData(self.cfg["style"])))
        style.currentIndexChanged.connect(lambda: self.set("style", style.currentData()))
        form.addRow("Style:", style)

        theme = QComboBox()
        theme.addItem("Dark", "dark")
        theme.addItem("Light", "light")
        theme.setCurrentIndex(max(0, theme.findData(self.cfg["theme"])))
        theme.currentIndexChanged.connect(lambda: self.set("theme", theme.currentData()))
        form.addRow("Theme:", theme)

        for key, label in (("h24", "24-hour time"), ("seconds", "Show seconds"),
                           ("smooth", "Smooth sweeping second hand")):
            cb = QCheckBox(label)
            cb.setChecked(bool(self.cfg[key]))
            cb.toggled.connect(lambda v, k=key: self.set(k, v))
            form.addRow("", cb)
        return w
