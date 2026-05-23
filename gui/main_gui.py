import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import threading
import paho.mqtt.client as mqtt
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

from gui.state import on_connect, on_disconnect, on_message
from gui.app import AquariumApp


def start_mqtt_thread(client):
    def run():
        try:
            import config
            client.connect(config.BROKER_HOST, config.BROKER_PORT, 60)
            client.loop_forever()
        except Exception as e:
            from gui.state import add_event
            add_event("WARNING", "MQTT error: " + str(e))
    threading.Thread(target=run, daemon=True).start()


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    start_mqtt_thread(client)

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 13))
    win = AquariumApp(client)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
