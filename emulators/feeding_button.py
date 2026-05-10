import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
import config

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Feeding button connected to broker")
    else:
        print("Connection failed with code: " + str(rc))

def on_disconnect(client, userdata, rc):
    print("Feeding button disconnected, reconnecting...")
    while True:
        try:
            client.reconnect()
            print("Reconnected!")
            break
        except Exception:
            time.sleep(5)

def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    try:
        client.connect(config.BROKER_HOST, config.BROKER_PORT, 60)
    except Exception as e:
        print("Could not connect to broker: {}".format(e))
        return

    client.loop_start()

    print("Feeding button emulator started. Press Ctrl+C to stop.")
    try:
        while True:
            now = datetime.now().isoformat()

            feed_data = {
                "action": "feed",
                "amount": "normal",
                "timestamp": now
            }
            try:
                client.publish(config.TOPIC_FEEDING_CMD, json.dumps(feed_data))
                print(f"[{now}] Feeding button pressed - dispensing food")
            except Exception as e:
                print("Error publishing feed command: " + str(e))

            time.sleep(config.FEEDING_INTERVAL)

    except KeyboardInterrupt:
        print("\nFeeding button stopped.")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
