import os
import socket
import threading
import time
import random
import requests
from prometheus_client import Counter, Gauge, start_http_server

REGISTRY = os.environ["REGISTRY_URL"]
DEVICE_ID = os.environ.get("DEVICE_ID", socket.gethostname())
SELF_URL = os.environ["SELF_URL"]
PORT = int(os.environ.get("PORT", 5000))
METRICS_PORT = int(os.environ.get("METRICS_PORT", 9100))
INTERVAL = float(os.environ.get("INTERVAL", 5))

SENT = Counter("sensor_sent_total", "Leituras enviadas", ["device_id"])
ERRORS = Counter("sensor_send_errors_total", "Falhas de envio", ["device_id"])
LAST = Gauge("sensor_last_temperature", "Ultima leitura gerada", ["device_id"])

def heartbeat():
    while True:
        try:
            requests.post(f"{REGISTRY}/register", json={"name": DEVICE_ID, "url": SELF_URL}, timeout=2)
        except Exception as e:
            print("Registry unavailable:", e, flush=True)
        time.sleep(30)

def main():
    start_http_server(METRICS_PORT)
    threading.Thread(target=heartbeat, daemon=True).start()
    while True:
        temp = round(random.uniform(20.0, 30.0), 2)
        payload = {"device_id": DEVICE_ID, "temperature": temp}
        try:
            ingestion = requests.get(f"{REGISTRY}/services/ingestion-service", timeout=2).json()["url"]
            requests.post(ingestion + "/ingest", json=payload, timeout=3)
            SENT.labels(device_id=DEVICE_ID).inc()
            LAST.labels(device_id=DEVICE_ID).set(temp)
            print("Sent:", payload, flush=True)
        except Exception as e:
            ERRORS.labels(device_id=DEVICE_ID).inc()
            print("Error:", e, flush=True)
        time.sleep(INTERVAL)

main()
