# Phase 3 — K1/K2/K3 button proof

Date: 2026-09-01. Host: `light@shieldxl-light.local`.  
Tool: `scripts/test-buttons.py` on the Pi as `/home/light/test-buttons.py`.  
Operator ran it in the Mac Terminal (foreground SSH). No overlay, no `config.txt` change, no reboot.

## Method

Linux GPIO character device (`python3-libgpiod` 2.2, already on the image).  
Chip: `/dev/gpiochip0` (`pinctrl-bcm2711`). Inputs only, `Bias.AS_IS`, 10 ms kernel debounce. No outputs, no pull-down enable.

| Label | BCM GPIO | Idle | Active |
|-------|----------|------|--------|
| K1 | 22 | HIGH | LOW (press) |
| K2 | 26 | HIGH | LOW (press) |
| K3 | 13 | HIGH | LOW (press) |

## Operator log

```
IDLE K1 gpio=22 HIGH
IDLE K2 gpio=26 HIGH
IDLE K3 gpio=13 HIGH
K1 PRESS  gpio=22  t+7.875s
K1 RELEASE  gpio=22  t+8.123s
K2 PRESS  gpio=26  t+9.719s
K2 RELEASE  gpio=26  t+9.903s
K3 PRESS  gpio=13  t+11.183s
K3 RELEASE  gpio=13  t+11.371s
```

Summary from the tool:

```
press order: K1 K2 K3
K1 GPIO22: 1 PRESS / 1 RELEASE  PASS
K2 GPIO26: 1 PRESS / 1 RELEASE  PASS
K3 GPIO13: 1 PRESS / 1 RELEASE  PASS
```

## Findings

- Schematic labels K1/K2/K3 match physical buttons pressed in that order.
- Active-low confirmed. Idle HIGH matches Phase 1 and shield 10 kΩ pull-ups.
- One PRESS + one RELEASE per key. No chatter.
- No GPIO/kernel errors. Ctrl-C released the lines.

## Phase 3 PASS

Operator accepted. Next gated step is E1 only (GPIO4 / GPIO27). Not E2/E3, not OLED.
