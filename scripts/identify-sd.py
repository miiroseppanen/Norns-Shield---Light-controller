#!/usr/bin/env python3
"""Identify the Shield XL bring-up microSD. Never assume a disk number.

Matches the Built In SDXC Reader SanDisk SDSR64G used for Milestone 0.2.
Prints KEY=VALUE on success, exits 1 on FAIL. Read-only: does not write disks.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

REQUIRED_SERIAL = os.environ.get("SHIELDXL_SD_SERIAL", "0xc7f8c338")
REQUIRED_BYTES = os.environ.get("SHIELDXL_SD_BYTES", "63864569856")
REQUIRED_PRODUCTS = ("SDSR64G", "SR64G")
FORBIDDEN_WHOLE_DISKS = {"disk0", "disk3"}  # Mac internal / Macintosh HD container


def kv(dev: str) -> dict:
    out = subprocess.check_output(["diskutil", "info", dev], text=True)
    d = {}
    for ln in out.splitlines():
        if ":" in ln:
            k, v = ln.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def fail(msg: str) -> None:
    print(f"ASSERT FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_card_reader(sp: str) -> dict:
    """Extract the built-in reader card that matches product + serial."""
    card: dict = {}
    in_builtin = False
    for raw in sp.splitlines():
        line = raw.strip()
        if "Built in SD Card Reader" in raw or "Built In SDXC" in raw:
            in_builtin = True
        if not in_builtin:
            continue
        if line.startswith("Product Name:"):
            card["product"] = line.split(":", 1)[1].strip()
        elif line.startswith("Serial Number:"):
            card["serial"] = line.split(":", 1)[1].strip().lower()
        elif line.startswith("BSD Name:"):
            # First BSD Name under the card is the whole disk (diskN), later ones are slices.
            if "disk" not in card:
                card["disk"] = line.split(":", 1)[1].strip()
        elif line.startswith("Capacity:") and "bytes" in line.lower() and "capacity_line" not in card:
            card["capacity_line"] = line
    return card


def iokit_flags(disk: str, ioreg: str) -> tuple[str | None, str | None]:
    wp = None
    idx = ioreg.find('"Product Name"="SR64G"')
    if idx >= 0:
        chunk = ioreg[max(0, idx - 80) : idx + 900]
        m = re.search(r'"Write Protect Enabled"=(\w+)', chunk)
        if m:
            wp = m.group(1)
    writable = None
    m = re.search(
        rf'"BSD Name" = "{re.escape(disk)}".{{0,2500}}?"Writable" = (Yes|No)',
        ioreg,
        re.S,
    )
    if m:
        writable = m.group(1)
    return wp, writable


def identify() -> dict:
    try:
        sp = subprocess.check_output(["system_profiler", "SPCardReaderDataType"], text=True)
    except subprocess.CalledProcessError as e:
        fail(f"system_profiler failed: {e}")

    card = parse_card_reader(sp)
    disk = card.get("disk")
    if not disk:
        fail("no BSD Name for the built-in SD reader card (card missing or not a block device)")
    if not disk.startswith("disk") or "s" in disk[4:]:
        fail(f"BSD Name is not a whole disk: {disk!r}")
    if disk in FORBIDDEN_WHOLE_DISKS:
        fail(f"{disk} is a forbidden system disk")

    product = card.get("product") or ""
    if not any(p in product or p in sp for p in REQUIRED_PRODUCTS):
        fail(f"product {product!r} is not SanDisk SDSR64G / SR64G")
    serial = (card.get("serial") or "").lower()
    if serial != REQUIRED_SERIAL.lower():
        fail(f"serial {serial!r} != {REQUIRED_SERIAL}")

    info = kv(disk)
    node = info.get("Device Node") or ""
    if node != f"/dev/{disk}":
        fail(f"device node {node!r}")
    media = info.get("Device / Media Name") or ""
    if "SDXC Reader" not in media or "Built In" not in media:
        fail(f"media name {media!r} is not Built In SDXC Reader")
    if info.get("Protocol") != "Secure Digital":
        fail(f"protocol {info.get('Protocol')!r}")
    size = info.get("Disk Size") or ""
    if REQUIRED_BYTES not in size:
        fail(f"size {size!r} does not contain {REQUIRED_BYTES}")
    if info.get("Removable Media") != "Removable":
        fail(f"removable {info.get('Removable Media')!r}")
    if info.get("Media Read-Only") != "No":
        fail(f"Media Read-Only={info.get('Media Read-Only')!r}")
    if info.get("Whole") != "Yes":
        fail("not a whole disk")

    root = kv("/")
    root_whole = (root.get("Part of Whole") or "").strip()
    root_node = root.get("Device Node") or ""
    if root_whole == disk:
        fail("macOS root volume is on the candidate disk")
    if root_node.startswith(f"/dev/{disk}"):
        fail("macOS root device is the candidate disk")

    ioreg = subprocess.check_output(["ioreg", "-lw0"], text=True, errors="replace")
    if "SR64G" not in ioreg:
        fail("SR64G not in IOKit")
    wp, writable = iokit_flags(disk, ioreg)
    if wp != "No":
        fail(f"Write Protect Enabled={wp!r}")
    if writable != "Yes":
        fail(f"IOMedia Writable={writable!r}")

    return {
        "TARGET_DISK": disk,
        "TARGET_NODE": node,
        "TARGET_RDISK": f"/dev/r{disk}",
        "MEDIA_NAME": media,
        "PROTOCOL": info.get("Protocol") or "",
        "DISK_SIZE": size,
        "SERIAL": serial,
        "PRODUCT": product,
        "REMOVABLE": info.get("Removable Media") or "",
        "MEDIA_READ_ONLY": info.get("Media Read-Only") or "",
        "WRITABLE": writable,
        "WRITE_PROTECT": wp,
        "ROOT_NODE": root_node,
        "ASSERT": "PASS",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--export", action="store_true", help="print KEY=VALUE for shell eval")
    args = p.parse_args()
    ident = identify()
    if args.export:
        for k, v in ident.items():
            v = str(v).replace("\n", " ").replace("'", "")
            print(f"{k}='{v}'")
    else:
        print(f"ASSERT PASS: {ident['TARGET_NODE']} {ident['MEDIA_NAME']} {ident['PRODUCT']} serial={ident['SERIAL']}")
        for k, v in ident.items():
            print(f"  {k}={v}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        fail(f"command failed: {e}")
