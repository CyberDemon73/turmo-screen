"""Message mode: show your own text, sized to fill the screen."""
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QComboBox, QPlainTextEdit

from ..draw import W, H
from ..fonts import font
from .base import Mode, panel

THEMES = {
    "dark": ((14, 14, 16), (245, 245, 247)),
    "claude": ((217, 119, 87), (255, 255, 255)),
    "light": ((242, 242, 247), (28, 28, 30)),
    "red": ((200, 30, 40), (255, 255, 255)),
    "green": ((30, 140, 70), (255, 255, 255)),
    "blue": ((10, 90, 200), (255, 255, 255)),
}


class MessageMode(Mode):
    id = "message"
    name = "Message"
    icon = "💬"
    description = "Show your own text, like “In a meeting” or “Do not disturb”."
    DEFAULTS = {"text": "Do not disturb", "theme": "red"}

    def __init__(self, settings):
        super().__init__(settings)
        self._key = None
        self._img = None

    def fps(self):
        return 2.0

    def render(self, now):
        key = (self.cfg["text"], self.cfg["theme"], self.size)
        if key != self._key:
            bg, fg = THEMES.get(self.cfg["theme"], THEMES["dark"])
            w, h = self.size
            img = Image.new("RGB", (w, h), bg)
            d = ImageDraw.Draw(img)
            text = self.cfg["text"].strip() or " "
            if self.portrait and "\n" not in text and len(text.split()) > 1:
                text = "\n".join(text.split())  # one word per line suits a tall screen
            size = 140
            while size > 12:
                f = font(size, "bold")
                l, t, r, b = d.multiline_textbbox((0, 0), text, font=f, spacing=size // 6, align="center")
                if r - l <= w - 32 and b - t <= h - 40:
                    break
                size -= 4
            d.multiline_text((w / 2, h / 2), text, font=font(size, "bold"), fill=fg, anchor="mm",
                             spacing=size // 6, align="center")
            self._img, self._key = img, key
        return self._img

    def build_settings(self):
        w, form = panel(self)
        text = QPlainTextEdit(self.cfg["text"])
        text.setMaximumHeight(90)
        text.textChanged.connect(lambda: self.set("text", text.toPlainText()))
        form.addRow("Text:", text)
        theme = QComboBox()
        for k in THEMES:
            theme.addItem(k.capitalize(), k)
        theme.setCurrentIndex(max(0, theme.findData(self.cfg["theme"])))
        theme.currentIndexChanged.connect(lambda: self.set("theme", theme.currentData()))
        form.addRow("Colors:", theme)
        return w
