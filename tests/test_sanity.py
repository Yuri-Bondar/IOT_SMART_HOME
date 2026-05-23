import sys
import os
import json
import sqlite3
import tempfile
import pytest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

# ── 1. Config sanity ─────────────────────────────────────────────────────────

def test_temp_normal_range_is_valid():
    assert config.TEMP_MIN_NORMAL < config.TEMP_MAX_NORMAL

def test_ph_normal_range_is_valid():
    assert config.PH_MIN_NORMAL < config.PH_MAX_NORMAL

def test_broker_port_is_standard():
    assert config.BROKER_PORT == 1883

def test_topic_prefix_not_empty():
    assert config.TOPIC_PREFIX.strip() != ""

def test_all_topics_start_with_prefix():
    topics = [
        config.TOPIC_TEMPERATURE,
        config.TOPIC_PH,
        config.TOPIC_FEEDING_CMD,
        config.TOPIC_FEEDING_STATUS,
        config.TOPIC_LIGHT_CMD,
        config.TOPIC_LIGHT_STATUS,
        config.TOPIC_ALERTS,
    ]
    for topic in topics:
        assert topic.startswith(config.TOPIC_PREFIX), f"Topic {topic} doesn't start with prefix"

# ── 2. Sensor data format ─────────────────────────────────────────────────────

def make_temp_payload(value):
    return json.dumps({
        "value": value,
        "unit": "celsius",
        "timestamp": datetime.now().isoformat()
    })

def make_ph_payload(value):
    return json.dumps({
        "value": value,
        "unit": "pH",
        "timestamp": datetime.now().isoformat()
    })

def test_temp_payload_is_valid_json():
    payload = make_temp_payload(25.0)
    data = json.loads(payload)
    assert "value" in data
    assert "unit" in data
    assert "timestamp" in data

def test_ph_payload_is_valid_json():
    payload = make_ph_payload(7.0)
    data = json.loads(payload)
    assert "value" in data
    assert "unit" in data
    assert "timestamp" in data

def test_temp_payload_unit():
    data = json.loads(make_temp_payload(25.0))
    assert data["unit"] == "celsius"

def test_ph_payload_unit():
    data = json.loads(make_ph_payload(7.0))
    assert data["unit"] == "pH"

def test_temp_value_is_float():
    data = json.loads(make_temp_payload(25.3))
    assert isinstance(data["value"], float)

# ── 3. Alert logic ────────────────────────────────────────────────────────────

def get_temp_alert_level(temp, thresholds):
    if temp < thresholds["temp_safe_min"] or temp > thresholds["temp_safe_max"]:
        return "ALARM"
    elif temp <= thresholds["temp_warn_min"] or temp >= thresholds["temp_warn_max"]:
        return "WARNING"
    return None

def get_ph_alert_level(ph, thresholds):
    if ph < thresholds["ph_safe_min"] or ph > thresholds["ph_safe_max"]:
        return "ALARM"
    elif ph <= thresholds["ph_warn_min"] or ph >= thresholds["ph_warn_max"]:
        return "WARNING"
    return None

_T = {
    "temp_safe_min": 22.0, "temp_safe_max": 28.0,
    "temp_warn_min": 22.6, "temp_warn_max": 27.4,
    "ph_safe_min": 6.5, "ph_safe_max": 8.0,
    "ph_warn_min": 6.6, "ph_warn_max": 7.9,
}

def test_normal_temp_no_alert():
    assert get_temp_alert_level(25.0, _T) is None

def test_temp_too_high_warning():
    assert get_temp_alert_level(27.5, _T) == "WARNING"

def test_temp_too_low_warning():
    assert get_temp_alert_level(22.5, _T) == "WARNING"

def test_temp_critical_high_alarm():
    assert get_temp_alert_level(28.5, _T) == "ALARM"

def test_temp_critical_low_alarm():
    assert get_temp_alert_level(21.5, _T) == "ALARM"

def test_normal_ph_no_alert():
    assert get_ph_alert_level(7.0, _T) is None

def test_ph_too_high_warning():
    assert get_ph_alert_level(7.95, _T) == "WARNING"

def test_ph_critical_alarm():
    assert get_ph_alert_level(8.1, _T) == "ALARM"

# ── 4. Database writes ────────────────────────────────────────────────────────

@pytest.fixture
def temp_db():
    # create a fresh temp DB for each test - don't touch the real one
    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = db_file.name
    db_file.close()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_type TEXT, value REAL, unit TEXT, timestamp TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE feeding_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT, amount TEXT, timestamp TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT, message TEXT, value REAL, threshold REAL, timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

    yield db_path
    os.unlink(db_path)

def test_save_sensor_reading(temp_db):
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sensor_readings (sensor_type, value, unit, timestamp) VALUES (?, ?, ?, ?)",
        ("temperature", 25.3, "celsius", datetime.now().isoformat())
    )
    conn.commit()
    cur.execute("SELECT value FROM sensor_readings WHERE sensor_type='temperature'")
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 25.3

def test_save_feeding_event(temp_db):
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO feeding_events (action, amount, timestamp) VALUES (?, ?, ?)",
        ("feed", "normal", datetime.now().isoformat())
    )
    conn.commit()
    cur.execute("SELECT action FROM feeding_events")
    row = cur.fetchone()
    conn.close()
    assert row[0] == "feed"

def test_save_alert(temp_db):
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO alerts (level, message, value, threshold, timestamp) VALUES (?, ?, ?, ?, ?)",
        ("WARNING", "Temperature too high: 29.5°C", 29.5, 28.0, datetime.now().isoformat())
    )
    conn.commit()
    cur.execute("SELECT level, value FROM alerts")
    row = cur.fetchone()
    conn.close()
    assert row[0] == "WARNING"
    assert row[1] == 29.5

def test_multiple_readings_saved(temp_db):
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    for val in [22.0, 24.5, 27.1]:
        cur.execute(
            "INSERT INTO sensor_readings (sensor_type, value, unit, timestamp) VALUES (?, ?, ?, ?)",
            ("temperature", val, "celsius", datetime.now().isoformat())
        )
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM sensor_readings")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 3

# ── 5. MQTT payload structure ─────────────────────────────────────────────────

def test_feed_command_payload():
    payload = json.dumps({
        "action": "feed",
        "amount": "normal",
        "timestamp": datetime.now().isoformat()
    })
    data = json.loads(payload)
    assert data["action"] == "feed"
    assert data["amount"] == "normal"
    assert "timestamp" in data

def test_light_command_payload():
    payload = json.dumps({
        "state": "on",
        "timestamp": datetime.now().isoformat()
    })
    data = json.loads(payload)
    assert data["state"] in ("on", "off")

def test_alert_payload_has_required_fields():
    payload = json.dumps({
        "level": "WARNING",
        "message": "Temperature too high: 29.5°C",
        "value": 29.5,
        "threshold": 28.0,
        "timestamp": datetime.now().isoformat()
    })
    data = json.loads(payload)
    for field in ("level", "message", "value", "threshold", "timestamp"):
        assert field in data, f"Missing field: {field}"

def test_alert_level_is_valid():
    for level in ("WARNING", "ALARM", "INFO"):
        payload = json.dumps({"level": level, "message": "test", "value": 0, "threshold": 0, "timestamp": ""})
        data = json.loads(payload)
        assert data["level"] in ("WARNING", "ALARM", "INFO")
