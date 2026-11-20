#!/usr/bin/env bash
# Recreate the image registry the cluster pulls from.
#
# Runs on the VM as user `ssle`: the docker daemon lives in the Incus container
# `docker`, and the cluster reaches it at 10.255.255.44:5000.
#
# The running container was created with an anonymous volume mounted at
# /var/registry, a path that does not exist inside registry:2, so its data sits
# in the container's writable layer. This script mounts /var/lib/registry on a
# named volume instead, which is where the registry actually writes.
#
# usage: ./registry.sh

set -euo pipefail

NAME="registry-imgs"
VOLUME="registry-data"
PORT="5000"

if incus exec docker -- docker inspect "$NAME" >/dev/null 2>&1; then
  echo "$NAME already exists; nothing to do"
  echo "to rebuild it on purpose: incus exec docker -- docker rm -f $NAME"
  exit 0
fi

incus exec docker -- docker run -d \
  --name "$NAME" \
  --restart always \
  -p "${PORT}:${PORT}" \
  -v "${VOLUME}:/var/lib/registry" \
  registry:2 >/dev/null

incus exec docker -- curl -sf "http://localhost:${PORT}/v2/_catalog"
echo
echo "$NAME listening on 10.255.255.44:${PORT}"
