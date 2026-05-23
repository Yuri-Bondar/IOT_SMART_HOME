import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import paho.mqtt.client as mqtt
import json
import time
import sqlite3
import threading
from datetime import datetime
import config

TOPIC_THRESHOLDS = config.TOPIC_PREFIX + "/config/thresholds"

# keep last known values for alert checking
last_temp = None
last_ph = None

# runtime thresholds — updated live via MQTT from the GUI settings
_DEF_PCT = 10
def _build_threshold_defaults():
    ts = config.TEMP_MAX_NORMAL - config.TEMP_MIN_NORMAL
    ps = config.PH_MAX_NORMAL   - config.PH_MIN_NORMAL
    return {
        "temp_safe_min": config.TEMP_MIN_NORMAL,
        "temp_safe_max": config.TEMP_MAX_NORMAL,
        "temp_warn_min": round(config.TEMP_MIN_NORMAL + ts * _DEF_PCT / 100, 1),
        "temp_warn_max": round(config.TEMP_MAX_NORMAL - ts * _DEF_PCT / 100, 1),
        "ph_safe_min":   config.PH_MIN_NORMAL,
        "ph_safe_max":   config.PH_MAX_NORMAL,
        "ph_warn_min":   round(config.PH_MIN_NORMAL + ps * _DEF_PCT / 100, 1),
        "ph_warn_max":   round(config.PH_MAX_NORMAL - ps * _DEF_PCT / 100, 1),
    }
_THRESHOLD_DEFAULTS = _build_threshold_defaults()

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "aquarium.db")

_THRESHOLD_KEYS = tuple(_THRESHOLD_DEFAULTS.keys())

def load_runtime_thresholds_from_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        placeholders = ",".join("?" * len(_THRESHOLD_KEYS))
        cur.execute(
            "SELECT key, value FROM allowed_ranges WHERE key IN ({})".format(placeholders),
            _THRESHOLD_KEYS
        )
        rows = dict(cur.fetchall())
        conn.close()
        if len(rows) == len(_THRESHOLD_KEYS):
            print("Thresholds loaded from DB.")
            return {k: float(rows[k]) for k in _THRESHOLD_KEYS}
    except Exception:
        pass
    print("Thresholds: using config defaults.")
    return dict(_THRESHOLD_DEFAULTS)

runtime_thresholds = load_runtime_thresholds_from_db()

last_fed_times = set()
_last_minute = None

def check_feeding_schedule(client):
    global last_fed_times, _last_minute
    now = datetime.now()
    current_minute = now.strftime("%H:%M")
    if current_minute != _last_minute:
        last_fed_times = set()
        _last_minute = current_minute
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name, time FROM feeding_schedules WHERE enabled=1")
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print("Feeding schedule check error: {}".format(e))
        return
    for name, feed_time in rows:
        if feed_time == current_minute and feed_time not in last_fed_times:
            last_fed_times.add(feed_time)
            payload = json.dumps({
                "action": "feed",
                "amount": "normal",
                "timestamp": now.isoformat(),
                "source": name,
            })
            client.publish(config.TOPIC_FEEDING_CMD, payload)
            print("[{}] Scheduled feeding triggered: {}".format(current_minute, name))

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_type TEXT,
            value REAL,
            unit TEXT,
            timestamp TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feeding_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            amount TEXT,
            timestamp TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS light_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT,
            source TEXT,
            timestamp TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT,
            message TEXT,
            value REAL,
            threshold REAL,
            timestamp TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feeding_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            time TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM feeding_schedules")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO feeding_schedules (name, time, enabled) VALUES (?, ?, ?)",
            [
                ("Morning Feed",   "08:00", 1),
                ("Afternoon Feed", "12:00", 1),
                ("Evening Feed",   "18:00", 1),
                ("Night Check",    "22:00", 0),
            ]
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS light_schedule (
            id INTEGER PRIMARY KEY,
            on_time  TEXT NOT NULL DEFAULT "08:00",
            off_time TEXT NOT NULL DEFAULT "22:00"
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM light_schedule")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO light_schedule (id, on_time, off_time) VALUES (1, '08:00', '22:00')"
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS allowed_ranges (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM allowed_ranges")
    if cursor.fetchone()[0] == 0:
        defaults = _build_threshold_defaults()
        cursor.executemany(
            "INSERT INTO allowed_ranges (key, value) VALUES (?, ?)",
            list(defaults.items()) + [("temp_warn_pct", 10.0), ("ph_warn_pct", 10.0)]
        )

    conn.commit()
    conn.close()
    print("Database initialized at: " + DB_PATH)

def save_sensor_reading(sensor_type, value, unit, timestamp):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sensor_readings (sensor_type, value, unit, timestamp) VALUES (?, ?, ?, ?)",
        (sensor_type, value, unit, timestamp)
    )
    conn.commit()
    conn.close()

def save_feeding_event(action, amount, timestamp):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO feeding_events (action, amount, timestamp) VALUES (?, ?, ?)",
        (action, amount, timestamp)
    )
    conn.commit()
    conn.close()

def save_light_event(state, source, timestamp):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO light_events (state, source, timestamp) VALUES (?, ?, ?)",
        (state, source, timestamp)
    )
    conn.commit()
    conn.close()

def save_alert(level, message, value, threshold, timestamp):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO alerts (level, message, value, threshold, timestamp) VALUES (?, ?, ?, ?, ?)",
        (level, message, value, threshold, timestamp)
    )
    conn.commit()
    conn.close()

def check_temperature_alerts(client, temp, timestamp):
    t = runtime_thresholds
    if temp < t["temp_safe_min"] or temp > t["temp_safe_max"]:
        level = "ALARM"
        if temp < t["temp_safe_min"]:
            msg = "Temperature critically low: {}°C".format(temp)
            threshold = t["temp_safe_min"]
        else:
            msg = "Temperature critically high: {}°C".format(temp)
            threshold = t["temp_safe_max"]
        publish_alert(client, level, msg, temp, threshold, timestamp)

    elif temp <= t["temp_warn_min"] or temp >= t["temp_warn_max"]:
        level = "WARNING"
        if temp <= t["temp_warn_min"]:
            msg = "Temperature approaching low limit: {}°C".format(temp)
            threshold = t["temp_warn_min"]
        else:
            msg = "Temperature approaching high limit: {}°C".format(temp)
            threshold = t["temp_warn_max"]
        publish_alert(client, level, msg, temp, threshold, timestamp)

def check_ph_alerts(client, ph, timestamp):
    t = runtime_thresholds
    if ph < t["ph_safe_min"] or ph > t["ph_safe_max"]:
        level = "ALARM"
        if ph < t["ph_safe_min"]:
            msg = "pH critically low: {}".format(ph)
            threshold = t["ph_safe_min"]
        else:
            msg = "pH critically high: {}".format(ph)
            threshold = t["ph_safe_max"]
        publish_alert(client, level, msg, ph, threshold, timestamp)

    elif ph <= t["ph_warn_min"] or ph >= t["ph_warn_max"]:
        level = "WARNING"
        if ph <= t["ph_warn_min"]:
            msg = "pH approaching low limit: {}".format(ph)
            threshold = t["ph_warn_min"]
        else:
            msg = "pH approaching high limit: {}".format(ph)
            threshold = t["ph_warn_max"]
        publish_alert(client, level, msg, ph, threshold, timestamp)

def publish_alert(client, level, message, value, threshold, timestamp):
    alert_data = {
        "level": level,
        "message": message,
        "value": value,
        "threshold": threshold,
        "timestamp": timestamp
    }
    try:
        client.publish(config.TOPIC_ALERTS, json.dumps(alert_data))
        print(f"  >> [{level}] {message}")
    except Exception as e:
        print("Error publishing alert: " + str(e))

    save_alert(level, message, value, threshold, timestamp)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Data Manager connected to broker")
        # subscribe to all aquarium topics
        client.subscribe(config.TOPIC_WILDCARD)
        print("Subscribed to " + config.TOPIC_WILDCARD)
    else:
        print("Connection failed with code: " + str(rc))

def on_disconnect(client, userdata, rc):
    print("Data Manager disconnected, reconnecting...")
    while True:
        try:
            client.reconnect()
            print("Reconnected!")
            break
        except Exception:
            time.sleep(5)

def on_message(client, userdata, msg):
    global last_temp, last_ph, runtime_thresholds

    topic = msg.topic
    now = datetime.now().isoformat()

    try:
        data = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print(f"[{now}] Bad JSON on topic: {topic}")
        return

    print(f"[{now}] {topic}: {data}")

    # figure out which topic this is and save to the right table
    if topic == config.TOPIC_TEMPERATURE:
        value = data.get("value", 0)
        unit = data.get("unit", "celsius")
        ts = data.get("timestamp", now)
        save_sensor_reading("temperature", value, unit, ts)
        last_temp = value
        check_temperature_alerts(client, value, ts)

    elif topic == config.TOPIC_PH:
        value = data.get("value", 0)
        unit = data.get("unit", "pH")
        ts = data.get("timestamp", now)
        save_sensor_reading("ph", value, unit, ts)
        last_ph = value
        check_ph_alerts(client, value, ts)

    elif topic == config.TOPIC_FEEDING_CMD:
        action = data.get("action", "feed")
        amount = data.get("amount", "normal")
        ts = data.get("timestamp", now)
        save_feeding_event(action, amount, ts)

    elif topic == config.TOPIC_LIGHT_STATUS:
        state = data.get("state", "off")
        source = data.get("source", "unknown")
        ts = data.get("timestamp", now)
        save_light_event(state, source, ts)

    elif topic == TOPIC_THRESHOLDS:
        valid_keys = set(runtime_thresholds.keys())
        updated = {k: float(v) for k, v in data.items() if k in valid_keys}
        runtime_thresholds.update(updated)
        print(f"[{now}] Thresholds updated: {updated}")


def main():
    init_db()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    try:
        client.connect(config.BROKER_HOST, config.BROKER_PORT, 60)
    except Exception as e:
        print("Could not connect to broker: {}".format(e))
        return

    def _feeding_scheduler():
        while True:
            check_feeding_schedule(client)
            time.sleep(30)

    threading.Thread(target=_feeding_scheduler, daemon=True).start()

    print("Data Manager started. Press Ctrl+C to stop.")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nData Manager stopped.")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
