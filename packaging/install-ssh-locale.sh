#!/bin/bash
# Stop sshd applying Mac LC_CTYPE=UTF-8 (not a locale name).
# Does not change /etc/default/locale. Does not restart Light Console or QLC.
# Run on the Shield Pi as: sudo bash packaging/install-ssh-locale.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: run as root (sudo bash packaging/install-ssh-locale.sh)" >&2
  exit 1
fi

SSHD_CONFIG="/etc/ssh/sshd_config"
OLD='AcceptEnv LANG LC_* COLORTERM NO_COLOR'
NEW='AcceptEnv LANG LC_NUMERIC LC_TIME LC_COLLATE LC_MONETARY LC_MESSAGES LC_PAPER LC_NAME LC_ADDRESS LC_TELEPHONE LC_MEASUREMENT LC_IDENTIFICATION COLORTERM NO_COLOR'

[[ -f "$SSHD_CONFIG" ]] || { echo "FAIL: missing $SSHD_CONFIG" >&2; exit 1; }

if grep -qxF "$NEW" "$SSHD_CONFIG"; then
  echo "sshd AcceptEnv already excludes LC_CTYPE"
else
  if ! grep -qxF "$OLD" "$SSHD_CONFIG"; then
    echo "FAIL: expected AcceptEnv line not found in $SSHD_CONFIG" >&2
    grep -n AcceptEnv "$SSHD_CONFIG" >&2 || true
    exit 1
  fi
  tmp="$(mktemp)"
  awk -v old="$OLD" -v new="$NEW" '{ if ($0 == old) print new; else print }' "$SSHD_CONFIG" > "$tmp"
  if ! grep -qxF "$NEW" "$tmp"; then
    echo "FAIL: AcceptEnv rewrite did not apply" >&2
    rm -f "$tmp"
    exit 1
  fi
  if grep -E '^[[:space:]]*AcceptEnv[[:space:]].*LC_\*' "$tmp"; then
    echo "FAIL: wildcard LC_* AcceptEnv still present" >&2
    rm -f "$tmp"
    exit 1
  fi
  cat "$tmp" > "$SSHD_CONFIG"
  rm -f "$tmp"
  echo "updated $SSHD_CONFIG AcceptEnv (dropped LC_CTYPE / LC_ALL)"
fi

if grep -E '^[[:space:]]*AcceptEnv[[:space:]].*LC_\*' "$SSHD_CONFIG"; then
  echo "FAIL: wildcard LC_* AcceptEnv still present" >&2
  exit 1
fi

/usr/sbin/sshd -t

pid=""
if [[ -r /run/sshd.pid ]]; then
  pid="$(tr -d ' \n' < /run/sshd.pid)"
fi
if [[ -z "$pid" ]] && [[ -r /run/sshd/sshd.pid ]]; then
  pid="$(tr -d ' \n' < /run/sshd/sshd.pid)"
fi
[[ -n "$pid" ]] || { echo "FAIL: sshd pid file missing" >&2; exit 1; }
kill -HUP "$pid"
echo "sshd configuration tested and reloaded (pid $pid)"
