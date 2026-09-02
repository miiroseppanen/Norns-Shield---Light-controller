# Milestone 0.5 — QLC+ integration (PAUSED)

Date: 2026-09-02  
Target: `light@shieldxl-light.local` (`192.168.88.246`)  
Baseline: `v0.4.0` = `d443537`; pre-0.5 HEAD `5c072d4`  
Pause: operator left LIGHT-CONTROL network. No further Shield SSH.

## 0.5 COMPLETE (local / partial Pi)

- Minimal test workspace: `qlc/projects/light-console-test.qxw` (no WiZ, PKNight, Launchpad, Art-Net).
- `packaging/systemd/qlcplus.service` + `packaging/install-qlc.sh` (independent of `light-console.service`).
- QLC client: `ConnectionState`, backoff 2s…16s, `FakeTransport`, `QlcWebSocketClient`, `QlcBinding` MASTER → `GM_VALUE`.
- OUTPUT screen: `QLC CONNECTED|OFFLINE|ERROR`, `ENGINE 5.2.2`, `HOST localhost`.
- Local tests for offline startup, connect/loss/reconnect, OUTPUT, MASTER sync, fake transport, packaging unit independence.
- Docs/client code deployed to Shield earlier in the session (rsync + `install-qlc.sh`).

## 0.5 PARTIALLY COMPLETE

- **0.5A systemd QLC engine:** unit installed and enabled on Shield, but **`--open` is not a viable headless web path** on this 5.2.2 QML build.
- **Live protocol:** proven only with **`-w` and no workspace loaded**.
- **Pi acceptance sequence** (stop-only-QLC / OUTPUT OFFLINE / auto CONNECTED / NRestarts / no LC restart): **not finished**.
- **Physical MASTER encoder → QLC:** **not finished**.

## 0.5 NOT STARTED / NOT DONE

- Tag (do not tag).
- WiZ / PKNight / Launchpad / production `.qxw` (intentionally out of scope).
- Final commit message `Milestone 0.5: integrate QLC engine` (this pause is WIP only).

## Last successful results

### Local (Mac, no Shield required)

Pause re-run (Mac, no Shield): **73 passed**. Duplicate names in `tests/test_qlc.py` exist (harmless; pytest keeps one of each).

### Shield (before network drop)

| Check | Result |
|-------|--------|
| QLC+ binary | `/usr/bin/qlcplus-qml` **5.2.2** |
| `-w` only (manual) | HTTP `:9999` **200**, `ws://127.0.0.1:9999/qlcplusWS` **connected**, `isProjectLoaded` **false**, `GM_VALUE\|128` accepted |
| `-w` idle CPU (manual, QML modules present) | ~100% at t=1–2, then ~18% at t=15 with HTTP 200 |
| `qlcplus.service` with `--open` | **active** but **100% CPU**, **never binds :9999** |
| POST `/loadProject` after `-w` | HTTP handler starts, then **event loop freeze**, `:9999` dies |
| `--open` without QML modules (earlier) | **SEGV** (`status=11`) |
| Light Console vs QLC ordering | units independent; LC stayed active while QLC down (observed earlier; full reconnect proof not done) |

### Verified WebSocket messages (live `-w`, empty project)

| Direction | Message | Observed |
|-----------|---------|----------|
| send | `QLC+API\|isProjectLoaded` | sent on connect |
| recv | `QLC+API\|isProjectLoaded\|false` | empty engine (no `--open`) |
| send | `GM_VALUE\|128` | probe `sends=[128]`, `gm=128` |

`isProjectLoaded|true` was **not** observed: loading `light-console-test.qxw` via `--open` or `/loadProject` blocks web.

## Shield services / config changed this session

Do **not** reboot, shutdown, or change Wi-Fi. Production Pi was not touched.

Installed on Shield (keep; do not `apt autoremove` Qt5 leftovers):

- `qml6-module-qtquick-controls`, `qml6-module-qtquick-layouts`, `qml6-module-qtquick-dialogs` (+ pulled Qt Quick deps)
- `qt6-svg-plugins` (adds `libqsvg.so`; SVG “Unsupported image format” gone; **`--open` still does not bind HTTP**)

GPIO/SPI packages were still `ii` after those installs (`gpiod`, `python3-libgpiod`, `libgpiod3`, `python3-spidev`).

`/etc/systemd/system/qlcplus.service` last installed from repo: `ExecStart=… qlcplus-qml -w --open …/light-console-test.qxw`. Unit **enabled**.

Sudoers unchanged this phase (halt-only NOPASSWD). Light Console code was rsynced; `light-console.service` was running the 0.5 client.

## Current expected Shield state (not re-checked after pause)

- **`light-console.service`:** **active** (last seen `active`, `NRestarts=0`). OUTPUT likely **OFFLINE** because QLC systemd was stopped. Independent of QLC; should still be usable.
- **`qlcplus.service`:** **inactive/stopped** (explicit `systemctl stop` before flag experiments; not restarted as a healthy web engine). **enabled**. Next systemd start with current unit **`--open` will spin and not serve :9999**.
- Manual `qlcplus-qml -w` from the last CPU probe: script **did** `kill` it (`killed` printed). No new SSH after that.

## Interrupted command

CPU/rdepends probe `ssh light@shieldxl-light.local` (manual `-w` for 15s) **completed** (exit 0) before this pause. No reboot/shutdown was issued. **No new remote commands** after the operator asked to stop.

## Exact next step when Shield is reachable again

1. **Do not** `systemctl start qlcplus` until `ExecStart` is **`-w` only** (no `--open`, no `/loadProject`).  
2. Change `packaging/systemd/qlcplus.service` to:

   `ExecStart=/usr/bin/qlcplus-qml -w`

   Keep `QT_QPA_PLATFORM=offscreen`. Leave the test `.qxw` in git as source of truth; do not load it until QML/offscreen can open a project without blocking WebAccess.  
3. `rsync` + `sudo bash packaging/install-qlc.sh` (or daemon-reload + reset-failed + restart).  
4. Prove HTTP 200, WS connect, `GM_VALUE`, then the stop-QLC-only / OUTPUT OFFLINE / restart-QLC / auto CONNECTED sequence **without** restarting Light Console.

## Forbidden (unchanged)

No production Pi, no WiZ/WIZ-LIGHTS, no PKNight, no Launchpad, no production `.qxw`, no LC `Requires=` QLC.
