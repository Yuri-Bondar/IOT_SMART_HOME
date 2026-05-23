import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import json
from datetime import datetime
from PyQt5.QtWidgets import (QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame)
from PyQt5.QtCore import Qt
import config
from gui.palette import (PRIMARY, PRIMARY2, ACCENT, BG, WHITE, TEXT_DARK,
                         TEXT_MID, TEXT_MUTED, SUCCESS, WARNING, DANGER, CARD_STYLE)
from gui.state import state, add_event, get_temp_color, get_ph_color
from gui.widgets import ToggleSwitch, hdivider, badge, make_txt


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
        hl = QVBoxLayout(hero); hl.setContentsMargins(28, 28, 28, 28)
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
        cl = QVBoxLayout(ctrl); cl.setContentsMargins(24, 24, 24, 24); cl.setSpacing(18)
        lr = QHBoxLayout(); lr.setSpacing(16)
        ic = QLabel("💡"); ic.setFixedSize(56, 56); ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(f"background:{ACCENT};border-radius:28px;font-size:26px;")
        lr.addWidget(ic)
        info = QVBoxLayout(); info.setSpacing(4)
        info.addWidget(make_txt("Aquarium Light", TEXT_DARK, 20, bold=True))
        self.light_sub = make_txt("STATUS: OFF", TEXT_MUTED, 14, bold=True)
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

        # Log
        lh = QHBoxLayout()
        lh.addWidget(make_txt("Status Log", TEXT_DARK, 20, bold=True))
        lh.addStretch()
        lh.addWidget(make_txt("VIEW ALL", PRIMARY2, 15, bold=True))
        lay.addLayout(lh)

        self.log_card = QFrame(); self.log_card.setStyleSheet(CARD_STYLE)
        self.log_lay = QVBoxLayout(self.log_card)
        self.log_lay.setContentsMargins(0, 0, 0, 0); self.log_lay.setSpacing(0)
        lay.addWidget(self.log_card)
        lay.addStretch()

    def _sensor_card(self, title, unit):
        card = QFrame(); card.setStyleSheet(CARD_STYLE)
        lay = QVBoxLayout(card); lay.setContentsMargins(20, 20, 20, 20); lay.setSpacing(6)
        lay.addWidget(make_txt(title, TEXT_MUTED, 14, bold=True))
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
        except Exception:
            add_event("WARNING", "Failed to send light command")

    def _feed(self):
        try:
            self.mqtt_client.publish(config.TOPIC_FEEDING_CMD,
                json.dumps({"action": "feed", "amount": "normal",
                            "timestamp": datetime.now().isoformat()}))
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
        vl = QVBoxLayout(w); vl.setContentsMargins(22, 16, 22, 0); vl.setSpacing(0)
        row = QHBoxLayout(); row.setSpacing(16)
        tl = QLabel(ts); tl.setStyleSheet(f"color:{PRIMARY2};font-size:18px;font-weight:600;min-width:55px;")
        ml = QLabel(msg); ml.setStyleSheet(f"color:{TEXT_DARK};font-size:18px;"); ml.setWordWrap(True)
        bc = SUCCESS if lvl in ("SUCCESS", "INFO") else (WARNING if lvl == "WARNING" else DANGER)
        bt = "SUCCESS" if lvl == "SUCCESS" else ("INFO" if lvl == "INFO" else lvl)
        row.addWidget(tl); row.addWidget(ml, 1); row.addWidget(badge(bt, bc))
        vl.addLayout(row)
        vl.addSpacing(16)
        if div: vl.addWidget(hdivider())
        return w
