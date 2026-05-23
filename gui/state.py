import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import time
import sqlite3
from datetime import datetime
import config
from gui.palette import SUCCESS, WARNING, DANGER, TEXT_MUTED

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

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'aquarium.db')
_AR_DB_PATH = DB_PATH
_AR_KEYS = ["temp_safe_min", "temp_safe_max", "temp_warn_min", "temp_warn_max",
            "ph_safe_min", "ph_safe_max", "ph_warn_min", "ph_warn_max",
            "temp_warn_pct", "ph_warn_pct"]

TOPIC_THRESHOLDS = config.TOPIC_PREFIX + "/config/thresholds"


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


def save_allowed_ranges(allowed_ranges):
    allowed_ranges["temp_warn_pct"] = temp_warn_pct
    allowed_ranges["ph_warn_pct"]   = ph_warn_pct
    try:
        conn = sqlite3.connect(_AR_DB_PATH)
        cur = conn.cursor()
        cur.executemany(
            "INSERT OR REPLACE INTO allowed_ranges (key, value) VALUES (?, ?)",
            [(k, allowed_ranges[k]) for k in _AR_KEYS]
        )
        conn.commit()
        conn.close()
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
