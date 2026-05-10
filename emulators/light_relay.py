import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
import config

# keep track of the light state
light_on = False

def get_scheduled_state():
    # light should be ON between 08:00 and 22:00
    hour = datetime.now().hour
    if 8 <= hour < 22:
        return True
    return False

def publish_light_status(client, state, source):
    now = datetime.now().isoformat()
    status_data = {
        "state": "on" if state else "off",
        "source": source,
        "timestamp": now
    }
    try:
        client.publish(config.TOPIC_LIGHT_STATUS, json.dumps(status_data))
        print(f"[{now}] Light is {'ON' if state else 'OFF'} (source: {source})")
    except Exception as e:
        print("Error publishing light status: " + str(e))

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Light relay connected to broker")
        # subscribe to light commands
        client.subscribe(config.TOPIC_LIGHT_CMD)
        print("Subscribed to " + config.TOPIC_LIGHT_CMD)
    else:
        print("Connection failed with code: " + str(rc))

def on_disconnect(client, userdata, rc):
    print("Light relay disconnected, reconnecting...")
    while True:
        try:
            client.reconnect()
            print("Reconnected!")
            break
        except Exception:
            time.sleep(5)

def on_message(client, userdata, msg):
    global light_on
    try:
        data = json.loads(msg.payload.decode())
        command = data.get("state", "").lower()
        if command == "on":
            light_on = True
            publish_light_status(client, True, "manual")
        elif command == "off":
            light_on = False
            publish_light_status(client, False, "manual")
        else:
            print("Unknown light command: " + str(command))
    except json.JSONDecodeError:
        print("Got bad JSON on light command topic")

def main():
    global light_on

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    try:
        client.connect(config.BROKER_HOST, config.BROKER_PORT, 60)
    except Exception as e:
        print("Could not connect to broker: {}".format(e))
        return

    client.loop_start()

    # set initial state based on schedule
    light_on = get_scheduled_state()
    print("Light relay started. Initial state: " + ("ON" if light_on else "OFF"))
    print("Press Ctrl+C to stop.")

    try:
        while True:
            # check schedule every 10 seconds
            scheduled = get_scheduled_state()
            if scheduled != light_on:
                light_on = scheduled
                publish_light_status(client, light_on, "schedule")
            else:
                # still publish current state so GUI stays updated
                publish_light_status(client, light_on, "schedule")

            time.sleep(10)

    except KeyboardInterrupt:
        print("\nLight relay stopped.")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
