# Milestone 0.3 — QLC+ engine bring-up (gated)

Status: **0.3 engine baseline COMPLETE.** 0.3A–0.3D PASS, including cold-boot runtime proof. No wizbridge, WIZ-LIGHTS, Launchpad, production `.qxw`, or systemd autostart.

Engine on `shieldxl-light`: **QLC+ 5.2.2** arm64 — [`qlc/VERSION.md`](../qlc/VERSION.md).

## 0.3A — Distro 4.14.1 headless proof

**PASS.** Replaced in 0.3D.

## 0.3B — Existing QLC+ 5.x Trixie archive

[`research/phase-03b-existing-qlc5-package.md`](../research/phase-03b-existing-qlc5-package.md). Disk image; do **not** flash onto the Shield card.

## 0.3C — 5.2.2 install plan

[`research/phase-03c-qlc522-install-plan.md`](../research/phase-03c-qlc522-install-plan.md). **READY TO INSTALL** — executed in 0.3D.

## 0.3D — 5.2.2 install + runtime proof

[`research/phase-03d-qlc522-install-proof.md`](../research/phase-03d-qlc522-install-proof.md).

**PASS:** package 5.2.2, `qlcplus-qml` headless, web 9999, WebSocket `QLC+API|isProjectLoaded`, Shield combined smoke concurrent. Cold-boot: no autostart; manual `-w` works; hardware still concurrent. **Stop.**
