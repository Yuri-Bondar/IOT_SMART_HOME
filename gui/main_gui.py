import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import paho.mqtt.client as mqtt
import json
import time
import threading
from datetime import datetime
import sqlite3
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QStackedWidget, QSlider,
    QDialog, QLineEdit, QTimeEdit
)
from PyQt5.QtCore import QTime
from PyQt5.QtCore import QTimer, Qt, QPointF, QRectF
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient, QPainterPath
)
import config

TOPIC_THRESHOLDS = config.TOPIC_PREFIX + "/config/thresholds"

# ── Palette ──────────────────────────────────────────────────────────────────
PRIMARY    = "#0D4F5C"
PRIMARY2   = "#1A7A8A"
ACCENT     = "#00C4CC"
BG         = "#F0F4F8"
WHITE      = "#FFFFFF"
TEXT_DARK  = "#1A2535"
TEXT_MID   = "#4A5568"
TEXT_MUTED = "#8B9BB4"
SUCCESS    = "#00C896"
WARNING    = "#FFB020"
DANGER     = "#FF4757"

# ── Shared state ─────────────────────────────────────────────────────────────
MAX_HISTORY = 4800
state = {
    "temperature": None,
    "ph": None,
    "light": "off",
    "last_feed": None,
    "last_update": None,
    "events": [],
    "temp_history": [],
    "ph_history": [],
    "system_status": "Waiting...",
}

_DEF_WARN_PCT = 10
temp_warn_pct = _DEF_WARN_PCT
ph_warn_pct   = _DEF_WARN_PCT

_AR_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'aquarium.db')
_AR_KEYS = ["temp_safe_min","temp_safe_max","temp_warn_min","temp_warn_max",
            "ph_safe_min","ph_safe_max","ph_warn_min","ph_warn_max",
            "temp_warn_pct","ph_warn_pct"]

def _ar_defaults():
    _ts = config.TEMP_MAX_NORMAL - config.TEMP_MIN_NORMAL
    _ps = config.PH_MAX_NORMAL   - config.PH_MIN_NORMAL
    return {
        "temp_safe_min": config.TEMP_MIN_NORMAL,
        "temp_safe_max": config.TEMP_MAX_NORMAL,
        "temp_warn_min": round(config.TEMP_MIN_NORMAL + _ts * _DEF_WARN_PCT / 100, 1),
        "temp_warn_max": round(config.TEMP_MAX_NORMAL - _ts * _DEF_WARN_PCT / 100, 1),
        "ph_safe_min":   config.PH_MIN_NORMAL,
        "ph_safe_max":   config.PH_MAX_NORMAL,
        "ph_warn_min":   round(config.PH_MIN_NORMAL + _ps * _DEF_WARN_PCT / 100, 1),
        "ph_warn_max":   round(config.PH_MAX_NORMAL - _ps * _DEF_WARN_PCT / 100, 1),
    }

def load_allowed_ranges():
    global temp_warn_pct, ph_warn_pct
    try:
        conn = sqlite3.connect(_AR_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM allowed_ranges")
        rows = {k: v for k, v in cur.fetchall()}
        conn.close()
        if all(k in rows for k in _AR_KEYS):
            temp_warn_pct = int(rows.get("temp_warn_pct", _DEF_WARN_PCT))
            ph_warn_pct   = int(rows.get("ph_warn_pct",   _DEF_WARN_PCT))
            return rows
    except Exception:
        pass
    return _ar_defaults()

def save_allowed_ranges():
    allowed_ranges["temp_warn_pct"] = temp_warn_pct
    allowed_ranges["ph_warn_pct"]   = ph_warn_pct
    try:
        conn = sqlite3.connect(_AR_DB_PATH)
        cur = conn.cursor()
        cur.executemany(
            "INSERT OR REPLACE INTO allowed_ranges (key, value) VALUES (?, ?)",
            [(k, allowed_ranges[k]) for k in _AR_KEYS]
        )
        conn.commit(); conn.close()
    except Exception:
        pass

allowed_ranges = load_allowed_ranges()

def add_event(level, message):
    now = datetime.now().strftime("%H:%M")
    state["events"].insert(0, (now, level, message))
    if len(state["events"]) > 50:
        state["events"] = state["events"][:50]
    recent = state["events"][:5]
    if any(e[1] == "ALARM" for e in recent):
        state["system_status"] = "Alert Active"
    elif any(e[1] == "WARNING" for e in recent):
        state["system_status"] = "Warning Active"
    else:
        state["system_status"] = "System Optimal"

# ── MQTT ──────────────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(config.TOPIC_TEMPERATURE)
        client.subscribe(config.TOPIC_PH)
        client.subscribe(config.TOPIC_LIGHT_STATUS)
        client.subscribe(config.TOPIC_FEEDING_STATUS)
        client.subscribe(config.TOPIC_ALERTS)
        add_event("INFO", "Connected to MQTT broker")
    else:
        add_event("WARNING", "Failed to connect to broker")

def on_disconnect(client, userdata, rc):
    add_event("WARNING", "Disconnected from broker")
    while True:
        try:
            client.reconnect()
            break
        except Exception:
            time.sleep(5)

def on_message(client, userdata, msg):
    topic = msg.topic
    try:
        data = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        return
    if topic == config.TOPIC_TEMPERATURE:
        v = data.get("value", 0)
        state["temperature"] = v
        state["last_update"] = datetime.now().strftime("%H:%M:%S")
        state["temp_history"].append(v)
        if len(state["temp_history"]) > MAX_HISTORY:
            state["temp_history"] = state["temp_history"][-MAX_HISTORY:]
    elif topic == config.TOPIC_PH:
        v = data.get("value", 0)
        state["ph"] = v
        state["last_update"] = datetime.now().strftime("%H:%M:%S")
        state["ph_history"].append(v)
        if len(state["ph_history"]) > MAX_HISTORY:
            state["ph_history"] = state["ph_history"][-MAX_HISTORY:]
    elif topic == config.TOPIC_LIGHT_STATUS:
        state["light"] = data.get("state", "off")
        source = data.get("source", "")
        label = "ON" if state["light"] == "on" else "OFF"
        src_label = f" ({source})" if source else ""
        add_event("INFO", f"Light turned {label}{src_label}")
    elif topic == config.TOPIC_FEEDING_STATUS:
        state["last_feed"] = datetime.now().strftime("%H:%M")
        add_event("SUCCESS", "Fish fed")
    elif topic == config.TOPIC_ALERTS:
        add_event(data.get("level", "WARNING"), data.get("message", "Alert"))

def start_mqtt_thread(client):
    def run():
        try:
            client.connect(config.BROKER_HOST, config.BROKER_PORT, 60)
            client.loop_forever()
        except Exception as e:
            add_event("WARNING", "MQTT error: " + str(e))
    threading.Thread(target=run, daemon=True).start()

def get_temp_color(v):
    if v is None:
        return TEXT_MUTED
    s_min = allowed_ranges["temp_safe_min"]; s_max = allowed_ranges["temp_safe_max"]
    w_min = allowed_ranges["temp_warn_min"]; w_max = allowed_ranges["temp_warn_max"]
    if v < s_min or v > s_max:
        return DANGER
    if v <= w_min or v >= w_max:
        return WARNING
    return SUCCESS

def get_ph_color(v):
    if v is None:
        return TEXT_MUTED
    s_min = allowed_ranges["ph_safe_min"]; s_max = allowed_ranges["ph_safe_max"]
    w_min = allowed_ranges["ph_warn_min"]; w_max = allowed_ranges["ph_warn_max"]
    if v < s_min or v > s_max:
        return DANGER
    if v <= w_min or v >= w_max:
        return WARNING
    return SUCCESS

# ── Toggle Switch ─────────────────────────────────────────────────────────────
from PyQt5.QtCore import pyqtSignal

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

        # time axis labels — always span the full 4h window, even with no data
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

        # safe range band — drawn behind the data line
        if self.target_lo is not None and self.target_hi is not None:
            band_pen = QPen(QColor(220, 50, 50, 150), 1, Qt.DashLine)
            lbl_font = QFont(); lbl_font.setPixelSize(10)
            for val in (self.target_lo, self.target_hi):
                vy = h - pad_bot - ((val - lo) / rng) * chart_h
                p.setPen(band_pen)
                p.drawLine(QPointF(pad, vy), QPointF(pad + chart_w, vy))
                p.setFont(lbl_font)
                p.setPen(QColor(TEXT_MUTED))
                p.drawText(pad + 2, int(vy) - 12, 36, 12, Qt.AlignLeft, str(val))

        p.setPen(QPen(QColor(self.color), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for i in range(n - 1):
            p.drawLine(pt(i, data[i]), pt(i + 1, data[i + 1]))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self.color)))
        p.drawEllipse(last, 7, 7)
        p.setBrush(QBrush(QColor(WHITE)))
        p.drawEllipse(last, 4, 4)

# ── Range Slider ─────────────────────────────────────────────────────────────
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

        # track background
        p.setBrush(QBrush(QColor("#E8EDF2")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(pad, cy - 3, w - 2 * pad, 6, 3, 3)

        # active zone
        x1, x2 = self._to_x(self._min), self._to_x(self._max)
        p.setBrush(QBrush(QColor(ACCENT)))
        p.drawRoundedRect(int(x1), cy - 3, int(x2 - x1), 6, 3, 3)

        # handles
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

# ── Helpers ───────────────────────────────────────────────────────────────────
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

CARD_STYLE = f"background:{WHITE}; border-radius:20px;"

# ── Dashboard ─────────────────────────────────────────────────────────────────
class DashboardPage(QScrollArea):
    def __init__(self, mqtt_client, parent=None):
        super().__init__(parent)
        self.mqtt_client = mqtt_client
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background:{BG};")
        w = QWidget(); w.setStyleSheet(f"background:{BG};")
        self.setWidget(w)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 18, 24, 24)
        lay.setSpacing(18)

        # Hero
        hero = QFrame()
        hero.setFixedHeight(260)
        hero.setStyleSheet(f"QFrame{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                           f"stop:0 {PRIMARY},stop:1 {PRIMARY2});border-radius:24px;}}")
        hl = QVBoxLayout(hero); hl.setContentsMargins(28,28,28,28)
        hl.addStretch()
        sub = QLabel("LIVE STATUS")
        sub.setStyleSheet("color:rgba(255,255,255,0.7);font-size:16px;font-weight:600;"
                          "letter-spacing:2px;background:transparent;")
        hl.addWidget(sub)
        self.status_lbl = QLabel("Waiting...")
        self.status_lbl.setStyleSheet("color:white;font-size:38px;font-weight:700;background:transparent;")
        hl.addWidget(self.status_lbl)
        lay.addWidget(hero)

        # Sensor cards row
        row = QHBoxLayout(); row.setSpacing(18)
        self.temp_val, tc = self._sensor_card("TEMPERATURE", "°C")
        self.ph_val, pc   = self._sensor_card("PH LEVEL", "pH")
        self.temp_bar = tc.findChild(QFrame, "bar")
        self.ph_bar   = pc.findChild(QFrame, "bar")
        row.addWidget(tc); row.addWidget(pc)
        lay.addLayout(row)

        # Controls card
        ctrl = QFrame(); ctrl.setStyleSheet(CARD_STYLE)
        cl = QVBoxLayout(ctrl); cl.setContentsMargins(24,24,24,24); cl.setSpacing(18)
        lr = QHBoxLayout(); lr.setSpacing(16)
        ic = QLabel("💡"); ic.setFixedSize(56,56); ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(f"background:{ACCENT};border-radius:28px;font-size:26px;")
        lr.addWidget(ic)
        info = QVBoxLayout(); info.setSpacing(4)
        info.addWidget(self._txt("Aquarium Light", TEXT_DARK, 20, bold=True))
        self.light_sub = self._txt("STATUS: OFF", TEXT_MUTED, 14, bold=True)
        info.addWidget(self.light_sub)
        lr.addLayout(info); lr.addStretch()
        self.light_tog = ToggleSwitch(False)
        self.light_tog.toggled.connect(self._on_light)
        lr.addWidget(self.light_tog)
        cl.addLayout(lr)
        fb = QPushButton("  🍽  FEED NOW"); fb.setFixedHeight(70)
        fb.setStyleSheet(f"QPushButton{{background:{PRIMARY};color:white;font-size:20px;"
                         f"font-weight:700;border-radius:16px;border:none;}}"
                         f"QPushButton:hover{{background:{PRIMARY2};}}"
                         f"QPushButton:pressed{{background:#0a3d4a;}}")
        fb.clicked.connect(self._feed)
        cl.addWidget(fb)
        lay.addWidget(ctrl)

        # Log header
        lh = QHBoxLayout()
        lh.addWidget(self._txt("Status Log", TEXT_DARK, 20, bold=True))
        lh.addStretch()
        lh.addWidget(self._txt("VIEW ALL", PRIMARY2, 15, bold=True))
        lay.addLayout(lh)

        self.log_card = QFrame(); self.log_card.setStyleSheet(CARD_STYLE)
        self.log_lay = QVBoxLayout(self.log_card)
        self.log_lay.setContentsMargins(0,0,0,0); self.log_lay.setSpacing(0)
        lay.addWidget(self.log_card)
        lay.addStretch()

    def _txt(self, text, color, size, bold=False):
        l = QLabel(text)
        w = "700" if bold else "400"
        l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{w};")
        return l

    def _sensor_card(self, title, unit):
        card = QFrame(); card.setStyleSheet(CARD_STYLE)
        lay = QVBoxLayout(card); lay.setContentsMargins(20,20,20,20); lay.setSpacing(6)
        lay.addWidget(self._txt(title, TEXT_MUTED, 14, bold=True))
        vr = QHBoxLayout(); vr.setSpacing(4)
        val = QLabel("--"); val.setStyleSheet(f"color:{TEXT_DARK};font-size:42px;font-weight:700;")
        u = QLabel(unit); u.setStyleSheet(f"color:{TEXT_MID};font-size:18px;padding-top:14px;")
        vr.addWidget(val); vr.addWidget(u); vr.addStretch()
        lay.addLayout(vr)
        bar = QFrame(); bar.setObjectName("bar"); bar.setFixedHeight(4)
        bar.setStyleSheet(f"background:{ACCENT};border-radius:2px;")
        lay.addWidget(bar)
        return val, card

    def _on_light(self, on):
        cmd = {"state": "on" if on else "off", "timestamp": datetime.now().isoformat()}
        try:
            self.mqtt_client.publish(config.TOPIC_LIGHT_CMD, json.dumps(cmd))
            add_event("INFO", f"Light {'ON' if on else 'OFF'} command sent")
        except Exception:
            add_event("WARNING", "Failed to send light command")

    def _feed(self):
        try:
            self.mqtt_client.publish(config.TOPIC_FEEDING_CMD,
                json.dumps({"action":"feed","amount":"normal","timestamp":datetime.now().isoformat()}))
            add_event("INFO", "Manual feeding triggered")
        except Exception:
            add_event("WARNING", "Failed to send feed command")

    def refresh(self):
        self.status_lbl.setText(state["system_status"])
        t = state["temperature"]
        if t is not None:
            col = get_temp_color(t)
            self.temp_val.setText(str(t))
            self.temp_val.setStyleSheet(f"color:{col};font-size:42px;font-weight:700;")
            self.temp_bar.setStyleSheet(f"background:{col};border-radius:2px;")
        ph = state["ph"]
        if ph is not None:
            col = get_ph_color(ph)
            self.ph_val.setText(str(ph))
            self.ph_val.setStyleSheet(f"color:{col};font-size:42px;font-weight:700;")
            self.ph_bar.setStyleSheet(f"background:{col};border-radius:2px;")
        is_on = state["light"] == "on"
        self.light_tog.setChecked(is_on)
        if is_on:
            self.light_sub.setText("STATUS: ON")
            self.light_sub.setStyleSheet(f"color:{ACCENT};font-size:14px;font-weight:700;")
        else:
            self.light_sub.setText("STATUS: OFF")
            self.light_sub.setStyleSheet(f"color:{TEXT_MUTED};font-size:14px;font-weight:700;")

        while self.log_lay.count():
            item = self.log_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        events = state["events"][:10]
        for i, (ts, lvl, msg) in enumerate(events):
            self.log_lay.addWidget(self._log_row(ts, lvl, msg, i < len(events) - 1))

    def _log_row(self, ts, lvl, msg, div):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(w); vl.setContentsMargins(22,16,22,0); vl.setSpacing(0)
        row = QHBoxLayout(); row.setSpacing(16)
        tl = QLabel(ts); tl.setStyleSheet(f"color:{PRIMARY2};font-size:18px;font-weight:600;min-width:55px;")
        ml = QLabel(msg); ml.setStyleSheet(f"color:{TEXT_DARK};font-size:18px;"); ml.setWordWrap(True)
        bc = SUCCESS if lvl in ("SUCCESS","INFO") else (WARNING if lvl == "WARNING" else DANGER)
        bt = "SUCCESS" if lvl == "SUCCESS" else ("INFO" if lvl == "INFO" else lvl)
        row.addWidget(tl); row.addWidget(ml,1); row.addWidget(badge(bt, bc))
        vl.addLayout(row)
        vl.addSpacing(16)
        if div: vl.addWidget(hdivider())
        return w

# ── Stats ─────────────────────────────────────────────────────────────────────
class StatsPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background:{BG};")
        w = QWidget(); w.setStyleSheet(f"background:{BG};"); self.setWidget(w)
        lay = QVBoxLayout(w); lay.setContentsMargins(24,18,24,24); lay.setSpacing(20)

        lay.addWidget(self._txt("Analytics", TEXT_DARK, 38, True))
        lay.addWidget(self._txt("Monitoring aquatic equilibrium over time.", TEXT_MUTED, 18))

        # Temperature chart card
        tc = QFrame(); tc.setStyleSheet(CARD_STYLE)
        tl = QVBoxLayout(tc); tl.setContentsMargins(22,22,22,22); tl.setSpacing(12)
        th = QHBoxLayout()
        th.addWidget(self._txt("WATER TEMPERATURE", PRIMARY2, 15, True))
        th.addStretch()
        tl.addLayout(th)
        self.cur_temp = QLabel("--°C")
        self.cur_temp.setStyleSheet(f"color:{TEXT_DARK};font-size:48px;font-weight:700;")
        tl.addWidget(self.cur_temp)
        self.temp_chart = LineChart(self._get_temp_data, ACCENT, 18, 35, time_axis=True,
                                    target_lo=allowed_ranges["temp_safe_min"],
                                    target_hi=allowed_ranges["temp_safe_max"])
        tl.addWidget(self.temp_chart)
        tf = QHBoxLayout()
        self.temp_avg = QLabel("Avg: --")
        self.temp_avg.setStyleSheet(f"color:{TEXT_MUTED};font-size:15px;")
        self.temp_peak = QLabel("Peak: --")
        self.temp_peak.setStyleSheet(f"color:{TEXT_MUTED};font-size:15px;")
        tf.addWidget(self.temp_avg); tf.addStretch(); tf.addWidget(self.temp_peak)
        tl.addLayout(tf)
        self.temp_target_lbl = self._txt(
            f"Target: {allowed_ranges['temp_safe_min']}°C – {allowed_ranges['temp_safe_max']}°C",
            TEXT_MUTED, 15)
        tl.addWidget(self.temp_target_lbl)
        lay.addWidget(tc)

        # pH card
        pc = QFrame(); pc.setStyleSheet(CARD_STYLE)
        pl2 = QVBoxLayout(pc); pl2.setContentsMargins(22,22,22,22); pl2.setSpacing(12)
        ph2 = QHBoxLayout()
        ph2.addWidget(self._txt("ACIDITY LEVEL", PRIMARY2, 15, True))
        ph2.addStretch()
        pl2.addLayout(ph2)
        self.cur_ph = QLabel("-- pH")
        self.cur_ph.setStyleSheet(f"color:{TEXT_DARK};font-size:48px;font-weight:700;")
        pl2.addWidget(self.cur_ph)
        self.ph_chart = LineChart(self._get_ph_data, "#A8D5D8", 4, 10, time_axis=True,
                                  target_lo=allowed_ranges["ph_safe_min"],
                                  target_hi=allowed_ranges["ph_safe_max"])
        pl2.addWidget(self.ph_chart)
        pf2 = QHBoxLayout()
        self.ph_target_lbl = self._txt(
            f"Target: {allowed_ranges['ph_safe_min']} – {allowed_ranges['ph_safe_max']}",
            TEXT_MUTED, 15)
        pf2.addWidget(self.ph_target_lbl)
        pf2.addStretch()
        self.ph_last = QLabel("Last: -- pH")
        self.ph_last.setStyleSheet(f"color:{TEXT_MUTED};font-size:15px;")
        pf2.addWidget(self.ph_last)
        pl2.addLayout(pf2)
        lay.addWidget(pc)

        lay.addStretch()

    def _get_temp_data(self):
        data = state["temp_history"]
        return data[-4800:] if len(data) > 4800 else list(data)

    def _get_ph_data(self):
        data = state["ph_history"]
        return data[-4800:] if len(data) > 4800 else list(data)

    def _txt(self, text, color, size, bold=False):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{'700' if bold else '400'};")
        return l

    def refresh(self):
        t = state["temperature"]
        self.cur_temp.setText(f"{t}°C" if t else "--°C")
        th = self._get_temp_data()
        self.temp_avg.setText(f"Avg: {sum(th)/len(th):.1f}°C" if th else "Avg: --")
        self.temp_peak.setText(f"Peak: {max(th):.1f}°C" if th else "Peak: --")
        self.temp_chart.target_lo = allowed_ranges["temp_safe_min"]
        self.temp_chart.target_hi = allowed_ranges["temp_safe_max"]
        self.temp_chart.update()

        ph = state["ph"]
        self.cur_ph.setText(f"{ph} pH" if ph else "-- pH")
        self.ph_last.setText(f"Last: {ph} pH" if ph else "Last: -- pH")
        self.ph_chart.target_lo = allowed_ranges["ph_safe_min"]
        self.ph_chart.target_hi = allowed_ranges["ph_safe_max"]
        self.ph_chart.update()
        self.temp_target_lbl.setText(
            f"Target: {allowed_ranges['temp_safe_min']}°C – {allowed_ranges['temp_safe_max']}°C")
        self.ph_target_lbl.setText(
            f"Target: {allowed_ranges['ph_safe_min']} – {allowed_ranges['ph_safe_max']}")

# ── Schedule ──────────────────────────────────────────────────────────────────
# ── Feeding schedule DB helpers ───────────────────────────────────────────────
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'aquarium.db')

def load_feeding_schedules():
    conn = sqlite3.connect(_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, time, enabled FROM feeding_schedules ORDER BY id")
    rows = [{"id": r[0], "name": r[1], "time": r[2], "enabled": bool(r[3])} for r in cur.fetchall()]
    conn.close()
    return rows

def save_feeding_schedule(name, time_str):
    conn = sqlite3.connect(_DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO feeding_schedules (name, time, enabled) VALUES (?, ?, 1)", (name, time_str))
    new_id = cur.lastrowid
    conn.commit(); conn.close()
    return new_id

def update_feeding_schedule(row_id, name, time_str, enabled):
    conn = sqlite3.connect(_DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE feeding_schedules SET name=?, time=?, enabled=? WHERE id=?",
                (name, time_str, 1 if enabled else 0, row_id))
    conn.commit(); conn.close()

def delete_feeding_schedule(row_id):
    conn = sqlite3.connect(_DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM feeding_schedules WHERE id=?", (row_id,))
    conn.commit(); conn.close()

def _fmt_time(t24):
    """Convert 'HH:MM' (24h) to 'HH:MM AM/PM' for display."""
    h, m = map(int, t24.split(":"))
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12:02d}:{m:02d} {suffix}"

def load_light_schedule():
    conn = sqlite3.connect(_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT on_time, off_time FROM light_schedule WHERE id=1")
    row = cur.fetchone()
    conn.close()
    return {"on_time": row[0], "off_time": row[1]} if row else {"on_time": "08:00", "off_time": "22:00"}

def save_light_schedule(on_time, off_time):
    conn = sqlite3.connect(_DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE light_schedule SET on_time=?, off_time=? WHERE id=1", (on_time, off_time))
    conn.commit(); conn.close()


class SchedulePage(QScrollArea):
    def __init__(self, mqtt_client, parent=None):
        super().__init__(parent)
        self.mqtt_client = mqtt_client
        self.setWidgetResizable(True); self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background:{BG};")
        self._root = QWidget(); self._root.setStyleSheet(f"background:{BG};")
        self.setWidget(self._root)
        self._lay = QVBoxLayout(self._root)
        self._lay.setContentsMargins(24,18,24,24); self._lay.setSpacing(20)

        self._lay.addWidget(self._txt("Automation Schedule", TEXT_DARK, 32, True))
        self._lay.addWidget(self._txt("Manage your tank's life cycles and routines.", TEXT_MUTED, 18))

        # Light simulation card
        lc = QFrame(); lc.setStyleSheet(CARD_STYLE)
        ll = QVBoxLayout(lc); ll.setContentsMargins(22,22,22,22); ll.setSpacing(16)
        top = QHBoxLayout(); top.setSpacing(12)
        il = QLabel("🌅"); il.setStyleSheet("font-size:26px;")
        top.addWidget(il)
        top.addWidget(self._txt("Light Simulation", TEXT_DARK, 22, True))
        top.addStretch()
        top.addWidget(ToggleSwitch(True))
        ll.addLayout(top)

        ls = load_light_schedule()
        tr = QHBoxLayout(); tr.setSpacing(16)
        for key, lbl in [("on_time", "LIGHT ON"), ("off_time", "LIGHT OFF")]:
            tf = QFrame(); tf.setStyleSheet("background:#F5F7FA;border-radius:14px;")
            tf.setCursor(Qt.PointingHandCursor)
            tfl = QVBoxLayout(tf); tfl.setContentsMargins(20,16,20,16); tfl.setSpacing(6)
            tfl.addWidget(self._txt(lbl, TEXT_MUTED, 14, True))
            val_lbl = QLabel(_fmt_time(ls[key]))
            val_lbl.setStyleSheet(
                f"color:{PRIMARY};font-size:24px;font-weight:700;"
                "text-decoration:underline;"
            )
            tfl.addWidget(val_lbl)
            tr.addWidget(tf)
            if key == "on_time":
                self.light_on_lbl = val_lbl
                self.light_on_frame = tf
            else:
                self.light_off_lbl = val_lbl
                self.light_off_frame = tf

        self.light_on_frame.mousePressEvent  = lambda e: self._open_light_dialog()
        self.light_off_frame.mousePressEvent = lambda e: self._open_light_dialog()

        ll.addLayout(tr)
        self._lay.addWidget(lc)

        # Routines header
        self._rh = QHBoxLayout()
        self._rh.addWidget(self._txt("Daily Routines", TEXT_DARK, 22, True))
        self._rh.addStretch()
        self._active_badge = badge("0 ACTIVE", PRIMARY2)
        self._rh.addWidget(self._active_badge)
        self._lay.addLayout(self._rh)

        # Feeding routines card (outer frame persists; inner rows are rebuilt)
        self._feed_card = QFrame(); self._feed_card.setStyleSheet(CARD_STYLE)
        self._feed_card_lay = QVBoxLayout(self._feed_card)
        self._feed_card_lay.setContentsMargins(0,0,0,0); self._feed_card_lay.setSpacing(0)
        self._lay.addWidget(self._feed_card)

        # "Add Feeding" button
        add_btn = QPushButton("＋ Add Feeding")
        add_btn.setStyleSheet(
            f"QPushButton{{background:{PRIMARY2};color:white;font-size:16px;font-weight:600;"
            f"border-radius:12px;padding:10px 24px;}}"
            f"QPushButton:hover{{background:{PRIMARY};}}"
        )
        add_btn.clicked.connect(self._open_add_dialog)
        self._lay.addWidget(add_btn, alignment=Qt.AlignLeft)

        self._lay.addStretch()
        self._rebuild_feed_rows()

    # ── feed rows ──────────────────────────────────────────────────────────────

    def _rebuild_feed_rows(self):
        # Clear existing row widgets from the card layout
        while self._feed_card_lay.count():
            item = self._feed_card_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        routines = load_feeding_schedules()
        active = sum(1 for r in routines if r["enabled"])
        self._active_badge.setText(f"{active} ACTIVE")

        row_colors = [SUCCESS, PRIMARY2, ACCENT, TEXT_MUTED]
        for i, r in enumerate(routines):
            on = r["enabled"]
            col = row_colors[i % len(row_colors)] if on else TEXT_MUTED

            rw = QWidget(); rw.setStyleSheet("background:transparent;")
            rvl = QVBoxLayout(rw); rvl.setContentsMargins(16,18,22,0); rvl.setSpacing(0)
            row = QHBoxLayout(); row.setSpacing(14)

            bar = QFrame(); bar.setFixedWidth(4)
            bar.setStyleSheet(f"background:{col if on else '#E8EDF2'};border-radius:2px;")
            row.addWidget(bar)

            ic = QLabel("🍽"); ic.setFixedSize(50,50); ic.setAlignment(Qt.AlignCenter)
            ic.setStyleSheet(f"background:{'#E8F8FC' if on else '#F0F4F8'};border-radius:25px;font-size:22px;")
            row.addWidget(ic)

            info = QVBoxLayout(); info.setSpacing(4)
            nl = QLabel(r["name"])
            nl.setStyleSheet(f"color:{TEXT_DARK if on else TEXT_MUTED};font-size:18px;font-weight:600;")
            sl = QLabel(f"⏰ {_fmt_time(r['time'])}")
            sl.setStyleSheet(f"color:{TEXT_MUTED};font-size:16px;")
            info.addWidget(nl); info.addWidget(sl)
            row.addLayout(info); row.addStretch()

            ts = ToggleSwitch(on)
            rid = r["id"]
            ts.toggled.connect(lambda checked, _id=rid, _r=r: self._on_toggle(_id, _r, checked))
            row.addWidget(ts)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedHeight(28)
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.setStyleSheet(
                "QPushButton{background:transparent;color:#4A5568;font-size:12px;font-weight:400;"
                "border:1px solid #E0E0E0;border-radius:6px;padding:4px 10px;}"
                f"QPushButton:hover{{background:#F5F5F5;border-color:{PRIMARY};}}"
            )
            edit_btn.clicked.connect(lambda _, _id=rid, _r=r: self._open_edit_dialog(_id, _r))
            row.addWidget(edit_btn)

            del_btn = QPushButton("Remove")
            del_btn.setFixedHeight(28)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet(
                "QPushButton{background:transparent;color:#E57373;font-size:12px;font-weight:400;"
                "border:1px solid #FFCDD2;border-radius:6px;padding:4px 10px;}"
                "QPushButton:hover{background:#FFEBEE;border-color:#E57373;}"
            )
            del_btn.clicked.connect(lambda _, _id=rid: self._delete_row(_id))
            row.addWidget(del_btn)

            rvl.addLayout(row); rvl.addSpacing(18)
            if i < len(routines) - 1:
                rvl.addWidget(hdivider())
            self._feed_card_lay.addWidget(rw)

    # ── slot helpers ───────────────────────────────────────────────────────────

    def _on_toggle(self, row_id, r, checked):
        update_feeding_schedule(row_id, r["name"], r["time"], checked)
        self._rebuild_feed_rows()

    def _delete_row(self, row_id):
        delete_feeding_schedule(row_id)
        self._rebuild_feed_rows()

    def _open_light_dialog(self):
        ls = load_light_schedule()
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Light Schedule")
        dlg.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        dlg.setFixedSize(320, 260)
        dlg.setStyleSheet("QDialog{background:#F8F9FA;}")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 24, 24, 24); lay.setSpacing(12)

        title_lbl = QLabel("Edit Light Schedule")
        title_lbl.setStyleSheet(f"color:{PRIMARY2};font-size:16px;font-weight:700;background:transparent;")
        lay.addWidget(title_lbl)

        field_style = (
            "QTimeEdit{background:white;border:1px solid #E0E0E0;border-radius:8px;"
            "padding:8px 12px;font-size:14px;color:#1A2535;}"
            f"QTimeEdit:focus{{border:1px solid {PRIMARY2};}}"
        )
        lbl_style = f"color:{TEXT_MID};font-size:13px;font-weight:400;background:transparent;"

        lay.addWidget(QLabel("Light On:")); lay.itemAt(lay.count()-1).widget().setStyleSheet(lbl_style)
        on_edit = QTimeEdit(); on_edit.setDisplayFormat("HH:mm"); on_edit.setStyleSheet(field_style)
        h, m = map(int, ls["on_time"].split(":")); on_edit.setTime(QTime(h, m))
        lay.addWidget(on_edit)

        lay.addWidget(QLabel("Light Off:")); lay.itemAt(lay.count()-1).widget().setStyleSheet(lbl_style)
        off_edit = QTimeEdit(); off_edit.setDisplayFormat("HH:mm"); off_edit.setStyleSheet(field_style)
        h, m = map(int, ls["off_time"].split(":")); off_edit.setTime(QTime(h, m))
        lay.addWidget(off_edit)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{TEXT_MID};font-size:13px;"
            f"border:1px solid #E0E0E0;border-radius:8px;padding:8px 24px;}}"
            f"QPushButton:hover{{background:#F5F5F5;}}"
        )
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(
            f"QPushButton{{background:{PRIMARY2};color:white;font-size:13px;font-weight:600;"
            f"border:none;border-radius:8px;padding:8px 24px;}}"
            f"QPushButton:hover{{background:{PRIMARY};}}"
        )
        save_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(save_btn)
        lay.addLayout(btn_row)

        if dlg.exec_() == QDialog.Accepted:
            on_t = on_edit.time()
            off_t = off_edit.time()
            on_str  = f"{on_t.hour():02d}:{on_t.minute():02d}"
            off_str = f"{off_t.hour():02d}:{off_t.minute():02d}"
            save_light_schedule(on_str, off_str)
            self.light_on_lbl.setText(_fmt_time(on_str))
            self.light_off_lbl.setText(_fmt_time(off_str))
            payload = json.dumps({"on_time": on_str, "off_time": off_str})
            self.mqtt_client.publish(config.TOPIC_PREFIX + "/config/light_schedule", payload)

    def _make_feed_dialog(self, title):
        """Return (dlg, lay, name_edit, time_edit) with app-styled layout."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        dlg.setFixedSize(320, 280)
        dlg.setStyleSheet("QDialog{background:#F8F9FA;}")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color:{PRIMARY2};font-size:16px;font-weight:700;background:transparent;")
        lay.addWidget(title_lbl)

        field_style = (
            "QLineEdit, QTimeEdit{"
            "background:white;border:1px solid #E0E0E0;border-radius:8px;"
            "padding:8px 12px;font-size:14px;color:#1A2535;}"
            f"QLineEdit:focus, QTimeEdit:focus{{border:1px solid {PRIMARY2};}}"
        )
        lbl_style = f"color:{TEXT_MID};font-size:13px;font-weight:400;background:transparent;"

        name_lbl = QLabel("Name:"); name_lbl.setStyleSheet(lbl_style)
        lay.addWidget(name_lbl)
        name_edit = QLineEdit()
        name_edit.setStyleSheet(field_style)
        lay.addWidget(name_edit)

        time_lbl = QLabel("Time:"); time_lbl.setStyleSheet(lbl_style)
        lay.addWidget(time_lbl)
        time_edit = QTimeEdit()
        time_edit.setDisplayFormat("HH:mm")
        time_edit.setStyleSheet(field_style)
        lay.addWidget(time_edit)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{TEXT_MID};font-size:13px;"
            f"border:1px solid #E0E0E0;border-radius:8px;padding:8px 24px;}}"
            f"QPushButton:hover{{background:#F5F5F5;}}"
        )
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(
            f"QPushButton{{background:{PRIMARY2};color:white;font-size:13px;font-weight:600;"
            f"border:none;border-radius:8px;padding:8px 24px;}}"
            f"QPushButton:hover{{background:{PRIMARY};}}"
        )
        save_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(save_btn)

        lay.addLayout(btn_row)
        return dlg, name_edit, time_edit

    def _open_add_dialog(self):
        dlg, name_edit, time_edit = self._make_feed_dialog("Add Feeding")
        name_edit.setPlaceholderText("e.g. Morning Feed")
        time_edit.setTime(QTime(8, 0))
        if dlg.exec_() == QDialog.Accepted:
            name = name_edit.text().strip() or "New Feed"
            t = time_edit.time()
            save_feeding_schedule(name, f"{t.hour():02d}:{t.minute():02d}")
            self._rebuild_feed_rows()

    def _open_edit_dialog(self, row_id, r):
        dlg, name_edit, time_edit = self._make_feed_dialog("Edit Feeding")
        name_edit.setText(r["name"])
        h, m = map(int, r["time"].split(":"))
        time_edit.setTime(QTime(h, m))
        if dlg.exec_() == QDialog.Accepted:
            name = name_edit.text().strip() or r["name"]
            t = time_edit.time()
            update_feeding_schedule(row_id, name, f"{t.hour():02d}:{t.minute():02d}", r["enabled"])
            self._rebuild_feed_rows()

    # ── misc ───────────────────────────────────────────────────────────────────

    def _txt(self, text, color, size, bold=False):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{'700' if bold else '400'};")
        return l

    def refresh(self):
        self._rebuild_feed_rows()

# ── Settings ──────────────────────────────────────────────────────────────────
class SettingsPage(QScrollArea):
    _PCT_OPTIONS = (5, 10, 15, 20)

    def __init__(self, mqtt_client, parent=None):
        super().__init__(parent)
        self.mqtt_client = mqtt_client
        self._temp_pct = temp_warn_pct
        self._ph_pct   = ph_warn_pct
        self.setWidgetResizable(True); self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background:{BG};")
        w = QWidget(); w.setStyleSheet(f"background:{BG};"); self.setWidget(w)
        lay = QVBoxLayout(w); lay.setContentsMargins(24,18,24,24); lay.setSpacing(20)

        # Hero
        hero = QFrame(); hero.setFixedHeight(200)
        hero.setStyleSheet("QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                           "stop:0 #1B5E20,stop:1 #388E3C);border-radius:24px;}")
        hl = QVBoxLayout(hero); hl.setContentsMargins(28,28,28,28); hl.addStretch()
        s1 = QLabel("DEVICE PREFERENCES")
        s1.setStyleSheet("color:rgba(255,255,255,0.7);font-size:14px;font-weight:600;"
                         "letter-spacing:2px;background:transparent;")
        s2 = QLabel("Settings & Alerts")
        s2.setStyleSheet("color:white;font-size:32px;font-weight:700;background:transparent;")
        hl.addWidget(s1); hl.addWidget(s2)
        lay.addWidget(hero)

        # Notification Preferences
        lay.addWidget(section_lbl("NOTIFICATION PREFERENCES"))
        nc = QFrame(); nc.setStyleSheet(CARD_STYLE)
        nl = QVBoxLayout(nc); nl.setContentsMargins(0,0,0,0); nl.setSpacing(0)
        nl.addWidget(self._notif_row("🔔","Push Notifications","Real-time alerts on your device",True))
        lay.addWidget(nc)

        # Safe Ranges
        lay.addWidget(section_lbl("SAFE RANGES & ALERTS"))
        rc = QFrame(); rc.setStyleSheet(CARD_STYLE)
        rl = QVBoxLayout(rc); rl.setContentsMargins(22,22,22,22); rl.setSpacing(16)

        # ── Temperature ──
        th = QHBoxLayout()
        th.addWidget(QLabel("🌡"))
        th.addWidget(self._txt("Temperature Range", TEXT_DARK, 18))
        th.addStretch()
        rl.addLayout(th)

        sr = QHBoxLayout(); sr.setSpacing(10)
        slbl = self._txt("✓ Safe", SUCCESS, 13, True); slbl.setFixedWidth(90)
        sr.addWidget(slbl)
        self.temp_safe_slider = RangeSlider(
            allowed_ranges["temp_safe_min"], allowed_ranges["temp_safe_max"],
            10.0, 40.0)
        self.temp_safe_slider.range_changed.connect(self._on_temp_safe)
        sr.addWidget(self.temp_safe_slider, 1)
        self.temp_safe_lbl = self._txt(
            f"{allowed_ranges['temp_safe_min']}°C – {allowed_ranges['temp_safe_max']}°C",
            SUCCESS, 13, True)
        self.temp_safe_lbl.setFixedWidth(110)
        sr.addWidget(self.temp_safe_lbl)
        rl.addLayout(sr)

        rl.addLayout(self._pct_row("temp"))
        self.temp_warn_info = self._txt("", WARNING, 13)
        rl.addWidget(self.temp_warn_info)
        self._update_temp_warn_info()

        rl.addWidget(hdivider())

        # ── pH ──
        ph_h = QHBoxLayout()
        ph_h.addWidget(QLabel("💧"))
        ph_h.addWidget(self._txt("pH Level Range", TEXT_DARK, 18))
        ph_h.addStretch()
        rl.addLayout(ph_h)

        psr = QHBoxLayout(); psr.setSpacing(10)
        pslbl = self._txt("✓ Safe", SUCCESS, 13, True); pslbl.setFixedWidth(90)
        psr.addWidget(pslbl)
        self.ph_safe_slider = RangeSlider(
            allowed_ranges["ph_safe_min"], allowed_ranges["ph_safe_max"],
            4.0, 10.0)
        self.ph_safe_slider.range_changed.connect(self._on_ph_safe)
        psr.addWidget(self.ph_safe_slider, 1)
        self.ph_safe_lbl = self._txt(
            f"{allowed_ranges['ph_safe_min']} – {allowed_ranges['ph_safe_max']}",
            SUCCESS, 13, True)
        self.ph_safe_lbl.setFixedWidth(110)
        psr.addWidget(self.ph_safe_lbl)
        rl.addLayout(psr)

        rl.addLayout(self._pct_row("ph"))
        self.ph_warn_info = self._txt("", WARNING, 13)
        rl.addWidget(self.ph_warn_info)
        self._update_ph_warn_info()

        lay.addWidget(rc)
        lay.addStretch()

    def _pct_row(self, param):
        row = QHBoxLayout(); row.setSpacing(8)
        row.addWidget(self._txt("⚠ Warning buffer:", WARNING, 13, True))
        current = self._temp_pct if param == "temp" else self._ph_pct
        btns = {}
        for pct in self._PCT_OPTIONS:
            btn = QPushButton(f"{pct}%")
            btn.setCheckable(True)
            btn.setChecked(pct == current)
            btn.setFixedSize(60, 34)
            self._style_pct_btn(btn, pct == current)
            btn.clicked.connect(lambda _, p=pct, par=param: self._on_pct_clicked(par, p))
            btns[pct] = btn
            row.addWidget(btn)
        setattr(self, f"_{param}_pct_btns", btns)
        row.addStretch()
        return row

    def _style_pct_btn(self, btn, active):
        if active:
            btn.setStyleSheet(
                f"QPushButton{{background:{WARNING};color:white;font-size:14px;font-weight:700;"
                f"border-radius:10px;border:none;}}"
                f"QPushButton:hover{{background:{WARNING};}}")
        else:
            btn.setStyleSheet(
                "QPushButton{background:#F0F4F8;color:#64748B;font-size:14px;font-weight:600;"
                "border-radius:10px;border:none;}"
                "QPushButton:hover{background:#E2E8F0;}")

    def _on_pct_clicked(self, param, pct):
        if param == "temp":
            self._temp_pct = pct
            for p, b in self._temp_pct_btns.items():
                self._style_pct_btn(b, p == pct)
            self._recompute_warn("temp")
            self._update_temp_warn_info()
        else:
            self._ph_pct = pct
            for p, b in self._ph_pct_btns.items():
                self._style_pct_btn(b, p == pct)
            self._recompute_warn("ph")
            self._update_ph_warn_info()
        self._publish_thresholds()

    def _recompute_warn(self, param):
        global temp_warn_pct, ph_warn_pct
        if param == "temp":
            temp_warn_pct = self._temp_pct
            span = allowed_ranges["temp_safe_max"] - allowed_ranges["temp_safe_min"]
            buf  = span * self._temp_pct / 100
            allowed_ranges["temp_warn_min"] = round(allowed_ranges["temp_safe_min"] + buf, 1)
            allowed_ranges["temp_warn_max"] = round(allowed_ranges["temp_safe_max"] - buf, 1)
        else:
            ph_warn_pct = self._ph_pct
            span = allowed_ranges["ph_safe_max"] - allowed_ranges["ph_safe_min"]
            buf  = span * self._ph_pct / 100
            allowed_ranges["ph_warn_min"] = round(allowed_ranges["ph_safe_min"] + buf, 1)
            allowed_ranges["ph_warn_max"] = round(allowed_ranges["ph_safe_max"] - buf, 1)

    def _update_temp_warn_info(self):
        s_min = allowed_ranges["temp_safe_min"]; s_max = allowed_ranges["temp_safe_max"]
        w_min = allowed_ranges["temp_warn_min"]; w_max = allowed_ranges["temp_warn_max"]
        self.temp_warn_info.setText(
            f"Warn when: {s_min}–{w_min}°C  or  {w_max}–{s_max}°C")

    def _update_ph_warn_info(self):
        s_min = allowed_ranges["ph_safe_min"]; s_max = allowed_ranges["ph_safe_max"]
        w_min = allowed_ranges["ph_warn_min"]; w_max = allowed_ranges["ph_warn_max"]
        self.ph_warn_info.setText(
            f"Warn when: {s_min}–{w_min}  or  {w_max}–{s_max}")

    def _on_temp_safe(self, mn, mx):
        allowed_ranges["temp_safe_min"] = mn
        allowed_ranges["temp_safe_max"] = mx
        self.temp_safe_lbl.setText(f"{mn}°C – {mx}°C")
        self._recompute_warn("temp")
        self._update_temp_warn_info()
        self._publish_thresholds()

    def _on_ph_safe(self, mn, mx):
        allowed_ranges["ph_safe_min"] = mn
        allowed_ranges["ph_safe_max"] = mx
        self.ph_safe_lbl.setText(f"{mn} – {mx}")
        self._recompute_warn("ph")
        self._update_ph_warn_info()
        self._publish_thresholds()

    def _txt(self, text, color, size, bold=False):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{'700' if bold else '400'};")
        return l

    def _notif_row(self, ico, title, sub, checked):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        row = QHBoxLayout(w); row.setContentsMargins(22,18,22,18); row.setSpacing(16)
        il = QLabel(ico); il.setFixedSize(50,50); il.setAlignment(Qt.AlignCenter)
        il.setStyleSheet("background:#F0F4F8;border-radius:25px;font-size:22px;")
        row.addWidget(il)
        info = QVBoxLayout(); info.setSpacing(4)
        info.addWidget(self._txt(title, TEXT_DARK, 18, True))
        info.addWidget(self._txt(sub, TEXT_MUTED, 14))
        row.addLayout(info); row.addStretch()
        row.addWidget(ToggleSwitch(checked))
        return w

    def _publish_thresholds(self):
        try:
            self.mqtt_client.publish(TOPIC_THRESHOLDS, json.dumps(allowed_ranges))
        except Exception:
            add_event("WARNING", "Failed to publish threshold update")
        save_allowed_ranges()

    def refresh(self):
        pass

# ── Nav Button ────────────────────────────────────────────────────────────────
class NavButton(QPushButton):
    def __init__(self, icon, label, parent=None):
        super().__init__(parent)
        self._active = False
        self.setFixedHeight(80); self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(4, 8, 4, 8); vl.setSpacing(2)
        vl.setAlignment(Qt.AlignCenter)

        self._ico_lbl = QLabel(icon)
        self._ico_lbl.setAlignment(Qt.AlignCenter)
        self._ico_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._txt_lbl = QLabel(label)
        self._txt_lbl.setAlignment(Qt.AlignCenter)
        self._txt_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)

        vl.addWidget(self._ico_lbl)
        vl.addWidget(self._txt_lbl)
        self._style()

    def set_active(self, on):
        self._active = on; self._style()

    def _style(self):
        if self._active:
            self.setStyleSheet(f"QPushButton{{background:{ACCENT};border-radius:18px;border:none;}}")
            self._ico_lbl.setStyleSheet(
                f"color:{PRIMARY};font-family:'Segoe MDL2 Assets';font-size:18px;"
                f"background:transparent;border:none;text-decoration:none;padding:0;")
            self._txt_lbl.setStyleSheet(
                f"color:{PRIMARY};font-size:15px;font-weight:700;background:transparent;border:none;")
        else:
            self.setStyleSheet(
                f"QPushButton{{background:transparent;border-radius:18px;border:none;}}"
                f"QPushButton:hover{{background:#F0F4F8;}}")
            self._ico_lbl.setStyleSheet(
                f"color:{TEXT_MUTED};font-family:'Segoe MDL2 Assets';font-size:18px;"
                f"background:transparent;border:none;text-decoration:none;padding:0;")
            self._txt_lbl.setStyleSheet(
                f"color:{TEXT_MUTED};font-size:15px;font-weight:500;background:transparent;border:none;")

# ── Main Window ───────────────────────────────────────────────────────────────
class AquariumApp(QMainWindow):
    def __init__(self, mqtt_client):
        super().__init__()
        self.mqtt_client = mqtt_client
        self.setWindowTitle("Aquarium Monitor")
        self.setMinimumSize(1100, 1000)
        self.resize(1200, 1050)
        self.setStyleSheet(f"background:{BG};")
        self._build()
        self.timer = QTimer(); self.timer.timeout.connect(self._tick); self.timer.start(1000)

    def _build(self):
        root = QWidget(); root.setStyleSheet(f"background:{BG};"); self.setCentralWidget(root)
        rl = QVBoxLayout(root); rl.setContentsMargins(0,0,0,0); rl.setSpacing(0)

        # Top bar
        tb = QWidget(); tb.setStyleSheet(f"background:{WHITE};border-bottom:1px solid #E8EDF2;")
        tb.setFixedHeight(76)
        tbl = QHBoxLayout(tb); tbl.setContentsMargins(24,0,24,0)
        logo = QLabel("≋  Aquarium Monitor")
        logo.setStyleSheet(f"color:{PRIMARY};font-size:26px;font-weight:700;")
        tbl.addWidget(logo); tbl.addStretch()
        bell = QLabel("🔔"); bell.setStyleSheet("font-size:28px;")
        tbl.addWidget(bell)
        rl.addWidget(tb)

        # Pages
        self.stack = QStackedWidget()
        self.dash = DashboardPage(self.mqtt_client)
        self.stats = StatsPage()
        self.sched = SchedulePage(self.mqtt_client)
        self.sett = SettingsPage(self.mqtt_client)
        for p in [self.dash, self.stats, self.sched, self.sett]:
            self.stack.addWidget(p)
        rl.addWidget(self.stack, 1)

        # Nav bar
        nb = QWidget(); nb.setStyleSheet(f"background:{WHITE};border-top:1px solid #E8EDF2;")
        nb.setFixedHeight(90)
        nbl = QHBoxLayout(nb); nbl.setContentsMargins(12,6,12,6); nbl.setSpacing(6)
        self.nav = []
        for i,(ico,lbl) in enumerate([("","Dashboard"),("","Stats"),("","Schedule"),("","Settings")]):
            btn = NavButton(ico, lbl)
            btn.clicked.connect(lambda _, idx=i: self._switch(idx))
            nbl.addWidget(btn); self.nav.append(btn)
        self.nav[0].set_active(True)
        rl.addWidget(nb)

    def _switch(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav): b.set_active(i == idx)

    def _tick(self):
        idx = self.stack.currentIndex()
        pages = [self.dash, self.stats, self.sched, self.sett]
        pages[idx].refresh()

def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    start_mqtt_thread(client)

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 13))
    win = AquariumApp(client)
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
