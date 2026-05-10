import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import paho.mqtt.client as mqtt
import json
import time
import threading
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QListWidget,
                             QListWidgetItem, QGroupBox, QFrame, QDoubleSpinBox,
                             QGridLayout)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QColor
import config

# shared state between MQTT thread and GUI
state = {
    "temperature": None,
    "ph": None,
    "light": "off",
    "last_feed": None,
    "last_update": None,
    "events": []  # list of (timestamp, level, message) tuples
}

MAX_EVENTS = 20

def add_event(level, message):
    now = datetime.now().strftime("%H:%M:%S")
    state["events"].insert(0, (now, level, message))
    # only keep last 20 events
    if len(state["events"]) > MAX_EVENTS:
        state["events"] = state["events"][:MAX_EVENTS]

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        # subscribe only to topics we need, not wildcard
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
        value = data.get("value", 0)
        state["temperature"] = value
        state["last_update"] = datetime.now().strftime("%H:%M:%S")
        add_event("INFO", f"Temperature: {value}°C")

    elif topic == config.TOPIC_PH:
        value = data.get("value", 0)
        state["ph"] = value
        state["last_update"] = datetime.now().strftime("%H:%M:%S")
        add_event("INFO", f"pH: {value}")

    elif topic == config.TOPIC_LIGHT_STATUS:
        light_state = data.get("state", "off")
        state["light"] = light_state

    elif topic == config.TOPIC_FEEDING_STATUS:
        state["last_feed"] = datetime.now().strftime("%H:%M:%S")
        add_event("INFO", "Fish fed")

    elif topic == config.TOPIC_ALERTS:
        level = data.get("level", "WARNING")
        message = data.get("message", "Unknown alert")
        add_event(level, message)

def start_mqtt_thread(client):
    # run MQTT loop in background so it doesn't block the GUI
    def mqtt_loop():
        try:
            client.connect(config.BROKER_HOST, config.BROKER_PORT, 60)
            client.loop_forever()
        except Exception as e:
            add_event("WARNING", "MQTT error: " + str(e))

    t = threading.Thread(target=mqtt_loop, daemon=True)
    t.start()

def get_temp_color(temp):
    if temp is None:
        return "gray"
    if config.TEMP_MIN_NORMAL <= temp <= config.TEMP_MAX_NORMAL:
        return "#2ecc71"  # green
    elif config.TEMP_MIN_WARNING <= temp <= config.TEMP_MAX_WARNING:
        return "#f39c12"  # orange
    else:
        return "#e74c3c"  # red

def get_ph_color(ph):
    if ph is None:
        return "gray"
    if config.PH_MIN_NORMAL <= ph <= config.PH_MAX_NORMAL:
        return "#2ecc71"
    elif config.PH_MIN_WARNING <= ph <= config.PH_MAX_WARNING:
        return "#f39c12"
    else:
        return "#e74c3c"


class AquariumDashboard(QMainWindow):
    def __init__(self, mqtt_client):
        super().__init__()
        self.mqtt_client = mqtt_client
        self.setWindowTitle("Smart Aquarium Dashboard")
        self.setMinimumSize(700, 550)
        self.setup_ui()

        # refresh GUI every second
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # title
        title = QLabel("Smart Aquarium Monitor")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50; margin: 10px;")
        main_layout.addWidget(title)

        # main content: left side + right side
        content_layout = QHBoxLayout()

        # ========== LEFT SIDE: Readings + Log ==========
        left_layout = QVBoxLayout()

        # sensor readings
        sensor_group = QGroupBox("Live Sensor Readings")
        sensor_group.setFont(QFont("Arial", 11, QFont.Bold))
        sensor_layout = QVBoxLayout()

        self.temp_label = QLabel("Temperature: --")
        self.temp_label.setFont(QFont("Arial", 22, QFont.Bold))
        self.temp_label.setAlignment(Qt.AlignCenter)
        sensor_layout.addWidget(self.temp_label)

        self.ph_label = QLabel("pH: --")
        self.ph_label.setFont(QFont("Arial", 22, QFont.Bold))
        self.ph_label.setAlignment(Qt.AlignCenter)
        sensor_layout.addWidget(self.ph_label)

        self.light_label = QLabel("Light: OFF")
        self.light_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.light_label.setAlignment(Qt.AlignCenter)
        self.light_label.setStyleSheet("background-color: #555; color: white; padding: 10px; border-radius: 5px;")
        sensor_layout.addWidget(self.light_label)

        self.update_label = QLabel("Last update: --")
        self.update_label.setAlignment(Qt.AlignCenter)
        self.update_label.setFont(QFont("Arial", 13))
        self.update_label.setStyleSheet("color: #7f8c8d;")
        sensor_layout.addWidget(self.update_label)

        sensor_group.setLayout(sensor_layout)
        left_layout.addWidget(sensor_group)

        # status log
        log_group = QGroupBox("Status Log")
        log_group.setFont(QFont("Arial", 11, QFont.Bold))
        log_layout = QVBoxLayout()

        self.event_list = QListWidget()
        self.event_list.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self.event_list)

        log_group.setLayout(log_layout)
        left_layout.addWidget(log_group)

        content_layout.addLayout(left_layout, stretch=3)

        # ========== RIGHT SIDE: Controls ==========
        right_layout = QVBoxLayout()

        # light controls
        light_group = QGroupBox("Light Control")
        light_group.setFont(QFont("Arial", 11, QFont.Bold))
        light_ctrl_layout = QVBoxLayout()

        light_btn_layout = QHBoxLayout()
        self.light_on_btn = QPushButton("Light ON")
        self.light_on_btn.setStyleSheet("background-color: #f1c40f; padding: 8px; font-weight: bold;")
        self.light_on_btn.clicked.connect(self.turn_light_on)
        light_btn_layout.addWidget(self.light_on_btn)

        self.light_off_btn = QPushButton("Light OFF")
        self.light_off_btn.setStyleSheet("background-color: #95a5a6; padding: 8px; font-weight: bold;")
        self.light_off_btn.clicked.connect(self.turn_light_off)
        light_btn_layout.addWidget(self.light_off_btn)
        light_ctrl_layout.addLayout(light_btn_layout)

        light_group.setLayout(light_ctrl_layout)
        right_layout.addWidget(light_group)

        # feeding controls
        feed_group = QGroupBox("Feeding")
        feed_group.setFont(QFont("Arial", 11, QFont.Bold))
        feed_layout = QVBoxLayout()

        self.feed_btn = QPushButton("Feed Now")
        self.feed_btn.setFont(QFont("Arial", 12, QFont.Bold))
        self.feed_btn.setStyleSheet("background-color: #3498db; color: white; padding: 12px; border-radius: 5px;")
        self.feed_btn.clicked.connect(self.feed_now)
        feed_layout.addWidget(self.feed_btn)

        self.feed_label = QLabel("Last feeding: --")
        self.feed_label.setAlignment(Qt.AlignCenter)
        self.feed_label.setFont(QFont("Arial", 13))
        self.feed_label.setStyleSheet("color: #7f8c8d;")
        feed_layout.addWidget(self.feed_label)

        feed_group.setLayout(feed_layout)
        right_layout.addWidget(feed_group)

        # temperature thresholds
        temp_group = QGroupBox("Temperature Thresholds (°C)")
        temp_group.setFont(QFont("Arial", 11, QFont.Bold))
        temp_grid = QGridLayout()

        temp_grid.addWidget(QLabel("Min Normal:"), 0, 0)
        self.temp_min_normal = QDoubleSpinBox()
        self.temp_min_normal.setRange(0, 50)
        self.temp_min_normal.setValue(config.TEMP_MIN_NORMAL)
        self.temp_min_normal.valueChanged.connect(self.update_thresholds)
        temp_grid.addWidget(self.temp_min_normal, 0, 1)

        temp_grid.addWidget(QLabel("Max Normal:"), 1, 0)
        self.temp_max_normal = QDoubleSpinBox()
        self.temp_max_normal.setRange(0, 50)
        self.temp_max_normal.setValue(config.TEMP_MAX_NORMAL)
        self.temp_max_normal.valueChanged.connect(self.update_thresholds)
        temp_grid.addWidget(self.temp_max_normal, 1, 1)

        temp_grid.addWidget(QLabel("Min Warning:"), 2, 0)
        self.temp_min_warning = QDoubleSpinBox()
        self.temp_min_warning.setRange(0, 50)
        self.temp_min_warning.setValue(config.TEMP_MIN_WARNING)
        self.temp_min_warning.valueChanged.connect(self.update_thresholds)
        temp_grid.addWidget(self.temp_min_warning, 2, 1)

        temp_grid.addWidget(QLabel("Max Warning:"), 3, 0)
        self.temp_max_warning = QDoubleSpinBox()
        self.temp_max_warning.setRange(0, 50)
        self.temp_max_warning.setValue(config.TEMP_MAX_WARNING)
        self.temp_max_warning.valueChanged.connect(self.update_thresholds)
        temp_grid.addWidget(self.temp_max_warning, 3, 1)

        temp_group.setLayout(temp_grid)
        right_layout.addWidget(temp_group)

        # pH thresholds
        ph_group = QGroupBox("pH Thresholds")
        ph_group.setFont(QFont("Arial", 11, QFont.Bold))
        ph_grid = QGridLayout()

        ph_grid.addWidget(QLabel("Min Normal:"), 0, 0)
        self.ph_min_normal = QDoubleSpinBox()
        self.ph_min_normal.setRange(0, 14)
        self.ph_min_normal.setSingleStep(0.1)
        self.ph_min_normal.setValue(config.PH_MIN_NORMAL)
        self.ph_min_normal.valueChanged.connect(self.update_thresholds)
        ph_grid.addWidget(self.ph_min_normal, 0, 1)

        ph_grid.addWidget(QLabel("Max Normal:"), 1, 0)
        self.ph_max_normal = QDoubleSpinBox()
        self.ph_max_normal.setRange(0, 14)
        self.ph_max_normal.setSingleStep(0.1)
        self.ph_max_normal.setValue(config.PH_MAX_NORMAL)
        self.ph_max_normal.valueChanged.connect(self.update_thresholds)
        ph_grid.addWidget(self.ph_max_normal, 1, 1)

        ph_grid.addWidget(QLabel("Min Warning:"), 2, 0)
        self.ph_min_warning = QDoubleSpinBox()
        self.ph_min_warning.setRange(0, 14)
        self.ph_min_warning.setSingleStep(0.1)
        self.ph_min_warning.setValue(config.PH_MIN_WARNING)
        self.ph_min_warning.valueChanged.connect(self.update_thresholds)
        ph_grid.addWidget(self.ph_min_warning, 2, 1)

        ph_grid.addWidget(QLabel("Max Warning:"), 3, 0)
        self.ph_max_warning = QDoubleSpinBox()
        self.ph_max_warning.setRange(0, 14)
        self.ph_max_warning.setSingleStep(0.1)
        self.ph_max_warning.setValue(config.PH_MAX_WARNING)
        self.ph_max_warning.valueChanged.connect(self.update_thresholds)
        ph_grid.addWidget(self.ph_max_warning, 3, 1)

        ph_group.setLayout(ph_grid)
        right_layout.addWidget(ph_group)

        right_layout.addStretch()
        content_layout.addLayout(right_layout, stretch=2)

        main_layout.addLayout(content_layout)

    def update_display(self):
        # update temperature
        temp = state["temperature"]
        if temp is not None:
            color = get_temp_color(temp)
            self.temp_label.setText(f"Temperature: {temp}°C")
            self.temp_label.setStyleSheet(f"color: {color};")
        else:
            self.temp_label.setText("Temperature: --")
            self.temp_label.setStyleSheet("color: gray;")

        # update pH
        ph = state["ph"]
        if ph is not None:
            color = get_ph_color(ph)
            self.ph_label.setText(f"pH: {ph}")
            self.ph_label.setStyleSheet(f"color: {color};")
        else:
            self.ph_label.setText("pH: --")
            self.ph_label.setStyleSheet("color: gray;")

        # update timestamp
        if state["last_update"]:
            self.update_label.setText("Last update: " + state["last_update"])

        # update light
        if state["light"] == "on":
            self.light_label.setText("Light: ON")
            self.light_label.setStyleSheet("background-color: #f1c40f; color: #2c3e50; padding: 10px; border-radius: 5px; font-size: 16px; font-weight: bold;")
        else:
            self.light_label.setText("Light: OFF")
            self.light_label.setStyleSheet("background-color: #555; color: white; padding: 10px; border-radius: 5px; font-size: 16px; font-weight: bold;")

        # update last feed time
        if state["last_feed"]:
            self.feed_label.setText("Last feeding: " + state["last_feed"])

        # update event log
        self.event_list.clear()
        for timestamp, level, message in state["events"]:
            item = QListWidgetItem(f"[{timestamp}] [{level}] {message}")
            if level == "ALARM":
                item.setForeground(QColor("#e74c3c"))
            elif level == "WARNING":
                item.setForeground(QColor("#f39c12"))
            else:
                item.setForeground(QColor("#3498db"))
            self.event_list.addItem(item)

    def update_thresholds(self):
        # update config values live from the spinboxes
        config.TEMP_MIN_NORMAL = self.temp_min_normal.value()
        config.TEMP_MAX_NORMAL = self.temp_max_normal.value()
        config.TEMP_MIN_WARNING = self.temp_min_warning.value()
        config.TEMP_MAX_NORMAL = self.temp_max_warning.value()
        config.PH_MIN_NORMAL = self.ph_min_normal.value()
        config.PH_MAX_NORMAL = self.ph_max_normal.value()
        config.PH_MIN_WARNING = self.ph_min_warning.value()
        config.PH_MAX_WARNING = self.ph_max_warning.value()

    def feed_now(self):
        now = datetime.now().isoformat()
        feed_data = {
            "action": "feed",
            "amount": "normal",
            "timestamp": now
        }
        try:
            self.mqtt_client.publish(config.TOPIC_FEEDING_CMD, json.dumps(feed_data))
        except Exception as e:
            add_event("WARNING", "Failed to send feed command")

    def turn_light_on(self):
        cmd = {"state": "on", "timestamp": datetime.now().isoformat()}
        try:
            self.mqtt_client.publish(config.TOPIC_LIGHT_CMD, json.dumps(cmd))
        except Exception:
            add_event("WARNING", "Failed to send light command")

    def turn_light_off(self):
        cmd = {"state": "off", "timestamp": datetime.now().isoformat()}
        try:
            self.mqtt_client.publish(config.TOPIC_LIGHT_CMD, json.dumps(cmd))
        except Exception:
            add_event("WARNING", "Failed to send light command")


def main():
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message

    start_mqtt_thread(mqtt_client)

    app = QApplication(sys.argv)
    window = AquariumDashboard(mqtt_client)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
