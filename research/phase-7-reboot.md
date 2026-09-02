# Phase 7 — Soft reboot persistence

Date: 2026-09-01. `sudo reboot` after `dtparam=spi=on` confirmed in config.txt (`SPI_PERSIST_OK`).

After SSH returned:

```
BOOT_CHECK PASS
/dev/spidev0.0: YES
dtparam=spi=on YES
GPIO K1–K3, E1–E3, OLED DC/RESET unused
```

OLED `test-oled.py` drew `LIGHT CONSOLE` / `OLED PASS` (remap `0x04,0x11`).

Combined: K1/K2/K3 PRESS+RELEASE, E1/E2/E3 CW and CCW. Ctrl-C summary held=False.

**Phase 7 PASS.**
