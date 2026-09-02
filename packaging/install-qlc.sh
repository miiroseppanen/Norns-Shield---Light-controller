#!/bin/bash
# Root install for qlcplus.service only. Does not start wizbridge or production .qxw.
# Run on the Shield Pi as: sudo bash packaging/install-qlc.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="$ROOT/packaging/systemd/qlcplus.service"
UNIT_DST="/etc/systemd/system/qlcplus.service"
QXW="$ROOT/qlc/projects/light-console-test.qxw"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root (sudo bash packaging/install-qlc.sh)" >&2
  exit 1
fi

[[ -x /usr/bin/qlcplus-qml ]] || { echo "FAIL: /usr/bin/qlcplus-qml missing" >&2; exit 1; }
[[ -f "$QXW" ]] || { echo "FAIL: missing $QXW" >&2; exit 1; }

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
systemctl reset-failed qlcplus.service || true
systemctl enable qlcplus.service
systemctl restart qlcplus.service
echo "installed unit $UNIT_DST"
systemctl is-active qlcplus.service
