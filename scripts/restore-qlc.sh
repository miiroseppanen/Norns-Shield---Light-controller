#!/bin/bash
# Start qlcplus.service only. Never match process command lines.
# Never restart the OLED UI unit.
set -euo pipefail

UNIT=qlcplus.service

if [[ "$(id -u)" -eq 0 ]]; then
  systemctl start "$UNIT"
else
  sudo systemctl start "$UNIT"
fi

systemctl is-active "$UNIT"
systemctl show -p MainPID --value "$UNIT"
