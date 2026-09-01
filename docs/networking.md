# Networking

Status: documented for later milestones. **0.1 does not change any network configuration.**

## Target (future Pi, new SD)

| Interface | Role |
|-----------|------|
| wlan1 | WIZ-LIGHTS AP, 10.42.0.1/24, NetworkManager **shared**, 2.4 GHz channel 6, PMF off |
| wlan0 | Optional upstream (LIGHT-CONTROL, phone hotspot, saved Wi-Fi) |

WiZ show must run with wlan0 down. When upstream exists, NM shared NAT may give WIZ-LIGHTS clients internet. That is optional.

Do **not** add a custom dnsmasq/NAT/dispatcher stack. Start from NetworkManager shared.

`./scripts/install.sh --configure-network` must print a diff and wait for confirmation. It is a stub in 0.1.

## Cold boot (observed on the current lighting Pi — do not “fix” automatically)

When Pi and WiZ lamps get power together:

- Lamps may associate before WIZ-LIGHTS AP is up (~15 s after Pi boot).
- They can sit offline for a long time, then retry and join.
- LIGHT-CONTROL / upstream is **not** required for this.
- Do **not** implement automatic AP restart. A later menu item “Retry WiZ AP” needs explicit approval after testing.

OLED should show `WiZ 0/6 WAIT` then `WiZ 6/6 OK` (counts from config `wiz.expected`, not hardcoded six).

## Status inputs (later)

Combine, do not ping-only: `iw` stations, neighbour, DHCP lease, wizbridge device table, getPilot. One missed keepalive ≠ offline.

## Isolation

Missing wlan0, missing PKNight, or missing Launchpad must not tear down WIZ-LIGHTS.
