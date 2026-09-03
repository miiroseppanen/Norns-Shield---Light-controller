# Production Pi parity audit (read-only)

Date: 2026-09-04  
Host: `valot@192.168.88.248` (`valot`)  
Method: SSH BatchMode, no sudo, no writes, no signals, no package/network changes.

## Side by side

| | PRODUCTION | SHIELD (before 0.8 install) |
|--|------------|-----------------------------|
| Hostname | valot | shieldxl-light |
| QLC | 5.2.2 | 5.2.2 |
| `qlcplus-qml` sha256 | `3ca3ee64b81c6096eec6d754cdb54099cd20b0a21c412d6eba3d552c8f06ed7f` | **identical** |
| Qt | 6.8.2 | 6.8.2 |
| ExecStart | `/usr/bin/qlcplus-qml -w -o /home/valot/siirtyma-startup.qxw` | `/usr/bin/qlcplus-qml -w` |
| QT_QPA_PLATFORM | offscreen | offscreen |
| HOME | /home/valot | /home/light |
| cwd | / | /home/light/light-console |
| ExecStartPre | `/bin/sleep 10` | none (repo has midi_wait, not installed) |
| After | network-online, sound | local-fs |
| Restart | always / 5s | on-failure / 3s |
| Workspace | `/home/valot/siirtyma-startup.qxw` (111648 B) | none loaded |
| QSettings recent0 | that workspace | absent |
| isProjectLoaded | **false** (CLI load) | false (empty) |
| Functions | 100, including `startup` id 0 Chaser | 0 |
| WebAccess | :9999 HTTP 200 | :9999 HTTP 200 |
| Art-Net | U0 → 127.0.0.1, U1 → 192.168.88.201 | none |
| MIDI | Launchpad Mini MIDI 1 Line 1, no UID in XML | not in live engine |
| Helper | `qlc-startup-chaser.service` + `start_qlc_chaser.py` | none |
| WiZ | wizbridge.service, wlan1 WIZ-LIGHTS | wlan1 present, DOWN, no AP |
| Second Wi-Fi | wlan1 | **wlan1 present** (Realtek 0bda:c811) |

## Autoload mechanism

QLC+ 5.2.2 QML: `-o/--open` is a **valueless** flag. Filename is positional `[file]`. Production argv is therefore WebAccess **plus** a startup workspace.

WebAccess binds **after** workspace/Virtual Console init. On production that was ~4 minutes on the 2026-09-03 boot. Shield 20s `-9` / positional trials were aborted during `Refresh 2D view`.

Do **not** use `-9` or POST `/loadProject`. Copy production: `-w -o /home/light/shows/master.qxw` and wait.

## Startup helper

`/home/valot/start_qlc_chaser.py`: ws `127.0.0.1:9999/qlcplusWS`, `getFunctionsList`, exactly one name `startup`, type Chaser, `VC_PAGE|1`, `setFunctionStatus|<id>|1`, confirm Running. 60 attempts.

## Workspace IO (production file, not copied live)

Universe 0: Launchpad Mini MIDI 1 Line 1, Art-Net `outputIP=127.0.0.1`  
Universe 1: Art-Net `outputIP=192.168.88.201`  
VC labels contain `192.168.88.248` ssh hints (not IO).

Shield-safe copy patches MIDI UID `1-1.2:0`, both Art-Net outputs to loopback, caption IPs to `HOST`.
