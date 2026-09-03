#!/bin/bash
# Root install for Shield appliance: sudoers drop-in + light-console.service.
# Run on the Shield Pi as: sudo bash packaging/install-appliance.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUDOERS_SRC="$ROOT/packaging/sudoers.d/light-console-shutdown"
SUDOERS_DST="/etc/sudoers.d/light-console-shutdown"
UNIT_SRC="$ROOT/packaging/systemd/light-console.service"
UNIT_DST="/etc/systemd/system/light-console.service"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root (sudo bash packaging/install-appliance.sh)" >&2
  exit 1
fi

bash "$ROOT/packaging/install-light-help.sh"

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
systemctl enable light-console.service
systemctl restart light-console.service
echo "installed sudoers $SUDOERS_DST and unit $UNIT_DST"
systemctl is-active light-console.service
