import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import paho.mqtt.client as mqtt
import json
import time
import random
from datetime import datetime
import config

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Sensor connected to MQTT broker")
    else:
        print("Failed to connect, return code: " + str(rc))

def on_disconnect(client, userdata, rc):
    print("Sensor disconnected from broker, trying to reconnect...")
    while True:
        try:
            client.reconnect()
            print("Reconnected!")
            break
        except Exception:
            # make sure we don't crash if broker is down
            time.sleep(5)

def generate_temperature():
    # most of the time normal range, sometimes spikes to trigger alerts
    if random.random() < 0.15:
        # spike outside normal range
        return round(random.uniform(18.0, 35.0), 1)
    else:
        return round(random.uniform(22.0, 28.0), 1)

def generate_ph():
    # same idea - usually normal, occasionally spikes
    if random.random() < 0.15:
        return round(random.uniform(5.8, 8.8), 1)
    else:
        return round(random.uniform(6.5, 8.0), 1)

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

    print("Temperature & pH sensor started. Press Ctrl+C to stop.")
    try:
        while True:
            now = datetime.now().isoformat()

            temp = generate_temperature()
            temp_data = {
                "value": temp,
                "unit": "celsius",
                "timestamp": now
            }
            try:
                client.publish(config.TOPIC_TEMPERATURE, json.dumps(temp_data))
                print(f"[{now}] Temperature: {temp}°C")
            except Exception as e:
                print("Error publishing temperature: " + str(e))

            ph = generate_ph()
            ph_data = {
                "value": ph,
                "unit": "pH",
                "timestamp": now
            }
            try:
                client.publish(config.TOPIC_PH, json.dumps(ph_data))
                print("[{}] pH: {}".format(now, ph))
            except Exception as e:
                print("Error publishing pH: " + str(e))

            time.sleep(config.SENSOR_INTERVAL)

    except KeyboardInterrupt:
        print("\nSensor stopped.")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
