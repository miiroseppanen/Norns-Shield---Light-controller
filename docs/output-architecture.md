# Lighting output architecture (Milestone 0.6A)

**Research and design only.** No real outputs, no WIZ-LIGHTS, no production Pi, no AIR2DMX changes. Inventory evidence: [`research/phase-06a-output-inventory.md`](../research/phase-06a-output-inventory.md).

Baseline: `v0.5.0`. Light Console ↔ QLC+ 5.2.2 is physically verified. QLC remains the show engine. Light Console must not grow a second DMX/WiZ transmit path.

## 1. Current hardware topology

```
                    LIGHT-CONTROL  (192.168.88.0/24, router .1)
         ┌──────────────────┼──────────────────────┐
         │                  │                      │
   Shield .246          prod Pi .248           PKNight .201
   wlan0 STA            (do not touch)         Art-Net → DMX
   QLC 5.2.2 -w         QLC + wizbridge
   no Art-Net listen    WIZ-LIGHTS AP 10.42.0.1
                        Art-Net U0 → 127.0.0.1:6454
                        Art-Net U1 → PKNight

Wired universe (today): 4× PAR 8ch @ 1/9/17/25, fog @ 33
WiZ universe (today): 9× 6ch @ 1,7,13,…,49
AIR2DMX: spare / mobile (config frozen in 0.6A)
```

Desired end state: **production Pi OFF + Shield ON = full rig.** That is **B**, not A. A is only a temporary DMX-only step while Shield has a single Wi-Fi radio.

## 2. Shield network capability

| Fact | Implication |
|------|-------------|
| One onboard Wi-Fi (`wlan0` / `brcmfmac`), STA on LIGHT-CONTROL | Cannot add a second SSID without another radio **or** giving up LIGHT-CONTROL on that radio |
| No USB Wi-Fi | Second concurrent **Wi-Fi** network: **HARDWARE REQUIRED** |
| `eth0` present, no carrier | Copper LIGHT-CONTROL + `wlan0` as WIZ-LIGHTS AP is possible **later** without USB Wi-Fi |
| NM 1.52.1, AP property yes | AP is possible; **STA+AP concurrent on one phy is unproven** — do not enable in 0.6A |
| `iw` not installed | Interface combinations not listed |

Do not create WIZ-LIGHTS until 0.6D and a chosen dual-network path exists.

## 3. QLC output capability

`libartnet.so` is installed. Plugin parameters: `outputIP`, `outputUni`, `transmitMode`. Multiple universes and loopback are supported (QLC+ 5 Art-Net docs). Current process does **not** bind UDP 6454 (empty `-w`, no IO patch).

**Never** patch QLC GPIO/SPI plugins onto Shield XL pins (OLED + encoders).

Headless `--open` still breaks web on this image. 0.6B must keep web/WS working (localhost Art-Net proof without re-breaking 0.5).

## 4. WiZ architecture recommendation

**Do not** drive lamps from Light Console UDP. **Do not** require the production Pi for the finished Shield.

| Option | Verdict |
|--------|---------|
| **A** Shield on LIGHT-CONTROL only; WiZ stays on production WIZ-LIGHTS | Acceptable **interim** for DMX-only. **Not** standalone. |
| **B** Shield owns WIZ-LIGHTS (second iface or eth0+AP) + local WiZ service | **Target.** Matches “Pi off, show on.” |
| **C** Light Console → WiZ directly | **Reject.** Couples UI to lamp IPs/UDP; duplicates the engine; breaks “UI crash must not stop the show.” |

**Implementation (B):** a **project-owned** systemd service (`services/wiz/`), not a verbatim drop-in of production `wiz_artnet_bridge.py`, and not vendored from the wiz-bridge repo until explicitly imported.

Responsibilities of that service:

- Listen Art-Net **unicast 127.0.0.1:6454**, universe **0** only.
- Map DMX 6-channel slots → `setPilot` / `getPilot` on **10.42.0.0/24**.
- Status (online count, RSSI if known) via a **local** API or file that Light Console **polls** — OLED fusion, not transmit.
- Static lamp table in **deploy config** (IPs/MACs not committed as production secrets).
- Internet **not** required. No automatic AP restart.
- Independent of Light Console. If the UI dies, QLC + WiZ service keep last look.

Reuse production ideas (Art-Net in, UDP out, expected-count WAIT). Rewrite for this repo: tests, bounded reconnect, no LIGHT-CONTROL dependency.

## 5. PKNight / AIR2DMX recommendation

**PKNight (`192.168.88.201`) is the primary wired DMX node** on LIGHT-CONTROL. Unicast Art-Net universe **1**. ICMP failed this inspect; treat reachability as a **status** input (`DMX NODE`), not a reason to skip the design.

**AIR2DMX is the alternate / mobile node**, not a second transmitter on the same fixtures. Same four PARs + fog must not be fed by two nodes.

| Mode | Rule |
|------|------|
| House / rehearsal | PKNight only |
| AIR2DMX in use | PKNight **off** (or its Art-Net output disabled); QLC destination IP swapped to the AIR2DMX address **after** arming |
| Both powered | **Forbidden** on the same Art-Net universe / same DMX chain |

Do not put both on separate Art-Net universes unless they drive **disjoint** fixtures (they do not, today). Duplicate DMX = fighting dimmers.

Universe numbering: see §6. Keep QLC UI labels (`WiZ`, `DMX`) so operators are not looking at “Universe 1 vs Art-Net 0.”

## 6. Canonical universe / address map

Three number spaces. Write all three in every patch note.

| QLC UI | `.qxw` `Universe ID` | Art-Net Net/Sub/Uni (default 0/0/n) | Purpose | Destination (armed) | DMX |
|--------|----------------------|--------------------------------------|---------|---------------------|-----|
| Universe 1 “WiZ” | 0 | 0/0/**0** | WiZ lamps | **127.0.0.1:6454** → WiZ service | 1–54 (9×6ch) |
| Universe 2 “DMX” | 1 | 0/0/**1** | Wired PAR + fog | **unicast 192.168.88.201** (PKNight) | 1–32 PARs, 33 fog |

QLC default: UI universe N → Art-Net universe N−1. Set `outputUni` explicitly so a future UI reordering cannot swap WiZ and DMX.

**Disarmed / 0.6B:** both outputs **127.0.0.1** (or plugin unpatched). Never broadcast `192.168.88.255` while the production Pi may also be sending.

WiZ channel order (unchanged): Dimmer, Red, Green, Blue, White, CCT.

Wired (8ch PAR assumed until a fixture-mode proof): PAR1 1–8, PAR2 9–16, PAR3 17–24, PAR4 25–32, fog 33.

## 7. Output arming / safety

Propose OLED **OUTPUT → OUTPUTS: DISARMED | ARMED** (not implemented in 0.6A).

| Boot | **DISARMED.** QLC may run. Art-Net must not leave the box (loopback only, or plugin closed). |
| Arm | Allowed only if: LIGHT-CONTROL ok (for DMX), **production Pi `.248` not answering** (or operator confirms override), PKNight XOR AIR2DMX, WIZ-LIGHTS up if WiZ is in the show. |
| Disarm | Stop forwarding / close Art-Net outputs immediately. QLC and UI stay up. MASTER still local. |
| Blackout | **QLC Grand Master only** (already 0.5). No Light Console UDP/DMX sidecar that can stick lamps after a UI crash. |
| QLC reconnect | Re-push intended GM (0.5). Do **not** auto-arm. Do not replay a blast of full-on looks until armed. |

Automatic resume of **ARMED** after reboot is **rejected** while two controllers can exist. After production Pi is decommissioned, a later milestone may add “resume last arm” with a long-press confirm.

## 8. Dual-controller conflict prevention

If Shield and production Pi are both on, they can both send Art-Net U1 to PKNight and/or both talk to WiZ.

**Design (do not implement yet):**

1. Default **DISARMED**; QLC Art-Net bound to **loopback**.
2. Before arm: probe `192.168.88.248`. If up → OLED `DUAL CTRL` / refuse arm (override is an explicit SYSTEM confirm, not a boot default).
3. Unicast only; no Art-Net broadcast on LIGHT-CONTROL.
4. WIZ-LIGHTS SSID: only one AP. Shield must not start the AP if production already hosts it (SSID scan is a later, careful check — not 0.6A).
5. Operational rule: **one brain.** Document on SYSTEM: “prod Pi must be off.”
6. Optional later: distinct Art-Net source name / shortName so a packet capture shows who is transmitting.

There is no safe automatic “preempt production.” Isolation is **arming + detection + unicast + one AP**.

ICMP ping to `.248` is **not** enough: the Pi can be up with QLC/wizbridge stopped, or down while another sender uses the same Art-Net universe. Later interlock should combine: host up, **UDP 6454 ArtDMX sourced from `.248`**, optional HTTP `:9999` (QLC web). Do not SSH the production Pi to decide.

**QLC can bypass Light Console:** the web `/config` page can still select `[ArtNet] 192.168.88.246`. Do not treat LC `patch_output` as a hard gate. Real-output enforcement should be: QLC patched **only** to loopback, plus a project-owned forwarder that is the only process allowed to send to PKNight when ARMED.

## 9. Startup / shutdown (target)

```
                    DISARMED
                         │
  NetworkManager wlan0 (LIGHT-CONTROL)     [already]
  optional: eth0 or wlan1 / WIZ-LIGHTS AP  [0.6D]
                         │
              qlcplus.service  (-w / future workspace)
              light-console.service     (independent)
              wiz.service               (loopback Art-Net in; no TX if disarmed)
                         │
              operator ARMS
                         │
              Art-Net U1 → PKNight XOR AIR2DMX
              Art-Net U0 → local WiZ service → lamps
```

Shutdown: disarm (or halt). Do not stop QLC because the UI exits. Do not restart WIZ-LIGHTS because `WiZ 0/n`.

Independence: Light Console down → show continues. QLC down → looks freeze (engine). WiZ service down → WiZ freeze, DMX continues. PKNight down → DMX freeze, WiZ continues. LIGHT-CONTROL down → DMX/Art-Net to PKNight fails; WiZ can continue if WIZ-LIGHTS is local. WIZ-LIGHTS down → WiZ fails; DMX continues.

Cold boot with lamps already on: WiZ WAIT (existing). Do not bounce AP. Production Pi accidentally on: refuse arm.

## 10. Repository layout (future)

| Path | Role |
|------|------|
| `docs/output-architecture.md` | This file |
| `research/phase-06a-output-inventory.md` | Measured facts |
| `qlc/projects/light-console-test.qxw` | Safe workspace (loopback only until arming) |
| `qlc/projects/` later show file | Still **not** production `siirtyma-startup.qxw` |
| `config/light-console.example.yaml` | Example IPs/counts; no secrets |
| `config/network/` (later) | NM connection *templates*, not live keys |
| `packaging/systemd/` | `qlcplus`, `light-console`, later `wiz` |
| `services/wiz/` | WiZ Art-Net listener (new code, tests) |
| `light_console/status/` | Pollers only (already) |
| **Not in git** | WIZ-LIGHTS PSK, lamp inventory with site MACs, AIR2DMX passwords |

Light Console still talks to QLC over WebSocket. It does not import `services/wiz` packet code.

## Failure modes (summary)

| Failure | Show |
|---------|------|
| QLC down | All looks freeze. UI OFFLINE. No auto `systemctl restart qlcplus`. |
| Light Console down | QLC + outputs continue. |
| LIGHT-CONTROL down | PKNight unreachable. Local WiZ OK if AP is on Shield. |
| WIZ-LIGHTS down | WiZ WAIT/0. DMX OK. No AP restart loop. |
| WiZ service down | WiZ freeze. DMX OK. |
| PKNight down | DMX NODE --. WiZ OK. |
| AIR2DMX down | Only matters if it was the armed destination. |
| One WiZ lamp | Count `n−1`; others continue. |
| Shield reboot | Boot DISARMED; lamps hold last WiZ/DMX until a controller arms. |
| Both Pis on | Refuse arm; operator power-off production. |

## Staged implementation (do not start until instructed)

| Stage | Proof | Still forbidden |
|-------|--------|-----------------|
| **0.6B** | **PASS 2026-09-02.** Art-Net loopback via `QLC+IO\|OUTPUT\|0\|ArtNet\|0` (web `/config` protocol). `--open` still not used. | Any `.201` / broadcast / lamps |
| **0.6C** | Unicast Art-Net U1 → **one** PKNight universe; **one** PAR at low intensity; arming prototype | WiZ, AIR2DMX, broadcast, prod Pi as engine |
| **0.6D** | Dual network: USB `wlan1` **or** eth0 + `wlan0` AP; SSID WIZ-LIGHTS **without** lamps if possible | Automatic AP restart; tearing down LIGHT-CONTROL accidentally |
| **0.6E** | WiZ service + **one** lamp on universe 0; expected-count WAIT | Full 9-lamp blast; LC→UDP |
| **0.6F** | Remaining WiZ + PARs + fog; PARAMS/PLAY still QLC | Dual node DMX |
| **0.6G** | Production Pi **off**; cold boot; DISARMED then ARM; full rig | Shipping dual-controller |

0.6B workaround: keep systemd `ExecStart=-w`. Intended IO lives in `qlc/projects/light-console-test.qxw` (loopback only). Runtime patch uses documented `QLC+IO|OUTPUT|0|ArtNet|0` (QLC 5.2.2 `/config` page). Never `ArtNet|1` (192.168.88.246). See [`research/phase-06b-local-artnet-proof.md`](../research/phase-06b-local-artnet-proof.md).
