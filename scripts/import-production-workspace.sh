#!/usr/bin/env bash
# Patch a production-style .qxw into Shield-safe master.qxw. Never writes the source.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MASTER="${LIGHT_CONSOLE_MASTER:-$ROOT/qlc/projects/siirtyma-shield.qxw}"

usage() {
  cat <<EOF
Usage:
  $0 --dry-run FILE.qxw
  $0 --apply FILE.qxw

Rewrites Launchpad Name/UID, forces Art-Net loopback, sanitizes IP captions.
Does not load QLC. Does not modify FILE.qxw.
EOF
}

die() { echo "error: $*" >&2; exit 1; }

APPLY=0
FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) APPLY=0; shift ;;
    --apply) APPLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) [[ -z "$FILE" ]] || die "unexpected argument: $1"; FILE="$1"; shift ;;
  esac
done

[[ -n "$FILE" ]] || { usage >&2; exit 1; }
[[ -f "$FILE" ]] || die "not a file: $FILE"

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python3 - "$FILE" "$MASTER" "$APPLY" <<'PY'
import sys
from pathlib import Path
from light_console.qxw import format_midi_report, parse_functions, prepare_file_report, prepare_for_shield_report

src = Path(sys.argv[1])
dest = Path(sys.argv[2])
apply = sys.argv[3] == "1"
original = src.read_text(encoding="utf-8")
if apply:
    patched, changes = prepare_file_report(src, dest)
else:
    patched, changes = prepare_for_shield_report(original)
print(format_midi_report(changes))
print("source (unchanged):", src)
print("dest:", dest)
print("functions:", len(parse_functions(patched)))
print("startup:", any(fn.name == "startup" for fn in parse_functions(patched)))
print("loopback outputs:", patched.count('outputIP="127.0.0.1"'))
print("dry-run:" if not apply else "applied:", dest if apply else "yes")
if src.read_text(encoding="utf-8") != original:
    raise SystemExit("source file changed")
PY
