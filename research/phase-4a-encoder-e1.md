# Phase 4a — Encoder E1 proof

Date: 2026-09-01. Host: `light@shieldxl-light.local`.  
Tool: `scripts/test-encoder-e1.py` (`/home/light/test-encoder-e1.py`).  
Operator ran it in the Mac Terminal (foreground SSH). No overlay, no `config.txt` change, no reboot.

## Method

libgpiod 2.x character device. Chip `/dev/gpiochip0` (`pinctrl-bcm2711`).  
E1 schematic: **A=GPIO4**, **B=GPIO27**. Inputs, `Bias.AS_IS`, 2 ms debounce.  
Software `CW +1` = A leads B. Four gray steps = one detent.

## Result (operator)

Operator accepted **E1 PASS**:

- Physical E1 is GPIO4 / GPIO27 (research mapping confirmed).
- Events in both directions; 3 detents identifiable; no bounce problem.
- Direction confirmed on hardware (software A-leads-B vs physical CW recorded by operator).

E2/E3 not tested in this phase.
