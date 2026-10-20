#!/bin/bash
# Install WIZ CONTROL lifecycle helper + Phase C wizbridge unit.
# Does not enable or start wizbridge. Does not bring WIZ-LIGHTS up.
# Does not modify QLC, workspace files, the onboard client radio, or restart Light Console.
# Run on the Shield as: sudo bash packaging/install-wiz-lifecycle.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HELPER_SRC="$ROOT/packaging/light-console-wiz"
HELPER_DST="/usr/sbin/light-console-wiz"
SUDOERS_SRC="$ROOT/packaging/sudoers.d/light-console-wiz"
SUDOERS_DST="/etc/sudoers.d/light-console-wiz"
UNIT_SRC="$ROOT/packaging/systemd/wizbridge.service"
UNIT_DST="/etc/systemd/system/wizbridge.service"
BRIDGE_PY="$ROOT/services/wiz/wiz_artnet_bridge.py"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root (sudo bash packaging/install-wiz-lifecycle.sh)" >&2
  exit 1
fi

[[ -f "$HELPER_SRC" ]] || { echo "FAIL: missing $HELPER_SRC" >&2; exit 1; }
[[ -f "$SUDOERS_SRC" ]] || { echo "FAIL: missing $SUDOERS_SRC" >&2; exit 1; }
[[ -f "$UNIT_SRC" ]] || { echo "FAIL: missing $UNIT_SRC" >&2; exit 1; }
[[ -f "$BRIDGE_PY" ]] || { echo "FAIL: missing $BRIDGE_PY" >&2; exit 1; }

if grep -E '^WantedBy=' "$UNIT_SRC" >/dev/null; then
  echo "FAIL: wizbridge.service must not auto-start at boot" >&2
  exit 1
fi

install -m 755 -o root -g root "$HELPER_SRC" "$HELPER_DST"
/usr/sbin/visudo -cf "$SUDOERS_SRC"
install -m 440 -o root -g root "$SUDOERS_SRC" "$SUDOERS_DST"
/usr/sbin/visudo -cf "$SUDOERS_DST"

install -m 644 -o root -g root "$UNIT_SRC" "$UNIT_DST"
verify_out="$(systemd-analyze verify "$UNIT_DST" 2>&1)" || {
  echo "$verify_out" >&2
  exit 1
}
if grep -q "Unknown key" <<<"$verify_out"; then
  echo "$verify_out" >&2
  exit 1
fi
if [[ -n "$verify_out" ]]; then
  echo "$verify_out"
fi

systemctl daemon-reload
systemctl disable wizbridge.service >/dev/null 2>&1 || true
systemctl stop wizbridge.service >/dev/null 2>&1 || true

echo "installed WIZ CONTROL helper and wizbridge unit (disabled, stopped)"
systemctl is-enabled wizbridge.service || true
systemctl is-active wizbridge.service || true
echo "WIZ-LIGHTS autoconnect left unchanged (must stay no)"
echo "did not modify workspace files, qlcplus, onboard wifi, or light-console.service"
