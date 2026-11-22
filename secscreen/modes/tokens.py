"""Claude Code token monitor with animated Claude spark."""
import time
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel

from ..draw import (BG, BLUE, GREEN, MUTED, ORANGE, PANEL, PURPLE, TEXT, W, H, bar, canvas,
                    fmt_span, fmt_tokens, spark)
from ..fonts import font
from ..usage import UsageWatcher
from .base import Mode, panel

ICON_BOX = (16, 8, 144)  # x, y, size
ICON_BOX_PORTRAIT = (12, 12, 120)


class TokensMode(Mode):
    id = "tokens"
    name = "Claude Tokens"
    icon = "✳"
    description = ("Live Claude Code token usage read from your local transcripts. "
                   "The spark ripples while Claude is working.")

    def __init__(self, settings):
        super().__init__(settings)
        self.watcher = UsageWatcher()
        self._static = None
        self._sig = None

    def activate(self):
        self.watcher.start()

    def fps(self):
        return 60.0 if self.watcher.stats.active(time.time()) else 30.0

    def _signature(self, s, now):
        return (s.loaded, s.today, s.t_msgs, s.block_tokens, int(s.burn_per_min), s.model, tuple(s.days),
                datetime.fromtimestamp(now).strftime("%H:%M"), s.active(now),
                int((now - s.last_time) // 60), int((s.block_end - now) // 60))

    def render(self, now):
        s = self.watcher.stats
        sig = (self.size,) + self._signature(s, now)
        if sig != self._sig or self._static is None:
            self._static = self._draw_portrait(s, now) if self.portrait else self._draw_static(s, now)
            self._sig = sig
        img = self._static.copy()
        x, y, size = ICON_BOX_PORTRAIT if self.portrait else ICON_BOX
        img.paste(spark(size, now, s.active(now)), (x, y))
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
        d.text((12, 364), "5H WINDOW", font=font(14, "semibold"), fill=MUTED, anchor="ls")
        d.text((172, 364), "BURN / MIN", font=font(14, "semibold"), fill=MUTED, anchor="ls")
        if s.block_active:
            left = s.block_end - now
            d.text((10, 395), fmt_tokens(s.block_tokens), font=font(28, "bold"), fill=TEXT, anchor="ls")
            frac = max(0.0, min(1.0, 1 - left / (5 * 3600)))
            bar(d, 12, 403, 84, 7, PANEL)
            bar(d, 12, 403, max(7, 84 * frac), 7, ORANGE)
            d.text((102, 411), fmt_span(left), font=font(14), fill=ORANGE, anchor="ls")
        else:
            d.text((10, 395), "idle", font=font(28, "bold"), fill=MUTED, anchor="ls")
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
        d.text((X, 212), "5H WINDOW", font=font(14, "semibold"), fill=MUTED, anchor="ls")
        d.text((BX, 212), "BURN / MIN", font=font(14, "semibold"), fill=MUTED, anchor="ls")
        if s.block_active:
            left = s.block_end - now
            d.text((X - 2, 243), fmt_tokens(s.block_tokens), font=font(28, "bold"), fill=TEXT, anchor="ls")
            frac = max(0.0, min(1.0, 1 - left / (5 * 3600)))
            bar(d, X, 251, 84, 7, PANEL)
            bar(d, X, 251, max(7, 84 * frac), 7, ORANGE)
            d.text((X + 90, 259), fmt_span(left), font=font(14), fill=ORANGE, anchor="ls")
        else:
            d.text((X - 2, 243), "idle", font=font(28, "bold"), fill=MUTED, anchor="ls")
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

    def build_settings(self):
        w, form = panel(self)
        roots = self.watcher.store.roots
        path = QLabel("<br>".join(str(r) for r in roots) or "No Claude Code data folder found")
        path.setWordWrap(True)
        form.addRow("Data folder:", path)
        count = QLabel("…")
        form.addRow("Messages loaded:", count)

        def refresh():
            s = self.watcher.stats
            count.setText(f"{len(self.watcher.store.entries):,}" if s.loaded else "Scanning…")

        timer = QTimer(w)
        timer.timeout.connect(refresh)
        timer.start(1000)
        refresh()
        return w
