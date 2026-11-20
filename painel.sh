#!/usr/bin/env bash
# Painel do Prometheus a partir do host.
#
# Cadeia: host -> VM 192.168.122.139:9090 -> device incus prom9090 -> 127.0.0.1:9090
# no k3s-master -> unidade systemd "prometheus-forward" (kubectl port-forward) -> pod.
#
# O relay é uma unidade transitoria do systemd dentro do k3s-master: sobrevive ao
# fechar do terminal, mas morre se o container reiniciar. Por isso o script e
# idempotente: rodar de novo religa o que tiver caido.
#
# uso: ./painel.sh [start|status|stop]      (padrao: start)

set -euo pipefail

UNIT="prometheus-forward"
VM_IP="192.168.122.139"
PORT="9090"
KUBECTL="/usr/local/bin/kubectl"
URL="http://${VM_IP}:${PORT}"

probe() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 2 "${URL}/-/ready" 2>/dev/null || true
}

start() {
  if incus exec k3s-master -- systemctl is-active --quiet "$UNIT"; then
    echo "relay ja estava ativo"
  else
    incus exec k3s-master -- systemd-run --unit="$UNIT" --collect \
      "$KUBECTL" port-forward svc/prometheus "${PORT}:${PORT}" >/dev/null
    echo "relay iniciado"
  fi

  for _ in $(seq 1 15); do
    if [ "$(probe)" = "200" ]; then
      echo "painel pronto: ${URL}"
      exit 0
    fi
    sleep 1
  done

  echo "o painel nao respondeu em 15 s" >&2
  echo "diagnostico:" >&2
  echo "  incus exec k3s-master -- journalctl -u ${UNIT} -n 20 --no-pager" >&2
  echo "  incus exec k3s-master -- kubectl get pods -l app=prometheus" >&2
  exit 1
}

case "${1:-start}" in
  start)  start ;;
  status)
    incus exec k3s-master -- systemctl status "$UNIT" --no-pager || true
    echo "painel: $(probe)"
    ;;
  stop)
    incus exec k3s-master -- systemctl stop "$UNIT"
    echo "relay parado"
    ;;
  *)
    echo "uso: $0 [start|status|stop]" >&2
    exit 2
    ;;
esac
