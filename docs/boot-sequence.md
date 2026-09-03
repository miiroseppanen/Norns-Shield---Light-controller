# Boot sequence

## Target appliance chain

```
network / local-fs / sound
        |
python3 -m light_console.midi_wait   (≤12s, then continue)
        |
qlcplus.service
  qlcplus-qml -w -o /home/light/shows/master.qxw
        |
workspace + Virtual Console refresh   (may be minutes)
        |
WebAccess :9999 /qlcplusWS
        |
qlc-startup-chaser.service  (TimeoutStartSec=360)
  find function `startup`
  VC_PAGE|1
  start if not already Running
        |
light-console.service   (independent; OLED status)
```

Light Console does not `Require=` QLC. If QLC is late, OLED shows OFF / WAIT.

## What production actually does

`qlcplus.service` on `valot`:

- `ExecStartPre=/bin/sleep 10`
- `ExecStart=/usr/bin/qlcplus-qml -w -o /home/valot/siirtyma-startup.qxw`
- `After=network-online.target sound.target`
- `qlc-startup-chaser.service` oneshot, 60 attempts, `websocket-client`

Boot log 2026-09-03: QLC process started 19:58:48; startup helper printed `STARTUP CHASER RUNNING` at 20:02:55 (~4 minutes). HTTP 200 and UDP 6454 were live afterward.

Shield trials that SIGTERM'd at 20s during `Refresh 2D view` were too short. That is why autoload looked impossible.

## Shield units

| Unit | Role |
|------|------|
| `qlcplus.service` | `-w -o /home/light/shows/master.qxw`, midi_wait ExecStartPre |
| `qlc-startup-chaser.service` | `python3 -m light_console.startup_chaser` |
| `light-console.service` | OLED status / shutdown |
| `wizbridge.service` | **not enabled** |

Install: `sudo bash packaging/install-appliance.sh`
