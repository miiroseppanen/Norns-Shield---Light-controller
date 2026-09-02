# Phase 8 — Cold boot persistence

Date: 2026-09-01.

`sudo shutdown -h now` completed (SSH closed). Operator power-cycled (~10 s off).

A follow-up line accidentally concatenated shutdown with `verify-boot.py` (`shutdown: virheellinen valitsin -- "u"`). That command is ignored.

After power-on, SSH worked. `test-combined.py` ran: OLED init, K1/K2/K3 PRESS+RELEASE, E1/E2/E3 both directions. Operator: looks working.

**Phase 8 PASS** (combined after cold boot; SPI/GPIO implied by OLED+controls).
