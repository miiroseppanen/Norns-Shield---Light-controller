# 0.6A — Output inventory (research)

Date: 2026-09-02  
Host: `shieldxl-light` (`192.168.88.246`)  
Baseline: `v0.5.0` = `7518219`  
Mode: **read-only**. No WIZ-LIGHTS, no Art-Net TX to fixtures, no AIR2DMX/production-Pi changes, no LC/QLC restart.

Canonical design: [`docs/output-architecture.md`](../docs/output-architecture.md).

## 1. Current hardware topology (as operated today)

```
LIGHT-CONTROL  (MikroTik 192.168.88.1)
 ├── shieldxl-light     192.168.88.246   wlan0 STA  (this repo)
 ├── production Pi      192.168.88.248   (DO NOT TOUCH)
 └── PKNight            192.168.88.201   Art-Net → DMX   (ICMP unanswered this inspect)

Production Pi (separate radio):
  SSID WIZ-LIGHTS  10.42.0.0/24  Pi = 10.42.0.1
  QLC → Art-Net U0 → 127.0.0.1:6454 → wiz_artnet_bridge.py → UDP 38899 lamps

Wired DMX (today via PKNight):
  4× Oloaxolx 60W PAR (8ch) + Eurolite N-150 MK2 fog (1ch)

AIR2DMX: present as spare/mobile Art-Net node. Configuration not inspected or changed.
```

## 2. Shield network inventory (non-destructive)

| Item | Observed 2026-09-02 22:46 EEST |
|------|-------------------------------|
| Hostname | `shieldxl-light` |
| `lo` | 127.0.0.1/8 UP |
| `wlan0` | UP, `192.168.88.246/24`, STA on **LIGHT-CONTROL**, NM connection `netplan-wlan0-LIGHT-CONTROL`, DHCP, gw `192.168.88.1`, metric 600 |
| `eth0` | UP at L2 admin, **NO-CARRIER**, no IPv4 (cable unplugged) |
| USB | Pi 4 hubs only (`1d6b` root, `2109:3431` VIA). **No USB Wi-Fi NIC** |
| Other `wlan*` | none (`p2p-dev-wlan0` disconnected) |
| NetworkManager | **1.52.1**, state `connected` / `full` |
| Wi-Fi radio | enabled; NM `WIFI-PROPERTIES.AP: yes` (2.4 + 5 GHz) |
| PHY | onboard SDIO `brcmfmac` / `brcm,bcm4329-fmac` (`phy0`) |
| `iw` | **not installed** — interface-combination (STA+AP) not proven |
| UDP 6454 | **not listening** |
| QLC / LC | both `active` (untouched) |
| ICMP 192.168.88.248 | ok |
| ICMP 192.168.88.201 | **fail** (node off, ICMP filtered, or absent) |

LIGHT-CONTROL was not disconnected. No scan, no AP, no netplan write.

### Second Wi-Fi

**Not available with current hardware** as a second radio: one Broadcom STA, no USB adapter.

NM advertises AP capability on `wlan0`, but running **WIZ-LIGHTS AP and LIGHT-CONTROL STA at once on the same phy is unproven** (`iw` missing; brcmfmac concurrent AP+STA is historically fragile). **Not to be enabled in 0.6A.**

Dual-network options *without* a second Wi-Fi radio:

- Plug **eth0** into the MikroTik; keep LIGHT-CONTROL on copper; use `wlan0` as WIZ-LIGHTS AP later.
- Or add a **USB 2.4 GHz adapter** (`wlan1`) matching the production pattern (wlan0 STA + wlan1 AP).

Report line: **HARDWARE REQUIRED** for a second simultaneous Wi-Fi network; ethernet is an alternative path, not a second Wi-Fi.

## 3. QLC+ 5.2.2 output capability

Binary `/usr/bin/qlcplus-qml` 5.2.2. Plugins:

`/usr/lib/aarch64-linux-gnu/qt6/plugins/qlcplus/libartnet.so` (present, strings `outputIP` `outputUni` `transmitMode`).

Also present (do **not** patch for show I/O on this Shield): `libspi.so` (`/dev/spidev0.0` — OLED), `libgpio.so` (K/E pins). Empty/`-w` workspace does not open SPI/GPIO lines (0.3C).

Other: loopback, E1.31, OSC, MIDI, USB DMX, UART, OLA, …

**Art-Net (QLC+ 5 docs, not live-TX tested):**

- Native plugin, UDP **6454**.
- Multiple interfaces including **127.0.0.1**.
- Multiple universes per interface.
- Default: QLC UI universe **N** → Art-Net universe **N−1** (UI 1 → wire 0).
- Unicast vs broadcast via `outputIP`; same-host traffic **must** use loopback, not the box’s own LAN IP.
- Settings that differ from defaults are stored in the **`.qxw`**.

Repo `qlc/projects/light-console-test.qxw` has `<Universe Name="Universe 1" ID="0"/>` and **no** Output patches. Runtime 0.5 is **`-w` only** (no `--open`). **No Art-Net listener** during this inspect → **QLC ARTNET capability PASS, live TX not done.**

`.qxw` shape (QLC workspace XML; do not put production destinations in git until arming exists):

```xml
<Universe Name="WiZ" ID="0">
  <Output Plugin="ArtNet" UID="127.0.0.1" Line="0">
    <PluginParameters outputIP="127.0.0.1" outputUni="0"/>
  </Output>
</Universe>
<Universe Name="DMX" ID="1">
  <Output Plugin="ArtNet" UID="127.0.0.1" Line="0">
    <PluginParameters outputIP="127.0.0.1" outputUni="1"/>
  </Output>
</Universe>
```

`--open` still **blocks web** on this 5.2.2 QML/offscreen image (0.5). Output work in 0.6B must not silently reintroduce `--open` without a working headless-web path.

## 4. WiZ (docs only — no production SSH)

Production chain: QLC Art-Net **universe 0** → `127.0.0.1:6454` → `wiz_artnet_bridge.py` → WIZ-LIGHTS → lamps UDP **38899** (`setPilot` / `getPilot`).

Slots (operator, 6 ch: Dimmer, R, G, B, White, CCT):

| Lamp | DMX |
|------|-----|
| WiZ1–9 | 1–6, 7–12, 13–18, 19–24, 25–30, 31–36, 37–42, 43–48, 49–54 |

Repo `config/light-console.example.yaml` still has `wiz.expected: 6`. Treat **9** as the production map; reconcile in a later config milestone (do not change YAML in 0.6A).

Cold boot (existing `docs/networking.md`): lamps may associate before AP; WAIT is normal; **no automatic AP restart**.

## 5. What was not done

No Art-Net/DMX/WiZ packets to fixtures. No AIR2DMX config. No production Pi. No NetworkManager writes. No service restarts.
