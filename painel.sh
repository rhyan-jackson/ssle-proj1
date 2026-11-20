#!/usr/bin/env bash
# Panels for the browser: Prometheus and the Wazuh dashboard, one command.
#
# Two different mechanisms behind the same script:
#
#   Prometheus  http://192.168.122.139:9090
#     host -> incus proxy device `prom9090` on k3s-master -> 127.0.0.1:9090
#          -> transient systemd unit `prometheus-forward` (kubectl port-forward) -> pod
#
#   Wazuh       https://192.168.122.139:8443
#     host -> incus proxy device `wazuh8443` on wazuh-container -> 127.0.0.1:443
#
# Prometheus needs the relay because its pod address is reachable only from
# inside the cluster. Wazuh needs nothing but the device: the dashboard already
# listens on 443 of its own container, and the certificate is self-signed, so
# the browser will warn and that is expected.
#
# Both devices listen on the address of the VM, not on 0.0.0.0, so nothing is
# published beyond the lab network.
#
# usage: ./painel.sh [start|status|stop]    (default: start)

set -euo pipefail

VM_IP="192.168.122.139"
PROM_PORT="9090"
WAZUH_PORT="8443"
UNIT="prometheus-forward"
KUBECTL="/usr/local/bin/kubectl"
PROM_URL="http://${VM_IP}:${PROM_PORT}"
WAZUH_URL="https://${VM_IP}:${WAZUH_PORT}"

ensure_device() {
    local container="$1" device="$2" listen="$3" connect="$4"
    if incus config device show "$container" 2>/dev/null | grep -q "^${device}:"; then
        return 0
    fi
    incus config device add "$container" "$device" proxy \
        listen="tcp:${listen}" connect="tcp:${connect}" >/dev/null
    echo "device ${device} created on ${container}: ${listen} -> ${connect}"
}

remove_device() {
    local container="$1" device="$2"
    if incus config device show "$container" 2>/dev/null | grep -q "^${device}:"; then
        incus config device remove "$container" "$device" >/dev/null
        echo "device ${device} removed from ${container}"
    fi
}

prom_code() {
    curl -s -o /dev/null -w '%{http_code}' --max-time 2 "${PROM_URL}/-/ready" 2>/dev/null || true
}

wazuh_code() {
    curl -sk -o /dev/null -w '%{http_code}' --max-time 3 "${WAZUH_URL}/" 2>/dev/null || true
}

start_prometheus() {
    ensure_device k3s-master prom9090 "${VM_IP}:${PROM_PORT}" "127.0.0.1:${PROM_PORT}"

    if incus exec k3s-master -- systemctl is-active --quiet "$UNIT"; then
        echo "prometheus relay already active"
    else
        incus exec k3s-master -- systemd-run --unit="$UNIT" --collect \
            "$KUBECTL" port-forward svc/prometheus "${PROM_PORT}:${PROM_PORT}" >/dev/null
        echo "prometheus relay started"
    fi

    for _ in $(seq 1 15); do
        if [ "$(prom_code)" = "200" ]; then
            return 0
        fi
        sleep 1
    done
    return 1
}

start_wazuh() {
    ensure_device wazuh-container wazuh8443 "${VM_IP}:${WAZUH_PORT}" "127.0.0.1:443"

    for _ in $(seq 1 10); do
        case "$(wazuh_code)" in
            200|301|302) return 0 ;;
        esac
        sleep 1
    done
    return 1
}

start() {
    local failed=0

    if start_prometheus; then
        echo "prometheus: ${PROM_URL}  (HTTP $(prom_code))"
    else
        failed=1
        echo "prometheus: no answer in 15 s" >&2
        echo "  incus exec k3s-master -- journalctl -u ${UNIT} -n 20 --no-pager" >&2
        echo "  incus exec k3s-master -- kubectl get pods -l app=prometheus" >&2
    fi

    if start_wazuh; then
        echo "wazuh:      ${WAZUH_URL}  (user admin, password in credentials.md, not in the repository)"
        echo "            the certificate is self-signed: the browser warning is expected"
    else
        failed=1
        echo "wazuh: no answer on ${WAZUH_URL} in 10 s" >&2
        echo "  incus exec wazuh-container -- ss -ltn | grep 443" >&2
        echo "  incus exec wazuh-container -- curl -sk -o /dev/null -w '%{http_code}\\n' https://127.0.0.1/" >&2
    fi

    return "$failed"
}

case "${1:-start}" in
    start)
        start
        ;;
    status)
        if incus exec k3s-master -- systemctl is-active --quiet "$UNIT"; then
            echo "relay ${UNIT}: active"
        else
            echo "relay ${UNIT}: inactive"
        fi
        echo "prometheus: $(prom_code)"
        echo "wazuh:      $(wazuh_code)"
        incus config device show k3s-master 2>/dev/null | grep -q '^prom9090:' \
            && echo "device prom9090: present" || echo "device prom9090: absent"
        incus config device show wazuh-container 2>/dev/null | grep -q '^wazuh8443:' \
            && echo "device wazuh8443: present" || echo "device wazuh8443: absent"
        ;;
    stop)
        incus exec k3s-master -- systemctl stop "$UNIT" 2>/dev/null || true
        echo "relay stopped"
        remove_device k3s-master prom9090
        remove_device wazuh-container wazuh8443
        ;;
    *)
        echo "usage: $0 [start|status|stop]" >&2
        exit 2
        ;;
esac
