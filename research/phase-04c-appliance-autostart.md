# Milestone 0.4c — Appliance autostart

Date: 2026-09-02  
Target: `light@shieldxl-light.local`

## Scope

Boot into Light Console UI as user `light`. No QLC systemd. No wizbridge. No WIZ-LIGHTS. No Launchpad.

## Sudoers

File: `packaging/sudoers.d/light-console-shutdown`

```
light ALL=(root) NOPASSWD: /usr/sbin/shutdown -h now
```

Installed to `/etc/sudoers.d/light-console-shutdown` after `visudo -cf`. Raspberry Pi OS still has password-required `(ALL) ALL`.

Non-destructive proof (after reboot or `sudo -k`):

- `sudo -n -l /usr/sbin/shutdown -h now` lists that command
- `sudo -n true` still needs a password
- Do **not** execute `shutdown` or `reboot` to prove sudo. A cached `timestamp_type=global` ticket makes `sudo -n reboot` actually reboot.

## systemd

`packaging/systemd/light-console.service` → `/etc/systemd/system/light-console.service`

- `User=light`, `WorkingDirectory` + `PYTHONPATH` `/home/light/light-console`
- `ExecStart=/usr/bin/python3 -u -m light_console.main --shield`
- `Restart=on-failure`, `RestartSec=3`
- `StartLimitIntervalSec=60` + `StartLimitBurst=5` in **`[Unit]`** (unknown in `[Service]` on systemd 257)
- Do not `After=`/`Wants=` `dev-spidev0.0.device` (pending job, blank OLED)
- Does not start QLC+

Install (already on the Pi, no nested SSH):

```
sudo bash /home/light/light-console/packaging/install-appliance.sh
```

## Single instance

`fcntl` exclusive lock `/tmp/light-console.instance.lock` for `--shield`. A second SSH foreground must exit 1 instead of stealing GPIO/SPI.

## Proof (2026-09-02, `shieldxl-light`)

- `visudo -cf` on the drop-in: parse OK. Installed mode 440.
- After reboot: `sudo -n true` denied; `sudo -n -l /usr/sbin/shutdown -h now` lists that command. `(ALL) ALL` still password-required.
- `systemd-analyze verify` exit 0 (StartLimit in `[Unit]`).
- Cold boot: `light-console.service` active as user `light` within seconds; journal `shield  PLAY`; NRestarts=0; SPI `/dev/spidev0.0` + gpio-line fds; no Traceback; QLC not started.
- Second `python3 -u -m light_console.main --shield` exits 1 (lock held). Service stays active.
- Did not execute UI shutdown confirm. Did not systemd-start QLC.
