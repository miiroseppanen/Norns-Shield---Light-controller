# Cold-boot appliance acceptance

Milestone 0.9 proves the Shield starts the full appliance from a true power-on, with no SSH, browser, or button input after power is applied.

Real lighting outputs stay **SAFE** (Art-Net loopback only). Do not arm PKNight, production Pi, or WiZ.

## Expected sequence

```
cold power
  -> Linux
  -> network interfaces (wlan0 LIGHT-CONTROL, wlan1 present)
  -> light-console.service (OLED; independent of QLC)
  -> qlcplus.service ExecStartPre: midi_wait (≤12s, continues if missing)
  -> qlcplus-qml -w -o /home/light/shows/master.qxw
  -> master.qxw + Virtual Console refresh (may be minutes)
  -> WebAccess HTTP :9999
  -> WebSocket /qlcplusWS
  -> qlc-startup-chaser.service (TimeoutStartSec=360)
       find function startup
       VC page 1
       start if not already Running
  -> status UI healthy (QLC connected, startup RUNNING, MIDI bound)
```

Light Console may become active before QLC. Transient QLC-offline, helper retries, and network delay are acceptable if the appliance converges.

## Time budget

Do not treat a short timeout as failure.

| Stage | Observed / configured | Budget |
|-------|------------------------|--------|
| Launchpad wait | `midi_wait` default 12s | ≤12s, then QLC starts anyway |
| QLC process after SIGKILL recovery | ~6s | warm-path only |
| Production WebAccess after VC refresh | ~4 min (2026-09-03: 19:58:48 → 20:02:55) | **up to 360s** |
| Startup helper | `TimeoutStartSec=360`, 90×2s attempts | **up to 360s** |
| wlan0 address | NetworkManager STA | tens of seconds |
| OLED visible | `light-console.service` independent | often before QLC HTTP |

Acceptance is the **final stable** state within that budget, not the first probe.

## Read-only check

On the Shield, after it is reachable:

```
cd /home/light/light-console
python3 -m light_console.appliance_check
```

or `/home/light/light-console/packaging/light-appliance-check`.

The command does not start, stop, or restart services and does not change configuration.

## One physical action

After software preparation:

Katkaise Shieldistä virta kokonaan noin 10 sekunniksi ja kytke takaisin.
Älä avaa SSH:ta, selainta tai paina mitään. Ilmoita vain kun OLED on taas näkyvissä.

One clean cold-boot PASS is enough. Repeat only after a software race fix.

## Physical acceptance PASS (2026-09-04)

Cold power-on. No SSH, browser, or button input until OLED was visible.

| Clock (EEST) | Event |
|--------------|--------|
| 07:40:57 | systemd journal start |
| 07:41:01 | `light-console.service` (OLED) |
| 07:41:12 | Launchpad present; `qlcplus-qml -w -o /home/light/shows/master.qxw` (PPID 1, NRestarts=0) |
| 07:41:12–18 | startup helper: 3× connection refused, then WS up |
| 07:41:18 | VC page 1; `startup` already Running; helper finished |
| 07:42:28 | Light Console WebSocket connected (reconnect backoff) |

`python3 -m light_console.appliance_check` **PASS** (0 failing). Uptime at probe ~168s (fresh boot). Functions 100. Art-Net loopback only. Production Pi up and unused. Throttled `0x0`. wlan0 `192.168.88.246` UP. wlan1 present DOWN (SAFE).

Boot to healthy: **21s** (systemd 07:40:57 → startup RUNNING 07:41:18).

### Boot notes (not failures)

- Helper retries while QLC binds WebAccess are expected.
- Light Console WS lagged ~70s after helper success because of reconnect backoff. OLED and `startup` were already healthy.
- MIDI profile file `Novation Launchpad Mini` missing on disk; Name + UID `1-1.2:0` still bound.
- A few bundled `.qxf` definitions under `/home/light/shows/` failed to load; function count stayed 100.
- No QLC restart loop. No Launchpad wait timeout. No undervoltage.
