import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from PyQt5.QtWidgets import (QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame)
from PyQt5.QtCore import Qt
from gui.palette import (PRIMARY, PRIMARY2, BG, WHITE, TEXT_DARK, TEXT_MID,
                         TEXT_MUTED, SUCCESS, WARNING, CARD_STYLE)
from gui.state import allowed_ranges, temp_warn_pct, ph_warn_pct, save_allowed_ranges, add_event, TOPIC_THRESHOLDS
from gui.widgets import RangeSlider, ToggleSwitch, section_lbl, hdivider, make_txt
import json


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
        lay = QVBoxLayout(w); lay.setContentsMargins(24, 18, 24, 24); lay.setSpacing(20)

        # Hero
        hero = QFrame(); hero.setFixedHeight(200)
        hero.setStyleSheet("QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                           "stop:0 #1B5E20,stop:1 #388E3C);border-radius:24px;}")
        hl = QVBoxLayout(hero); hl.setContentsMargins(28, 28, 28, 28); hl.addStretch()
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
        nl = QVBoxLayout(nc); nl.setContentsMargins(0, 0, 0, 0); nl.setSpacing(0)
        nl.addWidget(self._notif_row("🔔", "Push Notifications", "Real-time alerts on your device", True))
        lay.addWidget(nc)

        # Safe Ranges
        lay.addWidget(section_lbl("SAFE RANGES & ALERTS"))
        rc = QFrame(); rc.setStyleSheet(CARD_STYLE)
        rl = QVBoxLayout(rc); rl.setContentsMargins(22, 22, 22, 22); rl.setSpacing(16)

        # Temperature
        th = QHBoxLayout()
        th.addWidget(QLabel("🌡"))
        th.addWidget(make_txt("Temperature Range", TEXT_DARK, 18))
        th.addStretch()
        rl.addLayout(th)
        sr = QHBoxLayout(); sr.setSpacing(10)
        slbl = make_txt("✓ Safe", SUCCESS, 13, True); slbl.setFixedWidth(90)
        sr.addWidget(slbl)
        self.temp_safe_slider = RangeSlider(
            allowed_ranges["temp_safe_min"], allowed_ranges["temp_safe_max"], 10.0, 40.0)
        self.temp_safe_slider.range_changed.connect(self._on_temp_safe)
        sr.addWidget(self.temp_safe_slider, 1)
        self.temp_safe_lbl = make_txt(
            f"{allowed_ranges['temp_safe_min']}°C – {allowed_ranges['temp_safe_max']}°C",
            SUCCESS, 13, True)
        self.temp_safe_lbl.setFixedWidth(110)
        sr.addWidget(self.temp_safe_lbl)
        rl.addLayout(sr)
        rl.addLayout(self._pct_row("temp"))
        self.temp_warn_info = make_txt("", WARNING, 13)
        rl.addWidget(self.temp_warn_info)
        self._update_temp_warn_info()
        rl.addWidget(hdivider())

        # pH
        ph_h = QHBoxLayout()
        ph_h.addWidget(QLabel("💧"))
        ph_h.addWidget(make_txt("pH Level Range", TEXT_DARK, 18))
        ph_h.addStretch()
        rl.addLayout(ph_h)
        psr = QHBoxLayout(); psr.setSpacing(10)
        pslbl = make_txt("✓ Safe", SUCCESS, 13, True); pslbl.setFixedWidth(90)
        psr.addWidget(pslbl)
        self.ph_safe_slider = RangeSlider(
            allowed_ranges["ph_safe_min"], allowed_ranges["ph_safe_max"], 4.0, 10.0)
        self.ph_safe_slider.range_changed.connect(self._on_ph_safe)
        psr.addWidget(self.ph_safe_slider, 1)
        self.ph_safe_lbl = make_txt(
            f"{allowed_ranges['ph_safe_min']} – {allowed_ranges['ph_safe_max']}",
            SUCCESS, 13, True)
        self.ph_safe_lbl.setFixedWidth(110)
        psr.addWidget(self.ph_safe_lbl)
        rl.addLayout(psr)
        rl.addLayout(self._pct_row("ph"))
        self.ph_warn_info = make_txt("", WARNING, 13)
        rl.addWidget(self.ph_warn_info)
        self._update_ph_warn_info()

        lay.addWidget(rc)
        lay.addStretch()

    def _pct_row(self, param):
        row = QHBoxLayout(); row.setSpacing(8)
        row.addWidget(make_txt("⚠ Warning buffer:", WARNING, 13, True))
        current = self._temp_pct if param == "temp" else self._ph_pct
        btns = {}
        for pct in self._PCT_OPTIONS:
            btn = QPushButton(f"{pct}%")
            btn.setCheckable(True); btn.setChecked(pct == current); btn.setFixedSize(60, 34)
            self._style_pct_btn(btn, pct == current)
            btn.clicked.connect(lambda _, p=pct, par=param: self._on_pct_clicked(par, p))
            btns[pct] = btn; row.addWidget(btn)
        setattr(self, f"_{param}_pct_btns", btns)
        row.addStretch()
        return row

    def _style_pct_btn(self, btn, active):
        if active:
            btn.setStyleSheet(
                f"QPushButton{{background:{WARNING};color:white;font-size:14px;font-weight:700;"
                f"border-radius:10px;border:none;}}QPushButton:hover{{background:{WARNING};}}")
        else:
            btn.setStyleSheet(
                "QPushButton{background:#F0F4F8;color:#64748B;font-size:14px;font-weight:600;"
                "border-radius:10px;border:none;}QPushButton:hover{background:#E2E8F0;}")

    def _on_pct_clicked(self, param, pct):
        if param == "temp":
            self._temp_pct = pct
            for p, b in self._temp_pct_btns.items():
                self._style_pct_btn(b, p == pct)
            self._recompute_warn("temp"); self._update_temp_warn_info()
        else:
            self._ph_pct = pct
            for p, b in self._ph_pct_btns.items():
                self._style_pct_btn(b, p == pct)
            self._recompute_warn("ph"); self._update_ph_warn_info()
        self._publish_thresholds()

    def _recompute_warn(self, param):
        import gui.state as gs
        if param == "temp":
            gs.temp_warn_pct = self._temp_pct
            span = allowed_ranges["temp_safe_max"] - allowed_ranges["temp_safe_min"]
            buf  = span * self._temp_pct / 100
            allowed_ranges["temp_warn_min"] = round(allowed_ranges["temp_safe_min"] + buf, 1)
            allowed_ranges["temp_warn_max"] = round(allowed_ranges["temp_safe_max"] - buf, 1)
        else:
            gs.ph_warn_pct = self._ph_pct
            span = allowed_ranges["ph_safe_max"] - allowed_ranges["ph_safe_min"]
            buf  = span * self._ph_pct / 100
            allowed_ranges["ph_warn_min"] = round(allowed_ranges["ph_safe_min"] + buf, 1)
            allowed_ranges["ph_warn_max"] = round(allowed_ranges["ph_safe_max"] - buf, 1)

    def _update_temp_warn_info(self):
        s_min = allowed_ranges["temp_safe_min"]; s_max = allowed_ranges["temp_safe_max"]
        w_min = allowed_ranges["temp_warn_min"]; w_max = allowed_ranges["temp_warn_max"]
        self.temp_warn_info.setText(f"Warn when: {s_min}–{w_min}°C  or  {w_max}–{s_max}°C")

    def _update_ph_warn_info(self):
        s_min = allowed_ranges["ph_safe_min"]; s_max = allowed_ranges["ph_safe_max"]
        w_min = allowed_ranges["ph_warn_min"]; w_max = allowed_ranges["ph_warn_max"]
        self.ph_warn_info.setText(f"Warn when: {s_min}–{w_min}  or  {w_max}–{s_max}")

    def _on_temp_safe(self, mn, mx):
        allowed_ranges["temp_safe_min"] = mn; allowed_ranges["temp_safe_max"] = mx
        self.temp_safe_lbl.setText(f"{mn}°C – {mx}°C")
        self._recompute_warn("temp"); self._update_temp_warn_info(); self._publish_thresholds()

    def _on_ph_safe(self, mn, mx):
        allowed_ranges["ph_safe_min"] = mn; allowed_ranges["ph_safe_max"] = mx
        self.ph_safe_lbl.setText(f"{mn} – {mx}")
        self._recompute_warn("ph"); self._update_ph_warn_info(); self._publish_thresholds()

    def _notif_row(self, ico, title, sub, checked):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        row = QHBoxLayout(w); row.setContentsMargins(22, 18, 22, 18); row.setSpacing(16)
        il = QLabel(ico); il.setFixedSize(50, 50); il.setAlignment(Qt.AlignCenter)
        il.setStyleSheet("background:#F0F4F8;border-radius:25px;font-size:22px;")
        row.addWidget(il)
        info = QVBoxLayout(); info.setSpacing(4)
        info.addWidget(make_txt(title, TEXT_DARK, 18, True))
        info.addWidget(make_txt(sub, TEXT_MUTED, 14))
        row.addLayout(info); row.addStretch()
        row.addWidget(ToggleSwitch(checked))
        return w

    def _publish_thresholds(self):
        try:
            self.mqtt_client.publish(TOPIC_THRESHOLDS, json.dumps(allowed_ranges))
        except Exception:
            add_event("WARNING", "Failed to publish threshold update")
        save_allowed_ranges(allowed_ranges)

    def refresh(self):
        pass
