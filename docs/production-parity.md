# Production parity

Interactive SCENES/CHASERS work is **DEFERRED**. SHOWS switches named `.qxw` files onto `master.qxw` and restarts QLC. This milestone copies the working production Pi appliance.

```
POWER ON
  -> QLC+ `qlcplus-qml -w -o /home/light/shows/master.qxw`
  -> workspace load (Virtual Console refresh may take minutes)
  -> WebAccess :9999
  -> qlc-startup-chaser starts function `startup`
  -> Launchpad MIDI (Name + UID)
  -> Art-Net loopback (SAFE) until an explicit real-output test
```

Production reference (read-only 2026-09-04, `valot@192.168.88.248`):

```
ExecStart=/usr/bin/qlcplus-qml -w -o /home/valot/siirtyma-startup.qxw
QT_QPA_PLATFORM=offscreen
HOME=/home/valot
```

Same `qlcplus-qml` hash on Shield and production. `-o/--open` is a **boolean** flag; the workspace is the positional `[file]`. `-9` and POST `/loadProject` remain unused.

`QLC+API|isProjectLoaded` stays `false` after CLI load. Use `getFunctionsList` / function count. Production `startup` is function ID 0, type Chaser.

OLED PLAY is status-only: QLC / SHOW / STARTUP / MIDI / OUTPUT / MASTER. Restart is MENU → SYSTEM → RESTART → K3. Shutdown is MENU → SHUTDOWN → K3.

Outputs stay **SAFE** (both Art-Net universes `127.0.0.1`). PKNight `192.168.88.201` is configured in software mapping docs only. Production Pi is up; do not dual-drive the rig.

wlan1 (Realtek `0bda:c811`) is present and DOWN. WiZ bridge software is in `services/wiz/`. Do not enable `wizbridge.service` or WIZ-LIGHTS until that AP is intentionally started.
