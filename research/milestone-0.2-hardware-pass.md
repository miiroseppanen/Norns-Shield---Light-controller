# Milestone 0.2 — COMPLETE

Date: 2026-09-01. Operator accepted combined, reboot, and cold boot.

| Item | Result |
|------|--------|
| K1/K2/K3 | PASS — GPIO 22/26/13, active-low, idle HIGH |
| E1/E2/E3 | PASS — 4/27, 12/25, 24/23; overlay names match physical; schematic E2/E3 swapped |
| OLED SSD1322 | PASS — userspace SPI, 128 bytes/row, remap `0x04,0x11` |
| Combined | PASS — keys + encoders + OLED, no pin conflict |
| Soft reboot | PASS — `SPI_PERSIST_OK`, `BOOT_CHECK PASS`, OLED + combined |
| Cold boot | PASS — `shutdown -h now`, power cycle, SSH, combined |

SPI persist: `dtparam=spi=on` in `/boot/firmware/config.txt`.

**Stop. QLC not started.**
