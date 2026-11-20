# SSLE Project 1 — threat detection, monitoring and prevention

A service-oriented architecture on K3s, observed by two independent planes: Prometheus measures numbers,
Wazuh interprets logs. Three threats are demonstrated against it, each with a detection and a
countermeasure.

This repository is the source of truth for everything the system runs: the code of the services, the K3s
manifests, the configuration of the Wazuh manager and of the victim, and the few host-level pieces that
have no manifest. The report lives in `docs/`.

```
appsrc/    code and Dockerfile of each service, one directory per service
k3s/       Kubernetes manifests, applied from the VM
wazuh/     ossec.conf, local rules and the reputation lists of the manager
victim/    ossec.conf of the agent on the victim
vm/        what runs outside Kubernetes: the containers, the registry, the panel
docs/      the report
painel.sh  starts both panels on the host browser: Prometheus and Wazuh
```

## Elements

| Element | Where it runs | What it is |
|---|---|---|
| `registry` | K3s pod, `:5050` | service registry, name resolution of the architecture |
| `sensor` ×3 | K3s StatefulSet (`sensor-0..2`), `:9100` metrics | one reading every 5 s; the identity is built as `site.zone.node.element`, e.g. `ua.lab.k3s-node1.sensor-0` |
| `ingestion` | K3s pod, `:5001` | receives `/ingest`, forwards to storage |
| `storage` | K3s pod, `:5002` + PVC 1 Gi | SQLite on `/data/temp_data.db`, plausibility check, quarantine, `location` column |
| `analytics` | K3s pod, `:5003` | reads only trusted rows and aggregates |
| `prometheus` | K3s pod, `:9090` | scrapes `/metrics` every 15 s, 8 rules in 3 groups |
| `alertmanager` | K3s pod, `:9093` | groups and routes, webhook receiver with `send_resolved` |
| `action-response` | K3s pod, `:8080` | webhook that creates or deletes a `NetworkPolicy` |
| `node-exporter` | K3s DaemonSet, `:9100` | host metrics |
| `wazuh` | Incus container, `10.255.255.150` | manager, indexer and dashboard 4.14.10, all-in-one |
| `victim` | Incus container, `10.255.255.151` | apache2 and the Wazuh agent |
| cluster | Incus containers `k3s-master` `.100`, `k3s-node1` `.199` | K3s; application pods pinned to the worker |
| images | Incus container `docker`, `10.255.255.44:5000` | builds and serves the six images |

## Threats

| Threat | Target | Detection | Response |
|---|---|---|---|
| Volumetric DoS (`ab`) | `ingestion` | numeric: rate above 5 req/s, p95 latency, correlation with CPU | `NetworkPolicy` created by the webhook, removed on resolve |
| Man-in-the-middle | sensor → `ingestion` | numeric: plausibility counter published by `storage` | source blocked by `NetworkPolicy`; the row is stored with `trusted = 0` |
| Shellshock (CVE-2014-6271) | `victim` (apache) | semantic: Wazuh rule 31168 on the access log | `firewall-drop` by the agent, `iptables` for 60 s; reputation list for repeat offenders |

Identity is constructed, not assigned. `SITE` and `ZONE` come from the manifest, the node from
`spec.nodeName` through the downward API, and the element from the pod ordinal of a StatefulSet, which is
stable across restarts. The name alone says where the element is, in physical and logical terms, and the
`location` prefix travels with every reading, so `analytics` can aggregate by location.

The man-in-the-middle is executed by poisoning the service registry, which has no authentication and
overwrites entries by name. The Shellshock rule ships with Wazuh; what this project adds is the binding
between the rule and the active response, and the reputation list in `wazuh/lists/`.

## Deploying

On the VM, as user `ssle`. `/home/ssle/appsrc` and `/home/ssle/k8s` are symlinks into this repository, so
the commands below work from either path.

```bash
# build and publish an image, with a new tag on every build
incus file push /home/ssle/ssle-proj1/appsrc/<svc>/app.py docker/srv/app/<svc>/app.py
incus exec docker -- bash -c "cd /srv/app/<svc> && docker build -t 10.255.255.44:5000/<svc>:<tag> . && docker push 10.255.255.44:5000/<svc>:<tag>"

# apply a manifest
incus exec k3s-master -- kubectl apply -f - < /home/ssle/ssle-proj1/k3s/<svc>.yaml
```

The two Wazuh containers and the image registry are not managed by K3s. Their files in `wazuh/` and
`victim/` are copied into the containers by hand with `incus file push`, and `vm/README.md` describes how
the containers, the registry and the two panels are rebuilt.

```bash
# both panels on the host browser: Prometheus :9090 and the Wazuh dashboard :8443
/home/ssle/painel.sh
``` The `mitm` Deployment is applied at `replicas: 0`; it is the
attacker of the man-in-the-middle demonstration and is started with
`kubectl scale deploy/mitm --replicas=1`.
