# 0.6B — Localhost Art-Net proof

Date: 2026-09-02  
Host: `shieldxl-light`  
Software: QLC+ 5.2.2 `qlcplus.service` `-w` (no `--open`)  
Light Console pid **6137** throughout (not restarted)

No packets to PKNight, AIR2DMX, production Pi, WIZ-LIGHTS, or LIGHT-CONTROL broadcast.

## Workspace (git source of truth)

`qlc/projects/light-console-test.qxw`

| Field | Value |
|-------|--------|
| Universe name | WiZ-test |
| `.qxw` ID | 0 |
| QLC UI | Universe 1 |
| Output plugin | ArtNet |
| UID / interface | **127.0.0.1** (line 0 on `/config`) |
| `outputIP` | **127.0.0.1** |
| `outputUni` | **0** (wire Art-Net universe / Port-Address 0) |
| Fixture | Generic Smoke, mode Amount, 1 channel, address 0 (DMX 1) |

**Not loaded at runtime** (`--open` still blocks web). Tests fail the file if `192.168.88.201/246/248/255` or `10.42.` appear.

## QLC UI universe → Art-Net wire

QLC+ 5 default: UI universe **N** → Art-Net universe **N−1**.  
UI Universe 1 (XML ID 0) → **outputUni 0** → Port-Address **0** (net 0, subnet 0, universe 0).

`/config` Art-Net lines on this Shield:

| Line | Label |
|------|--------|
| `ArtNet\|0` | 127.0.0.1 — **SAFE_LOOPBACK** |
| `ArtNet\|1` | 192.168.88.246 — **REAL_OUTPUT** (refused by `QlcWebSocketClient.patch_output`) |

Runtime patch (documented 5.2.2 `/config` / `configuration.js`):

```
QLC+IO|OUTPUT|0|ArtNet|0
```

Channel source without a loaded project: Simple Desk **`CH\|<abs>\|<0-255>`** (QLC+ 5 web API). Absolute address 1 = UI Universe 1 / DMX 1. Light Console does **not** emit UDP; it uses the same WebSocket client.

MASTER / `GM_VALUE` did **not** change this Simple Desk slot on the empty engine (HTP desk held 255). MASTER remains GM for the UI. Channel proof uses `CH|1|…`.

## Captured ArtDMX (summarized)

Destination observed: **127.0.0.1:6454**. Sources: loopback only. `wlan0:6454` receive count **0**.

| `CH\|1\|` | ArtDMX slot 1 | seq | payload len | port-address |
|-----------|---------------|-----|-------------|--------------|
| 0 | 0 | 1 | 512 | 0 |
| 128 | 128 | 2 | 512 | 0 |
| 255 | 255 | 3 | 512 | 0 |
| 0 | 0 | 5 | 512 | 0 |

Unpatched QLC (`-w`, before first `QLC+IO`): **0** ArtDMX in 2 s.

After patch, **Standard** behaviour: a packet on each channel change; while holding a value, ~**0.9–1 Hz** (2 s window: 2 frames). Not a 50 Hz Full stream. Sequence increments. Length 512 (full universe in the datagram even for one used slot).

## Safety

- Monitor binds **127.0.0.1 only**.
- Client refuses `ArtNet|1`.
- `.qxw` loopback-only (CI).
- **Hole:** QLC web `/config` can still select the LAN Art-Net line. Real PKNight TX must not be a QLC patch until a loopback **forwarder** is ARMED (see output-architecture §8).

## Light Console

Pid 6137, NRestarts=0, OUTPUT CONNECTED during the proof. `sudo` ticket expired so `qlcplus` was **not** stopped in this session; 0.5 already proved LC survives QLC stop/start. Unpatched idle = no ArtDMX with QLC still up.

## Dual-controller (not implemented)

ICMP to `.248` only proves the host answers ping. Later: detect **ArtDMX sourced from 192.168.88.248**, plus whether `:9999` is a QLC web. Do not SSH production.

## Next

0.6C — one PKNight unicast, one PAR, arming prototype. Not started.
