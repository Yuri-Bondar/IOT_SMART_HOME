import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QStackedWidget)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

from gui.palette import PRIMARY, PRIMARY2, ACCENT, BG, WHITE, TEXT_MUTED
from gui.pages.dashboard import DashboardPage
from gui.pages.stats import StatsPage
from gui.pages.schedule import SchedulePage
from gui.pages.settings import SettingsPage


class NavButton(QPushButton):
    def __init__(self, icon, label, parent=None):
        super().__init__(parent)
        self._active = False
        self.setFixedHeight(80)
        self.setCursor(Qt.PointingHandCursor)
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
        self._active = on
        self._style()

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


class AquariumApp(QMainWindow):
    def __init__(self, mqtt_client):
        super().__init__()
        self.mqtt_client = mqtt_client
        self.setWindowTitle("Aquarium Monitor")
        self.setMinimumSize(1100, 1000)
        self.resize(1200, 1050)
        self.setStyleSheet(f"background:{BG};")
        self._build()
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def _build(self):
        root = QWidget(); root.setStyleSheet(f"background:{BG};")
        self.setCentralWidget(root)
        rl = QVBoxLayout(root); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)

        # Top bar
        tb = QWidget(); tb.setStyleSheet(f"background:{WHITE};border-bottom:1px solid #E8EDF2;")
        tb.setFixedHeight(76)
        tbl = QHBoxLayout(tb); tbl.setContentsMargins(24, 0, 24, 0)
        logo = QLabel("≋  Aquarium Monitor")
        logo.setStyleSheet(f"color:{PRIMARY};font-size:26px;font-weight:700;")
        tbl.addWidget(logo); tbl.addStretch()
        bell = QLabel("🔔"); bell.setStyleSheet("font-size:28px;")
        tbl.addWidget(bell)
        rl.addWidget(tb)

        # Pages
        self.stack = QStackedWidget()
        self.dash  = DashboardPage(self.mqtt_client)
        self.stats = StatsPage()
        self.sched = SchedulePage(self.mqtt_client)
        self.sett  = SettingsPage(self.mqtt_client)
        for p in [self.dash, self.stats, self.sched, self.sett]:
            self.stack.addWidget(p)
        rl.addWidget(self.stack, 1)

        # Nav bar
        nb = QWidget(); nb.setStyleSheet(f"background:{WHITE};border-top:1px solid #E8EDF2;")
        nb.setFixedHeight(90)
        nbl = QHBoxLayout(nb); nbl.setContentsMargins(12, 6, 12, 6); nbl.setSpacing(6)
        self.nav = []
        nav_items = [("", "Dashboard"), ("", "Stats"), ("", "Schedule"), ("", "Settings")]
        for i, (ico, lbl) in enumerate(nav_items):
            btn = NavButton(ico, lbl)
            btn.clicked.connect(lambda _, idx=i: self._switch(idx))
            nbl.addWidget(btn); self.nav.append(btn)
        self.nav[0].set_active(True)
        rl.addWidget(nb)

    def _switch(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav):
            b.set_active(i == idx)

    def _tick(self):
        idx = self.stack.currentIndex()
        pages = [self.dash, self.stats, self.sched, self.sett]
        pages[idx].refresh()
