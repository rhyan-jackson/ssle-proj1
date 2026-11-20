import os
import sqlite3
import threading
import time
from flask import Flask, request, jsonify, Response
import requests
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
DB = os.environ.get("DB_PATH", "/data/temp_data.db")
REGISTRY = os.environ["REGISTRY_URL"]
NAME = "storage-service"
SELF_URL = os.environ["SELF_URL"]
PORT = int(os.environ.get("PORT", 5002))
TEMP_MIN = float(os.environ.get("TEMP_MIN", "-50"))
TEMP_MAX = float(os.environ.get("TEMP_MAX", "60"))

INSERTED = Counter("storage_inserts_total", "Linhas inseridas em temperatures")
LAST_TEMP = Gauge("storage_last_temperature", "Ultima temperatura recebida por dispositivo", ["device_id"])
READS = Counter("storage_reads_total", "Consultas a /temperatures")
OUT_OF_RANGE = Counter("storage_out_of_range_total", "Leituras fora da faixa plausivel", ["device_id"])
QUARANTINED = Gauge("storage_quarantined_rows", "Linhas marcadas como nao confiaveis")

def init_db():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS temperatures ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, temperature REAL, "
        "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, trusted INTEGER DEFAULT 1)"
    )
    cols = [r[1] for r in conn.execute("PRAGMA table_info(temperatures)")]
    if "trusted" not in cols:
        conn.execute("ALTER TABLE temperatures ADD COLUMN trusted INTEGER DEFAULT 1")
    conn.commit()
    QUARANTINED.set(conn.execute("SELECT COUNT(*) FROM temperatures WHERE trusted = 0").fetchone()[0])
    conn.close()

def heartbeat():
    while True:
        try:
            requests.post(f"{REGISTRY}/register", json={"name": NAME, "url": SELF_URL}, timeout=2)
        except Exception as e:
            print("Registry unavailable:", e, flush=True)
        time.sleep(30)

def plausible(value):
    return TEMP_MIN <= value <= TEMP_MAX

@app.route("/store", methods=["POST"])
def store():
    d = request.get_json()
    trusted = 1 if plausible(d["temperature"]) else 0
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO temperatures (device_id, temperature, trusted) VALUES (?, ?, ?)",
        (d["device_id"], d["temperature"], trusted),
    )
    conn.commit(); conn.close()
    INSERTED.inc()
    LAST_TEMP.labels(device_id=d["device_id"]).set(d["temperature"])
    if not trusted:
        OUT_OF_RANGE.labels(device_id=d["device_id"]).inc()
        conn = sqlite3.connect(DB)
        QUARANTINED.set(conn.execute("SELECT COUNT(*) FROM temperatures WHERE trusted = 0").fetchone()[0])
        conn.close()
    return jsonify({"status": "stored", "trusted": bool(trusted)}), 200

@app.route("/temperatures", methods=["GET"])
def temperatures():
    only_trusted = request.args.get("trusted") == "1"
    sql = "SELECT device_id, temperature, timestamp, trusted FROM temperatures"
    if only_trusted:
        sql += " WHERE trusted = 1"
    conn = sqlite3.connect(DB)
    rows = conn.execute(sql).fetchall()
    quarantined = conn.execute("SELECT COUNT(*) FROM temperatures WHERE trusted = 0").fetchone()[0]
    conn.close()
    QUARANTINED.set(quarantined)
    READS.inc()
    return jsonify([
        {"device_id": r[0], "temperature": r[1], "timestamp": r[2], "trusted": bool(r[3])}
        for r in rows
    ])

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=heartbeat, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
