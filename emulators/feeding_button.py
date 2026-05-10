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
        print("Feeding emulator connected to broker")
        # listen for feeding commands from the GUI
        client.subscribe(config.TOPIC_FEEDING_CMD)
        print("Subscribed to " + config.TOPIC_FEEDING_CMD)
    else:
        print("Connection failed with code: " + str(rc))

def on_disconnect(client, userdata, rc):
    print("Feeding emulator disconnected, reconnecting...")
    while True:
        try:
            client.reconnect()
            print("Reconnected!")
            break
        except Exception:
            time.sleep(5)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        action = data.get("action", "")
        amount = data.get("amount", "normal")
        now = datetime.now().isoformat()

        if action == "feed":
            print(f"[{now}] Received feed command - dispensing {amount} amount of food")

            # send back confirmation that feeding was done
            status_data = {
                "status": "completed",
                "amount": amount,
                "timestamp": now
            }
            try:
                client.publish(config.TOPIC_FEEDING_STATUS, json.dumps(status_data))
                print(f"[{now}] Feeding completed!")
            except Exception as e:
                print("Error publishing feed status: " + str(e))

    except json.JSONDecodeError:
        print("Got bad JSON on feeding topic")

def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    try:
        client.connect(config.BROKER_HOST, config.BROKER_PORT, 60)
    except Exception as e:
        print("Could not connect to broker: {}".format(e))
        return

    print("Feeding emulator started. Waiting for feed commands...")
    print("Press Ctrl+C to stop.")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nFeeding emulator stopped.")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
