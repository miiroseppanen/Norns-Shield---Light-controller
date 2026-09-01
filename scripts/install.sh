#!/usr/bin/env bash
# Milestone 0.1: inspect / install stubs. Does not touch Norns SD or production Pi.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:---help}"

die() { echo "error: $*" >&2; exit 1; }

check() {
  echo "=== light-console install --check ==="
  echo "repo: $ROOT"
  python3 - <<'PY'
import platform, sys
print("python:", sys.version.split()[0])
print("machine:", platform.machine())
print("system:", platform.system())
try:
    model = open("/proc/device-tree/model").read().replace("\x00","")
    print("pi_model:", model)
except FileNotFoundError:
    print("pi_model: (not a Pi / no device-tree)")
PY
  echo "norns SD: not touched"
  echo "network: not modified"
  echo "OK"
}

install_app() {
  echo "=== light-console install --install ==="
  echo "Milestone 0.1 refuses Pi install. This is the Mac/simulator milestone."
  echo "On a future NEW microSD, this will: create venv, pip install, install systemd unit."
  echo "It will not format disks, not write Norns files, not change NetworkManager without --configure-network."
  die "refusing --install until Milestone 0.5 / explicit Pi work"
}

configure_network() {
  echo "=== planned network changes (NOT applied) ==="
  cat <<EOF
Would create NetworkManager connection WIZ-LIGHTS on wlan1:
  ipv4.method shared
  address 10.42.0.1/24
  wifi.band bg, channel 6
  wifi-sec.pmf disable
Would leave wlan0 as optional upstream.
Would NOT install custom dnsmasq/NAT/dispatcher.
Would backup any overwritten NM files first.
EOF
  die "refusing --configure-network in 0.1 (print-only complete; no apply path yet)"
}

case "$MODE" in
  --check) check ;;
  --install) install_app ;;
  --configure-network) configure_network ;;
  --help|-h)
    echo "Usage: $0 --check | --install | --configure-network"
    echo "Never run this on the production lighting Pi or the Norns SD."
    ;;
  *) die "unknown mode $MODE (try --help)" ;;
esac
