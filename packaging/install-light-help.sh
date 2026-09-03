#!/bin/bash
# Install light-help, the SSH login hook, and /home/light/shows.
# Does not start, stop, or restart services. Does not probe the network.
# Run on the Shield Pi as: sudo bash packaging/install-light-help.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HELP_SRC="$ROOT/packaging/light-help"
PROFILE_SRC="$ROOT/packaging/profile.d/light-help.sh"
HELP_DST="/usr/local/bin/light-help"
PROFILE_DST="/etc/profile.d/light-help.sh"
SHOWS_DIR="/home/light/shows"
SEED_QXW="$ROOT/qlc/projects/light-console-test.qxw"
SEED_NAME="light-console-test.qxw"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root (sudo bash packaging/install-light-help.sh)" >&2
  exit 1
fi

[[ -f "$HELP_SRC" ]] || { echo "FAIL: missing $HELP_SRC" >&2; exit 1; }
[[ -f "$PROFILE_SRC" ]] || { echo "FAIL: missing $PROFILE_SRC" >&2; exit 1; }
[[ -f "$SEED_QXW" ]] || { echo "FAIL: missing $SEED_QXW" >&2; exit 1; }

install -m 755 -o root -g root "$HELP_SRC" "$HELP_DST"
install -m 644 -o root -g root "$PROFILE_SRC" "$PROFILE_DST"

install -d -o light -g light -m 755 "$SHOWS_DIR"
if [[ ! -e "$SHOWS_DIR/$SEED_NAME" ]]; then
  install -m 644 -o light -g light "$SEED_QXW" "$SHOWS_DIR/$SEED_NAME"
fi
if [[ ! -e "$SHOWS_DIR/current.qxw" ]]; then
  ln -sfn "$SEED_NAME" "$SHOWS_DIR/current.qxw"
  chown -h light:light "$SHOWS_DIR/current.qxw"
fi

echo "installed $HELP_DST"
echo "installed $PROFILE_DST"
echo "shows dir $SHOWS_DIR"
ls -l "$HELP_DST" "$PROFILE_DST" "$SHOWS_DIR"
readlink "$SHOWS_DIR/current.qxw" || true
