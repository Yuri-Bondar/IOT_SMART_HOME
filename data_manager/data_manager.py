import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import paho.mqtt.client as mqtt
import json
import time
import sqlite3
from datetime import datetime
import config

# keep last known values for alert checking
last_temp = None
last_ph = None

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "aquarium.db")

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
    # check if temperature is in warning or alarm range
    if temp < config.TEMP_MIN_ALARM or temp > config.TEMP_MAX_ALARM:
        level = "ALARM"
        if temp < config.TEMP_MIN_ALARM:
            msg = "Temperature critically low: {}°C".format(temp)
            threshold = config.TEMP_MIN_ALARM
        else:
            msg = "Temperature critically high: {}°C".format(temp)
            threshold = config.TEMP_MAX_ALARM
        publish_alert(client, level, msg, temp, threshold, timestamp)

    elif temp < config.TEMP_MIN_WARNING or temp > config.TEMP_MAX_WARNING:
        level = "ALARM"
        if temp < config.TEMP_MIN_WARNING:
            msg = "Temperature dangerously low: {}°C".format(temp)
            threshold = config.TEMP_MIN_WARNING
        else:
            msg = "Temperature dangerously high: {}°C".format(temp)
            threshold = config.TEMP_MAX_WARNING
        publish_alert(client, level, msg, temp, threshold, timestamp)

    elif temp < config.TEMP_MIN_NORMAL or temp > config.TEMP_MAX_NORMAL:
        level = "WARNING"
        if temp < config.TEMP_MIN_NORMAL:
            msg = "Temperature too low: {}°C".format(temp)
            threshold = config.TEMP_MIN_NORMAL
        else:
            msg = "Temperature too high: {}°C".format(temp)
            threshold = config.TEMP_MAX_NORMAL
        publish_alert(client, level, msg, temp, threshold, timestamp)

def check_ph_alerts(client, ph, timestamp):
    if ph < config.PH_MIN_WARNING or ph > config.PH_MAX_WARNING:
        level = "ALARM"
        if ph < config.PH_MIN_WARNING:
            msg = "pH critically low: {}".format(ph)
            threshold = config.PH_MIN_WARNING
        else:
            msg = "pH critically high: {}".format(ph)
            threshold = config.PH_MAX_WARNING
        publish_alert(client, level, msg, ph, threshold, timestamp)

    elif ph < config.PH_MIN_NORMAL or ph > config.PH_MAX_NORMAL:
        level = "WARNING"
        if ph < config.PH_MIN_NORMAL:
            msg = "pH too low: {}".format(ph)
            threshold = config.PH_MIN_NORMAL
        else:
            msg = "pH too high: {}".format(ph)
            threshold = config.PH_MAX_NORMAL
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
    global last_temp, last_ph

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

        # send confirmation back
        status_data = {
            "status": "completed",
            "amount": amount,
            "timestamp": ts
        }
        try:
            client.publish(config.TOPIC_FEEDING_STATUS, json.dumps(status_data))
        except Exception:
            pass

    elif topic == config.TOPIC_LIGHT_STATUS:
        state = data.get("state", "off")
        source = data.get("source", "unknown")
        ts = data.get("timestamp", now)
        save_light_event(state, source, ts)

    elif topic == config.TOPIC_ALERTS:
        # alerts are already saved when they are generated
        # but if we get alerts from somewhere else, save them too
        level = data.get("level", "INFO")
        message = data.get("message", "")
        value = data.get("value", 0)
        threshold = data.get("threshold", 0)
        ts = data.get("timestamp", now)
        # don't double-save our own alerts (they're saved in publish_alert)

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

    print("Data Manager started. Press Ctrl+C to stop.")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nData Manager stopped.")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
