#!/usr/bin/env bash
# Patch a production-style .qxw into Shield-safe master.qxw. Never writes the source.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MASTER="${LIGHT_CONSOLE_MASTER:-$ROOT/qlc/projects/siirtyma-shield.qxw}"
HOST="${LIGHT_CONSOLE_HOST:-light@shieldxl-light.local}"
REMOTE_MASTER="${LIGHT_CONSOLE_REMOTE_MASTER:-/home/light/shows/master.qxw}"
INSTALL_ROOT="${LIGHT_CONSOLE_INSTALL_ROOT:-}"
CURRENT_FILE="${LIGHT_CONSOLE_CURRENT:-}"

usage() {
  cat <<EOF
Usage:
  $0 --dry-run FILE.qxw
  $0 --apply FILE.qxw
  $0 --install FILE.qxw
  $0 --install --dry-run FILE.qxw

Rewrites Launchpad Name/UID, forces Art-Net loopback, sanitizes IP captions.
--install also preserves current Shield U2 routing and installs
/home/light/shows/master.qxw with backup/rollback. Never writes FILE.qxw.
Does not load QLC. Does not contact 192.168.88.248.
EOF
}

die() { echo "error: $*" >&2; exit 1; }

APPLY=0
INSTALL=0
EXPLICIT_DRY=0
FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) EXPLICIT_DRY=1; APPLY=0; shift ;;
    --apply) APPLY=1; INSTALL=0; shift ;;
    --install) INSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) [[ -z "$FILE" ]] || die "unexpected argument: $1"; FILE="$1"; shift ;;
  esac
done

[[ -n "$FILE" ]] || { usage >&2; exit 1; }
[[ -f "$FILE" ]] || die "not a file: $FILE"
if [[ "$INSTALL" -eq 1 && "$APPLY" -eq 1 ]]; then
  die "--apply and --install cannot be combined"
fi
if [[ "$HOST" == *192.168.88.248* ]] || [[ "$HOST" == *valot.local* ]]; then
  die "refusing host $HOST"
fi
if [[ "$REMOTE_MASTER" == *192.168.88.248* ]]; then
  die "refusing remote path $REMOTE_MASTER"
fi

INSTALL_DRY=0
if [[ "$INSTALL" -eq 1 && "$EXPLICIT_DRY" -eq 1 ]]; then
  INSTALL_DRY=1
fi

TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/import-production.XXXXXX")"
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

fetch_current() {
  if [[ -n "$CURRENT_FILE" ]]; then
    [[ -f "$CURRENT_FILE" ]] || die "not a file: $CURRENT_FILE"
    cp "$CURRENT_FILE" "$TMPDIR/current.qxw"
    return
  fi
  if [[ -n "$INSTALL_ROOT" ]]; then
    [[ -f "$INSTALL_ROOT/master.qxw" ]] || die "missing $INSTALL_ROOT/master.qxw"
    cp "$INSTALL_ROOT/master.qxw" "$TMPDIR/current.qxw"
    return
  fi
  scp -q -o BatchMode=yes "$HOST:$REMOTE_MASTER" "$TMPDIR/current.qxw"
}

verify_installed() {
  local dest="$1"
  PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - "$dest" "$TMPDIR/current.qxw" <<'PY'
import sys
from pathlib import Path
from light_console.output.mutate import universe_block
from light_console.qxw import parse_functions

dest = Path(sys.argv[1])
current = Path(sys.argv[2]).read_text(encoding="utf-8")
text = dest.read_text(encoding="utf-8")
if "192.168.88.248" in text:
    raise SystemExit("production Pi address in installed workspace")
if text.count('outputIP="127.0.0.1"') < 1:
    raise SystemExit("WiZ loopback missing")
fns = parse_functions(text)
if not any(fn.name == "startup" for fn in fns):
    raise SystemExit("startup chaser missing")
if universe_block(text, 1) != universe_block(current, 1):
    raise SystemExit("U2 routing mismatch after install")
if universe_block(text, 0) is None:
    raise SystemExit("U1 universe missing")
print("verified:", dest)
print("functions:", len(fns))
PY
}

install_local() {
  local dest="$INSTALL_ROOT/master.qxw"
  local bak="$INSTALL_ROOT/master.qxw.bak"
  local incoming="$INSTALL_ROOT/.incoming.$$.master.qxw"
  mkdir -p "$INSTALL_ROOT"
  cp "$TMPDIR/patched.qxw" "$incoming"
  if [[ -f "$dest" ]]; then
    cp -p "$dest" "$bak"
  fi
  mv "$incoming" "$dest"
  chmod 644 "$dest"
  if ! verify_installed "$dest"; then
    if [[ -f "$bak" ]]; then
      mv "$bak" "$dest"
      echo "error: verify failed; rolled back $dest" >&2
    fi
    exit 1
  fi
}

install_remote() {
  local remote_dir
  remote_dir="$(dirname "$REMOTE_MASTER")"
  local incoming=".incoming.$$.master.qxw"
  scp -q -o BatchMode=yes "$TMPDIR/patched.qxw" "$HOST:$remote_dir/$incoming"
  ssh -o BatchMode=yes "$HOST" "set -euo pipefail
SHOWS='$remote_dir'
IN='$incoming'
DEST='$REMOTE_MASTER'
BAK=\"\$SHOWS/master.qxw.bak\"
if [[ \"\$DEST\" == *192.168.88.248* ]]; then
  echo 'error: refusing production Pi path' >&2
  rm -f \"\$SHOWS/\$IN\"
  exit 1
fi
if [[ -f \"\$DEST\" ]]; then
  cp -p \"\$DEST\" \"\$BAK\"
fi
mv \"\$SHOWS/\$IN\" \"\$DEST\"
chmod 644 \"\$DEST\"
if grep -F '192.168.88.248' \"\$DEST\" >/dev/null; then
  echo 'error: production Pi address in installed workspace' >&2
  if [[ -f \"\$BAK\" ]]; then mv \"\$BAK\" \"\$DEST\"; fi
  exit 1
fi
if ! grep -F 'outputIP=\"127.0.0.1\"' \"\$DEST\" >/dev/null; then
  echo 'error: WiZ loopback missing' >&2
  if [[ -f \"\$BAK\" ]]; then mv \"\$BAK\" \"\$DEST\"; fi
  exit 1
fi
ls -l \"\$DEST\"
"
}

python3 - "$FILE" "$MASTER" "$APPLY" "$INSTALL" "$TMPDIR/patched.qxw" <<'PY'
import sys
from pathlib import Path
from light_console.output.mutate import cover_universe_fixtures, universe_channels
from light_console.qxw import format_midi_report, parse_functions, prepare_for_shield_report

src = Path(sys.argv[1])
dest = Path(sys.argv[2])
apply = sys.argv[3] == "1"
do_install = sys.argv[4] == "1"
out_path = Path(sys.argv[5])
original = src.read_text(encoding="utf-8")
patched, changes = prepare_for_shield_report(original)
before_ch = universe_channels(patched, 0)
patched = cover_universe_fixtures(patched, 0)
print(format_midi_report(changes))
print("source (unchanged):", src)
if do_install:
    print("dest:", "/home/light/shows/master.qxw")
else:
    print("dest:", dest)
print("functions:", len(parse_functions(patched)))
print("startup:", any(fn.name == "startup" for fn in parse_functions(patched)))
print("loopback outputs:", patched.count('outputIP="127.0.0.1"'))
print("u1 channels:", before_ch, "->", universe_channels(patched, 0))
if src.read_text(encoding="utf-8") != original:
    raise SystemExit("source file changed")
if do_install:
    out_path.write_text(patched, encoding="utf-8")
elif apply:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(patched, encoding="utf-8")
    print("applied:", dest)
else:
    print("dry-run:", "yes")
PY

if [[ "$INSTALL" -eq 1 ]]; then
  fetch_current
  python3 - "$TMPDIR/patched.qxw" "$TMPDIR/current.qxw" <<'PY'
import sys
from pathlib import Path
from light_console.output.mutate import preserve_managed_universe
from light_console.output.routing import parse_output_routes
from light_console.output.targets import MANAGED_QLC_UNIVERSE
from light_console.qxw import parse_functions

prepared_path = Path(sys.argv[1])
current = Path(sys.argv[2]).read_text(encoding="utf-8")
merged = preserve_managed_universe(prepared_path.read_text(encoding="utf-8"), current)
prepared_path.write_text(merged, encoding="utf-8")
routes = parse_output_routes(merged)
managed = [route for route in routes if route.qlc_universe == MANAGED_QLC_UNIVERSE]
wiz = [route for route in routes if route.qlc_universe == 1]
print("wiz loopback:", wiz[0].output_ip if wiz else None)
print("u2 preserved:", managed[0].output_ip if managed else None)
print("functions:", len(parse_functions(merged)))
print("startup:", any(fn.name == "startup" for fn in parse_functions(merged)))
PY
  BEFORE="$(cksum "$FILE")"
  if [[ "$INSTALL_DRY" -eq 1 ]]; then
    echo "dry-run: not installed to the Shield"
    echo "source (unchanged): $FILE"
    [[ "$(cksum "$FILE")" == "$BEFORE" ]] || die "source file changed"
    exit 0
  fi
  if [[ -n "$INSTALL_ROOT" ]]; then
    install_local
    echo "applied: $INSTALL_ROOT/master.qxw"
  else
    install_remote
    echo "applied: $REMOTE_MASTER"
  fi
  [[ "$(cksum "$FILE")" == "$BEFORE" ]] || die "source file changed"
fi
