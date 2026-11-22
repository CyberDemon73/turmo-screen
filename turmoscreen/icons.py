"""Line icons drawn with QPainter, so they look the same on every platform (no emoji fonts needed).

Each icon is drawn on a 24x24 grid with round strokes, in the style of SF Symbols / Lucide.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication

STROKE = 1.8


def _p(x, y):
    return QPointF(x, y)


def _tokens(p):
    lengths = [9.5, 7.0, 8.8, 6.4, 9.2, 7.4, 8.6, 6.8]
    for i, length in enumerate(lengths):
        a = math.radians(i * 45 - 90)
        p.drawLine(_p(12 + math.cos(a) * 2.6, 12 + math.sin(a) * 2.6),
                   _p(12 + math.cos(a) * length, 12 + math.sin(a) * length))


def _clock(p):
    p.drawEllipse(_p(12, 12), 9, 9)
    p.drawLine(_p(12, 12), _p(12, 7))
    p.drawLine(_p(12, 12), _p(15.5, 14))


def _tasks(p):
    p.drawEllipse(_p(12, 12), 9, 9)
    path = QPainterPath(_p(8, 12.4))
    path.lineTo(11, 15.2)
    path.lineTo(16.4, 9.4)
    p.drawPath(path)


def _photo(p):
    p.drawRoundedRect(QRectF(3, 5, 18, 14), 2.5, 2.5)
    path = QPainterPath(_p(4, 17.5))
    path.lineTo(9.5, 11.5)
    path.lineTo(13.5, 15.5)
    path.lineTo(16, 13)
    path.lineTo(20, 17)
    p.drawPath(path)
    p.drawEllipse(_p(15.5, 9), 1.4, 1.4)


def _gif(p):
    p.drawRoundedRect(QRectF(3, 5, 18, 14), 2.5, 2.5)
    for x in (7, 17):
        p.drawLine(_p(x, 5), _p(x, 19))
    tri = QPolygonF([_p(10.6, 9.4), _p(10.6, 14.6), _p(14.6, 12)])
    p.save()
    p.setBrush(p.pen().color())
    p.drawPolygon(tri)
    p.restore()


def _timer(p):
    p.drawLine(_p(6.5, 3.5), _p(17.5, 3.5))
    p.drawLine(_p(6.5, 20.5), _p(17.5, 20.5))
    path = QPainterPath(_p(8, 3.5))
    path.cubicTo(8, 8.5, 12, 9.5, 12, 12)
    path.cubicTo(12, 14.5, 8, 15.5, 8, 20.5)
    path.moveTo(16, 3.5)
    path.cubicTo(16, 8.5, 12, 9.5, 12, 12)
    path.cubicTo(12, 14.5, 16, 15.5, 16, 20.5)
    p.drawPath(path)


def _stopwatch(p):
    p.drawEllipse(_p(12, 13.5), 7.5, 7.5)
    p.drawLine(_p(10, 2.8), _p(14, 2.8))
    p.drawLine(_p(12, 2.8), _p(12, 6))
    p.drawLine(_p(12, 13.5), _p(12, 9.5))
    p.drawLine(_p(18.2, 6.8), _p(19.6, 5.4))


def _system(p):
    p.drawRoundedRect(QRectF(3, 4, 18, 13), 2, 2)
    p.drawLine(_p(9, 20.5), _p(15, 20.5))
    path = QPainterPath(_p(6, 12.5))
    path.lineTo(9, 12.5)
    path.lineTo(10.8, 8.5)
    path.lineTo(13.4, 14)
    path.lineTo(15, 10.5)
    path.lineTo(18, 10.5)
    p.drawPath(path)


def _message(p):
    path = QPainterPath()
    path.addRoundedRect(QRectF(3, 4.5, 18, 12.5), 3.5, 3.5)
    p.drawPath(path)
    tail = QPainterPath(_p(8, 17))
    tail.lineTo(7.5, 20.8)
    tail.lineTo(12, 17)
    p.drawPath(tail)


def _screen(p):
    for y, knob in ((6.5, 9), (12, 15.5), (17.5, 7.5)):
        p.drawLine(_p(3.5, y), _p(20.5, y))
        p.save()
        p.setBrush(p.pen().color())
        p.drawEllipse(_p(knob, y), 2.3, 2.3)
        p.restore()


def _refresh(p):
    p.drawArc(QRectF(4.5, 4.5, 15, 15), 60 * 16, 290 * 16)
    head = QPainterPath(_p(14.2, 2.8))
    head.lineTo(16.4, 5.6)
    head.lineTo(13.2, 7)
    p.drawPath(head)


def _sun(p):
    p.drawEllipse(_p(12, 12), 3.8, 3.8)
    for i in range(8):
        a = math.radians(i * 45)
        p.drawLine(_p(12 + math.cos(a) * 6.6, 12 + math.sin(a) * 6.6),
                   _p(12 + math.cos(a) * 8.8, 12 + math.sin(a) * 8.8))


DRAW = {
    "tokens": _tokens, "clock": _clock, "tasks": _tasks, "photo": _photo, "gif": _gif, "timer": _timer,
    "stopwatch": _stopwatch, "system": _system, "message": _message, "screen": _screen,
    "refresh": _refresh, "sun": _sun,
}


def _pixmap(name, color, size, dpr):
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24, size / 24)
    pen = QPen(QColor(color), STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    DRAW[name](p)
    p.end()
    return pm


def icon(name, size=20, color=None, selected_color="#FFFFFF"):
    """QIcon for `name`; uses the palette's text color unless one is given, white when selected."""
    if color is None:
        app = QApplication.instance()
        color = app.palette().text().color().name() if app else "#DDDDDD"
    dpr = 2.0
    ic = QIcon()
    ic.addPixmap(_pixmap(name, color, size, dpr), QIcon.Mode.Normal)
    ic.addPixmap(_pixmap(name, selected_color, size, dpr), QIcon.Mode.Selected)
    ic.addPixmap(_pixmap(name, selected_color, size, dpr), QIcon.Mode.Active)
    return ic
