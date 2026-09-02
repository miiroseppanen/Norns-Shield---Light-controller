# Phase 6 — Combined keys + encoders + OLED

Date: 2026-09-01. Host: `light@shieldxl-light.local`.  
Tool: `scripts/test-combined.py`. Operator, Mac Terminal, foreground SSH.  
No QLC, no audio, no WIZ-LIGHTS.

## Result (operator: “kaikki toimii”)

Same boot: SSD1322 userspace (`spidev0.0`, remap `0x04,0x11`) plus libgpiod inputs.

| Control | Log |
|---------|-----|
| K1 | PRESS+RELEASE at t+5.6s and again t+19.7s / t+63.9s |
| K2 | PRESS+RELEASE t+7.6s, t+20.3s, t+62.1s |
| K3 | PRESS+RELEASE t+8.7s, t+21.2s, t+62.7s |
| E3 | CW and CCW from t+10s; more at t+60s |
| E2 | CW and CCW from t+13s; more at t+61s |
| E1 | CW and CCW from t+16s; more at t+64s |

Run lasted >1 minute. OLED kept updating (`LIGHT CONSOLE` + last event + encoder nets). No SPI/GPIO conflict with buttons or encoders.

## Phase 6 PASS
