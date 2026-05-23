import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import json
import sqlite3
from PyQt5.QtWidgets import (QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QDialog, QLineEdit, QTimeEdit)
from PyQt5.QtCore import Qt, QTime
from gui.palette import (PRIMARY, PRIMARY2, ACCENT, BG, WHITE, TEXT_DARK, TEXT_MID,
                         TEXT_MUTED, SUCCESS, CARD_STYLE)
from gui.widgets import ToggleSwitch, hdivider, badge, make_txt
from gui.state import DB_PATH as _DB_PATH
import config


def _fmt_time(t24):
    h, m = map(int, t24.split(":"))
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12:02d}:{m:02d} {suffix}"

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
        self._lay.setContentsMargins(24, 18, 24, 24); self._lay.setSpacing(20)

        self._lay.addWidget(make_txt("Automation Schedule", TEXT_DARK, 32, True))
        self._lay.addWidget(make_txt("Manage your tank's life cycles and routines.", TEXT_MUTED, 18))

        # Light schedule card
        lc = QFrame(); lc.setStyleSheet(CARD_STYLE)
        ll = QVBoxLayout(lc); ll.setContentsMargins(22, 22, 22, 22); ll.setSpacing(16)
        top = QHBoxLayout(); top.setSpacing(12)
        il = QLabel("🌅"); il.setStyleSheet("font-size:26px;")
        top.addWidget(il)
        top.addWidget(make_txt("Light Simulation", TEXT_DARK, 22, True))
        top.addStretch()
        top.addWidget(ToggleSwitch(True))
        ll.addLayout(top)

        ls = load_light_schedule()
        tr = QHBoxLayout(); tr.setSpacing(16)
        for key, lbl in [("on_time", "LIGHT ON"), ("off_time", "LIGHT OFF")]:
            tf = QFrame(); tf.setStyleSheet("background:#F5F7FA;border-radius:14px;")
            tf.setCursor(Qt.PointingHandCursor)
            tfl = QVBoxLayout(tf); tfl.setContentsMargins(20, 16, 20, 16); tfl.setSpacing(6)
            tfl.addWidget(make_txt(lbl, TEXT_MUTED, 14, True))
            val_lbl = QLabel(_fmt_time(ls[key]))
            val_lbl.setStyleSheet(
                f"color:{PRIMARY};font-size:24px;font-weight:700;text-decoration:underline;")
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
        rh = QHBoxLayout()
        rh.addWidget(make_txt("Daily Routines", TEXT_DARK, 22, True))
        rh.addStretch()
        self._active_badge = badge("0 ACTIVE", PRIMARY2)
        rh.addWidget(self._active_badge)
        self._lay.addLayout(rh)

        self._feed_card = QFrame(); self._feed_card.setStyleSheet(CARD_STYLE)
        self._feed_card_lay = QVBoxLayout(self._feed_card)
        self._feed_card_lay.setContentsMargins(0, 0, 0, 0); self._feed_card_lay.setSpacing(0)
        self._lay.addWidget(self._feed_card)

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

    def _rebuild_feed_rows(self):
        while self._feed_card_lay.count():
            item = self._feed_card_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        routines = load_feeding_schedules()
        active = sum(1 for r in routines if r["enabled"])
        self._active_badge.setText(f"{active} ACTIVE")
        row_colors = [SUCCESS, PRIMARY2, ACCENT, TEXT_MUTED]
        for i, r in enumerate(routines):
            on = r["enabled"]
            col = row_colors[i % len(row_colors)] if on else TEXT_MUTED
            rw = QWidget(); rw.setStyleSheet("background:transparent;")
            rvl = QVBoxLayout(rw); rvl.setContentsMargins(16, 18, 22, 0); rvl.setSpacing(0)
            row = QHBoxLayout(); row.setSpacing(14)
            bar = QFrame(); bar.setFixedWidth(4)
            bar.setStyleSheet(f"background:{col if on else '#E8EDF2'};border-radius:2px;")
            row.addWidget(bar)
            ic = QLabel("🍽"); ic.setFixedSize(50, 50); ic.setAlignment(Qt.AlignCenter)
            ic.setStyleSheet(f"background:{'#E8F8FC' if on else '#F0F4F8'};border-radius:25px;font-size:22px;")
            row.addWidget(ic)
            info = QVBoxLayout(); info.setSpacing(4)
            nl = QLabel(r["name"])
            nl.setStyleSheet(f"color:{TEXT_DARK if on else TEXT_MUTED};font-size:18px;font-weight:600;")
            sl = QLabel(f"⏰ {_fmt_time(r['time'])}")
            sl.setStyleSheet(f"color:{TEXT_MUTED};font-size:16px;")
            info.addWidget(nl); info.addWidget(sl)
            row.addLayout(info); row.addStretch()
            rid = r["id"]
            ts = ToggleSwitch(on)
            ts.toggled.connect(lambda checked, _id=rid, _r=r: self._on_toggle(_id, _r, checked))
            row.addWidget(ts)
            edit_btn = QPushButton("Edit"); edit_btn.setFixedHeight(28)
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.setStyleSheet(
                "QPushButton{background:transparent;color:#4A5568;font-size:12px;font-weight:400;"
                "border:1px solid #E0E0E0;border-radius:6px;padding:4px 10px;}"
                f"QPushButton:hover{{background:#F5F5F5;border-color:{PRIMARY};}}")
            edit_btn.clicked.connect(lambda _, _id=rid, _r=r: self._open_edit_dialog(_id, _r))
            row.addWidget(edit_btn)
            del_btn = QPushButton("Remove"); del_btn.setFixedHeight(28)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet(
                "QPushButton{background:transparent;color:#E57373;font-size:12px;font-weight:400;"
                "border:1px solid #FFCDD2;border-radius:6px;padding:4px 10px;}"
                "QPushButton:hover{background:#FFEBEE;border-color:#E57373;}")
            del_btn.clicked.connect(lambda _, _id=rid: self._delete_row(_id))
            row.addWidget(del_btn)
            rvl.addLayout(row); rvl.addSpacing(18)
            if i < len(routines) - 1:
                rvl.addWidget(hdivider())
            self._feed_card_lay.addWidget(rw)

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
        lay = QVBoxLayout(dlg); lay.setContentsMargins(24, 24, 24, 24); lay.setSpacing(12)
        title_lbl = QLabel("Edit Light Schedule")
        title_lbl.setStyleSheet(f"color:{PRIMARY2};font-size:16px;font-weight:700;background:transparent;")
        lay.addWidget(title_lbl)
        field_style = ("QTimeEdit{background:white;border:1px solid #E0E0E0;border-radius:8px;"
                       f"padding:8px 12px;font-size:14px;color:#1A2535;}}QTimeEdit:focus{{border:1px solid {PRIMARY2};}}")
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
        cancel_btn = QPushButton("Cancel"); cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{TEXT_MID};font-size:13px;"
            f"border:1px solid #E0E0E0;border-radius:8px;padding:8px 24px;}}"
            f"QPushButton:hover{{background:#F5F5F5;}}")
        cancel_btn.clicked.connect(dlg.reject); btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save"); save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(
            f"QPushButton{{background:{PRIMARY2};color:white;font-size:13px;font-weight:600;"
            f"border:none;border-radius:8px;padding:8px 24px;}}"
            f"QPushButton:hover{{background:{PRIMARY};}}")
        save_btn.clicked.connect(dlg.accept); btn_row.addWidget(save_btn)
        lay.addLayout(btn_row)
        if dlg.exec_() == QDialog.Accepted:
            on_t = on_edit.time(); off_t = off_edit.time()
            on_str  = f"{on_t.hour():02d}:{on_t.minute():02d}"
            off_str = f"{off_t.hour():02d}:{off_t.minute():02d}"
            save_light_schedule(on_str, off_str)
            self.light_on_lbl.setText(_fmt_time(on_str))
            self.light_off_lbl.setText(_fmt_time(off_str))
            self.mqtt_client.publish(config.TOPIC_PREFIX + "/config/light_schedule",
                                     json.dumps({"on_time": on_str, "off_time": off_str}))

    def _make_feed_dialog(self, title):
        dlg = QDialog(self); dlg.setWindowTitle(title)
        dlg.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        dlg.setFixedSize(320, 280); dlg.setStyleSheet("QDialog{background:#F8F9FA;}")
        lay = QVBoxLayout(dlg); lay.setContentsMargins(24, 24, 24, 24); lay.setSpacing(12)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color:{PRIMARY2};font-size:16px;font-weight:700;background:transparent;")
        lay.addWidget(title_lbl)
        field_style = ("QLineEdit, QTimeEdit{background:white;border:1px solid #E0E0E0;border-radius:8px;"
                       f"padding:8px 12px;font-size:14px;color:#1A2535;}}QLineEdit:focus, QTimeEdit:focus{{border:1px solid {PRIMARY2};}}")
        lbl_style = f"color:{TEXT_MID};font-size:13px;font-weight:400;background:transparent;"
        name_lbl = QLabel("Name:"); name_lbl.setStyleSheet(lbl_style); lay.addWidget(name_lbl)
        name_edit = QLineEdit(); name_edit.setStyleSheet(field_style); lay.addWidget(name_edit)
        time_lbl = QLabel("Time:"); time_lbl.setStyleSheet(lbl_style); lay.addWidget(time_lbl)
        time_edit = QTimeEdit(); time_edit.setDisplayFormat("HH:mm")
        time_edit.setStyleSheet(field_style); lay.addWidget(time_edit)
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()
        cancel_btn = QPushButton("Cancel"); cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{TEXT_MID};font-size:13px;"
            f"border:1px solid #E0E0E0;border-radius:8px;padding:8px 24px;}}"
            f"QPushButton:hover{{background:#F5F5F5;}}")
        cancel_btn.clicked.connect(dlg.reject); btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save"); save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(
            f"QPushButton{{background:{PRIMARY2};color:white;font-size:13px;font-weight:600;"
            f"border:none;border-radius:8px;padding:8px 24px;}}"
            f"QPushButton:hover{{background:{PRIMARY};}}")
        save_btn.clicked.connect(dlg.accept); btn_row.addWidget(save_btn)
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

