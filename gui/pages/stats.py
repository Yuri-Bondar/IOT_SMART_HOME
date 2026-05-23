import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from PyQt5.QtWidgets import (QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QFrame)
from PyQt5.QtCore import Qt
from gui.palette import (PRIMARY2, BG, WHITE, TEXT_DARK, TEXT_MUTED, ACCENT, CARD_STYLE)
from gui.state import state, allowed_ranges, MAX_HISTORY
from gui.widgets import LineChart, make_txt


class StatsPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background:{BG};")
        w = QWidget(); w.setStyleSheet(f"background:{BG};"); self.setWidget(w)
        lay = QVBoxLayout(w); lay.setContentsMargins(24, 18, 24, 24); lay.setSpacing(20)

        lay.addWidget(make_txt("Analytics", TEXT_DARK, 38, True))
        lay.addWidget(make_txt("Monitoring aquatic equilibrium over time.", TEXT_MUTED, 18))

        # Temperature chart card
        tc = QFrame(); tc.setStyleSheet(CARD_STYLE)
        tl = QVBoxLayout(tc); tl.setContentsMargins(22, 22, 22, 22); tl.setSpacing(12)
        th = QHBoxLayout()
        th.addWidget(make_txt("WATER TEMPERATURE", PRIMARY2, 15, True))
        th.addStretch()
        tl.addLayout(th)
        self.cur_temp = QLabel("--°C")
        self.cur_temp.setStyleSheet(f"color:{TEXT_DARK};font-size:48px;font-weight:700;")
        tl.addWidget(self.cur_temp)
        self.temp_chart = LineChart(self._get_temp_data, ACCENT, 10, 40, time_axis=True,
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
        self.temp_target_lbl = make_txt(
            f"Target: {allowed_ranges['temp_safe_min']}°C – {allowed_ranges['temp_safe_max']}°C",
            TEXT_MUTED, 15)
        tl.addWidget(self.temp_target_lbl)
        lay.addWidget(tc)

        # pH chart card
        pc = QFrame(); pc.setStyleSheet(CARD_STYLE)
        pl = QVBoxLayout(pc); pl.setContentsMargins(22, 22, 22, 22); pl.setSpacing(12)
        ph = QHBoxLayout()
        ph.addWidget(make_txt("ACIDITY LEVEL", PRIMARY2, 15, True))
        ph.addStretch()
        pl.addLayout(ph)
        self.cur_ph = QLabel("-- pH")
        self.cur_ph.setStyleSheet(f"color:{TEXT_DARK};font-size:48px;font-weight:700;")
        pl.addWidget(self.cur_ph)
        self.ph_chart = LineChart(self._get_ph_data, "#A8D5D8", 4, 10, time_axis=True,
                                  target_lo=allowed_ranges["ph_safe_min"],
                                  target_hi=allowed_ranges["ph_safe_max"])
        pl.addWidget(self.ph_chart)
        pf = QHBoxLayout()
        self.ph_target_lbl = make_txt(
            f"Target: {allowed_ranges['ph_safe_min']} – {allowed_ranges['ph_safe_max']}",
            TEXT_MUTED, 15)
        pf.addWidget(self.ph_target_lbl)
        pf.addStretch()
        self.ph_last = QLabel("Last: -- pH")
        self.ph_last.setStyleSheet(f"color:{TEXT_MUTED};font-size:15px;")
        pf.addWidget(self.ph_last)
        pl.addLayout(pf)
        lay.addWidget(pc)

        lay.addStretch()

    def _get_temp_data(self):
        data = state["temp_history"]
        return data[-MAX_HISTORY:] if len(data) > MAX_HISTORY else list(data)

    def _get_ph_data(self):
        data = state["ph_history"]
        return data[-MAX_HISTORY:] if len(data) > MAX_HISTORY else list(data)

    def refresh(self):
        t = state["temperature"]
        self.cur_temp.setText(f"{t}°C" if t is not None else "--°C")
        th = self._get_temp_data()
        self.temp_avg.setText(f"Avg: {sum(th)/len(th):.1f}°C" if th else "Avg: --")
        self.temp_peak.setText(f"Peak: {max(th):.1f}°C" if th else "Peak: --")
        self.temp_chart.target_lo = allowed_ranges["temp_safe_min"]
        self.temp_chart.target_hi = allowed_ranges["temp_safe_max"]
        self.temp_chart.update()

        ph = state["ph"]
        self.cur_ph.setText(f"{ph} pH" if ph is not None else "-- pH")
        self.ph_last.setText(f"Last: {ph} pH" if ph is not None else "Last: -- pH")
        self.ph_chart.target_lo = allowed_ranges["ph_safe_min"]
        self.ph_chart.target_hi = allowed_ranges["ph_safe_max"]
        self.ph_chart.update()
        self.temp_target_lbl.setText(
            f"Target: {allowed_ranges['temp_safe_min']}°C – {allowed_ranges['temp_safe_max']}°C")
        self.ph_target_lbl.setText(
            f"Target: {allowed_ranges['ph_safe_min']} – {allowed_ranges['ph_safe_max']}")
