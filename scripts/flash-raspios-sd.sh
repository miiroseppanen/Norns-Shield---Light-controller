#!/usr/bin/env bash
# Flash official Raspberry Pi OS Lite (xz) onto the identified Shield XL microSD.
#
# macOS WARNING: never use conv=sync on an xzcat|dd pipe. BSD dd pads every
# short stdin read with NULs up to bs, which inflates a ~2.84 GiB image to
# the full SD card and corrupts the FAT. Use a plain dd, then a separate sync.
#
# Does not touch Norns SD, production lighting Pi, or the Mac system disk.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IDENTIFY="$ROOT/scripts/identify-sd.py"
MODE="${1:-}"
shift || true

EXPECTED_UNCOMPRESSED=2977955840
EXPECTED_SHA256="${SHIELDXL_IMAGE_SHA256:-acff736ca7945e3b305f07cda4abdb870910e12634991da69783611756e381b3}"
IMG="${SHIELDXL_IMAGE:-/tmp/shieldxl-rpi-os/2026-06-18-raspios-trixie-arm64-lite.img.xz}"
STATUS_DIR="${SHIELDXL_FLASH_STATUS_DIR:-/tmp/shieldxl-flash-status}"
LOG="$STATUS_DIR/flash.log"
STATUS="$STATUS_DIR/flash.status"
HEAD_IMG="$STATUS_DIR/img-head.bin"
HEAD_DISK="$STATUS_DIR/disk-head.bin"
VERIFY_MIB="${SHIELDXL_VERIFY_MIB:-8}"
FIRSTBOOT_PY="${SHIELDXL_FIRSTBOOT_PY:-$ROOT/scripts/write-raspios-firstboot.py}"

die() { echo "FAIL: $*" | tee -a "$LOG" >&2; echo FAIL > "$STATUS"; exit 1; }

python_bin() {
  if command -v python3.11 >/dev/null 2>&1; then
    command -v python3.11
  else
    command -v python3
  fi
}

forbid_conv_sync_pipeline() {
  # Belt: refuse to execute if this script's live pipeline line ever gains conv=sync.
  if grep -E '^[[:space:]]*xzcat .*\| dd ' "$0" | grep -v '^[[:space:]]*#' | grep -q 'conv=sync'; then
    die "refusing to run: flash script still contains xzcat|dd conv=sync"
  fi
}

identify_export() {
  local py
  py="$(python_bin)"
  "$py" "$IDENTIFY" --export
}

preflight_image() {
  [[ -f "$IMG" ]] || die "image missing: $IMG"
  local got
  got="$(shasum -a 256 "$IMG" | awk '{print $1}')"
  [[ "$got" == "$EXPECTED_SHA256" ]] || die "SHA256 mismatch: $got"
  local uncompressed
  "$(python_bin)" - "$EXPECTED_UNCOMPRESSED" <<'PY' || die "uncompressed size constant mismatch"
import sys
exp = int(sys.argv[1])
assert exp == 2840 * 1024 * 1024, exp
PY
  COMPRESSED_BYTES="$(stat -f %z "$IMG" 2>/dev/null || stat -c %s "$IMG")"
  export COMPRESSED_BYTES
}

report_plan() {
  cat <<EOF
=== Phase 0 flash plan (no secrets) ===
target node:     $TARGET_NODE
target rdisk:    $TARGET_RDISK
media:           $MEDIA_NAME
product:         $PRODUCT
serial:          $SERIAL
disk size:       $DISK_SIZE
removable:       $REMOVABLE
writable:        $WRITABLE
write protect:   $WRITE_PROTECT
macOS root:      $ROOT_NODE
image:           $IMG
compressed:      $COMPRESSED_BYTES bytes
uncompressed:    $EXPECTED_UNCOMPRESSED bytes
SHA256:          $EXPECTED_SHA256 OK
dd command:      xzcat \"$IMG\" | dd of=$TARGET_RDISK bs=4m status=progress
post-write:      sync
FORBIDDEN:       conv=sync on this pipe
EOF
}

load_identity() {
  local export_txt
  export_txt="$(identify_export)" || die "identity assert failed"
  eval "$export_txt"
  [[ "${ASSERT:-}" == "PASS" ]] || die "identity ASSERT not PASS"
  [[ -n "${TARGET_RDISK:-}" && -n "${TARGET_NODE:-}" ]] || die "identity missing target"
  case "$TARGET_DISK" in
    disk0|disk3) die "refusing system disk $TARGET_DISK" ;;
  esac
  [[ "$TARGET_NODE" == /dev/disk* ]] || die "unexpected TARGET_NODE $TARGET_NODE"
  [[ "$TARGET_RDISK" == /dev/rdisk* ]] || die "unexpected TARGET_RDISK $TARGET_RDISK"
}

assert_dd_payload() {
  local logf="$1"
  grep -q "${EXPECTED_UNCOMPRESSED} bytes transferred" "$logf" \
    || die "dd did not transfer exactly $EXPECTED_UNCOMPRESSED bytes"
  # Output records must be 710 full 4 MiB blocks. Input records from a pipe are
  # often 0+N short reads; requiring 710+0 records in is wrong and was a false FAIL.
  grep -Eq '710\+0 records out' "$logf" || die "dd records out is not 710+0"
  if grep -Eq '1522[0-9]\+[0-9] records out' "$logf"; then
    die "dd output record count looks like conv=sync inflation"
  fi
}

verify_prefix() {
  local rdisk="$1"
  local n=$((VERIFY_MIB * 1048576))
  xzcat "$IMG" | dd bs=1048576 count="$VERIFY_MIB" of="$HEAD_IMG" status=none
  dd if="$rdisk" bs=1048576 count="$VERIFY_MIB" of="$HEAD_DISK" status=none
  cmp "$HEAD_IMG" "$HEAD_DISK" || die "read-only prefix cmp mismatch (${VERIFY_MIB} MiB)"
  echo "prefix cmp OK (${VERIFY_MIB} MiB)"
}

find_bootfs() {
  local vol
  for vol in /Volumes/bootfs /Volumes/boot /Volumes/BOOTFS /Volumes/BOOT; do
    if [[ -f "$vol/config.txt" ]]; then
      echo "$vol"
      return 0
    fi
  done
  for vol in /Volumes/*/config.txt; do
    [[ -f "$vol" ]] || continue
    echo "$(dirname "$vol")"
    return 0
  done
  return 1
}

flash() {
  mkdir -p "$STATUS_DIR"
  : > "$LOG"
  echo RUNNING > "$STATUS"
  forbid_conv_sync_pipeline
  preflight_image
  load_identity
  report_plan | tee -a "$LOG"

  echo "unmount $TARGET_DISK" | tee -a "$LOG"
  diskutil unmountDisk force "$TARGET_DISK" || die "unmount failed"

  local before="$TARGET_NODE"
  load_identity
  [[ "$TARGET_NODE" == "$before" ]] || die "device node changed after unmount: $before -> $TARGET_NODE"
  report_plan | tee -a "$LOG"

  local ddlog="$STATUS_DIR/dd.stderr"
  : > "$ddlog"
  echo "writing image (no conv=sync)" | tee -a "$LOG"
  # conv=sync is intentionally absent. Do not add it.
  set +e
  xzcat "$IMG" | dd of="$TARGET_RDISK" bs=4m status=progress 2>&1 | tee -a "$ddlog" "$LOG"
  local pipe_ec=("${PIPESTATUS[@]}")
  set -e
  [[ "${pipe_ec[0]}" -eq 0 ]] || die "xzcat exit ${pipe_ec[0]}"
  [[ "${pipe_ec[1]}" -eq 0 ]] || die "dd exit ${pipe_ec[1]}"
  echo "dd exit 0" | tee -a "$LOG"

  echo "sync" | tee -a "$LOG"
  sync

  assert_dd_payload "$ddlog"

  echo "unmount after write" | tee -a "$LOG"
  diskutil unmountDisk force "$TARGET_DISK" || true

  echo "read-only prefix verification" | tee -a "$LOG"
  verify_prefix "$TARGET_RDISK" | tee -a "$LOG"

  echo "partition table" | tee -a "$LOG"
  diskutil list "$TARGET_DISK" | tee -a "$LOG"
  diskutil list "$TARGET_DISK" | grep -q "Windows_FAT_32\|DOS_FAT_32\|Microsoft Basic Data" \
    || die "no FAT/boot partition in table"
  diskutil list "$TARGET_DISK" | grep -qi Linux || die "no Linux root partition in table"

  echo "remount" | tee -a "$LOG"
  diskutil mountDisk "$TARGET_DISK" || die "mountDisk failed"

  local boot
  boot="$(find_bootfs)" || die "boot FAT did not mount (no config.txt)"
  echo "bootfs=$boot" | tee -a "$LOG"
  [[ -f "$boot/config.txt" ]] || die "config.txt missing on bootfs"
  if ls "$boot"/norns* >/dev/null 2>&1; then
    die "norns files found on boot volume"
  fi
  diskutil info "${TARGET_DISK}s1" | tee -a "$LOG"
  diskutil info "${TARGET_DISK}s1" | grep -qiE 'FAT|MS-DOS|msdos' \
    || die "boot slice file system not recognized as FAT"

  if [[ -f "$FIRSTBOOT_PY" && -f /tmp/shieldxl-firstboot.env ]]; then
    echo "writing first-boot cloud-init (secrets not logged)" | tee -a "$LOG"
    "$(python_bin)" "$FIRSTBOOT_PY" | tee -a "$LOG" \
      || die "first-boot config write failed"
    grep -q "hostname: shieldxl-light" "$boot/user-data" \
      || die "hostname missing from user-data"
    grep -q "enable_ssh: true" "$boot/user-data" \
      || die "enable_ssh missing from user-data"
    grep -q "LIGHT-CONTROL" "$boot/network-config" \
      || die "Wi-Fi SSID missing from network-config"
    [[ -f "$boot/ssh" ]] || die "legacy ssh enable file missing"
  else
    die "first-boot helper or secrets file missing; not treating image-only as Phase 0 PASS"
  fi

  sync
  echo "eject $TARGET_DISK" | tee -a "$LOG"
  diskutil eject "$TARGET_DISK" || diskutil unmountDisk "$TARGET_DISK" || true
  echo PASS > "$STATUS"
  echo "FLASH_PASS" | tee -a "$LOG"
}

usage() {
  cat <<EOF
Usage:
  $0 --identify     # read-only identity assert
  $0 --plan         # identity + image checksum + print dd command (no write)
  $0 --write        # flash only after asserts PASS; stop on any FAIL (no retry)

Environment:
  SHIELDXL_IMAGE  SHIELDXL_IMAGE_SHA256  SHIELDXL_SD_SERIAL  SHIELDXL_SD_BYTES
EOF
}

case "$MODE" in
  --identify)
    identify_export
    "$(python_bin)" "$IDENTIFY"
    ;;
  --plan)
    mkdir -p "$STATUS_DIR"
    : > "$LOG"
    forbid_conv_sync_pipeline
    preflight_image
    load_identity
    report_plan
    ;;
  --write)
    flash
    ;;
  --help|-h|"")
    usage
    ;;
  *)
    die "unknown mode $MODE"
    ;;
esac
