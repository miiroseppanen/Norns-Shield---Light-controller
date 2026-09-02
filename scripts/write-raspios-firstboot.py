#!/usr/bin/env python3
"""Write Raspberry Pi OS Trixie cloud-init files onto a mounted bootfs.

Reads secrets from an env file (default /tmp/shieldxl-firstboot.env).
Never prints passwords. Do not copy the env file into git.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ENV_PATH = Path(os.environ.get("SHIELDXL_FIRSTBOOT_ENV", "/tmp/shieldxl-firstboot.env"))


def bootfs() -> Path:
    for name in ("bootfs", "boot", "BOOTFS", "BOOT"):
        p = Path("/Volumes") / name
        if p.is_dir() and (p / "config.txt").exists():
            return p
    for p in Path("/Volumes").iterdir():
        if (p / "config.txt").exists() and (
            (p / "start.elf").exists() or (p / "kernel8.img").exists() or (p / "user-data").exists()
        ):
            return p
    raise SystemExit("bootfs not found")


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        env[k] = v
    return env


def main() -> int:
    if not ENV_PATH.is_file():
        raise SystemExit(f"secrets env missing: {ENV_PATH}")
    boot = bootfs()
    env = load_env(ENV_PATH)
    hashed = subprocess.check_output(
        ["openssl", "passwd", "-6", "-stdin"],
        input=env["LIGHT_PASS"].encode(),
    ).decode().strip()
    if not hashed.startswith("$6$"):
        raise SystemExit("password hash failed")

    user = env["LIGHT_USER"]
    host = env["HOSTNAME"]
    tz = env["TIMEZONE"]
    ssid = env["WIFI_SSID"]
    psk = env["WIFI_PSK"]
    country = env["WIFI_COUNTRY"]
    pubkey = env["PUBKEY"]
    layout = env["KEYMAP"]

    user_data = f"""#cloud-config
hostname: {host}
manage_etc_hosts: true
timezone: {tz}
locale: fi_FI.UTF-8
keyboard:
  model: pc105
  layout: {layout}
users:
  - name: {user}
    groups: users,adm,dialout,audio,netdev,video,plugdev,cdrom,games,input,gpio,spi,i2c,render,sudo
    shell: /bin/bash
    lock_passwd: false
    passwd: {hashed}
    ssh_authorized_keys:
      - {pubkey}
    sudo: ALL=(ALL) ALL
enable_ssh: true
ssh_pwauth: true
"""
    net = f"""network:
  version: 2
  wifis:
    renderer: NetworkManager
    wlan0:
      dhcp4: true
      regulatory-domain: {json.dumps(country)}
      access-points:
        {json.dumps(ssid)}:
          password: {json.dumps(psk)}
      optional: true
"""
    (boot / "user-data").write_text(user_data)
    (boot / "network-config").write_text(net)
    (boot / "ssh").write_text("")
    meta = boot / "meta-data"
    if not meta.exists() or meta.stat().st_size == 0:
        meta.write_text(f"instance-id: {host}\nlocal-hostname: {host}\n")

    text = (boot / "user-data").read_text()
    assert f"hostname: {host}" in text
    assert "enable_ssh: true" in text
    assert tz in text
    assert f"layout: {layout}" in text
    assert user in text
    assert pubkey.split()[1] in text
    assert env["LIGHT_PASS"] not in text
    net_text = (boot / "network-config").read_text()
    assert ssid in net_text
    print(f"firstboot written to {boot}")
    print("user-data hostname+ssh OK")
    print("network-config SSID present; PSK not logged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
