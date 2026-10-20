#!/bin/bash
# Install WIZ-LIGHTS NetworkManager AP on wlan1 + FORWARD isolation.
# Production-parity: NetworkManager shared only. No extra AP/DHCP/NAT daemons.
# Run on the Shield as: sudo bash packaging/install-wiz-lights.sh [--up]
# Does not start/enable wizbridge. Does not modify QLC or wlan0.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NFT_SRC="$ROOT/packaging/nftables/shieldxl-wiz-lights.nft"
NFT_DST="/etc/nftables.d/shieldxl-wiz-lights.nft"
UNIT_SRC="$ROOT/packaging/systemd/shieldxl-wiz-isolation.service"
UNIT_DST="/etc/systemd/system/shieldxl-wiz-isolation.service"
PSK_FILE="${WIZ_LIGHTS_PSK_FILE:-/etc/light-console/wiz-lights.psk}"
CON_NAME="WIZ-LIGHTS"
IFACE="wlan1"
BRING_UP=0

if [[ "${1:-}" == "--up" ]]; then
  BRING_UP=1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root (sudo bash packaging/install-wiz-lights.sh)" >&2
  exit 1
fi

if [[ "$IFACE" != "wlan1" ]]; then
  echo "FAIL: refusing iface $IFACE (WIZ-LIGHTS is wlan1 only)" >&2
  exit 1
fi

command -v nmcli >/dev/null || { echo "FAIL: nmcli missing" >&2; exit 1; }
command -v nft >/dev/null || { echo "FAIL: nft missing" >&2; exit 1; }
[[ -x /usr/sbin/dnsmasq ]] || { echo "FAIL: dnsmasq-base missing" >&2; exit 1; }
[[ -f "$NFT_SRC" ]] || { echo "FAIL: missing $NFT_SRC" >&2; exit 1; }
[[ -f "$UNIT_SRC" ]] || { echo "FAIL: missing $UNIT_SRC" >&2; exit 1; }

if ! ip link show "$IFACE" >/dev/null 2>&1; then
  echo "FAIL: $IFACE missing. Diagnose USB/PCIe before NetworkManager." >&2
  lsusb 2>/dev/null | grep -i "0bda:c811" || echo "USB 0bda:c811 not enumerated"
  exit 1
fi

EXPECTED_NFT="$(cd "$ROOT" && PYTHONPATH="$ROOT" /usr/bin/python3 -c 'from light_console.output.wiz_ap import isolation_nft; print(isolation_nft(), end="")')"
if [[ "$(cat "$NFT_SRC")" != "$EXPECTED_NFT" ]]; then
  echo "FAIL: nft source does not match light_console.output.wiz_ap.isolation_nft()" >&2
  exit 1
fi

install -d -m 755 /etc/nftables.d
install -m 644 -o root -g root "$NFT_SRC" "$NFT_DST"
install -m 644 -o root -g root "$UNIT_SRC" "$UNIT_DST"
systemd-analyze verify "$UNIT_DST"
systemctl daemon-reload
systemctl enable --now shieldxl-wiz-isolation.service

PSK=""
if [[ -n "${WIZ_LIGHTS_PSK:-}" ]]; then
  PSK="$WIZ_LIGHTS_PSK"
elif [[ -f "$PSK_FILE" ]]; then
  PSK="$(tr -d '\r\n' < "$PSK_FILE")"
fi
if [[ -z "$PSK" ]]; then
  echo "FAIL: WIZ-LIGHTS PSK missing." >&2
  echo "Isolation is installed. NM profile was not created." >&2
  echo "As root, write the existing production PSK to $PSK_FILE (mode 0600)" >&2
  echo "or re-run with WIZ_LIGHTS_PSK set. Do not invent a new PSK." >&2
  exit 2
fi

cd "$ROOT"
export CON_NAME IFACE
DECISION="$(
  PYTHONPATH="$ROOT" /usr/bin/python3 - <<'PY'
import os, subprocess, sys
from light_console.output.wiz_ap import (
    WizApError,
    parse_nmcli_key_values,
    parse_nmcli_name_uuid,
    select_wiz_lights_uuid,
    validate_existing_wiz_profile,
)
name = os.environ["CON_NAME"]
listed = subprocess.run(
    ["nmcli", "-t", "-f", "NAME,UUID", "connection", "show"],
    capture_output=True, text=True,
)
if listed.returncode != 0:
    sys.stderr.write(listed.stderr or listed.stdout or "nmcli connection show failed\n")
    sys.exit(1)
try:
    uuid = select_wiz_lights_uuid(parse_nmcli_name_uuid(listed.stdout or ""))
except WizApError as exc:
    sys.stderr.write(f"FAIL: {exc}\n")
    sys.exit(4)
if uuid is None:
    print("CREATE")
    sys.exit(0)
detail = subprocess.run(
    [
        "nmcli", "-t", "-f",
        "connection.id,connection.interface-name,connection.uuid,"
        "802-11-wireless.ssid,802-11-wireless.mode",
        "connection", "show", uuid,
    ],
    capture_output=True, text=True,
)
if detail.returncode != 0:
    sys.stderr.write(detail.stderr or detail.stdout or "nmcli connection show failed\n")
    sys.exit(1)
try:
    validate_existing_wiz_profile(parse_nmcli_key_values(detail.stdout or ""))
except WizApError as exc:
    sys.stderr.write(f"FAIL: {exc}\n")
    sys.exit(5)
print(f"REUSE {uuid}")
PY
)"

if [[ "$DECISION" == "CREATE" ]]; then
  nmcli connection add type wifi ifname "$IFACE" con-name "$CON_NAME" ssid "$CON_NAME" \
    autoconnect no \
    802-11-wireless.mode ap \
    ipv4.method shared \
    ipv6.method disabled \
    802-11-wireless-security.key-mgmt wpa-psk
  echo "created connection $CON_NAME"
else
  echo "reusing existing connection ${DECISION#REUSE }"
fi

PYTHONPATH="$ROOT" /usr/bin/python3 - "$CON_NAME" <<'PY'
import subprocess, sys
from light_console.output.wiz_ap import assert_wlan1_only, profile_settings
name = sys.argv[1]
assert_wlan1_only("wlan1")
args = ["nmcli", "connection", "modify", name]
for key, value in profile_settings("wlan1"):
    args.extend([key, value])
proc = subprocess.run(args, capture_output=True, text=True)
if proc.returncode != 0:
    sys.stderr.write(proc.stderr or proc.stdout or "nmcli modify failed\n")
    sys.exit(1)
PY

nmcli connection modify "$CON_NAME" 802-11-wireless-security.psk "$PSK"
unset PSK
unset WIZ_LIGHTS_PSK || true

if [[ "$BRING_UP" -eq 1 ]]; then
  nmcli -w 30 connection up "$CON_NAME"
fi

echo "installed WIZ-LIGHTS profile on wlan1 (autoconnect=no)"
echo "isolation unit: shieldxl-wiz-isolation.service"
echo "wizbridge not started"
