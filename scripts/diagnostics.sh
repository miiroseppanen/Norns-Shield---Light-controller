#!/usr/bin/env bash
# One-shot diagnostics. No passwords. Safe to run on Mac (limited) or Pi.
set -euo pipefail
echo "===== SYSTEM ====="
uname -a || true
echo
echo "===== OS ====="
if [[ -f /etc/os-release ]]; then
  grep -E '^(NAME|VERSION)=' /etc/os-release || true
else
  sw_vers 2>/dev/null || true
fi
echo
echo "===== KERNEL ====="
uname -r || true
echo
echo "===== PI MODEL ====="
if [[ -f /proc/device-tree/model ]]; then
  tr -d '\0' </proc/device-tree/model; echo
else
  echo "(not a Raspberry Pi)"
fi
echo
echo "===== SHIELD / GPIO ====="
echo "(Milestone 0.1: no GPIO probe. See research/shieldxl.md)"
if command -v pinctrl >/dev/null 2>&1; then
  pinctrl 2>/dev/null | head -40 || true
fi
ls /dev/spidev* 2>/dev/null || echo "spidev: none"
ls /dev/fb* 2>/dev/null || echo "fb: none"
echo
echo "===== QLC / WIZBRIDGE / LIGHT-CONSOLE ====="
systemctl is-active qlcplus 2>/dev/null || echo "qlcplus: (no systemd or inactive)"
systemctl is-active wizbridge 2>/dev/null || echo "wizbridge: (no systemd or inactive)"
systemctl is-active light-console 2>/dev/null || echo "light-console: (no systemd or inactive)"
echo
echo "===== NETWORK ====="
if command -v nmcli >/dev/null 2>&1; then
  nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status || true
else
  ifconfig 2>/dev/null | grep -E '^[a-z]|inet ' || ip -br addr 2>/dev/null || true
fi
echo
echo "===== ROUTES ====="
netstat -rn 2>/dev/null | head -20 || ip route 2>/dev/null || true
echo
echo "===== WIZ ====="
echo "(no leases dumped if path missing; never print PSK)"
iw dev wlan1 station dump 2>/dev/null | head -40 || echo "iw wlan1: n/a"
echo
echo "===== MIDI ====="
if command -v lsusb >/dev/null 2>&1; then
  lsusb | grep -iE '1235:0036|novation|launch' || echo "(Launchpad USB not seen)"
else
  echo "(lsusb n/a)"
fi
if command -v aconnect >/dev/null 2>&1; then
  aconnect -l || true
fi
echo
echo "===== DMX ====="
echo "PKNight probe skipped unless ping allowed; this script does not claim DMX OK from Art-Net TX"
echo
echo "===== END ====="
