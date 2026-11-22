"""Tasks mode: a to-do list in the style of Apple Reminders."""
import time

from PIL import Image, ImageDraw
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton)

from ..fonts import font
from .base import Mode, panel

ACCENTS = {
    "blue": (10, 132, 255), "orange": (255, 159, 10), "red": (255, 69, 58),
    "green": (48, 209, 88), "purple": (191, 90, 242), "pink": (255, 55, 95),
}
THEMES = {
    "dark": dict(bg=(28, 28, 30), text=(255, 255, 255), muted=(142, 142, 147), sep=(56, 56, 58),
                 ring=(99, 99, 102)),
    "light": dict(bg=(255, 255, 255), text=(0, 0, 0), muted=(142, 142, 147), sep=(229, 229, 234),
                  ring=(199, 199, 204)),
}
SS = 2  # supersampling for smooth circles


def _ellipsize(text, f, width):
    if f.getlength(text) <= width:
        return text
    while text and f.getlength(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


class TasksMode(Mode):
    id = "tasks"
    name = "Tasks"
    icon = "✅"
    description = "A to-do list in the style of Apple Reminders. Add tasks below and tick them off when done."
    DEFAULTS = {"title": "Today", "tasks": [], "accent": "blue", "theme": "dark", "show_done": True}

    def __init__(self, settings):
        super().__init__(settings)
        self._key = None
        self._img = None

    def fps(self):
        return 2.0

    # ------------------------------------------------------------ data (GUI thread)
    def _save_tasks(self, tasks):
        self.set("tasks", tasks)

    def add(self, text):
        text = text.strip()
        if text:
            self._save_tasks(list(self.cfg["tasks"]) + [{"id": time.time_ns(), "text": text, "done": False}])

    # ------------------------------------------------------------ render
    def render(self, now):
        c = self.cfg
        key = (repr(c["tasks"]), c["title"], c["accent"], c["theme"], c["show_done"], self.size)
        if key == self._key:
            return self._img
        t = THEMES.get(c["theme"], THEMES["dark"])
        accent = ACCENTS.get(c["accent"], ACCENTS["blue"])
        w, h = self.size
        S = SS
        img = Image.new("RGB", (w * S, h * S), t["bg"])
        d = ImageDraw.Draw(img)
        m = 20

        tasks = list(c["tasks"])
        todo = [x for x in tasks if not x.get("done")]
        done = [x for x in tasks if x.get("done")]
        shown = todo + (done if c["show_done"] else [])

        # header: big colored title + count
        d.text((m * S, 48 * S), _ellipsize(c["title"] or "Tasks", font(32 * S, "bold"), (w - 150) * S),
               font=font(32 * S, "bold"), fill=accent, anchor="ls")
        count = str(len(todo))
        d.text(((w - m) * S, 48 * S), count, font=font(32 * S, "bold"), fill=t["text"], anchor="rs")
        if tasks:
            sub = f"{len(done)} of {len(tasks)} done"
            d.text(((w - m) * S, 70 * S), sub, font=font(14 * S), fill=t["muted"], anchor="rs")
            # thin progress line under the title
            frac = len(done) / len(tasks)
            d.rounded_rectangle((m * S, 62 * S, (m + 140) * S, 66 * S), radius=2 * S, fill=t["sep"])
            if frac:
                d.rounded_rectangle((m * S, 62 * S, (m + max(4, 140 * frac)) * S, 66 * S), radius=2 * S,
                                    fill=accent)

        top, row_h = 84, (40 if self.portrait else 37)
        max_rows = max(1, (h - top - 6) // row_h)
        if not shown:
            msg = "All done" if tasks else "No tasks"
            d.text((w / 2 * S, (h / 2 + 10) * S), msg, font=font(24 * S, "semibold"), fill=t["muted"], anchor="ms")
            d.text((w / 2 * S, (h / 2 + 36) * S), "Add tasks in the app" if not tasks else "Nice work!",
                   font=font(15 * S), fill=t["muted"], anchor="ms")
        overflow = len(shown) - max_rows
        rows = shown[:max_rows - 1] + [None] if overflow > 0 else shown
        f = font(19 * S)
        r = 11
        for i, task in enumerate(rows):
            y0 = top + i * row_h
            cy = y0 + row_h / 2
            cx = m + r
            if task is None:
                d.text(((m + 2 * r + 14) * S, (cy + 6) * S), f"+{overflow + 1} more", font=font(17 * S),
                       fill=t["muted"], anchor="ls")
                break
            if task.get("done"):
                d.ellipse(((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S), fill=accent)
                d.line([((cx - 5) * S, cy * S), ((cx - 1.5) * S, (cy + 4) * S), ((cx + 5.5) * S, (cy - 4.5) * S)],
                       fill=(255, 255, 255), width=int(2.4 * S), joint="curve")
                color = t["muted"]
            else:
                d.ellipse(((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S), outline=t["ring"],
                          width=int(2 * S))
                color = t["text"]
            tx = m + 2 * r + 14
            d.text((tx * S, (cy + 7) * S), _ellipsize(task["text"], f, (w - tx - m) * S), font=f, fill=color,
                   anchor="ls")
            if i < len(rows) - 1:
                d.line((tx * S, (y0 + row_h) * S, (w - m) * S, (y0 + row_h) * S), fill=t["sep"], width=S)
        self._img = img.resize((w, h), Image.LANCZOS)
        self._key = key
        return self._img

    # ------------------------------------------------------------ settings
    def build_settings(self):
        w, form = panel(self)

        title = QLineEdit(self.cfg["title"])
        title.setPlaceholderText("List title")
        title.textChanged.connect(lambda v: self.set("title", v))
        form.addRow("Title:", title)

        add_row = QHBoxLayout()
        entry = QLineEdit()
        entry.setPlaceholderText("New task… (press Enter)")
        add_btn = QPushButton("Add")
        add_row.addWidget(entry, 1)
        add_row.addWidget(add_btn)
        form.addRow(add_row)

        lw = QListWidget()
        lw.setMinimumHeight(150)
        lw.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        lw.setToolTip("Tick to mark done · double-click to edit · drag to reorder")
        form.addRow(lw)

        def fill():
            lw.blockSignals(True)
            lw.clear()
            for task in self.cfg["tasks"]:
                item = QListWidgetItem(task["text"])
                item.setData(Qt.ItemDataRole.UserRole, task["id"])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
                item.setCheckState(Qt.CheckState.Checked if task.get("done") else Qt.CheckState.Unchecked)
                f = item.font()
                f.setStrikeOut(bool(task.get("done")))
                item.setFont(f)
                lw.addItem(item)
            lw.blockSignals(False)

        def sync_from_list(*_):
            """Read order, text and done state back from the list widget."""
            tasks = []
            for i in range(lw.count()):
                item = lw.item(i)
                text = item.text().strip()
                if text:
                    tasks.append({"id": item.data(Qt.ItemDataRole.UserRole), "text": text,
                                  "done": item.checkState() == Qt.CheckState.Checked})
            self._save_tasks(tasks)
            fill()

        def on_add():
            self.add(entry.text())
            entry.clear()
            fill()

        entry.returnPressed.connect(on_add)
        add_btn.clicked.connect(on_add)
        lw.itemChanged.connect(sync_from_list)
        lw.model().rowsMoved.connect(sync_from_list)

        actions = QHBoxLayout()
        delete = QPushButton("Delete selected")
        clear_done = QPushButton("Clear completed")
        actions.addWidget(delete)
        actions.addWidget(clear_done)
        form.addRow(actions)

        def on_delete():
            for item in lw.selectedItems():
                lw.takeItem(lw.row(item))
            sync_from_list()

        def on_clear_done():
            self._save_tasks([x for x in self.cfg["tasks"] if not x.get("done")])
            fill()

        delete.clicked.connect(on_delete)
        clear_done.clicked.connect(on_clear_done)

        accent = QComboBox()
        for k in ACCENTS:
            accent.addItem(k.capitalize(), k)
        accent.setCurrentIndex(max(0, accent.findData(self.cfg["accent"])))
        accent.currentIndexChanged.connect(lambda: self.set("accent", accent.currentData()))
        form.addRow("Color:", accent)

        theme = QComboBox()
        theme.addItem("Dark", "dark")
        theme.addItem("Light", "light")
        theme.setCurrentIndex(max(0, theme.findData(self.cfg["theme"])))
        theme.currentIndexChanged.connect(lambda: self.set("theme", theme.currentData()))
        form.addRow("Theme:", theme)

        show_done = QCheckBox("Show completed tasks")
        show_done.setChecked(bool(self.cfg["show_done"]))
        show_done.toggled.connect(lambda v: self.set("show_done", v))
        form.addRow("", show_done)

        fill()
        return w
