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
/usr/bin/qlcplus-qml -w
```

**Do not use `--open` or POST `/loadProject` on this 5.2.2 QML + offscreen build.** Both load the native Function Manager / 2D view and block WebAccess (`:9999` never binds, or freezes after POST). The repo still owns [`qlc/projects/light-console-test.qxw`](../qlc/projects/light-console-test.qxw) (no WiZ, PKNight, Launchpad, Art-Net) as the future workspace; it is **not loaded at runtime**.

Qt packages already on the Shield for the QML UI (keep; do not `apt autoremove` Qt5 leftovers): `qml6-module-qtquick-controls`, `qml6-module-qtquick-layouts`, `qml6-module-qtquick-dialogs`, `qt6-svg-plugins`.

Install QLC unit: `sudo bash packaging/install-qlc.sh`

## Endpoint

```
ws://127.0.0.1:9999/qlcplusWS
```

HTTP: `http://127.0.0.1:9999/` (QLC+ web UI).

## Verified QLC+ 5.2.2 WebSocket messages (0.5)

Messages are `field|field|…` text. Proven against the Shield engine with `-w` (empty project):

| Direction | Message | Observed |
|-----------|---------|----------|
| send | `QLC+API\|isProjectLoaded` | sent on connect |
| recv | `QLC+API\|isProjectLoaded\|false` | no workspace loaded |
| send | `GM_VALUE\|<0-255>` | set Grand Master |
| recv | `GM_VALUE\|<value>` or `GM_VALUE\|<value>\|<value>` | engine GM (web UI uses `msg[1]`, `msg[2]`) |

`POLL` is documented as ignored keepalive; not required for 0.5.

MASTER on PLAY/PARAMS is 0–100 (shared Parameter). Binding maps `int(master * 255 / 100)` to `GM_VALUE`. Default PLAY master is **80** → `GM_VALUE|204`. Offline, the parameter still changes AppState. On reconnect, the current master is sent once (duplicates suppressed).

PLAY **E1** is MASTER. PARAMS shows the same value (E3 when Master is selected).

## Client

`QLCClient` + `MockQLCClient` (tests/simulator) + `QlcWebSocketClient` (Shield). States: `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `ERROR`. Bounded exponential backoff (2s…16s). `pump()` from the UI tick; GPIO handlers do not block on the socket.

Runtime snapshot: `/tmp/light-console.status` (`screen`, `master`, `qlc_state`, `qlc=CONNECTED|OFFLINE|ERROR`).

## OUTPUT

```
QLC        CONNECTED | OFFLINE | ERROR
ENGINE     5.2.2
HOST       localhost
```

## Forbidden

- Restart QLC from light-console on disconnect
- `Requires=` / `After=` coupling so Light Console cannot start if QLC is down
- Copy production `.qxw`
- WiZ / PKNight / Launchpad in this workspace
- `--open` / `/loadProject` until QML offscreen can load a project without blocking web
