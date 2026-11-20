# What runs outside Kubernetes

The system is not only K3s objects. Five Incus containers, one docker registry
and one proxy device have no manifest, and this directory is where they are
written down so they can be rebuilt. Each script is the command that was
actually used, made idempotent where it could be.

| Piece | Where it runs | Recreated by |
|---|---|---|
| the five Incus containers | host | the description below |
| image registry `registry-imgs` | container `docker` | `registry.sh` |
| the panel proxy `prom9090` | `k3s-master` | `prom9090.sh` |
| the Prometheus panel relay | `k3s-master` | `painel.sh` at the root of the repository |

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

## Known defect: the registry volume mounts the wrong path

The running container `registry-imgs` has an anonymous volume at `/var/registry`,
which does not exist inside the container. The images live in `/var/lib/registry`,
in the container's writable layer, 126.9 MB of it on 2026-11-20.

Consequence: `docker restart registry-imgs` keeps the catalogue, because the
writable layer survives a restart, but removing or recreating the container
loses every image. `registry.sh` below mounts the correct path and a named
volume, so a recreation no longer repeats this.
