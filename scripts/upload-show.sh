#!/usr/bin/env bash
# Upload a QLC+ workspace to the Shield from the Mac.
# Does not modify the source file. Does not restart services.
# Run on the Mac, not inside an SSH session on the Shield.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${LIGHT_CONSOLE_HOST:-light@shieldxl-light.local}"
REMOTE_SHOWS="/home/light/shows"

usage() {
  cat <<EOF
Usage:
  $0 [--dry-run] [--replace] FILE.qxw
  $0 --list

Run this on the Mac. Do not copy a .qxw straight onto current.qxw.

  --dry-run   Validate and patch locally; do not copy to the Shield
  --replace   Install the file and point current.qxw at it
  --list      List /home/light/shows on the Shield

Without --replace the file is stored next to current.qxw and the
active symlink is left unchanged. An invalid workspace is rejected
and never replaces a working project.
EOF
}

die() { echo "error: $*" >&2; exit 1; }

DRY_RUN=0
REPLACE=0
LIST=0
FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --replace) REPLACE=1; shift ;;
    --list) LIST=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) die "unknown option $1 (try --help)" ;;
    *)
      [[ -z "$FILE" ]] || die "unexpected argument: $1"
      FILE="$1"
      shift
      ;;
  esac
done

if [[ "$LIST" -eq 1 ]]; then
  [[ -z "$FILE" ]] || die "--list does not take a file"
  ssh -o BatchMode=yes "$HOST" "ls -l '$REMOTE_SHOWS'; echo; echo -n 'current: '; readlink '$REMOTE_SHOWS/current.qxw' || echo '(missing)'"
  exit 0
fi

[[ -n "$FILE" ]] || { usage >&2; exit 1; }
[[ -f "$FILE" ]] || die "not a file: $FILE"

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/upload-show.XXXXXX")"
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

NAME="$(python3 -c 'import sys; from pathlib import Path; from light_console.qxw import safe_show_name; print(safe_show_name(Path(sys.argv[1])))' "$FILE")"
PATCHED="$TMPDIR/$NAME"
python3 -c 'import sys; from pathlib import Path; from light_console.qxw import prepare_file; prepare_file(Path(sys.argv[1]), Path(sys.argv[2]))' "$FILE" "$PATCHED"

echo "source (unchanged): $FILE"
echo "remote name:        $NAME"
echo "host:               $HOST"
echo "shows dir:          $REMOTE_SHOWS"
if [[ "$REPLACE" -eq 1 ]]; then
  echo "current.qxw:        will point at $NAME"
else
  echo "current.qxw:        left unchanged"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "dry-run: not copied to the Shield"
  exit 0
fi

INCOMING=".incoming.$$.$NAME"
scp -q "$PATCHED" "$HOST:$REMOTE_SHOWS/$INCOMING"
ssh -o BatchMode=yes "$HOST" "set -euo pipefail
SHOWS='$REMOTE_SHOWS'
NAME='$NAME'
IN='$INCOMING'
REPLACE='$REPLACE'
case \"\$NAME\" in
  */*|.*|*..*) echo 'error: unsafe remote name' >&2; rm -f \"\$SHOWS/\$IN\"; exit 1 ;;
esac
if grep -E '192\\.168\\.88\\.(201|246|248|255)|10\\.42\\.|255\\.255\\.255\\.255' \"\$SHOWS/\$IN\" >/dev/null; then
  echo 'error: forbidden address in uploaded workspace' >&2
  rm -f \"\$SHOWS/\$IN\"
  exit 1
fi
CUR=\$(readlink \"\$SHOWS/current.qxw\" 2>/dev/null || true)
if [[ \"\$REPLACE\" != 1 ]]; then
  if [[ -e \"\$SHOWS/\$NAME\" ]]; then
    echo \"error: \$SHOWS/\$NAME already exists; pass --replace\" >&2
    rm -f \"\$SHOWS/\$IN\"
    exit 1
  fi
  if [[ \"\$CUR\" == \"\$NAME\" ]]; then
    echo 'error: would overwrite the active show; pass --replace' >&2
    rm -f \"\$SHOWS/\$IN\"
    exit 1
  fi
fi
mv \"\$SHOWS/\$IN\" \"\$SHOWS/\$NAME\"
chmod 644 \"\$SHOWS/\$NAME\"
if [[ \"\$REPLACE\" == 1 ]]; then
  ln -sfn \"\$NAME\" \"\$SHOWS/current.qxw\"
fi
ls -l \"\$SHOWS/\$NAME\" \"\$SHOWS/current.qxw\"
echo -n 'current: '
readlink \"\$SHOWS/current.qxw\"
"
