import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from PyQt5.QtWidgets import QWidget, QLabel, QFrame
from PyQt5.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QBrush, QLinearGradient, QPainterPath
import config
from gui.palette import (ACCENT, PRIMARY, WHITE, TEXT_MUTED, TEXT_DARK, TEXT_MID, CARD_STYLE)


# ── Toggle Switch ─────────────────────────────────────────────────────────────
class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(72, 40)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self):
        return self._checked

    def setChecked(self, val):
        if self._checked != val:
            self._checked = val
            self.update()

    def mousePressEvent(self, e):
        self._checked = not self._checked
        self.toggled.emit(self._checked)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        track = QColor(ACCENT) if self._checked else QColor("#CBD5E0")
        p.setBrush(QBrush(track))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, h // 2, h // 2)
        m = 4
        tx = w - h + m if self._checked else m
        p.setBrush(QBrush(QColor(WHITE)))
        p.drawEllipse(tx, m, h - 2 * m, h - 2 * m)


# ── Line Chart ────────────────────────────────────────────────────────────────
class LineChart(QWidget):
    def __init__(self, data_fn, color=ACCENT, lo=None, hi=None, time_axis=False,
                 target_lo=None, target_hi=None, parent=None):
        super().__init__(parent)
        self.data_fn = data_fn
        self.color = color
        self.lo = lo
        self.hi = hi
        self.time_axis = time_axis
        self.target_lo = target_lo
        self.target_hi = target_hi
        self.setMinimumHeight(180 if time_axis else 160)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        data = self.data_fn()
        w, h = self.width(), self.height()
        pad = 12
        axis_h = 22 if self.time_axis else 0
        pad_bot = pad + axis_h
        WINDOW = 10800  # fixed 3-hour x range in seconds
        chart_w = w - 2 * pad
        chart_h = h - pad - pad_bot
        n = len(data)

        if self.time_axis:
            now_ts = datetime.now().timestamp()
            mark_ts = (int(now_ts) // 1800) * 1800
            font = QFont(); font.setPixelSize(11)
            p.setFont(font)
            p.setPen(QColor(TEXT_MUTED))
            while True:
                secs_ago = now_ts - mark_ts
                if secs_ago > WINDOW:
                    break
                lx = int(pad + (1.0 - secs_ago / WINDOW) * chart_w)
                p.drawText(lx - 20, h - axis_h + 4, 40, 16, Qt.AlignCenter,
                           datetime.fromtimestamp(mark_ts).strftime("%H:%M"))
                mark_ts -= 1800

        if n < 2:
            p.setPen(QColor(TEXT_MUTED))
            p.drawText(QRectF(pad, pad, chart_w, chart_h), Qt.AlignCenter, "Waiting for data...")
            return

        if self.lo is not None and self.hi is not None:
            lo, hi = self.lo, self.hi
        else:
            lo = self.lo if self.lo is not None else min(data) - 1
            hi = self.hi if self.hi is not None else max(data) + 1
        rng = hi - lo if hi != lo else 1

        def pt(i, v):
            age_s = (n - 1 - i) * config.SENSOR_INTERVAL
            x = pad + (1.0 - age_s / WINDOW) * chart_w
            y = h - pad_bot - ((v - lo) / rng) * chart_h
            return QPointF(x, y)

        p0 = pt(0, data[0])
        path = QPainterPath()
        path.moveTo(p0)
        for i in range(1, n):
            path.lineTo(pt(i, data[i]))
        last = pt(n - 1, data[-1])
        path.lineTo(QPointF(last.x(), h - pad_bot))
        path.lineTo(QPointF(p0.x(), h - pad_bot))
        path.closeSubpath()
        grad = QLinearGradient(0, 0, 0, h - axis_h)
        c1 = QColor(self.color); c1.setAlpha(55)
        c2 = QColor(self.color); c2.setAlpha(5)
        grad.setColorAt(0, c1); grad.setColorAt(1, c2)
        p.fillPath(path, QBrush(grad))

        if self.target_lo is not None and self.target_hi is not None:
            band_pen = QPen(QColor(220, 50, 50, 150), 1, Qt.DashLine)
            lbl_font = QFont(); lbl_font.setPixelSize(11)
            for val in (self.target_lo, self.target_hi):
                vy = h - pad_bot - ((val - lo) / rng) * chart_h
                p.setPen(band_pen)
                p.drawLine(QPointF(pad, vy), QPointF(pad + chart_w, vy))
                p.setFont(lbl_font)
                p.setPen(QColor(220, 50, 50, 200))
                p.drawText(pad + 2, int(vy) - 13, 40, 13, Qt.AlignLeft, str(val))

        p.setPen(QPen(QColor(self.color), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for i in range(n - 1):
            p.drawLine(pt(i, data[i]), pt(i + 1, data[i + 1]))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self.color)))
        p.drawEllipse(last, 7, 7)
        p.setBrush(QBrush(QColor(WHITE)))
        p.drawEllipse(last, 4, 4)


# ── Range Slider ──────────────────────────────────────────────────────────────
class RangeSlider(QWidget):
    range_changed = pyqtSignal(float, float)

    def __init__(self, mn, mx, lo, hi, parent=None):
        super().__init__(parent)
        self._lo, self._hi = lo, hi
        self._min, self._max = mn, mx
        self._r = 11
        self._dragging = None
        self.setFixedHeight(44)
        self.setMouseTracking(True)

    def _to_x(self, v):
        pad = self._r + 4
        return pad + (v - self._lo) / (self._hi - self._lo) * (self.width() - 2 * pad)

    def _to_val(self, x):
        pad = self._r + 4
        v = self._lo + (x - pad) / (self.width() - 2 * pad) * (self._hi - self._lo)
        return max(self._lo, min(self._hi, round(v, 1)))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cy = h // 2
        pad = self._r + 4
        p.setBrush(QBrush(QColor("#E8EDF2")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(pad, cy - 3, w - 2 * pad, 6, 3, 3)
        x1, x2 = self._to_x(self._min), self._to_x(self._max)
        p.setBrush(QBrush(QColor(ACCENT)))
        p.drawRoundedRect(int(x1), cy - 3, int(x2 - x1), 6, 3, 3)
        for x in (x1, x2):
            p.setBrush(QBrush(QColor(PRIMARY)))
            p.setPen(QPen(QColor(WHITE), 2.5))
            p.drawEllipse(QPointF(x, cy), self._r, self._r)

    def mousePressEvent(self, e):
        x1, x2 = self._to_x(self._min), self._to_x(self._max)
        self._dragging = "min" if abs(e.x() - x1) <= abs(e.x() - x2) else "max"
        self._move(e.x())

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._move(e.x())
        else:
            x1, x2 = self._to_x(self._min), self._to_x(self._max)
            near = abs(e.x() - x1) < self._r + 6 or abs(e.x() - x2) < self._r + 6
            self.setCursor(Qt.PointingHandCursor if near else Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        self._dragging = None

    def _move(self, x):
        v = self._to_val(x)
        if self._dragging == "min":
            self._min = min(v, round(self._max - 0.1, 1))
        else:
            self._max = max(v, round(self._min + 0.1, 1))
        self.range_changed.emit(self._min, self._max)
        self.update()

    def set_bounds(self, lo, hi):
        self._lo, self._hi = lo, hi
        self._min = max(lo, min(self._min, round(hi - 0.1, 1)))
        self._max = min(hi, max(self._max, round(lo + 0.1, 1)))
        self.update()

    def set_values(self, mn, mx):
        self._min = max(self._lo, min(round(mn, 1), round(self._hi - 0.1, 1)))
        self._max = min(self._hi, max(round(mx, 1), round(self._lo + 0.1, 1)))
        self.update()


# ── Shared UI helpers ─────────────────────────────────────────────────────────
def hdivider():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("background: #E8EDF2; border: none; max-height: 1px;")
    return f

def section_lbl(text):
    l = QLabel(text)
    l.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 16px; font-weight: 600; letter-spacing: 1px;")
    return l

def badge(text, color):
    l = QLabel(text)
    l.setStyleSheet(f"background:{color}; color:white; font-size:14px; font-weight:700;"
                    f"border-radius:10px; padding:4px 12px;")
    l.setAlignment(Qt.AlignCenter)
    return l

def make_txt(text, color, size, bold=False):
    l = QLabel(text)
    w = "700" if bold else "400"
    l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{w};")
    return l
