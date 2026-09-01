#!/usr/bin/env bash
# Copy a config file to a timestamped backup before any installer mutation.
set -euo pipefail
src="${1:?usage: backup-config.sh <file>}"
if [[ ! -f "$src" ]]; then
  echo "no file $src — nothing to backup"
  exit 0
fi
dest="${src}.bak.$(date +%Y%m%d-%H%M%S)"
cp -p "$src" "$dest"
echo "backup: $dest"
