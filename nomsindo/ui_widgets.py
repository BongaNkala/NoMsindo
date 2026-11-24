"""Custom-painted widgets for the NoMsindo interface."""
from __future__ import annotations

import math
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)
from PySide6.QtWidgets import QFrame, QWidget

MINT, CYAN, VIOLET, AMBER, RED = "#2af5b5", "#22d3ee", "#7c5cff", "#ffb020", "#ff5d5d"
TEXT, MUTED, DIM = "#e6f4f1", "#7aa09c", "#3d5b58"


def rgba(hex_: str, a: float) -> QColor:
    c = QColor(hex_); c.setAlphaF(max(0.0, min(1.0, a))); return c


class Backdrop(QWidget):
    """Deep gradient with soft coloured glows behind everything."""

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, w, h); g.setColorAt(0, QColor("#05090c")); g.setColorAt(1, QColor("#0a191c"))
        p.fillRect(self.rect(), g)
        for cx, cy, r, col, a in ((w * 0.92, -h * 0.05, w * 0.75, CYAN, 0.16), (w * 0.02, h * 1.02, w * 0.65, VIOLET, 0.15),
                                  (w * 0.55, h * 0.35, w * 0.55, MINT, 0.05)):
            rg = QRadialGradient(cx, cy, r); rg.setColorAt(0, rgba(col, a)); rg.setColorAt(1, rgba(col, 0))
            p.fillRect(self.rect(), rg)


class GlassPanel(QFrame):
    """Rounded frosted-glass card; glows mint when `glow` is on."""

    def __init__(self, radius: int = 16):
        super().__init__()
        self.radius, self._glow = radius, False

    def set_glow(self, on: bool) -> None:
        if on != self._glow:
            self._glow = on; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self._glow:
            for i, a in enumerate((0.10, 0.06, 0.03)):
                p.setPen(QPen(rgba(MINT, a), 3 + i * 3)); p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r, self.radius, self.radius)
        fill = QLinearGradient(0, r.top(), 0, r.bottom())
        fill.setColorAt(0, QColor(26, 48, 54, 232)); fill.setColorAt(1, QColor(10, 22, 25, 238))
        edge = QLinearGradient(0, r.top(), 0, r.bottom())
        edge.setColorAt(0, rgba(MINT if self._glow else "#8fffe8", 0.42 if self._glow else 0.22))
        edge.setColorAt(1, rgba("#3c8c8c", 0.16))
        p.setBrush(fill); p.setPen(QPen(QBrush(edge), 1)); p.drawRoundedRect(r, self.radius, self.radius)
        p.setPen(QPen(rgba("#ffffff", 0.07), 1))                    # top inner highlight
        p.drawLine(QPointF(r.left() + self.radius, r.top() + 1.5), QPointF(r.right() - self.radius, r.top() + 1.5))


class Waveform(QWidget):
    """Raw input flows in from the left; the cleaned signal flows out to the right of the playhead."""
    N = 150

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(96)
        self.inp = deque([0.0] * 400, maxlen=400)
        self.out = deque([0.0] * 400, maxlen=400)
        self.idle = True

    def push(self, a: float, b: float) -> None:
        self.inp.append(a); self.out.append(b); self.update()

    @staticmethod
    def _h(v: float) -> float:
        return min(1.0, (v ** 0.55) * 1.1)

    def _series(self, data, n):
        vals = [self._h(data[-1 - i]) for i in range(n)]
        sm = [(vals[max(0, i - 1)] + 2 * vals[i] + vals[min(n - 1, i + 1)]) / 4 for i in range(n)]
        return sm

    def _path(self, vals, x0, step, cy, amp):
        top = [QPointF(x0 + step * i, cy - max(1.2, v * amp)) for i, v in enumerate(vals)]
        bot = [QPointF(pt.x(), 2 * cy - pt.y()) for pt in top]
        path = QPainterPath(top[0])
        for a, b in zip(top, top[1:]):
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2); path.quadTo(a, mid)
        path.lineTo(top[-1]); path.lineTo(bot[-1])
        for a, b in zip(reversed(bot), list(reversed(bot))[1:]):
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2); path.quadTo(a, mid)
        path.closeSubpath()
        return path

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height(); cy = h / 2; amp = cy - 10
        bg = QLinearGradient(0, 0, 0, h); bg.setColorAt(0, QColor("#050b0d")); bg.setColorAt(1, QColor("#08161a"))
        p.setBrush(bg); p.setPen(QPen(rgba("#8fffe8", 0.14), 1)); p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)
        p.setClipRect(QRectF(1, 1, w - 2, h - 2))
        p.setPen(QPen(rgba("#ffffff", 0.035), 1))                     # faint grid
        for gx in range(0, w, 36):
            p.drawLine(gx, 0, gx, h)
        p.drawLine(0, int(cy), w, int(cy))
        ph = w * 0.56; ll = int(ph / (w / self.N)); rr = int((w - ph) / (w / self.N)); step = w / self.N
        # raw (left of the playhead, older to the left)
        left = list(reversed(self._series(self.inp, max(2, ll))))
        lp = self._path(left, ph - step * (len(left) - 1), step, cy, amp)
        lg = QLinearGradient(0, 0, ph, 0); lg.setColorAt(0, rgba("#dfe8ff", 0)); lg.setColorAt(1, rgba("#e8eeff", 0.62))
        p.setBrush(lg); p.setPen(Qt.NoPen); p.drawPath(lp)
        p.setBrush(Qt.NoBrush); sg = QLinearGradient(0, 0, ph, 0); sg.setColorAt(0, rgba("#ffffff", 0)); sg.setColorAt(1, rgba("#ffffff", 0.85))
        p.setPen(QPen(QBrush(sg), 1.1)); p.drawPath(lp)
        # cleaned (right of the playhead, older to the right)
        right = self._series(self.out, max(2, rr))
        rp = self._path(right, ph, step, cy, amp)
        gg = QLinearGradient(ph, 0, w, 0); gg.setColorAt(0, rgba(MINT, 0.85)); gg.setColorAt(0.5, rgba(CYAN, 0.45)); gg.setColorAt(1, rgba(VIOLET, 0.06))
        p.setPen(QPen(rgba(MINT, 0.10), 6)); p.setBrush(Qt.NoBrush); p.drawPath(rp)           # glow
        p.setBrush(gg); p.setPen(Qt.NoPen); p.drawPath(rp)
        eg = QLinearGradient(ph, 0, w, 0); eg.setColorAt(0, rgba("#d6fff4", 0.95)); eg.setColorAt(1, rgba(CYAN, 0.1))
        p.setBrush(Qt.NoBrush); p.setPen(QPen(QBrush(eg), 1.2)); p.drawPath(rp)
        # playhead
        pg = QLinearGradient(0, 0, 0, h); pg.setColorAt(0, rgba(MINT, 0)); pg.setColorAt(0.5, rgba("#bffff0", 0.95)); pg.setColorAt(1, rgba(MINT, 0))
        p.setPen(QPen(rgba(MINT, 0.18), 7)); p.drawLine(QPointF(ph, 0), QPointF(ph, h))
        p.setPen(QPen(QBrush(pg), 1.4)); p.drawLine(QPointF(ph, 0), QPointF(ph, h))
        p.setClipping(False)
        f = QFont(self.font()); f.setPixelSize(9); f.setBold(True); f.setLetterSpacing(QFont.AbsoluteSpacing, 1.6); p.setFont(f)
        p.setPen(rgba("#cfd9ee", 0.55)); p.drawText(QRectF(12, 7, 80, 12), Qt.AlignLeft, "RAW")
        p.setPen(rgba(MINT, 0.75)); p.drawText(QRectF(w - 92, 7, 80, 12), Qt.AlignRight, "CLEAN")
        if self.idle:
            p.setPen(rgba(TEXT, 0.55)); f.setBold(False); f.setPixelSize(11); f.setLetterSpacing(QFont.AbsoluteSpacing, 0); p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, "Press the power button to start cleaning")


class VuMeter(QWidget):
    SEG = 20
    TICKS = ((0, "0"), (-6, "-6"), (-12, "-12"), (-24, "-24"), (-40, "-40"), (-60, "-60"))

    def __init__(self):
        super().__init__()
        self.setFixedWidth(84); self.setMinimumHeight(120)
        self.lv_in = self.lv_out = 0.0; self.pk_in = self.pk_out = 0.0

    @staticmethod
    def _norm(db: float) -> float:
        return max(0.0, min(1.0, (db + 60.0) / 60.0))

    def set_levels(self, in_db: float, out_db: float) -> None:
        self.lv_in, self.lv_out = self._norm(in_db), self._norm(out_db)
        self.pk_in = max(self.lv_in, self.pk_in - 0.012); self.pk_out = max(self.lv_out, self.pk_out - 0.012)
        self.update()

    def _bar(self, p: QPainter, x: float, level: float, peak: float, top: float, h: float) -> None:
        gap = 2.0; sh = (h - gap * (self.SEG - 1)) / self.SEG
        for i in range(self.SEG):
            f = (i + 1) / self.SEG; y = top + h - (i + 1) * sh - i * gap
            col = MINT if f <= 0.62 else AMBER if f <= 0.84 else RED
            lit = level >= f - 0.5 / self.SEG
            if lit:
                p.setBrush(rgba(col, 0.16)); p.setPen(Qt.NoPen); p.drawRoundedRect(QRectF(x - 2, y - 1, 20, sh + 2), 3, 3)
            p.setBrush(rgba(col, 1.0) if lit else rgba("#a8d8d0", 0.07)); p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x, y, 16, sh), 2.5, 2.5)
        if peak > 0.04:
            i = min(self.SEG - 1, int(peak * self.SEG)); y = top + h - (i + 1) * sh - i * gap
            p.setBrush(rgba("#ffffff", 0.9)); p.drawRoundedRect(QRectF(x, y, 16, max(1.5, sh * 0.35)), 1, 1)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        top, h = 4.0, self.height() - 24.0
        self._bar(p, 0, self.lv_in, self.pk_in, top, h); self._bar(p, self.width() - 16, self.lv_out, self.pk_out, top, h)
        f = QFont(self.font()); f.setPixelSize(8); p.setFont(f); p.setPen(rgba(MUTED, 0.9))
        for db, t in self.TICKS:
            y = top + h * (1 - self._norm(db)); p.drawText(QRectF(18, y - 6, self.width() - 36, 12), Qt.AlignCenter, t)
        f.setPixelSize(9); f.setBold(True); f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2); p.setFont(f)
        p.setPen(rgba("#cfd9ee", 0.6)); p.drawText(QRectF(-4, self.height() - 16, 24, 12), Qt.AlignCenter, "IN")
        p.setPen(rgba(MINT, 0.8)); p.drawText(QRectF(self.width() - 30, self.height() - 16, 30, 12), Qt.AlignCenter, "OUT")


class GlowSlider(QWidget):
    valueChanged = Signal(int)

    def __init__(self, value: int = 85):
        super().__init__()
        self._v = int(value); self.setFixedHeight(54); self.setMinimumWidth(200)
        self.setFocusPolicy(Qt.StrongFocus); self.setCursor(Qt.PointingHandCursor); self._drag = False

    def value(self) -> int:
        return self._v

    def setValue(self, v: int) -> None:
        v = max(0, min(100, int(v)))
        if v != self._v:
            self._v = v; self.valueChanged.emit(v); self.update()

    PAD = 12

    def _x(self, v: float) -> float:
        return self.PAD + (self.width() - 2 * self.PAD) * v / 100.0

    def _from_x(self, x: float) -> int:
        return round(100 * (x - self.PAD) / max(1, self.width() - 2 * self.PAD))

    def mousePressEvent(self, e):
        self._drag = True; self.setValue(self._from_x(e.position().x()))

    def mouseMoveEvent(self, e):
        if self._drag:
            self.setValue(self._from_x(e.position().x()))

    def mouseReleaseEvent(self, e):
        self._drag = False

    def wheelEvent(self, e):
        self.setValue(self._v + (2 if e.angleDelta().y() > 0 else -2))

    def keyPressEvent(self, e):
        d = {Qt.Key_Left: -1, Qt.Key_Down: -1, Qt.Key_Right: 1, Qt.Key_Up: 1}.get(e.key())
        self.setValue(self._v + d) if d else super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        cy = 17.0; x = self._x(self._v)
        p.setPen(Qt.NoPen); p.setBrush(rgba("#a8d8d0", 0.10)); p.drawRoundedRect(QRectF(self.PAD, cy - 3.5, self.width() - 2 * self.PAD, 7), 3.5, 3.5)
        g = QLinearGradient(self.PAD, 0, self._x(100), 0); g.setColorAt(0, QColor(VIOLET)); g.setColorAt(0.55, QColor("#3b82f6")); g.setColorAt(1, QColor(MINT))
        p.setBrush(rgba(CYAN, 0.0)); p.setPen(QPen(rgba(CYAN, 0.12), 9, Qt.SolidLine, Qt.RoundCap)); p.drawLine(QPointF(self.PAD, cy), QPointF(x, cy))
        p.setPen(Qt.NoPen); p.setBrush(g); p.drawRoundedRect(QRectF(self.PAD, cy - 3.5, max(0.1, x - self.PAD), 7), 3.5, 3.5)
        f = QFont(self.font()); f.setPixelSize(9); p.setFont(f)
        for v in range(0, 101, 10):
            tx = self._x(v); on = v <= self._v
            p.setPen(QPen(rgba(MINT if on else DIM, 0.8 if on else 0.9), 1)); p.drawLine(QPointF(tx, 30), QPointF(tx, 34 if v % 50 else 37))
            p.setPen(rgba(TEXT if on else MUTED, 0.8 if on else 0.65)); p.drawText(QRectF(tx - 14, 38, 28, 12), Qt.AlignCenter, str(v))
        rg = QRadialGradient(x, cy, 16); rg.setColorAt(0, rgba(MINT, 0.5)); rg.setColorAt(1, rgba(MINT, 0))
        p.setPen(Qt.NoPen); p.setBrush(rg); p.drawEllipse(QPointF(x, cy), 16, 16)
        hg = QLinearGradient(0, cy - 9, 0, cy + 9); hg.setColorAt(0, QColor("#ffffff")); hg.setColorAt(1, QColor("#c9d8e6"))
        p.setBrush(hg); p.setPen(QPen(rgba("#7cf5d3", 0.9), 1.6)); p.drawEllipse(QPointF(x, cy), 8.5, 8.5)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush); p.setPen(QPen(rgba(MINT, 0.5), 1)); p.drawEllipse(QPointF(x, cy), 12, 12)


class Segmented(QWidget):
    changed = Signal(int)

    def __init__(self, items: list[str], index: int = 0):
        super().__init__()
        self.items, self._i = items, index
        self.setFixedHeight(34); self.setFixedWidth(190); self.setCursor(Qt.PointingHandCursor)

    def index(self) -> int:
        return self._i

    def setIndex(self, i: int) -> None:
        if i != self._i:
            self._i = i; self.changed.emit(i); self.update()

    def mousePressEvent(self, e):
        self.setIndex(min(len(self.items) - 1, int(e.position().x() / (self.width() / len(self.items)))))

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(rgba("#050b0d", 0.7)); p.setPen(QPen(rgba("#8fffe8", 0.18), 1)); p.drawRoundedRect(r, 17, 17)
        sw = r.width() / len(self.items)
        f = QFont(self.font()); f.setPixelSize(12); p.setFont(f)
        for k, t in enumerate(self.items):
            seg = QRectF(r.left() + k * sw + 3, r.top() + 3, sw - 6, r.height() - 6)
            if k == self._i:
                g = QLinearGradient(seg.topLeft(), seg.bottomLeft()); g.setColorAt(0, QColor(54, 130, 126, 230)); g.setColorAt(1, QColor(30, 84, 88, 230))
                p.setBrush(g); p.setPen(QPen(rgba(MINT, 0.45), 1)); p.drawRoundedRect(seg, 14, 14)
            p.setPen(rgba(TEXT, 1.0 if k == self._i else 0.55)); f.setBold(k == self._i); p.setFont(f); p.drawText(seg, Qt.AlignCenter, t)


class PowerButton(QWidget):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(76, 76); self.setCursor(Qt.PointingHandCursor)
        self._on, self._hover, self._t = False, False, 0.0
        self._timer = QTimer(self); self._timer.setInterval(40); self._timer.timeout.connect(self._tick)

    def setChecked(self, on: bool) -> None:
        self._on = on
        self._timer.start() if on else self._timer.stop()
        self.update()

    def isChecked(self) -> bool:
        return self._on

    def _tick(self) -> None:
        self._t = (self._t + 0.06) % (2 * math.pi); self.update()

    def enterEvent(self, e):
        self._hover = True; self.update()

    def leaveEvent(self, e):
        self._hover = False; self.update()

    def mouseReleaseEvent(self, e):
        if self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        if self._on:
            pulse = 0.5 + 0.5 * math.sin(self._t)
            rg = QRadialGradient(c, 38); rg.setColorAt(0.45, rgba(MINT, 0.30 + 0.18 * pulse)); rg.setColorAt(1, rgba(MINT, 0))
            p.setPen(Qt.NoPen); p.setBrush(rg); p.drawEllipse(c, 38, 38)
        g = QLinearGradient(c.x(), c.y() - 26, c.x(), c.y() + 26)
        if self._on:
            g.setColorAt(0, QColor("#38ffc0")); g.setColorAt(1, QColor("#0fb883"))
        else:
            g.setColorAt(0, QColor("#223a3d" if not self._hover else "#2b4a4e")); g.setColorAt(1, QColor("#142528"))
        p.setBrush(g); p.setPen(QPen(rgba(MINT if self._on else "#8fffe8", 0.7 if self._on else 0.25), 1.4)); p.drawEllipse(c, 25, 25)
        col = QColor("#032a1d") if self._on else QColor(MUTED if not self._hover else TEXT)
        p.setBrush(Qt.NoBrush); p.setPen(QPen(col, 3.0, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(c.x() - 10, c.y() - 9.5, 20, 20), 120 * 16, -300 * 16)
        p.drawLine(QPointF(c.x(), c.y() - 13), QPointF(c.x(), c.y() - 2))
