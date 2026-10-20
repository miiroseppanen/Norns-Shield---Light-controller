#!/bin/bash
# Install LIGHT-CONTROL NETWORK/STANDALONE helper.
# Does not restart Light Console, QLC, or wizbridge.
# Does not bring WIZ-LIGHTS up or down.
# Run on the Shield as: sudo bash packaging/install-netmode.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HELPER_SRC="$ROOT/packaging/light-console-net"
HELPER_DST="/usr/sbin/light-console-net"
SUDOERS_SRC="$ROOT/packaging/sudoers.d/light-console-net"
SUDOERS_DST="/etc/sudoers.d/light-console-net"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root (sudo bash packaging/install-netmode.sh)" >&2
  exit 1
fi

[[ -f "$HELPER_SRC" ]] || { echo "FAIL: missing $HELPER_SRC" >&2; exit 1; }
[[ -f "$SUDOERS_SRC" ]] || { echo "FAIL: missing $SUDOERS_SRC" >&2; exit 1; }

if grep -E 'wlan1|WIZ-LIGHTS' "$HELPER_SRC" >/dev/null; then
  echo "FAIL: net helper must not mention wlan1 or WIZ-LIGHTS" >&2
  exit 1
fi
if grep -E 'nmcli|NOPASSWD: ALL' "$SUDOERS_SRC" >/dev/null; then
  echo "FAIL: net sudoers must not grant nmcli or ALL" >&2
  exit 1
fi

install -m 755 -o root -g root "$HELPER_SRC" "$HELPER_DST"
/usr/sbin/visudo -cf "$SUDOERS_SRC"
install -m 440 -o root -g root "$SUDOERS_SRC" "$SUDOERS_DST"
/usr/sbin/visudo -cf "$SUDOERS_DST"

echo "installed LIGHT-CONTROL net helper"
echo "did not modify workspace files, qlcplus, hotspot profile, bridge unit, or light-console.service"
echo "did not restart any service"
