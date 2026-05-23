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

# ── 2. Threshold defaults ─────────────────────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data_manager.data_manager import _build_threshold_defaults

def test_warn_range_inside_safe_range_temp():
    d = _build_threshold_defaults()
    assert d["temp_warn_min"] > d["temp_safe_min"]
    assert d["temp_warn_max"] < d["temp_safe_max"]

def test_warn_range_inside_safe_range_ph():
    d = _build_threshold_defaults()
    assert d["ph_warn_min"] > d["ph_safe_min"]
    assert d["ph_warn_max"] < d["ph_safe_max"]

def test_defaults_match_config():
    d = _build_threshold_defaults()
    assert d["temp_safe_min"] == config.TEMP_MIN_NORMAL
    assert d["temp_safe_max"] == config.TEMP_MAX_NORMAL
    assert d["ph_safe_min"]   == config.PH_MIN_NORMAL
    assert d["ph_safe_max"]   == config.PH_MAX_NORMAL

def test_load_allowed_ranges_fallback_to_defaults():
    from gui.state import _ar_defaults
    d = _ar_defaults()
    assert d["temp_safe_min"] < d["temp_safe_max"]
    assert d["temp_warn_min"] > d["temp_safe_min"]
    assert d["temp_warn_max"] < d["temp_safe_max"]

def test_add_event_caps_at_50():
    from gui.state import state, add_event
    state["events"] = []
    for i in range(55):
        add_event("INFO", f"event {i}")
    assert len(state["events"]) <= 50

def test_system_status_alarm():
    from gui.state import state, add_event
    state["events"] = []
    add_event("ALARM", "critical!")
    assert state["system_status"] == "Alert Active"

def test_system_status_warning():
    from gui.state import state, add_event
    state["events"] = []
    add_event("WARNING", "warning!")
    assert state["system_status"] == "Warning Active"

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

# ── 6. Alert functions (data_manager) ────────────────────────────────────────

from unittest.mock import MagicMock, patch
import data_manager.data_manager as dm

def test_no_alert_published_for_normal_temp():
    client = MagicMock()
    dm.runtime_thresholds = _build_threshold_defaults()
    dm.check_temperature_alerts(client, 25.0, "2026-01-01T00:00:00")
    client.publish.assert_not_called()

def test_no_alert_published_for_normal_ph():
    client = MagicMock()
    dm.runtime_thresholds = _build_threshold_defaults()
    dm.check_ph_alerts(client, 7.0, "2026-01-01T00:00:00")
    client.publish.assert_not_called()

# ── 7. Boundary conditions ────────────────────────────────────────────────────

def test_temp_exactly_at_warn_max_is_warning():
    assert get_temp_alert_level(_T["temp_warn_max"], _T) == "WARNING"

def test_temp_exactly_at_safe_max_is_warning_not_alarm():
    # safe_max is inclusive lower bound of warning zone (condition is >)
    assert get_temp_alert_level(_T["temp_safe_max"], _T) == "WARNING"

def test_temp_just_above_safe_max_is_alarm():
    assert get_temp_alert_level(_T["temp_safe_max"] + 0.1, _T) == "ALARM"

def test_ph_exactly_at_warn_min_is_warning():
    assert get_ph_alert_level(_T["ph_warn_min"], _T) == "WARNING"

# ── 8. save / load allowed_ranges round-trip ─────────────────────────────────

import gui.state as gs

def test_save_load_allowed_ranges_roundtrip(tmp_path, monkeypatch):
    db = str(tmp_path / "ar.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE allowed_ranges (key TEXT PRIMARY KEY, value REAL NOT NULL)")
    conn.commit(); conn.close()

    monkeypatch.setattr(gs, "DB_PATH", db)

    test_ranges = {
        "temp_safe_min": 20.0, "temp_safe_max": 30.0,
        "temp_warn_min": 22.0, "temp_warn_max": 28.0,
        "ph_safe_min": 6.0,   "ph_safe_max": 8.5,
        "ph_warn_min": 6.2,   "ph_warn_max": 8.3,
    }
    gs.save_allowed_ranges(dict(test_ranges))
    loaded = gs.load_allowed_ranges()

    for key in test_ranges:
        assert float(loaded[key]) == test_ranges[key], f"Mismatch on {key}"

# ── 9. Color helper functions ─────────────────────────────────────────────────

from gui.palette import SUCCESS, WARNING as WARN_COLOR, DANGER

def test_get_temp_color_normal():
    backup = dict(gs.allowed_ranges)
    gs.allowed_ranges.update(_T)
    assert gs.get_temp_color(25.0) == SUCCESS
    gs.allowed_ranges.update(backup)

def test_get_temp_color_warning():
    backup = dict(gs.allowed_ranges)
    gs.allowed_ranges.update(_T)
    assert gs.get_temp_color(27.5) == WARN_COLOR
    gs.allowed_ranges.update(backup)

def test_get_temp_color_alarm():
    backup = dict(gs.allowed_ranges)
    gs.allowed_ranges.update(_T)
    assert gs.get_temp_color(29.0) == DANGER
    gs.allowed_ranges.update(backup)

# ── 10. System status resets to optimal ──────────────────────────────────────

def test_system_status_resets_to_optimal():
    from gui.state import state, add_event
    state["events"] = []
    add_event("ALARM", "critical!")
    assert state["system_status"] == "Alert Active"
    for i in range(5):
        add_event("INFO", f"normal {i}")
    assert state["system_status"] == "System Optimal"

# ── 11. Feeding deduplication ─────────────────────────────────────────────────

def test_feeding_not_triggered_twice_same_minute(tmp_path, monkeypatch):
    fixed_minute = "14:30"

    db = str(tmp_path / "feed.db")
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE feeding_schedules
                    (id INTEGER PRIMARY KEY, name TEXT, time TEXT, enabled INTEGER)""")
    conn.execute("INSERT INTO feeding_schedules VALUES (1,'Test',?,1)", (fixed_minute,))
    conn.execute("""CREATE TABLE feeding_events
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, amount TEXT, timestamp TEXT)""")
    conn.commit(); conn.close()

    monkeypatch.setattr(dm, "DB_PATH", db)
    monkeypatch.setattr(dm, "last_fed_times", set())
    monkeypatch.setattr(dm, "_last_minute", None)

    fake_now = MagicMock()
    fake_now.strftime.return_value = fixed_minute
    fake_now.isoformat.return_value = "2026-01-01T14:30:00"

    client = MagicMock()
    with patch("data_manager.data_manager.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        dm.check_feeding_schedule(client)
        dm.check_feeding_schedule(client)

    assert client.publish.call_count == 1
