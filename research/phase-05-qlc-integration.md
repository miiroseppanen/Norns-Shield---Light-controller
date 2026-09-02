# Milestone 0.5 — QLC+ integration (PAUSED — sudo)

Date: 2026-09-02 (resume + pause)  
Target: `light@shieldxl-light.local`  
Checkpoint before this resume: `dfc5dc43d0401c493a2b8899a9f87d8d663aef15`  
Baseline: `v0.4.0` = `d443537`

Shield is reachable. **sudo ticket expired** (`sudo -n` → password required). Operator cannot enter sudo now. No `qlcplus.service` start, no Light Console restart, no stray `qlcplus-qml`.

## 0.5 COMPLETE (local)

- Client, OUTPUT, MASTER binding, fake transport, test workspace (unchanged).
- **`qlcplus.service` ExecStart is now `-w` only** (no `--open`). Proven necessary: `--open` never binds `:9999`.
- `install-qlc.sh` still copies that unit (needs root).
- `/tmp/light-console.status` snapshot (`screen`, `master`, `qlc`).
- SIGUSR1 on the running UI: PLAY + E1 +5 (same `EncoderEvent` as the knob; GPIO lines are exclusive). **Do not SIGUSR1 the pre-restart process** (old binary has no handler; default is terminate).
- Local tests: **74 PASS**.

## 0.5 PARTIALLY COMPLETE

- Repo + `~/light-console` on Shield have the `-w` unit file.
- **`/etc/systemd/system/qlcplus.service` still has `--open`** (last root install). Unit enabled, **inactive**.
- `light-console.service`: **active**, pid **1821**, **NRestarts=0** (old process; not restarted after this rsync).
- Live `-w` HTTP/WS/`GM_VALUE` from the morning pause still stands; not re-proven this evening.

## 0.5 NOT DONE

- daemon-reload / start `qlcplus.service` with `-w`
- HTTP :9999 as a **service**
- Reconnect A–C without LC restart
- Physical E1 MASTER + offline resync on Shield
- Commit `Milestone 0.5: integrate QLC engine` / tag

## Shield last known (2026-09-02 21:57 EEST)

| Item | State |
|------|--------|
| Reachable | yes |
| `light-console.service` | active, NRestarts=0, pid 1821 |
| `qlcplus.service` | inactive/stopped, enabled, **ExecStart still `--open` in /etc** |
| `:9999` | not listening |
| `qlcplus-qml` process | none |
| QLC+ | 5.2.2 `/usr/bin/qlcplus-qml` |
| sudo | **password required** |

Home copy: `grep ExecStart ~/light-console/packaging/systemd/qlcplus.service` → `ExecStart=/usr/bin/qlcplus-qml -w`

## Exact next step

On a terminal that can type the `light` sudo password:

```bash
ssh light@shieldxl-light.local 'sudo bash /home/light/light-console/packaging/install-qlc.sh && sudo systemctl restart light-console.service'
```

Then continue 0.5: prove service HTTP/WS, reconnect A–C **without** another LC restart, MASTER (E1 / status / `GM_VALUE`), docs, commit `Milestone 0.5: integrate QLC engine`. **Do not tag.**

Until LC is restarted, **do not `kill -USR1` pid 1821**.

## Forbidden (unchanged)

No production Pi, no WiZ/WIZ-LIGHTS, no PKNight, no Launchpad, no production `.qxw`, no `--open` start, no reboot/shutdown.
