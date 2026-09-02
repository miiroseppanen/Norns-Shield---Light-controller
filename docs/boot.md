# Boot

Deterministic, diagnosable, no restart loops that flash the show.

## Milestone 0.4c (now)

`light-console.service` starts the OLED UI on boot. QLC+ is **not** started.

```
packaging/systemd/light-console.service
```

On the Shield Pi:

```
User=light
WorkingDirectory=/home/light/light-console
PYTHONPATH=/home/light/light-console
ExecStart=/usr/bin/python3 -u -m light_console.main --shield
Restart=on-failure (3s, burst 5 / 60s in [Unit])
```

Do **not** order the unit after `dev-spidev0.0.device`. On Raspberry Pi OS that `.device` unit can stay inactive while `/dev/spidev0.0` exists; systemd then leaves `light-console.service` as a pending job and the OLED stays blank.

A flock on `/tmp/light-console.instance.lock` prevents a second `--shield` from stealing GPIO/SPI.

Halt: `/etc/sudoers.d/light-console-shutdown` is NOPASSWD for **only** `/usr/sbin/shutdown -h now`. Raspberry Pi OS still has password-required `(ALL) ALL`. After a reboot (or `sudo -k`), `sudo -n true` must fail; `sudo -n -l /usr/sbin/shutdown -h now` must list that command. Never prove sudo by executing `reboot` or `shutdown`. The UI still requires SYSTEM → SHUTDOWN → K3 confirm.

## Intended order (later)

1. NetworkManager: WIZ-LIGHTS AP (wlan1) — not in 0.4c
2. wizbridge.service — not in 0.4c
3. qlcplus.service — not in 0.4c
4. light-console.service — PLAY UI (this milestone)

## Forbidden

- Restart QLC because OLED failed
- Restart WIZ-LIGHTS in a loop because WiZ count is 0
- Require wlan0 before starting the UI
- Broad NOPASSWD sudo for `light`
