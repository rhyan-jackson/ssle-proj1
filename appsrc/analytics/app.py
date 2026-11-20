import os
import threading
import time
from flask import Flask, jsonify, Response
import requests
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
REGISTRY = os.environ["REGISTRY_URL"]
NAME = "analytics-service"
SELF_URL = os.environ["SELF_URL"]
PORT = int(os.environ.get("PORT", 5003))

QUERIES = Counter("analytics_requests_total", "Pedidos recebidos", ["endpoint"])
LAST_AVG = Gauge("analytics_average_temperature", "Ultima media calculada")
UPSTREAM_ERRORS = Counter("analytics_upstream_errors_total", "Falhas ao consultar o storage")

LISTENERS = Counter("analytics_storage_listeners", "Resolucoes do storage")

def rows():
    storage = requests.get(f"{REGISTRY}/services/storage-service", timeout=2).json()["url"]
    return requests.get(storage + "/temperatures?trusted=1", timeout=3).json()

def heartbeat():
    while True:
        try:
            requests.post(f"{REGISTRY}/register", json={"name": NAME, "url": SELF_URL}, timeout=2)
        except Exception as e:
            print("Registry unavailable:", e, flush=True)
        time.sleep(30)

@app.route("/average", methods=["GET"])
def average():
    QUERIES.labels(endpoint="average").inc()
    try:
        data = rows()
    except Exception:
        UPSTREAM_ERRORS.inc()
        raise
    if not data:
        return jsonify({"average_temperature": None})
    value = round(sum(r["temperature"] for r in data) / len(data), 2)
    LAST_AVG.set(value)
    return jsonify({"average_temperature": value})

@app.route("/per-device", methods=["GET"])
def per_device():
    QUERIES.labels(endpoint="per-device").inc()
    try:
        data = rows()
    except Exception:
        UPSTREAM_ERRORS.inc()
        raise
    out = {}
    for r in data:
        out.setdefault(r["device_id"], []).append(r["temperature"])
    return jsonify({k: round(sum(v) / len(v), 2) for k, v in out.items()})

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    threading.Thread(target=heartbeat, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
