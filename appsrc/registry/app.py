import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
registry = {}
PORT = int(os.environ.get("PORT", 5050))

REGISTRATIONS = Counter("registry_registrations_total", "Registos recebidos")
SERVICES = Gauge("registry_services_registered", "Servicos atualmente registados")

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    name, url = data.get("name"), data.get("url")
    if not name or not url:
        return jsonify({"error": "Missing name or url"}), 400
    registry[name] = {"url": url, "timestamp": datetime.now(timezone.utc).isoformat()}
    REGISTRATIONS.inc()
    SERVICES.set(len(registry))
    return jsonify({"message": f"{name} registered"}), 200

@app.route("/services", methods=["GET"])
def services():
    return jsonify(registry)

@app.route("/services/<name>", methods=["GET"])
def get_service(name):
    svc = registry.get(name)
    return jsonify(svc) if svc else (jsonify({"error": "Not found"}), 404)

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
