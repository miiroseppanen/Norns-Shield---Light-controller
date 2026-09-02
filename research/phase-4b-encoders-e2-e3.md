# Phase 4b — Encoders E2 + E3 proof

Date: 2026-09-01. Host: `light@shieldxl-light.local`.  
Tool: `scripts/test-encoders-e2-e3.py`. Operator, Mac Terminal, foreground SSH.  
No overlay, no `config.txt` change, no reboot.

## Method

Both candidate pairs watched in one run. Software `CW +1` = A leads B. 4 gray steps = 1 detent.

| Label | GPIO A | GPIO B | norns overlay | schematic part |
|-------|--------|--------|---------------|----------------|
| PAIR-A | 12 | 25 | e2 | E3 |
| PAIR-B | 24 | 23 | e3 | E2 |

Operator: physical E2 first (3 CW + 3 CCW), then physical E3 (3 CW + 3 CCW).

## Log

```
PAIR-A CW +1  (×3)
PAIR-A CCW -1 (×3)
PAIR-B CW +1  (×3)
PAIR-B CCW -1 (×3)

PAIR-A GPIO12/25: CW=3 CCW=3 invalid=0 leftover_q=0
PAIR-B GPIO24/23: CW=3 CCW=3 invalid=0 leftover_q=0
```

## Mapping (physical, this Shield XL)

| Physical knob | GPIO A/B | Overlay name | Schematic part |
|---------------|----------|--------------|----------------|
| E1 (earlier) | 4 / 27 | e1 | E1 — match |
| **E2** | **12 / 25** | **e2** | schematic **E3** — swapped vs silkscreen/part |
| **E3** | **24 / 23** | **e3** | schematic **E2** — swapped vs silkscreen/part |

Norns overlay `e2`/`e3` names match **physical** E2/E3.  
Eagle schematic part labels E2/E3 are swapped relative to those knobs.

## Direction (U2)

Physical clockwise produced software `CW +1` (A leads B) on both E2 and E3. No invert.

## PASS

3+3 detents each, `invalid=0`, no chatter, mapping unambiguous.
