# QLC+ integration

Show engine: **QLC+ 5.2.2** (`/usr/bin/qlcplus-qml`). light-console is a WebSocket client only. It never starts or restarts QLC+.

## Services (independent)

| Unit | Role |
|------|------|
| `light-console.service` | OLED UI as user `light` |
| `qlcplus.service` | Headless QLC+ 5.2.2, web on :9999 |

Neither `Requires=` the other. If `qlcplus.service` is stopped, the UI stays up and OUTPUT shows `OFFLINE`.

```
QT_QPA_PLATFORM=offscreen
/usr/bin/qlcplus-qml -w --open /home/light/light-console/qlc/projects/light-console-test.qxw
```

This 5.2.2 image needs Qt 6 QML modules for `--open` (otherwise SEGV): `qml6-module-qtquick-controls`, `qml6-module-qtquick-layouts`, `qml6-module-qtquick-dialogs`.

Install QLC unit: `sudo bash packaging/install-qlc.sh`

Test workspace: [`qlc/projects/light-console-test.qxw`](../qlc/projects/light-console-test.qxw). No WiZ, PKNight, Launchpad, or production Art-Net.

## Endpoint

```
ws://127.0.0.1:9999/qlcplusWS
```

HTTP: `http://127.0.0.1:9999/` (QLC+ web UI).

## Verified QLC+ 5.2.2 WebSocket messages (0.5)

Messages are `field|field|…` text. Proven against the Shield engine:

| Direction | Message | Meaning |
|-----------|---------|---------|
| send | `QLC+API\|isProjectLoaded` | Ask if a workspace is loaded |
| recv | `QLC+API\|isProjectLoaded\|true` or `…\|false` | Workspace loaded |
| send | `GM_VALUE\|<0-255>` | Set Grand Master |
| recv | `GM_VALUE\|<value>\|<value>` | Echo / engine GM change (web UI: `msg[1]`, `msg[2]`) |

`POLL` is documented as ignored keepalive; not required for 0.5.

MASTER on PLAY/PARAMS is 0–100. Binding maps `int(master * 255 / 100)` to `GM_VALUE`. Offline, the parameter still changes AppState. On reconnect, the current master is sent once (duplicates suppressed).

## Client

`QLCClient` + `MockQLCClient` (tests/simulator) + `QlcWebSocketClient` (Shield). States: `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `ERROR`. Bounded exponential backoff. `pump()` from the UI tick; GPIO handlers do not block on the socket.

## OUTPUT

```
QLC        CONNECTED | OFFLINE | ERROR
ENGINE     5.2.2
HOST       localhost
```

## Forbidden

- Restart QLC from light-console on disconnect
- Copy production `.qxw`
- WiZ / PKNight / Launchpad in this workspace
