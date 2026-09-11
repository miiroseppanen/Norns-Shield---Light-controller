#!/bin/bash
# Root install for Shield appliance units + operator help + safe master workspace.
# Run on the Shield Pi as: sudo bash packaging/install-appliance.sh
# Does not enable wizbridge, WIZ-LIGHTS, or real Art-Net destinations.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUDOERS_SRC="$ROOT/packaging/sudoers.d/light-console-shutdown"
SUDOERS_DST="/etc/sudoers.d/light-console-shutdown"
QLC_SUDOERS_SRC="$ROOT/packaging/sudoers.d/light-console-qlc"
QLC_SUDOERS_DST="/etc/sudoers.d/light-console-qlc"
LC_SRC="$ROOT/packaging/systemd/light-console.service"
LC_DST="/etc/systemd/system/light-console.service"
OLED_SRC="$ROOT/packaging/systemd/shieldxl-oled-starting.service"
OLED_DST="/etc/systemd/system/shieldxl-oled-starting.service"
QLC_SRC="$ROOT/packaging/systemd/qlcplus.service"
QLC_DST="/etc/systemd/system/qlcplus.service"
START_SRC="$ROOT/packaging/systemd/qlc-startup-chaser.service"
START_DST="/etc/systemd/system/qlc-startup-chaser.service"
MASTER_SRC="$ROOT/qlc/projects/siirtyma-shield.qxw"
SHOWS_DIR="/home/light/shows"
MASTER_DST="$SHOWS_DIR/master.qxw"
META_SRC="$ROOT/qlc/projects/siirtyma.yaml"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root (sudo bash packaging/install-appliance.sh)" >&2
  exit 1
fi

[[ -x /usr/bin/qlcplus-qml ]] || { echo "FAIL: /usr/bin/qlcplus-qml missing" >&2; exit 1; }
[[ -f "$MASTER_SRC" ]] || { echo "FAIL: missing $MASTER_SRC" >&2; exit 1; }

bash "$ROOT/packaging/install-light-help.sh"

install -d -o light -g light -m 755 "$SHOWS_DIR"
install -m 644 -o light -g light "$MASTER_SRC" "$MASTER_DST"
if [[ -f "$META_SRC" ]]; then
  install -m 644 -o light -g light "$META_SRC" "$SHOWS_DIR/siirtyma.yaml"
  echo siirtyma > "$SHOWS_DIR/active-show"
  chown light:light "$SHOWS_DIR/active-show"
fi

/usr/sbin/visudo -cf "$SUDOERS_SRC"
install -m 440 -o root -g root "$SUDOERS_SRC" "$SUDOERS_DST"
/usr/sbin/visudo -cf "$SUDOERS_DST"

/usr/sbin/visudo -cf "$QLC_SUDOERS_SRC"
install -m 440 -o root -g root "$QLC_SUDOERS_SRC" "$QLC_SUDOERS_DST"
/usr/sbin/visudo -cf "$QLC_SUDOERS_DST"

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
install_unit "$LC_SRC" "$LC_DST"
install_unit "$QLC_SRC" "$QLC_DST"
install_unit "$START_SRC" "$START_DST"

systemctl daemon-reload
systemctl reset-failed qlcplus.service qlc-startup-chaser.service light-console.service shieldxl-oled-starting.service || true
systemctl enable shieldxl-oled-starting.service light-console.service qlcplus.service qlc-startup-chaser.service
systemctl restart qlcplus.service
systemctl restart light-console.service
# oneshot After=qlcplus; start it so RemainAfterExit tracks this boot.
systemctl restart qlc-startup-chaser.service || true

echo "installed appliance units and $MASTER_DST"
systemctl is-active light-console.service qlcplus.service || true
echo "NOTE: WebAccess may take minutes after workspace load. Outputs remain loopback/SAFE."
echo "wizbridge.service is not enabled."
