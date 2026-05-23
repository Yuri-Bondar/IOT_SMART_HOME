# config.py - central configuration for the smart aquarium system

import os
from dotenv import load_dotenv
load_dotenv()

# We use the HiveMQ public broker for testing.
# Anyone can connect to it - do not send sensitive data.
BROKER_HOST = "broker.hivemq.com"
BROKER_PORT = 1883  # plain TCP, no TLS needed for public broker
# No username/password required for the public broker

# Set IOT_USER in a .env file or env var to use a personal MQTT channel
TOPIC_PREFIX = os.environ.get("IOT_USER", "aquarium_hit_admin")

# --- MQTT Topics ---
TOPIC_TEMPERATURE = TOPIC_PREFIX + "/sensor/temperature"
TOPIC_PH = TOPIC_PREFIX + "/sensor/ph"
TOPIC_FEEDING_CMD = TOPIC_PREFIX + "/feeding/command"
TOPIC_FEEDING_STATUS = TOPIC_PREFIX + "/feeding/status"
TOPIC_LIGHT_CMD = TOPIC_PREFIX + "/light/command"
TOPIC_LIGHT_STATUS = TOPIC_PREFIX + "/light/status"
TOPIC_ALERTS = TOPIC_PREFIX + "/alerts"
TOPIC_WILDCARD = TOPIC_PREFIX + "/#"

# --- Temperature thresholds (Celsius) ---
# Normal range
TEMP_MIN_NORMAL = 22.0
TEMP_MAX_NORMAL = 28.0
# Warning range (outside normal but not critical)
TEMP_MIN_WARNING = 20.0
TEMP_MAX_WARNING = 30.0
# Alarm range (critical - danger to fish)
TEMP_MIN_ALARM = 18.0
TEMP_MAX_ALARM = 35.0

# --- pH thresholds ---
PH_MIN_NORMAL = 6.5
PH_MAX_NORMAL = 8.0
PH_MIN_WARNING = 6.0
PH_MAX_WARNING = 8.5

# --- Intervals (seconds) ---
FEEDING_INTERVAL = 5
SENSOR_INTERVAL = 3
