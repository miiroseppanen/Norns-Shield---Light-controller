# Milestone 0.5 — QLC+ integration

Date: 2026-09-02  
Target: `light@shieldxl-light.local`  
Baseline: `v0.4.0` = `d443537`  
WIP pauses: `dfc5dc4`, `47d4293`

## Result

**PASS** (automated + physical). Headless QLC+ 5.2.2 is a separate systemd unit (`-w` only). Light Console reconnects without restart. PLAY MASTER maps to `GM_VALUE`.

Software commit: `c9a2327`. Physical acceptance: 2026-09-02, operator on real Shield.

## Physical acceptance PASS

Verified on real Shield:

- PLAY E1 controls MASTER
- PARAMS shares the same MASTER state
- OUTPUT shows QLC CONNECTED / ENGINE 5.2.2
- stopping `qlcplus` does not stop or restart Light Console
- OUTPUT transitions to OFFLINE
- MASTER remains usable while QLC is offline
- starting `qlcplus` causes automatic reconnect
- OUTPUT returns to CONNECTED without restarting Light Console
- offline intended MASTER state resynchronizes to QLC

Automated tests: **75 PASS**.

Tag: `v0.5.0` (do not move `v0.4.0`).

## Runtime (verified)

```
QT_QPA_PLATFORM=offscreen
/usr/bin/qlcplus-qml -w
```

**Do not `--open` or POST `/loadProject`.** Both block WebAccess on this 5.2.2 QML + offscreen image (2D view spin; `:9999` dies or never binds). Repo workspace `qlc/projects/light-console-test.qxw` is the future show file (no WiZ/PKNight/Launchpad/Art-Net); **not loaded**.

| Check | Result |
|-------|--------|
| `qlcplus.service` | active, `NRestarts=0`, ExecStart `-w` |
| QLC+ | **5.2.2** |
| HTTP `http://127.0.0.1:9999/` | **200**, title QLC+ |
| `ws://127.0.0.1:9999/qlcplusWS` | connected |
| `light-console.service` | active, `NRestarts=0` (pid 6137 through reconnect) |
| Crash loop / traceback | none |

## Verified WebSocket messages (live 5.2.2, empty project)

| Direction | Message | Observed |
|-----------|---------|----------|
| send | `QLC+API\|isProjectLoaded` | on connect |
| recv | `QLC+API\|isProjectLoaded\|false` | no workspace |
| send | `GM_VALUE\|<0-255>` | set Grand Master |
| — | `GM_VALUE\|204` | master 80% |
| — | `GM_VALUE\|216` | master 85% after offline E1 |
| — | `GM_VALUE\|229` | master 90% online |

`int(master * 255 / 100)`: 80→204, 85→216, 90→229.

## Reconnect (no Light Console restart)

A. OUTPUT / status `qlc=CONNECTED`  
B. `systemctl stop qlcplus` only → LC stays **active**, same pid, `qlc=OFFLINE`, UI still accepts PLAY E1 (80→85)  
C. `systemctl start qlcplus` → auto `QLC connected`, `GM_VALUE|216 master=85%`, `qlc=CONNECTED`

Internal `qlc_state` may be `error` while the engine is down; OLED word is **OFFLINE**.

## MASTER path

GPIO / PLAY E1 → `EncoderEvent` → shared Parameter `master` (PLAY and PARAMS) → `QlcBinding` → `GM_VALUE`. Pi proof used `SIGUSR1` → same `EncoderEvent(E1, +5)` because the running UI holds the encoder GPIOs. Physical knob is the operator check.

Offline change is kept in AppState; reconnect sends current master once.

## Services / packages on Shield (this milestone)

- `qml6-module-qtquick-controls`, `layouts`, `dialogs`, `qt6-svg-plugins` (keep; no `apt autoremove`)
- Units independent: neither `Requires=` the other
- sudoers unchanged (halt-only NOPASSWD)

## Forbidden (held)

No production Pi, WiZ/WIZ-LIGHTS, PKNight, Launchpad, production `.qxw`, reboot, shutdown.
