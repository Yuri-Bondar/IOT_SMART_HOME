import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import paho.mqtt.client as mqtt
import json
import time
import threading
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QStackedWidget, QSlider
)
from PyQt5.QtCore import QTimer, Qt, QPointF, QRectF
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient, QPainterPath
)
import config

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
MAX_HISTORY = 24
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
    if config.TEMP_MIN_NORMAL <= v <= config.TEMP_MAX_NORMAL:
        return SUCCESS
    if config.TEMP_MIN_WARNING <= v <= config.TEMP_MAX_WARNING:
        return WARNING
    return DANGER

def get_ph_color(v):
    if v is None:
        return TEXT_MUTED
    if config.PH_MIN_NORMAL <= v <= config.PH_MAX_NORMAL:
        return SUCCESS
    if config.PH_MIN_WARNING <= v <= config.PH_MAX_WARNING:
        return WARNING
    return DANGER

# ── Toggle Switch ─────────────────────────────────────────────────────────────
from PyQt5.QtCore import pyqtSignal

class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(52, 28)
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
        m = 3
        tx = w - h + m if self._checked else m
        p.setBrush(QBrush(QColor(WHITE)))
        p.drawEllipse(tx, m, h - 2 * m, h - 2 * m)

# ── Line Chart ────────────────────────────────────────────────────────────────
class LineChart(QWidget):
    def __init__(self, data_fn, color=ACCENT, lo=None, hi=None, parent=None):
        super().__init__(parent)
        self.data_fn = data_fn
        self.color = color
        self.lo = lo
        self.hi = hi
        self.setMinimumHeight(100)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        data = self.data_fn()
        w, h = self.width(), self.height()
        pad = 8
        if len(data) < 2:
            p.setPen(QColor(TEXT_MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "Waiting for data...")
            return
        lo = self.lo if self.lo is not None else min(data) - 1
        hi = self.hi if self.hi is not None else max(data) + 1
        rng = hi - lo if hi != lo else 1

        def pt(i, v):
            x = pad + (i / (len(data) - 1)) * (w - 2 * pad)
            y = h - pad - ((v - lo) / rng) * (h - 2 * pad)
            return QPointF(x, y)

        path = QPainterPath()
        path.moveTo(pt(0, data[0]))
        for i in range(1, len(data)):
            path.lineTo(pt(i, data[i]))
        path.lineTo(QPointF(w - pad, h - pad))
        path.lineTo(QPointF(pad, h - pad))
        path.closeSubpath()
        grad = QLinearGradient(0, 0, 0, h)
        c1 = QColor(self.color); c1.setAlpha(55)
        c2 = QColor(self.color); c2.setAlpha(5)
        grad.setColorAt(0, c1); grad.setColorAt(1, c2)
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(self.color), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for i in range(len(data) - 1):
            p.drawLine(pt(i, data[i]), pt(i + 1, data[i + 1]))
        last = pt(len(data) - 1, data[-1])
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self.color)))
        p.drawEllipse(last, 5, 5)
        p.setBrush(QBrush(QColor(WHITE)))
        p.drawEllipse(last, 3, 3)

# ── Bar Chart ─────────────────────────────────────────────────────────────────
class BarChart(QWidget):
    def __init__(self, data_fn, color="#A8D5D8", highlight=PRIMARY, parent=None):
        super().__init__(parent)
        self.data_fn = data_fn
        self.color = color
        self.highlight = highlight
        self.setMinimumHeight(90)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        raw = self.data_fn()
        w, h = self.width(), self.height()
        if not raw:
            p.setPen(QColor(TEXT_MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "Waiting for data...")
            return
        show = raw[-7:] if len(raw) >= 7 else raw
        while len(show) < 7:
            show = [None] + list(show)
        n = len(show)
        gap = 6
        bar_w = (w - gap * (n + 1)) / n
        vals = [v for v in show if v is not None]
        hi = max(vals) + 1 if vals else 10
        pad_top = 8
        usable_h = h - pad_top
        for i, v in enumerate(show):
            x = gap + i * (bar_w + gap)
            bar_h = max(8, (v / hi) * usable_h) if v is not None else 8
            y = h - bar_h
            col = self.highlight if i == len(show) - 1 else self.color
            p.setBrush(QBrush(QColor(col)))
            p.setPen(Qt.NoPen)
            r = min(bar_w / 3, 4)
            p.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), r, r)

# ── Helpers ───────────────────────────────────────────────────────────────────
def hdivider():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("background: #E8EDF2; border: none; max-height: 1px;")
    return f

def section_lbl(text):
    l = QLabel(text)
    l.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;")
    return l

def badge(text, color):
    l = QLabel(text)
    l.setStyleSheet(f"background:{color}; color:white; font-size:10px; font-weight:700;"
                    f"border-radius:8px; padding:2px 8px;")
    l.setAlignment(Qt.AlignCenter)
    return l

CARD_STYLE = f"background:{WHITE}; border-radius:16px; border:1px solid #E8EDF2;"

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
        lay.setContentsMargins(16, 12, 16, 16)
        lay.setSpacing(12)

        # Hero
        hero = QFrame()
        hero.setFixedHeight(180)
        hero.setStyleSheet(f"QFrame{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                           f"stop:0 {PRIMARY},stop:1 {PRIMARY2});border-radius:20px;}}")
        hl = QVBoxLayout(hero); hl.setContentsMargins(20,20,20,20)
        hl.addStretch()
        sub = QLabel("LIVE STATUS")
        sub.setStyleSheet("color:rgba(255,255,255,0.7);font-size:11px;font-weight:600;"
                          "letter-spacing:2px;background:transparent;")
        hl.addWidget(sub)
        self.status_lbl = QLabel("Waiting...")
        self.status_lbl.setStyleSheet("color:white;font-size:26px;font-weight:700;background:transparent;")
        hl.addWidget(self.status_lbl)
        lay.addWidget(hero)

        # Sensor cards row
        row = QHBoxLayout(); row.setSpacing(12)
        self.temp_val, tc = self._sensor_card("TEMPERATURE", "°C")
        self.ph_val, pc   = self._sensor_card("PH LEVEL", "pH")
        self.temp_bar = tc.findChild(QFrame, "bar")
        self.ph_bar   = pc.findChild(QFrame, "bar")
        row.addWidget(tc); row.addWidget(pc)
        lay.addLayout(row)

        # Controls card
        ctrl = QFrame(); ctrl.setStyleSheet(CARD_STYLE)
        cl = QVBoxLayout(ctrl); cl.setContentsMargins(16,16,16,16); cl.setSpacing(12)
        # light row
        lr = QHBoxLayout(); lr.setSpacing(12)
        ic = QLabel("💡"); ic.setFixedSize(40,40); ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(f"background:{ACCENT};border-radius:20px;font-size:18px;")
        lr.addWidget(ic)
        info = QVBoxLayout(); info.setSpacing(2)
        info.addWidget(self._txt("Aquarium Light", TEXT_DARK, 15, bold=True))
        self.light_sub = self._txt("STATUS: OFF", TEXT_MUTED, 10, bold=True)
        info.addWidget(self.light_sub)
        lr.addLayout(info); lr.addStretch()
        self.light_tog = ToggleSwitch(False)
        self.light_tog.toggled.connect(self._on_light)
        lr.addWidget(self.light_tog)
        cl.addLayout(lr)
        # feed button
        fb = QPushButton("  🍽  FEED NOW"); fb.setFixedHeight(52)
        fb.setStyleSheet(f"QPushButton{{background:{PRIMARY};color:white;font-size:15px;"
                         f"font-weight:700;border-radius:12px;border:none;}}"
                         f"QPushButton:hover{{background:{PRIMARY2};}}"
                         f"QPushButton:pressed{{background:#0a3d4a;}}")
        fb.clicked.connect(self._feed)
        cl.addWidget(fb)
        lay.addWidget(ctrl)

        # Log header
        lh = QHBoxLayout()
        lh.addWidget(self._txt("Status Log", TEXT_DARK, 15, bold=True))
        lh.addStretch()
        lh.addWidget(self._txt("VIEW ALL", PRIMARY2, 11, bold=True))
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
        lay = QVBoxLayout(card); lay.setContentsMargins(14,14,14,14); lay.setSpacing(4)
        lay.addWidget(self._txt(title, TEXT_MUTED, 10, bold=True))
        vr = QHBoxLayout(); vr.setSpacing(2)
        val = QLabel("--"); val.setStyleSheet(f"color:{TEXT_DARK};font-size:28px;font-weight:700;")
        u = QLabel(unit); u.setStyleSheet(f"color:{TEXT_MID};font-size:13px;padding-top:10px;")
        vr.addWidget(val); vr.addWidget(u); vr.addStretch()
        lay.addLayout(vr)
        bar = QFrame(); bar.setObjectName("bar"); bar.setFixedHeight(3)
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
            self.temp_val.setStyleSheet(f"color:{col};font-size:28px;font-weight:700;")
            self.temp_bar.setStyleSheet(f"background:{col};border-radius:2px;")
        ph = state["ph"]
        if ph is not None:
            col = get_ph_color(ph)
            self.ph_val.setText(str(ph))
            self.ph_val.setStyleSheet(f"color:{col};font-size:28px;font-weight:700;")
            self.ph_bar.setStyleSheet(f"background:{col};border-radius:2px;")
        is_on = state["light"] == "on"
        self.light_tog.setChecked(is_on)
        if is_on:
            self.light_sub.setText("STATUS: ON")
            self.light_sub.setStyleSheet(f"color:{ACCENT};font-size:10px;font-weight:700;")
        else:
            self.light_sub.setText("STATUS: OFF")
            self.light_sub.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;font-weight:700;")

        # rebuild log rows
        while self.log_lay.count():
            item = self.log_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for i, (ts, lvl, msg) in enumerate(state["events"][:3]):
            self.log_lay.addWidget(self._log_row(ts, lvl, msg, i < 2))

    def _log_row(self, ts, lvl, msg, div):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(w); vl.setContentsMargins(16,12,16,0); vl.setSpacing(0)
        row = QHBoxLayout(); row.setSpacing(12)
        tl = QLabel(ts); tl.setStyleSheet(f"color:{PRIMARY2};font-size:13px;font-weight:600;min-width:40px;")
        ml = QLabel(msg); ml.setStyleSheet(f"color:{TEXT_DARK};font-size:13px;"); ml.setWordWrap(True)
        bc = SUCCESS if lvl in ("SUCCESS","INFO") else (WARNING if lvl == "WARNING" else DANGER)
        bt = "SUCCESS" if lvl == "SUCCESS" else ("INFO" if lvl == "INFO" else lvl)
        row.addWidget(tl); row.addWidget(ml,1); row.addWidget(badge(bt, bc))
        vl.addLayout(row)
        vl.addSpacing(12)
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
        lay = QVBoxLayout(w); lay.setContentsMargins(16,12,16,16); lay.setSpacing(14)

        lay.addWidget(self._txt("Analytics", TEXT_DARK, 26, True))
        lay.addWidget(self._txt("Monitoring aquatic equilibrium over time.", TEXT_MUTED, 13))

        # Pills
        pf = QFrame(); pf.setStyleSheet("background:#E8EDF2;border-radius:10px;")
        pl = QHBoxLayout(pf); pl.setContentsMargins(4,4,4,4); pl.setSpacing(4)
        for i, t in enumerate(["Day","Week","Month"]):
            b = QPushButton(t)
            if i == 0:
                b.setStyleSheet(f"background:{PRIMARY};color:white;border-radius:8px;"
                                f"font-weight:600;font-size:13px;padding:6px 16px;border:none;")
            else:
                b.setStyleSheet(f"background:transparent;color:{TEXT_MID};border-radius:8px;"
                                f"font-size:13px;padding:6px 16px;border:none;")
            pl.addWidget(b)
        ph = QHBoxLayout(); ph.addWidget(pf); ph.addStretch()
        lay.addLayout(ph)

        # Temperature chart card
        tc = QFrame(); tc.setStyleSheet(CARD_STYLE)
        tl = QVBoxLayout(tc); tl.setContentsMargins(16,16,16,16); tl.setSpacing(8)
        th = QHBoxLayout()
        th.addWidget(self._txt("WATER TEMPERATURE", PRIMARY2, 11, True))
        th.addStretch()
        trend = QLabel("↗ 0.2%")
        trend.setStyleSheet(f"background:#E8F8F5;color:{SUCCESS};font-size:11px;"
                            f"font-weight:600;border-radius:6px;padding:2px 8px;")
        th.addWidget(trend)
        tl.addLayout(th)
        self.cur_temp = QLabel("--°C")
        self.cur_temp.setStyleSheet(f"color:{TEXT_DARK};font-size:32px;font-weight:700;")
        tl.addWidget(self.cur_temp)
        self.temp_chart = LineChart(lambda: state["temp_history"], ACCENT, 18, 35)
        tl.addWidget(self.temp_chart)
        tf = QHBoxLayout()
        self.temp_avg = QLabel("Avg: --")
        self.temp_avg.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        self.temp_peak = QLabel("Peak: --")
        self.temp_peak.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        tf.addWidget(self.temp_avg); tf.addStretch(); tf.addWidget(self.temp_peak)
        tl.addLayout(tf)
        lay.addWidget(tc)

        # pH card
        pc = QFrame(); pc.setStyleSheet(CARD_STYLE)
        pl2 = QVBoxLayout(pc); pl2.setContentsMargins(16,16,16,16); pl2.setSpacing(8)
        ph2 = QHBoxLayout()
        ph2.addWidget(self._txt("ACIDITY LEVEL", PRIMARY2, 11, True))
        ph2.addStretch()
        sb = QLabel("✓  STABLE")
        sb.setStyleSheet(f"background:#E8F8F5;color:{SUCCESS};font-size:11px;"
                         f"font-weight:600;border-radius:6px;padding:2px 8px;")
        ph2.addWidget(sb)
        pl2.addLayout(ph2)
        self.cur_ph = QLabel("-- pH")
        self.cur_ph.setStyleSheet(f"color:{TEXT_DARK};font-size:32px;font-weight:700;")
        pl2.addWidget(self.cur_ph)
        self.ph_chart = BarChart(lambda: state["ph_history"], "#A8D5D8", PRIMARY)
        pl2.addWidget(self.ph_chart)
        pf2 = QHBoxLayout()
        pf2.addWidget(self._txt(f"Target: {config.PH_MIN_NORMAL} – {config.PH_MAX_NORMAL}", TEXT_MUTED, 11))
        pf2.addStretch()
        self.ph_last = QLabel("Last: -- pH")
        self.ph_last.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        pf2.addWidget(self.ph_last)
        pl2.addLayout(pf2)
        lay.addWidget(pc)

        # Photoperiod + Salinity
        sr = QHBoxLayout(); sr.setSpacing(12)
        for ico, val, unit in [("☀️","12h","PHOTOPERIOD"),("💧","1.025","SALINITY (SG)")]:
            card = QFrame(); card.setStyleSheet(CARD_STYLE)
            cl = QVBoxLayout(card); cl.setContentsMargins(16,16,16,16); cl.setSpacing(4)
            il = QLabel(ico); il.setStyleSheet("font-size:22px;background:transparent;")
            cl.addWidget(il); cl.addStretch()
            vl = QLabel(val); vl.setStyleSheet(f"color:{TEXT_DARK};font-size:22px;font-weight:700;")
            ul = QLabel(unit); ul.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;font-weight:600;")
            cl.addWidget(vl); cl.addWidget(ul)
            sr.addWidget(card)
        lay.addLayout(sr)

        # Recent Activity
        ah = QHBoxLayout()
        ah.addWidget(self._txt("Recent Activity", TEXT_DARK, 15, True))
        ah.addStretch()
        ah.addWidget(self._txt("View Logs", PRIMARY2, 12, True))
        lay.addLayout(ah)
        self.act_card = QFrame(); self.act_card.setStyleSheet(CARD_STYLE)
        self.act_lay = QVBoxLayout(self.act_card)
        self.act_lay.setContentsMargins(0,0,0,0); self.act_lay.setSpacing(0)
        lay.addWidget(self.act_card)
        lay.addStretch()

    def _txt(self, text, color, size, bold=False):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{'700' if bold else '400'};")
        return l

    def refresh(self):
        t = state["temperature"]
        self.cur_temp.setText(f"{t}°C" if t else "--°C")
        th = state["temp_history"]
        self.temp_avg.setText(f"Avg: {sum(th)/len(th):.1f}°C" if th else "Avg: --")
        self.temp_peak.setText(f"Peak: {max(th):.1f}°C" if th else "Peak: --")
        self.temp_chart.update()

        ph = state["ph"]
        self.cur_ph.setText(f"{ph} pH" if ph else "-- pH")
        self.ph_last.setText(f"Last: {ph} pH" if ph else "Last: -- pH")
        self.ph_chart.update()

        while self.act_lay.count():
            item = self.act_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for i, (ts, lvl, msg) in enumerate(state["events"][:4]):
            row_w = QWidget(); row_w.setStyleSheet("background:transparent;")
            vl = QVBoxLayout(row_w); vl.setContentsMargins(16,12,16,0); vl.setSpacing(0)
            row = QHBoxLayout(); row.setSpacing(12)
            tl = QLabel(ts); tl.setStyleSheet(f"color:{TEXT_DARK};font-size:13px;font-weight:600;min-width:40px;")
            col = QVBoxLayout()
            ml = QLabel(msg); ml.setStyleSheet(f"color:{TEXT_DARK};font-size:13px;")
            sl = QLabel(lvl.upper()); sl.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;font-weight:600;letter-spacing:1px;")
            col.addWidget(ml); col.addWidget(sl)
            row.addWidget(tl); row.addLayout(col); row.addStretch()
            ck = QLabel("✓"); ck.setStyleSheet(f"color:{SUCCESS};font-size:16px;")
            row.addWidget(ck)
            vl.addLayout(row); vl.addSpacing(12)
            if i < 3: vl.addWidget(hdivider())
            self.act_lay.addWidget(row_w)

# ── Schedule ──────────────────────────────────────────────────────────────────
class SchedulePage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background:{BG};")
        w = QWidget(); w.setStyleSheet(f"background:{BG};"); self.setWidget(w)
        lay = QVBoxLayout(w); lay.setContentsMargins(16,12,16,16); lay.setSpacing(14)

        lay.addWidget(self._txt("Automation Schedule", TEXT_DARK, 22, True))
        lay.addWidget(self._txt("Manage your tank's life cycles and routines.", TEXT_MUTED, 13))

        # Light simulation card
        lc = QFrame(); lc.setStyleSheet(CARD_STYLE)
        ll = QVBoxLayout(lc); ll.setContentsMargins(16,16,16,16); ll.setSpacing(12)
        top = QHBoxLayout(); top.setSpacing(8)
        il = QLabel("🌅"); il.setStyleSheet("font-size:18px;")
        top.addWidget(il)
        top.addWidget(self._txt("Light Simulation", TEXT_DARK, 16, True))
        top.addStretch()
        top.addWidget(ToggleSwitch(True))
        ll.addLayout(top)
        tr = QHBoxLayout(); tr.setSpacing(12)
        for lbl, val in [("SUNRISE","06:30 AM"),("SUNSET","08:15 PM")]:
            tf = QFrame(); tf.setStyleSheet("background:#F5F7FA;border-radius:10px;")
            tfl = QVBoxLayout(tf); tfl.setContentsMargins(16,12,16,12); tfl.setSpacing(4)
            tfl.addWidget(self._txt(lbl, TEXT_MUTED, 10, True))
            tfl.addWidget(self._txt(val, PRIMARY, 18, True))
            tr.addWidget(tf)
        ll.addLayout(tr)
        eb = QPushButton("EDIT CYCLE DURATION")
        eb.setStyleSheet(f"QPushButton{{background:transparent;color:{TEXT_DARK};border:1px solid #CBD5E0;"
                         f"border-radius:8px;font-size:12px;font-weight:600;letter-spacing:1px;padding:10px;}}"
                         f"QPushButton:hover{{background:#F0F4F8;}}")
        ll.addWidget(eb)
        lay.addWidget(lc)

        # Routines header
        rh = QHBoxLayout()
        rh.addWidget(self._txt("Daily Routines", TEXT_DARK, 16, True))
        rh.addStretch(); rh.addWidget(badge("3 ACTIVE", PRIMARY2))
        lay.addLayout(rh)

        # Routines card
        rc = QFrame(); rc.setStyleSheet(CARD_STYLE)
        rcl = QVBoxLayout(rc); rcl.setContentsMargins(0,0,0,0); rcl.setSpacing(0)
        routines = [
            ("🍽","Morning Feed","08:00 AM",True,SUCCESS),
            ("💧","CO2 Injection","09:00 AM – 05:00 PM",True,PRIMARY2),
            ("🍽","Evening Feed","06:00 PM",False,TEXT_MUTED),
            ("🧪","Liquid Fertilizers","Mon, Wed, Fri",True,ACCENT),
        ]
        for i,(ico,name,sched,on,col) in enumerate(routines):
            rw = QWidget(); rw.setStyleSheet("background:transparent;")
            rvl = QVBoxLayout(rw); rvl.setContentsMargins(12,14,16,0); rvl.setSpacing(0)
            row = QHBoxLayout(); row.setSpacing(10)
            bar = QFrame(); bar.setFixedWidth(3)
            bar.setStyleSheet(f"background:{col if on else '#E8EDF2'};border-radius:2px;")
            row.addWidget(bar)
            ic = QLabel(ico); ic.setFixedSize(36,36); ic.setAlignment(Qt.AlignCenter)
            ic.setStyleSheet(f"background:{'#E8F8FC' if on else '#F0F4F8'};border-radius:18px;font-size:16px;")
            row.addWidget(ic)
            info = QVBoxLayout(); info.setSpacing(2)
            nl = QLabel(name); nl.setStyleSheet(f"color:{TEXT_DARK if on else TEXT_MUTED};font-size:14px;font-weight:600;")
            prefix = "⏰" if ":" in sched else "📅"
            sl = QLabel(f"{prefix} {sched}"); sl.setStyleSheet(f"color:{TEXT_MUTED};font-size:12px;")
            info.addWidget(nl); info.addWidget(sl)
            row.addLayout(info); row.addStretch()
            row.addWidget(ToggleSwitch(on))
            rvl.addLayout(row); rvl.addSpacing(14)
            if i < len(routines)-1: rvl.addWidget(hdivider())
            rcl.addWidget(rw)
        lay.addWidget(rc)

        ab = QPushButton("  +  Add New Task"); ab.setFixedHeight(52)
        ab.setStyleSheet(f"QPushButton{{background:{PRIMARY};color:white;font-size:15px;"
                         f"font-weight:700;border-radius:12px;border:none;}}"
                         f"QPushButton:hover{{background:{PRIMARY2};}}")
        lay.addWidget(ab)

        lf = QFrame(); lf.setStyleSheet(CARD_STYLE)
        lfl = QVBoxLayout(lf); lfl.setContentsMargins(16,14,16,14); lfl.setSpacing(8)
        lfl.addWidget(self._txt("LAST ACTIONS", TEXT_MUTED, 10, True))
        self.last_lay = QVBoxLayout(); self.last_lay.setSpacing(6)
        lfl.addLayout(self.last_lay)
        lay.addWidget(lf)
        lay.addStretch()

    def _txt(self, text, color, size, bold=False):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{'700' if bold else '400'};")
        return l

    def refresh(self):
        while self.last_lay.count():
            item = self.last_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for ts, lvl, msg in state["events"][:3]:
            rw = QWidget(); rw.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(rw); rl.setContentsMargins(0,0,0,0); rl.setSpacing(8)
            tl = QLabel(ts); tl.setStyleSheet(f"color:{PRIMARY2};font-size:12px;font-weight:600;min-width:45px;")
            status = "OK" if lvl in ("SUCCESS","INFO") else lvl
            ml = QLabel(f"{msg[:35]}... [{status}]" if len(msg)>35 else f"{msg} [{status}]")
            ml.setStyleSheet(f"color:{TEXT_MID};font-size:12px;")
            rl.addWidget(tl); rl.addWidget(ml); rl.addStretch()
            self.last_lay.addWidget(rw)

# ── Settings ──────────────────────────────────────────────────────────────────
class SettingsPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background:{BG};")
        w = QWidget(); w.setStyleSheet(f"background:{BG};"); self.setWidget(w)
        lay = QVBoxLayout(w); lay.setContentsMargins(16,12,16,16); lay.setSpacing(14)

        # Hero
        hero = QFrame(); hero.setFixedHeight(140)
        hero.setStyleSheet("QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                           "stop:0 #1B5E20,stop:1 #388E3C);border-radius:20px;}")
        hl = QVBoxLayout(hero); hl.setContentsMargins(20,20,20,20); hl.addStretch()
        s1 = QLabel("DEVICE PREFERENCES")
        s1.setStyleSheet("color:rgba(255,255,255,0.7);font-size:10px;font-weight:600;"
                         "letter-spacing:2px;background:transparent;")
        s2 = QLabel("Settings & Alerts")
        s2.setStyleSheet("color:white;font-size:22px;font-weight:700;background:transparent;")
        hl.addWidget(s1); hl.addWidget(s2)
        lay.addWidget(hero)

        # Notification Preferences
        lay.addWidget(section_lbl("NOTIFICATION PREFERENCES"))
        nc = QFrame(); nc.setStyleSheet(CARD_STYLE)
        nl = QVBoxLayout(nc); nl.setContentsMargins(0,0,0,0); nl.setSpacing(0)
        nl.addWidget(self._notif_row("🔔","Push Notifications","Real-time alerts on your device",True))
        nl.addWidget(hdivider())
        nl.addWidget(self._notif_row("✉️","Email Alerts","Daily summaries and critical logs",False))
        lay.addWidget(nc)

        # Safe Ranges
        lay.addWidget(section_lbl("SAFE RANGES & ALERTS"))
        rc = QFrame(); rc.setStyleSheet(CARD_STYLE)
        rl = QVBoxLayout(rc); rl.setContentsMargins(16,16,16,16); rl.setSpacing(10)
        tr = QHBoxLayout()
        tr.addWidget(QLabel("🌡")); tr.addWidget(self._txt("Temperature Range", TEXT_DARK, 14))
        tr.addStretch()
        tr.addWidget(self._txt(f"{config.TEMP_MIN_NORMAL}°C – {config.TEMP_MAX_NORMAL}°C", PRIMARY2, 14, True))
        rl.addLayout(tr)
        ts = QSlider(Qt.Horizontal); ts.setRange(150,350); ts.setValue(250)
        ts.setStyleSheet(self._slider_style()); rl.addWidget(ts)
        labels = QHBoxLayout()
        for t in [f"MIN: {config.TEMP_MIN_ALARM}°C","IDEAL ZONE",f"MAX: {config.TEMP_MAX_ALARM}°C"]:
            l = QLabel(t); l.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
            if t == "IDEAL ZONE": l.setAlignment(Qt.AlignCenter); labels.addWidget(l,1)
            else: labels.addWidget(l)
        rl.addLayout(labels)
        rl.addWidget(hdivider())
        pr = QHBoxLayout()
        pr.addWidget(QLabel("💧")); pr.addWidget(self._txt("pH Level Limit", TEXT_DARK, 14))
        pr.addStretch()
        pr.addWidget(self._txt(f"{config.PH_MIN_NORMAL} – {config.PH_MAX_NORMAL}", PRIMARY2, 14, True))
        rl.addLayout(pr)
        ps = QSlider(Qt.Horizontal); ps.setRange(50,90); ps.setValue(70)
        ps.setStyleSheet(self._slider_style()); rl.addWidget(ps)
        lay.addWidget(rc)

        # Sensor Calibration
        lay.addWidget(section_lbl("SENSOR CALIBRATION"))
        cc = QFrame(); cc.setStyleSheet(CARD_STYLE)
        cl = QVBoxLayout(cc); cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)
        cl.addWidget(self._calib_row("🔬","Temperature Probe","Last calibrated: 12 days ago"))
        cl.addWidget(hdivider())
        cl.addWidget(self._calib_row("💧","Water Level Sensor","Automatic calibration active"))
        lay.addWidget(cc)

        # Device Info
        lay.addWidget(section_lbl("DEVICE INFORMATION"))
        ic = QFrame(); ic.setStyleSheet(CARD_STYLE)
        il = QVBoxLayout(ic); il.setContentsMargins(16,8,16,8); il.setSpacing(0)
        for ico, lbl, val in [("⚙️","Firmware Version","v2.4.12-stable"),
                               ("📶","Wi-Fi Signal Strength","-54 dBm"),
                               ("🌐","Network SSID","AquaNet_2.4G")]:
            row = QHBoxLayout()
            row.addWidget(self._txt(f"{ico}  {lbl}", TEXT_MID, 13))
            row.addStretch()
            vl = QLabel(val)
            vl.setStyleSheet(f"color:{PRIMARY};font-size:13px;font-weight:600;font-family:monospace;")
            row.addWidget(vl)
            il.addSpacing(12); il.addLayout(row)
        il.addSpacing(12)
        lay.addWidget(ic)

        rb = QPushButton("  ↺  Reset Device to Factory Settings"); rb.setFixedHeight(52)
        rb.setStyleSheet(f"QPushButton{{background:transparent;color:{DANGER};border:1.5px solid {DANGER};"
                         f"border-radius:12px;font-size:14px;font-weight:600;}}"
                         f"QPushButton:hover{{background:#FFF0F0;}}")
        lay.addWidget(rb)
        lay.addStretch()

    def _txt(self, text, color, size, bold=False):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{'700' if bold else '400'};")
        return l

    def _slider_style(self):
        return (f"QSlider::groove:horizontal{{height:4px;background:#E8EDF2;border-radius:2px;}}"
                f"QSlider::sub-page:horizontal{{background:{ACCENT};border-radius:2px;}}"
                f"QSlider::handle:horizontal{{background:{PRIMARY};border-radius:8px;"
                f"width:16px;height:16px;margin:-6px 0;}}")

    def _notif_row(self, ico, title, sub, checked):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        row = QHBoxLayout(w); row.setContentsMargins(16,14,16,14); row.setSpacing(12)
        il = QLabel(ico); il.setFixedSize(36,36); il.setAlignment(Qt.AlignCenter)
        il.setStyleSheet("background:#F0F4F8;border-radius:18px;font-size:16px;")
        row.addWidget(il)
        info = QVBoxLayout(); info.setSpacing(2)
        info.addWidget(self._txt(title, TEXT_DARK, 14, True))
        info.addWidget(self._txt(sub, TEXT_MUTED, 11))
        row.addLayout(info); row.addStretch()
        row.addWidget(ToggleSwitch(checked))
        return w

    def _calib_row(self, ico, title, sub):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        row = QHBoxLayout(w); row.setContentsMargins(16,14,16,14); row.setSpacing(12)
        il = QLabel(ico); il.setFixedSize(36,36); il.setAlignment(Qt.AlignCenter)
        il.setStyleSheet("background:#F0F4F8;border-radius:18px;font-size:16px;")
        row.addWidget(il)
        info = QVBoxLayout(); info.setSpacing(2)
        info.addWidget(self._txt(title, TEXT_DARK, 14, True))
        info.addWidget(self._txt(sub, TEXT_MUTED, 11))
        row.addLayout(info); row.addStretch()
        arr = QLabel(">"); arr.setStyleSheet(f"color:{TEXT_MUTED};font-size:18px;")
        row.addWidget(arr)
        return w

    def refresh(self):
        pass

# ── Nav Button ────────────────────────────────────────────────────────────────
class NavButton(QPushButton):
    def __init__(self, icon, label, parent=None):
        super().__init__(parent)
        self._icon = icon; self._label = label; self._active = False
        self.setFixedHeight(60); self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True); self._style()

    def set_active(self, on):
        self._active = on; self._style()

    def _style(self):
        self.setText(f"{self._icon}\n{self._label}")
        if self._active:
            self.setStyleSheet(f"QPushButton{{background:{ACCENT};color:{PRIMARY};font-size:11px;"
                               f"font-weight:700;border-radius:14px;padding:6px 4px;border:none;}}")
        else:
            self.setStyleSheet(f"QPushButton{{background:transparent;color:{TEXT_MUTED};font-size:11px;"
                               f"font-weight:500;border-radius:14px;padding:6px 4px;border:none;}}"
                               f"QPushButton:hover{{color:{TEXT_MID};}}")

# ── Main Window ───────────────────────────────────────────────────────────────
class AquariumApp(QMainWindow):
    def __init__(self, mqtt_client):
        super().__init__()
        self.mqtt_client = mqtt_client
        self.setWindowTitle("Aquarium Monitor")
        self.setFixedWidth(400)
        self.setMinimumHeight(760)
        self.setStyleSheet(f"background:{BG};")
        self._build()
        self.timer = QTimer(); self.timer.timeout.connect(self._tick); self.timer.start(1000)

    def _build(self):
        root = QWidget(); root.setStyleSheet(f"background:{BG};"); self.setCentralWidget(root)
        rl = QVBoxLayout(root); rl.setContentsMargins(0,0,0,0); rl.setSpacing(0)

        # Top bar
        tb = QWidget(); tb.setStyleSheet(f"background:{WHITE};border-bottom:1px solid #E8EDF2;")
        tb.setFixedHeight(56)
        tbl = QHBoxLayout(tb); tbl.setContentsMargins(16,0,16,0)
        logo = QLabel("≋  Aquarium Monitor")
        logo.setStyleSheet(f"color:{PRIMARY};font-size:18px;font-weight:700;")
        tbl.addWidget(logo); tbl.addStretch()
        bell = QLabel("🔔"); bell.setStyleSheet("font-size:20px;")
        tbl.addWidget(bell)
        rl.addWidget(tb)

        # Pages
        self.stack = QStackedWidget()
        self.dash = DashboardPage(self.mqtt_client)
        self.stats = StatsPage()
        self.sched = SchedulePage()
        self.sett = SettingsPage()
        for p in [self.dash, self.stats, self.sched, self.sett]:
            self.stack.addWidget(p)
        rl.addWidget(self.stack, 1)

        # Nav bar
        nb = QWidget(); nb.setStyleSheet(f"background:{WHITE};border-top:1px solid #E8EDF2;")
        nb.setFixedHeight(68)
        nbl = QHBoxLayout(nb); nbl.setContentsMargins(8,4,8,4); nbl.setSpacing(4)
        self.nav = []
        for i,(ico,lbl) in enumerate([("⊞","Dashboard"),("📊","Stats"),("📅","Schedule"),("⚙","Settings")]):
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
    app.setFont(QFont("Segoe UI", 10))
    win = AquariumApp(client)
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
