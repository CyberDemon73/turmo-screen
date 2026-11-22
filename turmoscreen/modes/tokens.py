"""Claude Code monitor: token dashboard, plan limits and a buddy view with the Claude character."""
import time
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QSpinBox

from ..draw import (BG, BLUE, CLAWD_COLS, GREEN, MUTED, ORANGE, PANEL, PURPLE, TEXT, W, H, bar, canvas,
                    draw_clawd, fmt_span, fmt_tokens, spark)
from ..fonts import font
from ..usage import LimitsWatcher, UsageWatcher
from .base import Mode, panel

ICON_BOX = (16, 8, 144)  # x, y, size
ICON_BOX_PORTRAIT = (12, 12, 120)

VIEWS = {"dashboard": "Dashboard (tokens)", "limits": "Plan limits", "buddy": "Buddy (big character)",
         "rotate": "Rotate through all"}
OK_GREEN, WARN, ALERT = (48, 208, 88), (248, 160, 16), (248, 68, 56)


def pct_color(p):
    return OK_GREEN if p < 50 else (WARN if p < 80 else ALERT)


def reset_text(ts, now):
    if not ts:
        return ""
    left = ts - now
    if left <= 0:
        return "resets now"
    if left < 24 * 3600:
        return "resets in " + fmt_span(left)
    return "resets " + datetime.fromtimestamp(ts).strftime("%a %H:%M")


class TokensMode(Mode):
    id = "tokens"
    name = "Claude Tokens"
    icon = "✳"
    description = ("Claude Code usage: live tokens from your local transcripts, plus your plan's 5-hour and "
                   "weekly limits (from your Claude Code login, like its /usage screen).")
    DEFAULTS = {"view": "dashboard", "rotate_seconds": 15, "limits": True}

    def __init__(self, settings):
        super().__init__(settings)
        self.watcher = UsageWatcher()
        self.limits = LimitsWatcher()
        self._static = None
        self._sig = None

    def activate(self):
        self.watcher.start()
        self.limits.enabled = bool(self.cfg["limits"])
        self.limits.start()

    def _view(self, now):
        v = self.cfg["view"]
        if v == "rotate":
            order = ("dashboard", "limits", "buddy")
            return order[int(now // max(3, int(self.cfg["rotate_seconds"]))) % len(order)]
        return v if v in VIEWS else "dashboard"

    def fps(self):
        active = self.watcher.stats.active(time.time())
        if self._view(time.time()) == "dashboard":
            return 60.0 if active else 30.0
        return 12.0 if active else 8.0

    def _signature(self, s, now):
        return (s.loaded, s.today, s.t_msgs, s.block_tokens, int(s.burn_per_min), s.model, tuple(s.days),
                datetime.fromtimestamp(now).strftime("%H:%M"), s.active(now),
                int((now - s.last_time) // 60), int((s.block_end - now) // 60),
                tuple((l.key, round(l.percent), l.resets_at) for l in self.limits.limits), self.limits.status)

    def render(self, now):
        s = self.watcher.stats
        view = self._view(now)
        sig = (self.size, view) + self._signature(s, now)
        if sig != self._sig or self._static is None:
            if view == "limits":
                self._static = self._draw_limits(s, now)
            elif view == "buddy":
                self._static = self._draw_buddy(s, now)
            else:
                self._static = self._draw_portrait(s, now) if self.portrait else self._draw_static(s, now)
            self._sig = sig
        img = self._static.copy()
        if view == "dashboard":
            x, y, size = ICON_BOX_PORTRAIT if self.portrait else ICON_BOX
            img.paste(spark(size, now, s.active(now)), (x, y))
        else:
            from PIL import ImageDraw
            x, y, unit = self._clawd_box(view)
            draw_clawd(ImageDraw.Draw(img), x, y, unit, now, s.active(now), BG)
        return img

    # ------------------------------------------------------------ character views
    def _clawd_box(self, view):
        w, h = self.size
        if view == "buddy":
            unit = 12 if self.portrait else 14
            return (w - CLAWD_COLS * unit) // 2, (100 if self.portrait else 36), unit
        unit = 8
        if self.portrait:
            return (w - CLAWD_COLS * unit) // 2, 22, unit
        return (176 - CLAWD_COLS * unit) // 2, 64, unit

    def _status_line(self, d, cx, y, s, now, size=18):
        active = s.active(now)
        st = "Working" if active else self._status(s, now)
        f = font(size, "semibold")
        tw = d.textlength(st, font=f)
        x = cx - (tw + 16) / 2
        d.ellipse((x, y - size * 0.62, x + 11, y - size * 0.62 + 11), fill=ORANGE if active else MUTED)
        d.text((x + 16, y), st, font=f, fill=TEXT if active else MUTED, anchor="ls")

    def _limit_rows(self, d, x0, x1, y, row_h, now, max_rows):
        lims = self.limits.limits[:max_rows]
        if not lims:
            msg = self.limits.status if self.cfg["limits"] else "Plan limits are turned off"
            d.text((x0, y + 24), "Plan limits unavailable", font=font(18, "semibold"), fill=TEXT, anchor="ls")
            f = font(14)
            line, yy = "", y + 48
            for word in msg.split():
                if f.getlength(line + " " + word) > x1 - x0 and line:
                    d.text((x0, yy), line, font=f, fill=MUTED, anchor="ls")
                    line, yy = word, yy + 19
                else:
                    line = (line + " " + word).strip()
            d.text((x0, yy), line, font=f, fill=MUTED, anchor="ls")
            return
        for i, l in enumerate(lims):
            top = y + i * row_h
            col = pct_color(l.percent)
            d.text((x0, top + 20), l.label, font=font(16, "semibold"), fill=TEXT, anchor="ls")
            d.text((x1, top + 24), f"{l.percent:.0f}%", font=font(28, "bold"), fill=col, anchor="rs")
            bar(d, x0, top + 34, x1 - x0, 10, PANEL)
            if l.percent > 0:
                bar(d, x0, top + 34, max(10, (x1 - x0) * min(100.0, l.percent) / 100), 10, col)
            d.text((x0, top + 64), reset_text(l.resets_at, now), font=font(14), fill=MUTED, anchor="ls")

    def _draw_limits(self, s, now):
        w, h = self.size
        img, d = canvas(BG, self.size)
        upd = (" · updated " + datetime.fromtimestamp(self.limits.updated).strftime("%H:%M")
               if self.limits.limits else "")
        if self.portrait:
            self._status_line(d, w / 2, 134, s, now)
            d.line((16, 150, w - 16, 150), fill=PANEL, width=2)
            d.text((16, 174), "PLAN LIMITS" + upd, font=font(13, "semibold"), fill=MUTED, anchor="ls")
            self._limit_rows(d, 16, w - 16, 180, 92, now, 3)
            d.text((16, h - 14), f"Today {fmt_tokens(s.today)} tokens", font=font(14), fill=MUTED, anchor="ls")
            return img
        d.text((88, 40), "Claude Code", font=font(20, "semibold"), fill=TEXT, anchor="ms")
        self._status_line(d, 88, 178, s, now, 17)
        d.text((88, 250), "TODAY", font=font(13, "semibold"), fill=MUTED, anchor="ms")
        d.text((88, 282), fmt_tokens(s.today), font=font(28, "bold"), fill=TEXT, anchor="ms")
        d.line((176, 14, 176, h - 14), fill=PANEL, width=2)
        d.text((192, 26), "PLAN LIMITS" + upd, font=font(13, "semibold"), fill=MUTED, anchor="ls")
        self._limit_rows(d, 192, w - 14, 34, 94, now, 3)
        return img

    def _draw_buddy(self, s, now):
        w, h = self.size
        img, d = canvas(BG, self.size)
        active = s.active(now)
        if self.portrait:
            d.text((w / 2, 60), "Claude Code", font=font(22, "semibold"), fill=TEXT, anchor="ms")
            self._status_line(d, w / 2, 290, s, now, 22)
            y = 340
        else:
            self._status_line(d, w / 2, 222, s, now, 24)
            y = 262
        bits = []
        for key, short in (("five_hour", "5h"), ("seven_day", "week")):
            l = self.limits.get(key)
            if l:
                bits.append((f"{short} {l.percent:.0f}%", pct_color(l.percent)))
        bits.append((f"today {fmt_tokens(s.today)}", MUTED))
        f = font(18, "semibold")
        if self.portrait:  # one item per line
            for i, (txt, col) in enumerate(bits):
                d.text((w / 2, y + i * 30), txt, font=f, fill=col, anchor="ms")
        else:
            sep = "   ·   "
            total = sum(d.textlength(t, font=f) for t, _ in bits) + d.textlength(sep, font=f) * (len(bits) - 1)
            x = (w - total) / 2
            for i, (txt, col) in enumerate(bits):
                d.text((x, y + 14), txt, font=f, fill=col, anchor="ls")
                x += d.textlength(txt, font=f)
                if i < len(bits) - 1:
                    d.text((x, y + 14), sep, font=f, fill=PANEL, anchor="ls")
                    x += d.textlength(sep, font=f)
        lim = self.limits.get("five_hour")
        if lim:  # thin session meter along the bottom
            bar(d, 40, h - 22, w - 80, 6, PANEL)
            bar(d, 40, h - 22, max(6, (w - 80) * min(100.0, lim.percent) / 100), 6, pct_color(lim.percent))
        return img

    @staticmethod
    def _status(s, now):
        if not s.loaded:
            return "Loading…"
        if s.active(now):
            return "Working"
        if s.last_time:
            return "Idle " + fmt_span(now - s.last_time)
        return "No data"

    def _draw_portrait(self, s, now):
        img, d = canvas(BG, (320, 480))
        active = s.active(now)
        lt = datetime.fromtimestamp(now)
        XR = 308

        # Header: spark (pasted later) + title, status, clock
        x = 144
        d.text((x, 38), "Claude Code", font=font(21, "semibold"), fill=TEXT, anchor="ls")
        st = self._status(s, now)
        d.ellipse((x + 1, 54, x + 11, 64), fill=ORANGE if active else MUTED)
        d.text((x + 16, 66), st, font=font(17, "semibold"), fill=TEXT if active else MUTED, anchor="ls")
        d.text((x - 2, 108), lt.strftime("%H:%M"), font=font(36, "bold"), fill=TEXT, anchor="ls")
        d.text((x, 130), lt.strftime("%a %d %b").replace(" 0", " "), font=font(15), fill=MUTED, anchor="ls")
        d.line((12, 146, XR, 146), fill=PANEL, width=2)

        # Today
        d.text((12, 170), "TODAY", font=font(14, "semibold"), fill=MUTED, anchor="ls")
        d.text((XR, 170), f"{s.t_msgs:,} msgs", font=font(14), fill=MUTED, anchor="rs")
        d.text((9, 228), fmt_tokens(s.today), font=font(56, "bold"), fill=TEXT, anchor="ls")
        d.text((XR, 226), "tokens", font=font(17), fill=MUTED, anchor="rs")
        rows = [("Input", s.t_in, BLUE), ("Output", s.t_out, ORANGE),
                ("Cache wr", s.t_cw, PURPLE), ("Cache rd", s.t_cr, GREEN)]
        tot = max(1, s.today)
        for i, (name, v, col) in enumerate(rows):
            base = 258 + i * 24
            d.ellipse((12, base - 11, 22, base - 1), fill=col)
            d.text((27, base), name, font=font(17), fill=TEXT, anchor="ls")
            bar(d, 118, base - 10, 110, 8, PANEL)
            if v:
                bar(d, 118, base - 10, max(8, 110 * v / tot), 8, col)
            d.text((XR, base), fmt_tokens(v), font=font(17, "semibold"), fill=TEXT, anchor="rs")
        d.line((12, 344, XR, 344), fill=PANEL, width=2)

        # Window + burn
        self._window_block(d, 12, 364, s, now)
        d.text((172, 364), "BURN / MIN", font=font(14, "semibold"), fill=MUTED, anchor="ls")
        d.text((170, 395), fmt_tokens(s.burn_per_min), font=font(28, "bold"), fill=TEXT, anchor="ls")

        # 7 days
        mx = max(1, max(s.days))
        slot = (XR - 12) / 7
        bw, top, hmax = 24, 420, 30
        for i in range(7):
            bx = 12 + i * slot + (slot - bw) / 2
            h = max(3, hmax * s.days[i] / mx) if s.days[i] else 2
            d.rectangle((bx, top + hmax - h, bx + bw, top + hmax), fill=ORANGE if i == 6 else (125, 117, 108))
            d.text((bx + bw / 2, 470), s.day_names[i], font=font(14),
                   fill=TEXT if i == 6 else MUTED, anchor="ms")
        return img

    def _draw_static(self, s, now):
        img, d = canvas(BG)
        active = s.active(now)
        lt = datetime.fromtimestamp(now)

        # Left column
        d.text((89, 180), "Claude Code", font=font(22, "semibold"), fill=TEXT, anchor="ms")
        if not s.loaded:
            st = "Loading…"
        elif active:
            st = "Working"
        elif s.last_time:
            st = "Idle " + fmt_span(now - s.last_time)
        else:
            st = "No data"
        f = font(18, "semibold")
        tw = d.textlength(st, font=f)
        sx = 89 - (tw + 16) / 2
        d.ellipse((sx, 194, sx + 11, 205), fill=ORANGE if active else MUTED)
        d.text((sx + 16, 207), st, font=f, fill=TEXT if active else MUTED, anchor="ls")
        d.text((89, 252), lt.strftime("%H:%M"), font=font(40, "bold"), fill=TEXT, anchor="ms")
        d.text((89, 276), lt.strftime("%a %d %b").replace(" 0", " "), font=font(16), fill=MUTED, anchor="ms")
        model = s.model[7:] if s.model.startswith("claude-") else s.model
        d.text((89, 306), model, font=font(14), fill=MUTED, anchor="ms")
        d.line((178, 14, 178, 306), fill=PANEL, width=2)

        # Right column
        X, XR = 194, 468
        d.text((X, 22), "TODAY", font=font(14, "semibold"), fill=MUTED, anchor="ls")
        d.text((XR, 22), f"{s.t_msgs:,} msgs", font=font(14), fill=MUTED, anchor="rs")
        d.text((X - 3, 80), fmt_tokens(s.today), font=font(56, "bold"), fill=TEXT, anchor="ls")
        d.text((XR, 78), "tokens", font=font(17), fill=MUTED, anchor="rs")

        rows = [("Input", s.t_in, BLUE), ("Output", s.t_out, ORANGE),
                ("Cache wr", s.t_cw, PURPLE), ("Cache rd", s.t_cr, GREEN)]
        tot = max(1, s.today)
        for i, (name, v, col) in enumerate(rows):
            base = 108 + i * 24
            d.ellipse((X, base - 11, X + 10, base - 1), fill=col)
            d.text((X + 15, base), name, font=font(17), fill=TEXT, anchor="ls")
            bar(d, 300, base - 10, 96, 8, PANEL)
            if v:
                bar(d, 300, base - 10, max(8, 96 * v / tot), 8, col)
            d.text((XR, base), fmt_tokens(v), font=font(17, "semibold"), fill=TEXT, anchor="rs")

        d.line((X, 193, XR, 193), fill=PANEL, width=2)
        BX = 342
        self._window_block(d, X, 212, s, now)
        d.text((BX, 212), "BURN / MIN", font=font(14, "semibold"), fill=MUTED, anchor="ls")
        d.text((BX - 2, 243), fmt_tokens(s.burn_per_min), font=font(28, "bold"), fill=TEXT, anchor="ls")

        mx = max(1, max(s.days))
        slot = (XR - X) / 7
        bw, top, hmax = 24, 266, 30
        for i in range(7):
            x = X + i * slot + (slot - bw) / 2
            h = max(3, hmax * s.days[i] / mx) if s.days[i] else 2
            d.rectangle((x, top + hmax - h, x + bw, top + hmax), fill=ORANGE if i == 6 else (125, 117, 108))
            d.text((x + bw / 2, 314), s.day_names[i], font=font(14),
                   fill=TEXT if i == 6 else MUTED, anchor="ms")
        return img

    def _window_block(self, d, x, label_y, s, now):
        """5-hour block: real plan limit % when available, otherwise tokens and time left in the window."""
        lim = self.limits.get("five_hour")
        if lim:
            col = pct_color(lim.percent)
            d.text((x, label_y), "5H LIMIT", font=font(14, "semibold"), fill=MUTED, anchor="ls")
            d.text((x - 2, label_y + 31), f"{lim.percent:.0f}%", font=font(28, "bold"), fill=col, anchor="ls")
            bar(d, x, label_y + 39, 84, 7, PANEL)
            if lim.percent > 0:
                bar(d, x, label_y + 39, max(7, 84 * min(100.0, lim.percent) / 100), 7, col)
            if lim.resets_at:
                d.text((x + 90, label_y + 47), fmt_span(lim.resets_at - now), font=font(14), fill=col, anchor="ls")
            return
        d.text((x, label_y), "5H WINDOW", font=font(14, "semibold"), fill=MUTED, anchor="ls")
        if s.block_active:
            left = s.block_end - now
            d.text((x - 2, label_y + 31), fmt_tokens(s.block_tokens), font=font(28, "bold"), fill=TEXT, anchor="ls")
            frac = max(0.0, min(1.0, 1 - left / (5 * 3600)))
            bar(d, x, label_y + 39, 84, 7, PANEL)
            bar(d, x, label_y + 39, max(7, 84 * frac), 7, ORANGE)
            d.text((x + 90, label_y + 47), fmt_span(left), font=font(14), fill=ORANGE, anchor="ls")
        else:
            d.text((x - 2, label_y + 31), "idle", font=font(28, "bold"), fill=MUTED, anchor="ls")

    def build_settings(self):
        w, form = panel(self)

        view = QComboBox()
        for k, label in VIEWS.items():
            view.addItem(label, k)
        view.setCurrentIndex(max(0, view.findData(self.cfg["view"])))
        view.currentIndexChanged.connect(lambda: self.set("view", view.currentData()))
        form.addRow("View:", view)

        rotate = QSpinBox()
        rotate.setRange(3, 600)
        rotate.setSuffix(" s")
        rotate.setValue(int(self.cfg["rotate_seconds"]))
        rotate.valueChanged.connect(lambda v: self.set("rotate_seconds", v))
        form.addRow("Rotate every:", rotate)

        limits_on = QCheckBox("Show plan limits (5-hour and weekly)")
        limits_on.setToolTip("Uses your Claude Code login, the same way Claude Code's /usage screen does.\n"
                             "The login is only sent to Anthropic and is never stored or changed.")
        limits_on.setChecked(bool(self.cfg["limits"]))

        def toggle_limits(v):
            self.set("limits", v)
            self.limits.enabled = v
            self.limits.refresh_now()

        limits_on.toggled.connect(toggle_limits)
        form.addRow("", limits_on)
        lim_row = QHBoxLayout()
        lim_status = QLabel("…")
        lim_status.setWordWrap(True)
        lim_refresh = QPushButton("Refresh now")
        lim_refresh.clicked.connect(self.limits.refresh_now)
        lim_row.addWidget(lim_status, 1)
        lim_row.addWidget(lim_refresh)
        form.addRow("Limits:", lim_row)

        roots = self.watcher.store.roots
        path = QLabel("<br>".join(str(r) for r in roots) or "No Claude Code data folder found")
        path.setWordWrap(True)
        form.addRow("Data folder:", path)
        count = QLabel("…")
        form.addRow("Messages loaded:", count)

        def refresh():
            s = self.watcher.stats
            count.setText(f"{len(self.watcher.store.entries):,}" if s.loaded else "Scanning…")
            if self.limits.limits:
                parts = [f"{l.label} {l.percent:.0f}%" for l in self.limits.limits]
                when = datetime.fromtimestamp(self.limits.updated).strftime("%H:%M")
                lim_status.setText(f"Connected · {' · '.join(parts)} (updated {when})")
            else:
                lim_status.setText(self.limits.status)

        timer = QTimer(w)
        timer.timeout.connect(refresh)
        timer.start(1000)
        refresh()
        return w
