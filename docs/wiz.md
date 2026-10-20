# WiZ

wizbridge remains a **separate** program (see the wiz-bridge repository). This repo does not modify production wizbridge in 0.1.

## Role

QLC+ Art-Net universe 0 → wizbridge → WiZ local UDP (`setPilot` / `getPilot`).

## OLED

`WiZ {online}/{expected}` from status fusion, not from “we sent Art-Net”.

Diagnostics page: per-fixture OK / `--` and RSSI when known.

WIZ → INFO: lamps join the AP slowly after boot and then show in DEVICES. If a lamp is still missing after 10 minutes, power-cycle it. K2 back.

## Cold boot

See `docs/networking.md`. Show `WAIT` while AP is up but lamps have not joined. No automatic network restart.

## Expected count

`config` `wiz.expected` (default 6). UI must not hardcode six lamps.
