# What runs outside Kubernetes

The system is not only K3s objects. Five Incus containers, one docker registry
and two proxy devices have no manifest, and this directory is where they are
written down so they can be rebuilt. Each script is the command that was
actually used, made idempotent where it could be.

| Piece | Where it runs | Recreated by |
|---|---|---|
| the five Incus containers | host | the description below |
| image registry `registry-imgs` | container `docker` | `registry.sh` |
| the two panel devices | `k3s-master` and `wazuh-container` | `painel.sh` at the root of the repository |

## The containers

| Name | Address | What it is |
|---|---|---|
| `docker` | `10.255.255.44` | docker daemon that builds and serves the images on `:5000` |
| `k3s-master` | `10.255.255.100` | K3s server; tainted, takes no application pods |
| `k3s-node1` | `10.255.255.199` | K3s agent, `role=worker`; runs every application pod |
| `wazuh-container` | `10.255.255.150` | Wazuh 4.14.10 all-in-one: manager, indexer, dashboard |
| `victim-container` | `10.255.255.151` | apache2 with the Wazuh agent, the target of Shellshock |

They were created from images of the course guide, on the `incusbr0` bridge,
with `10.255.255.0/24` as the only network the attack traffic may use. The two
K3s nodes carry the profile `k3s`; the addresses above come from the profile,
not from a manifest, so a container recreated without the profile will not
answer on the same address.

## The two panels

Both panels are published by `painel.sh`, on the address of the VM and not on
`0.0.0.0`, so nothing leaves the lab network. They use different mechanisms
because the services behind them are reachable in different ways.

```
Prometheus   http://192.168.122.139:9090
  host -> device prom9090 on k3s-master -> 127.0.0.1:9090
       -> transient unit prometheus-forward (kubectl port-forward) -> pod

Wazuh        https://192.168.122.139:8443
  host -> device wazuh8443 on wazuh-container -> 127.0.0.1:443
```

Prometheus needs the relay because its pod address exists only inside the
cluster. The Wazuh dashboard listens on 443 of its own container, so a proxy
device is enough. Its certificate is self-signed and the browser warning is
expected. The login is `admin`, and the password is not in this repository.

`painel.sh start` creates whichever device is missing, starts the relay if it is
not active, and prints both addresses; `status` shows the relay, both HTTP codes
and whether each device is present; `stop` stops the relay and removes both
devices, which is how the ports are closed again.

## Known defect: the registry volume mounts the wrong path

The running container `registry-imgs` has an anonymous volume at `/var/registry`,
which does not exist inside the container. The images live in `/var/lib/registry`,
in the container's writable layer, 126.9 MB of it on 2026-11-20.

Consequence: `docker restart registry-imgs` keeps the catalogue, because the
writable layer survives a restart, but removing or recreating the container
loses every image. `registry.sh` below mounts the correct path and a named
volume, so a recreation no longer repeats this. The defect is kept as a
declared limitation: the container is not rebuilt before the delivery, because
the images it would lose are the ones the cluster runs.
