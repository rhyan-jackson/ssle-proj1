import json, os, ssl, sys, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SA = "/var/run/secrets/kubernetes.io/serviceaccount"
API = "https://kubernetes.default.svc"
NS = os.environ.get("NAMESPACE", "default")
ACTION = os.environ.get("ACTION", "netpol")
PORT = int(os.environ.get("PORT", "8080"))
POLICY = "ingestion-allow-sensors"

NP = {
    "apiVersion": "networking.k8s.io/v1",
    "kind": "NetworkPolicy",
    "metadata": {"name": POLICY, "labels": {"managed-by": "action-response"}},
    "spec": {
        "podSelector": {"matchLabels": {"app": "ingestion"}},
        "policyTypes": ["Ingress"],
        "ingress": [{
                "from": [{"podSelector": {"matchLabels": {"app": "sensor"}}}],
                "ports": [{"protocol": "TCP", "port": 5001}],
            },
            {
                "from": [{"podSelector": {"matchLabels": {"app": "prometheus"}}}],
                "ports": [{"protocol": "TCP", "port": 5001}],
            }],
    },
}

NP_PATH = f"/apis/networking.k8s.io/v1/namespaces/{NS}/networkpolicies"
SCALE_PATH = f"/apis/apps/v1/namespaces/{NS}/deployments/ingestion/scale"


def call(method, path, body=None, ctype="application/json"):
    with open(f"{SA}/token") as f:
        token = f.read().strip()
    ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def block():
    if call("GET", f"{NP_PATH}/{POLICY}") != 404:
        return f"networkpolicy {POLICY} já existia"
    code = call("POST", NP_PATH, NP)
    return f"networkpolicy {POLICY} criada (HTTP {code})"


def unblock():
    code = call("DELETE", f"{NP_PATH}/{POLICY}")
    return f"networkpolicy {POLICY} removida (HTTP {code})"


def scale(n):
    body = {"spec": {"replicas": n}}
    code = call("PATCH", SCALE_PATH, body, "application/merge-patch+json")
    return f"ingestion escalado para {n} réplicas (HTTP {code})"


VOLUMETRIC = {"TaxaDeIngestaoAlta", "LatenciaIngestaoAlta", "PayloadAdulterado"}


def react(payload):
    out = []
    for a in payload.get("alerts", []):
        name = a.get("labels", {}).get("alertname", "")
        status = a.get("status", "")
        if name not in VOLUMETRIC:
            out.append(f"ignorado: {name} ({status})")
            continue
        if status == "firing":
            out.append(block() if ACTION == "netpol" else scale(3))
        elif status == "resolved":
            out.append(unblock() if ACTION == "netpol" else scale(1))
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/", "/healthz"):
            return self._send(200, '{"ready": true}')
        self._send(404, '{"error": "not found"}')

    def do_POST(self):
        if self.path != "/alert":
            return self._send(404, '{"error": "not found"}')
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, '{"error": "bad json"}')
        actions = react(payload)
        for a in actions:
            print(f"[action] {a}", flush=True)
        self._send(200, json.dumps({"actions": actions}))

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")


if __name__ == "__main__":
    print(f"[action] a ouvir :{PORT} | modo={ACTION} | namespace={NS}", flush=True)
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
