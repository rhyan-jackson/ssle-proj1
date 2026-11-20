#!/usr/bin/env bash
# Publish the Prometheus panel on the host without a NodePort.
#
# The chain is: host -> 192.168.122.139:9090 -> incus proxy device `prom9090`
# -> 127.0.0.1:9090 inside k3s-master -> the relay unit started by painel.sh
# -> the prometheus pod.
#
# The device lives in the container's config, not in Kubernetes, so it survives
# a restart of the whole cluster and has to be recreated only if the container
# itself is recreated.
#
# usage: ./prom9090.sh

set -euo pipefail

CONTAINER="k3s-master"
DEVICE="prom9090"
LISTEN="192.168.122.139:9090"
CONNECT="127.0.0.1:9090"

if incus config device show "$CONTAINER" 2>/dev/null | grep -q "^${DEVICE}:"; then
  echo "device $DEVICE already exists"
  exit 0
fi

incus config device add "$CONTAINER" "$DEVICE" proxy \
  listen="tcp:${LISTEN}" connect="tcp:${CONNECT}"

echo "device $DEVICE added: ${LISTEN} -> ${CONNECT}"
echo "now start the relay: /home/ssle/painel.sh"
