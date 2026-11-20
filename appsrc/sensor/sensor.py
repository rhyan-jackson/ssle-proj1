import os
import socket
import threading
import time
import random
import requests
from prometheus_client import Counter, Gauge, start_http_server

REGISTRY = os.environ["REGISTRY_URL"]

# Hierarchical, constructed identity. The name says where the element is, in
# physical and in logical terms, so an incident can be located from the name
# alone: site.zone.node.element
SITE = os.environ.get("SITE", "ua")
ZONE = os.environ.get("ZONE", "lab")
NODE = os.environ.get("NODE_NAME", socket.gethostname())
ELEMENT = os.environ.get("POD_NAME", socket.gethostname())
LOCATION = f"{SITE}.{ZONE}.{NODE}"
DEVICE_ID = f"{LOCATION}.{ELEMENT}"

SELF_URL = os.environ["SELF_URL"]
PORT = int(os.environ.get("PORT", 5000))
METRICS_PORT = int(os.environ.get("METRICS_PORT", 9100))
INTERVAL = float(os.environ.get("INTERVAL", 5))

SENT = Counter("sensor_sent_total", "Leituras enviadas", ["device_id", "location"])
ERRORS = Counter(
    "sensor_send_errors_total", "Falhas de envio", ["device_id", "location"]
)
LAST = Gauge(
    "sensor_last_temperature", "Ultima leitura gerada", ["device_id", "location"]
)


def heartbeat():
    while True:
        try:
            requests.post(
                f"{REGISTRY}/register",
                json={"name": DEVICE_ID, "url": SELF_URL},
                timeout=2,
            )
        except Exception as e:
            print("Registry unavailable:", e, flush=True)
        time.sleep(30)


def main():
    start_http_server(METRICS_PORT)
    print(f"identity: {DEVICE_ID}  location: {LOCATION}", flush=True)
    threading.Thread(target=heartbeat, daemon=True).start()
    while True:
        temp = round(random.uniform(20.0, 30.0), 2)
        payload = {"device_id": DEVICE_ID, "location": LOCATION, "temperature": temp}
        try:
            ingestion = requests.get(
                f"{REGISTRY}/services/ingestion-service", timeout=2
            ).json()["url"]
            requests.post(ingestion + "/ingest", json=payload, timeout=3)
            SENT.labels(device_id=DEVICE_ID, location=LOCATION).inc()
            LAST.labels(device_id=DEVICE_ID, location=LOCATION).set(temp)
            print("Sent:", payload, flush=True)
        except Exception as e:
            ERRORS.labels(device_id=DEVICE_ID, location=LOCATION).inc()
            print("Error:", e, flush=True)
        time.sleep(INTERVAL)


main()
