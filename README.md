# Smart Aquarium IoT System

A complete IoT monitoring and control system for a smart aquarium, built as a course project at HIT (Holon Institute of Technology), IoT 2026.

The system monitors water temperature and pH in real time, controls feeding and lighting, stores all data locally, and alerts the user when sensor readings go out of range.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   MQTT Broker                        │
│              (broker.hivemq.com:1883)                │
└───────────┬──────────────────────────┬──────────────┘
            │                          │
   ┌────────┴────────┐        ┌────────┴────────┐
   │   Emulators     │        │  Data Manager   │
   │ • temp_ph_sensor│        │ • Subscribes to │
   │ • feeding_button│        │   all topics    │
   │ • light_relay   │        │ • Saves to DB   │
   └─────────────────┘        │ • Sends alerts  │
                               └────────┬────────┘
                                        │
                               ┌────────┴────────┐
                               │   SQLite DB     │
                               │  aquarium.db    │
                               └────────┬────────┘
                                        │
                               ┌────────┴────────┐
                               │    GUI App      │
                               │ • Dashboard     │
                               │ • Stats/Charts  │
                               │ • Schedule      │
                               │ • Settings      │
                               └─────────────────┘
```

All components communicate through MQTT. The GUI subscribes directly to the broker for live updates and also reads from the local database for history and charts.

---

## Components

### Emulators (`emulators/`)

| File | Type | Description |
|------|------|-------------|
| `temp_ph_sensor.py` | Sensor (data producer) | Publishes temperature and pH readings every 3 seconds. 85% of readings are in normal range; 15% are random spikes to trigger alerts. |
| `feeding_button.py` | Actuator (button) | Listens for feed commands from the GUI, simulates food dispensing, and publishes a confirmation status back. |
| `light_relay.py` | Actuator (relay) | Controls aquarium lighting. Responds to manual on/off commands and fires automatically at scheduled on/off times (trigger-once logic — no repeated firing). |

### Data Manager (`data_manager/data_manager.py`)

- Connects to the MQTT broker and subscribes to all aquarium topics
- Saves every sensor reading, feeding event, light event, and alert to SQLite
- Checks temperature and pH against configurable thresholds and publishes WARNING / ALARM messages
- Listens for threshold updates from the GUI settings page and applies them immediately (no restart needed)
- Runs a background thread that checks the feeding schedule every 30 seconds and triggers automatic feeds

### GUI App (`gui/`)

Built with **PyQt5**. Four pages accessible from a bottom navigation bar:

- **Dashboard** — live temperature, pH, light state, last feed time, system status, and a scrollable event log with a "View All" live popup dialog
- **Stats** — historical charts for temperature and pH with color-coded warning/alarm threshold lines
- **Schedule** — manage feeding schedule (add/remove/enable times) and set light on/off times; changes persist to DB and publish to the relay via MQTT
- **Settings** — adjust safe ranges and warning buffer (%) for temperature and pH using sliders; changes publish to the data manager live

### Database (`db/aquarium.db`)

SQLite database, created automatically on first run:

| Table | Contents |
|-------|----------|
| `sensor_readings` | All temperature and pH readings |
| `feeding_events` | Feed commands with action, amount, timestamp |
| `light_events` | Light state changes with source (manual / schedule) |
| `alerts` | All WARNING and ALARM events |
| `feeding_schedules` | Named feeding times with enabled/disabled flag |
| `light_schedule` | Single row with on_time and off_time |
| `allowed_ranges` | Persisted threshold values including warn percentages |

---

## MQTT Topics

All topics are prefixed with the value of `TOPIC_PREFIX` (default: `aquarium_hit_admin`).  
Override by setting `IOT_USER` in a `.env` file.

| Topic | Direction | Description |
|-------|-----------|-------------|
| `{prefix}/sensor/temperature` | Sensor → All | Temperature reading |
| `{prefix}/sensor/ph` | Sensor → All | pH reading |
| `{prefix}/feeding/command` | GUI → Feeder | Trigger a feed |
| `{prefix}/feeding/status` | Feeder → All | Feed completed confirmation |
| `{prefix}/light/command` | GUI → Relay | Turn light on/off |
| `{prefix}/light/status` | Relay → All | Light state change |
| `{prefix}/alerts` | Data Manager → GUI | WARNING / ALARM events |
| `{prefix}/config/thresholds` | GUI → Data Manager | Updated threshold values |
| `{prefix}/config/light_schedule` | GUI → Relay | Updated on/off schedule |

### Monitor live messages in browser

1. Go to https://www.hivemq.com/demos/websocket-client/
2. Host: `broker.hivemq.com`, Port: `8000` → **Connect**
3. Subscribe to `aquarium_hit_admin/#` (or your custom prefix)

---

## Alert Logic

Two severity levels:

- **WARNING** — reading is inside the safe range but past the warning buffer (default: within 10% of the edge)
- **ALARM** — reading is outside the safe range entirely

Default thresholds (configurable live from the Settings page):

| Parameter | Safe Range | Default Warn Buffer |
|-----------|------------|---------------------|
| Temperature | 22.0 – 28.0 °C | 10% from each edge |
| pH | 6.5 – 8.0 | 10% from each edge |

---

## Project Structure

```
Smart Aquarium IoT Project/
├── config.py                  # Broker address, topics, default thresholds
├── emulators/
│   ├── temp_ph_sensor.py      # Temperature & pH sensor emulator
│   ├── feeding_button.py      # Feeding actuator emulator
│   └── light_relay.py         # Light relay emulator
├── data_manager/
│   └── data_manager.py        # MQTT subscriber, DB writer, alert engine
├── gui/
│   ├── app.py                 # Main window, navigation
│   ├── state.py               # Shared state, MQTT callbacks, DB helpers
│   ├── palette.py             # Color constants
│   ├── widgets.py             # RangeSlider, LineChart, ToggleSwitch, etc.
│   ├── main_gui.py            # Entry point (starts MQTT + launches app)
│   └── pages/
│       ├── dashboard.py       # Live readings + event log
│       ├── stats.py           # Historical charts
│       ├── schedule.py        # Feeding & light schedule management
│       └── settings.py        # Threshold sliders
├── db/
│   └── aquarium.db            # SQLite database (auto-created on first run)
├── tests/
│   └── test_sanity.py         # 40 unit tests
└── README.md
```

---

## Setup & Running

### Requirements

```
Python 3.10+
paho-mqtt
PyQt5
python-dotenv
pytest  (for tests only)
```

Install:

```bash
pip install paho-mqtt PyQt5 python-dotenv
```

Or on Windows:

```bash
py -m pip install -r requirements.txt
```

### Optional: custom MQTT prefix

Create a `.env` file in the project root:

```
IOT_USER=your_unique_prefix
```

### Running

Open 5 terminals and start each component:

```bash
# 1. Data Manager (start first)
py data_manager/data_manager.py

# 2. Temperature & pH sensor
py emulators/temp_ph_sensor.py

# 3. Feeding button emulator
py emulators/feeding_button.py

# 4. Light relay emulator
py emulators/light_relay.py

# 5. GUI application
py gui/main_gui.py
```

### Tests

```bash
py -m pytest tests/ -v
```

40 tests covering config sanity, threshold defaults, alert logic, database writes, boundary conditions, color helpers, save/load round-trip, and feeding deduplication.

---

## Course

HIT — Internet of Things, 2026
