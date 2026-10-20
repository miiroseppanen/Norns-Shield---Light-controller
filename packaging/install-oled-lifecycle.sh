#!/bin/bash
# Install OLED lifecycle systemd units only. Does not touch QLC, workspace,
# routing, or WIZ. Does not restart Light Console.
# Run on the Shield: sudo bash packaging/install-oled-lifecycle.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LC_SRC="$ROOT/packaging/systemd/light-console.service"
LC_DST="/etc/systemd/system/light-console.service"
OLED_SRC="$ROOT/packaging/systemd/shieldxl-oled-starting.service"
OLED_DST="/etc/systemd/system/shieldxl-oled-starting.service"
OLED_STOP_SRC="$ROOT/packaging/systemd/shieldxl-oled-shutdown.service"
OLED_STOP_DST="/etc/systemd/system/shieldxl-oled-shutdown.service"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root (sudo bash packaging/install-oled-lifecycle.sh)" >&2
  exit 1
fi

install_unit() {
  local src="$1" dst="$2"
  install -m 644 -o root -g root "$src" "$dst"
  local verify_out
  verify_out="$(systemd-analyze verify "$dst" 2>&1)" || {
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
}

install_unit "$OLED_SRC" "$OLED_DST"
install_unit "$OLED_STOP_SRC" "$OLED_STOP_DST"
install_unit "$LC_SRC" "$LC_DST"

systemctl daemon-reload
systemctl enable shieldxl-oled-starting.service shieldxl-oled-shutdown.service light-console.service
# ExecStart=/usr/bin/true only. Do not restart this unit later (that would paint
# SHUTTING DOWN). Start is a no-op if already active.
systemctl start shieldxl-oled-shutdown.service
echo "installed OLED lifecycle units"
systemctl is-enabled shieldxl-oled-starting.service shieldxl-oled-shutdown.service light-console.service
systemctl is-active shieldxl-oled-shutdown.service light-console.service || true
