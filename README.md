# Smart Aquarium IoT System

A simulation of a smart aquarium monitoring system built with Python, MQTT, and PyQt5.
The system uses IoT concepts to monitor water temperature and pH, control lighting,
automate fish feeding, and alert when conditions are dangerous.

## System Architecture

```
[Temp/pH Sensor] ──┐
[Feeding Button] ──┼──► [HiveMQ Broker] ──► [Data Manager] ──► [SQLite DB]
[Light Relay]    ──┘           │
                               └──────────────► [Main GUI]
```

## Components

- **temp_ph_sensor.py** - Simulates a temperature and pH sensor (data producer). Publishes readings every few seconds.
- **feeding_button.py** - Simulates an automatic feeding button that dispenses food at regular intervals.
- **light_relay.py** - Controls the aquarium LED light with a day/night schedule (ON 08:00-22:00).
- **data_manager.py** - Subscribes to all MQTT topics, logs data to SQLite, and generates warnings/alarms.
- **main_gui.py** - PyQt5 dashboard showing live sensor data, controls, and a color-coded event log.

## MQTT Broker Setup

This project uses the **free HiveMQ public broker** - no registration or password needed!

- Host: `broker.hivemq.com`
- Port: `1883` (plain TCP)

**Important:** Change `TOPIC_PREFIX` in `config.py` to something unique (like your name) so your
messages don't mix with other students on the public broker.

### Monitor Messages in Browser

You can watch all MQTT messages live using the HiveMQ WebSocket client:

1. Go to https://www.hivemq.com/demos/websocket-client/
2. Set Host to `broker.hivemq.com`, Port to `8000`
3. Click **Connect**
4. Subscribe to `aquarium_hit_yuri/#` (or whatever your prefix is)
5. You'll see all messages in real time!

## Installation (Windows)

```
py -m pip install -r requirements.txt
```

## How to Run

Open **5 separate terminals** and run each component in this order:

```bash
# Terminal 1 - start the data manager first:
py data_manager/data_manager.py

# Terminal 2 - temperature and pH sensor:
py emulators/temp_ph_sensor.py

# Terminal 3 - feeding button:
py emulators/feeding_button.py

# Terminal 4 - light relay:
py emulators/light_relay.py

# Terminal 5 - GUI dashboard:
py gui/main_gui.py
```

## Changing Thresholds

All thresholds are configured in `config.py`. Just edit the values and restart:

| Parameter | Default | Description |
|-----------|---------|-------------|
| TEMP_MIN_NORMAL | 22.0°C | Lower bound of normal temperature |
| TEMP_MAX_NORMAL | 28.0°C | Upper bound of normal temperature |
| TEMP_MIN_WARNING | 20.0°C | Lower bound of warning range |
| TEMP_MAX_WARNING | 30.0°C | Upper bound of warning range |
| TEMP_MIN_ALARM | 18.0°C | Critical low temperature |
| TEMP_MAX_ALARM | 35.0°C | Critical high temperature |
| PH_MIN_NORMAL | 6.5 | Lower bound of normal pH |
| PH_MAX_NORMAL | 8.0 | Upper bound of normal pH |
| PH_MIN_WARNING | 6.0 | Lower bound of warning pH |
| PH_MAX_WARNING | 8.5 | Upper bound of warning pH |

## MQTT Topic Map

| Topic | Direction | Description |
|-------|-----------|-------------|
| `{prefix}/sensor/temperature` | Sensor → Broker | Temperature readings (°C) |
| `{prefix}/sensor/ph` | Sensor → Broker | pH level readings |
| `{prefix}/feeding/command` | Button/GUI → Broker | Feed command trigger |
| `{prefix}/feeding/status` | Data Manager → Broker | Feeding confirmation |
| `{prefix}/light/command` | GUI → Broker | Light on/off command |
| `{prefix}/light/status` | Light Relay → Broker | Current light state |
| `{prefix}/alerts` | Data Manager → Broker | Warning and alarm messages |

## Database Schema

The SQLite database (`db/aquarium.db`) is created automatically on first run.

**sensor_readings** - Stores temperature and pH readings
- id, sensor_type, value, unit, timestamp

**feeding_events** - Logs each feeding event
- id, action, amount, timestamp

**light_events** - Logs light state changes
- id, state, source, timestamp

**alerts** - Stores warning and alarm events
- id, level, message, value, threshold, timestamp
