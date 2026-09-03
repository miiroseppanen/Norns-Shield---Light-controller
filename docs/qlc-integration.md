# QLC+ integration

Show engine: **QLC+ 5.2.2** (`/usr/bin/qlcplus-qml`). light-console is a WebSocket client. It never starts QLC+ itself.

**Milestone 0.7:** `qlcplus.service` is `-w` only. QLC starts with WebAccess and **no workspace**. Canonical show content is `master.qxw`; Light Console SHOWS are logical YAML groups. Automatic cold-boot load of master is **UNRESOLVED**. Do not POST `/loadProject`, pass a positional workspace, or use `-9`. Switching SHOWS does not load QLC.

## Services (independent)

| Unit | Role |
|------|------|
| `light-console.service` | OLED UI as user `light` |
| `qlcplus.service` | Headless QLC+ 5.2.2, web on :9999, `-w` only |

Neither Light Console nor QLC `Requires=` the other. Light Console has **no** systemctl sudo.

**Physical acceptance PASS** (2026-09-02, real Shield): PLAY E1 MASTER, PARAMS shared MASTER, OUTPUT CONNECTED/OFFLINE, QLC stop/start without Light Console restart, offline MASTER resync.

Verified 5.2.2 CLI (`qlcplus-qml --help`):

```
Usage: qlcplus-qml [options] [file]
  -w, --web     Enable remote web access
  file          File to open.
```

`--open` is a valueless flag on this build and is **not** how a path is passed. Live `ExecStart` is:

```
QT_QPA_PLATFORM=offscreen
/usr/bin/qlcplus-qml -w
```

The WebAccess browser loads a workspace with `POST /loadProject` (multipart field `qlcprj`, **file contents**, not a server path). Do **not** automate that POST from Light Console on this 5.2.2 QML + offscreen image: `show-a.qxw` ingested then wedged HTTP `:9999`. See [`docs/show-ui.md`](show-ui.md).

Install: `sudo bash packaging/install-qlc.sh`

Qt packages already on the Shield for the QML UI (keep; do not `apt autoremove` Qt5 leftovers): `qml6-module-qtquick-controls`, `qml6-module-qtquick-layouts`, `qml6-module-qtquick-dialogs`, `qt6-svg-plugins`.

## Endpoint

```
ws://127.0.0.1:9999/qlcplusWS
```

HTTP: `http://127.0.0.1:9999/` (QLC+ web UI).

## Verified QLC+ 5.2.2 WebSocket messages

Messages are `field|field|…` text. Do not invent additional protocol.

| Direction | Message | Use |
|-----------|---------|-----|
| send | `QLC+API\|isProjectLoaded` | on connect |
| recv | `QLC+API\|isProjectLoaded\|true` / `false` | project loaded |
| send | `QLC+API\|getFunctionsNumber` | on connect |
| recv | `QLC+API\|getFunctionsNumber\|<n>` | function count |
| send | `QLC+API\|getFunctionsList` | on connect |
| recv | `QLC+API\|getFunctionsList\|<id>\|<name>\|…` | id/name pairs |
| send | `QLC+API\|getFunctionType\|<id>` | type string (optional) |
| recv | `QLC+API\|getFunctionType\|<id>\|<Scene\|Chaser\|…>` | |
| send | `QLC+API\|setFunctionStatus\|<id>\|<0\|1>` | stop / start (GO) |
| send | `GM_VALUE\|<0-255>` | Grand Master |
| recv | `GM_VALUE\|<value>` or `GM_VALUE\|<value>\|<value>` | |

OLED scene/chaser **names** come from logical show metadata (`/home/light/shows/*.yaml`), not from scraping the QLC browser. GO sends `setFunctionStatus` only when the live `getFunctionsList` id+name pair matches that metadata. Mismatch → no command (`ID MISMATCH`). If QLC has no project loaded, GO is `NO PROJECT`.

`POLL` is documented as ignored keepalive; not required.

MASTER on PLAY is 0–100 (shared Parameter). Binding maps `int(master * 255 / 100)` to `GM_VALUE`. Default PLAY master is **80** → `GM_VALUE|204`. Offline, the parameter still changes AppState. On reconnect, the current master is sent once (duplicates suppressed). Momentary GO is **not** replayed after reconnect.

PLAY: K1 MENU, E1 MASTER, E2 SCENE, K2 SCENE GO, E3 CHASER, K3 CHASER GO.

## Client

`QLCClient` + `MockQLCClient` (tests/simulator) + `QlcWebSocketClient` (Shield). States: `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `ERROR`. Bounded exponential backoff (2s…16s). `pump()` from the UI tick; GPIO handlers do not block on the socket.

Runtime snapshot: `/tmp/light-console.status` (`screen`, `master`, `qlc_state`, `qlc=CONNECTED|OFFLINE`). Engine unreachable uses `qlc_state=error` internally; OUTPUT still shows `OFFLINE`.

## OUTPUT

```
QLC        CONNECTED | OFFLINE
ENGINE     5.2.2
HOST       localhost
```

## Forbidden

- Restart QLC from light-console on disconnect (show load uses `.reload-qlc` + systemd path, not UI sudo)
- `Requires=` / `After=` coupling so Light Console cannot start if QLC is down
- Copy production `.qxw`
- WiZ / PKNight / Launchpad in test workspaces
- `--open <path>` / `/loadProject` until QML offscreen can load a project without blocking web
- `NOPASSWD: ALL` or generic `systemctl` sudo for user `light`
