import os
import threading
import time
from flask import Flask, request, jsonify, Response
import requests
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
REGISTRY = os.environ["REGISTRY_URL"]
NAME = "ingestion-service"
SELF_URL = os.environ["SELF_URL"]
PORT = int(os.environ.get("PORT", 5001))

REQUESTS = Counter("ingest_requests_total", "Pedidos recebidos em /ingest", ["status"])
LATENCY = Histogram("ingest_latency_seconds", "Latencia do reencaminhamento para o storage")
FORWARD_ERRORS = Counter("ingest_forward_errors_total", "Falhas ao contactar o storage")

def resolve(svc):
    return requests.get(f"{REGISTRY}/services/{svc}", timeout=2).json()["url"]

def heartbeat():
    while True:
        try:
            requests.post(f"{REGISTRY}/register", json={"name": NAME, "url": SELF_URL}, timeout=2)
        except Exception as e:
            print("Registry unavailable:", e, flush=True)
        time.sleep(30)

@app.route("/ingest", methods=["POST"])
def ingest():
    data = request.get_json()
    start = time.time()
    try:
        storage = resolve("storage-service")
        r = requests.post(storage + "/store", json=data, timeout=3)
    except Exception:
        FORWARD_ERRORS.inc()
        REQUESTS.labels(status="error").inc()
        raise
    LATENCY.observe(time.time() - start)
    REQUESTS.labels(status=str(r.status_code)).inc()
    return jsonify({"stored": True, "via": storage}), r.status_code

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    threading.Thread(target=heartbeat, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
