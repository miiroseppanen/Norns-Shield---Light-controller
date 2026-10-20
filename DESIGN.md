---
name: Shield XL Light Console
description: 128×64 1-bit OLED operator page for a lighting desk in the dark.
colors:
  ink: "#FFFFFF"
  pit: "#000000"
typography:
  display:
    fontFamily: "Shield XL wordmark, ui-monospace, monospace"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: 16
    letterSpacing: "2px"
  label:
    fontFamily: "Shield XL 5×7, ui-monospace, monospace"
    fontSize: "7px"
    fontWeight: 400
    lineHeight: 8
    letterSpacing: "normal"
rounded:
  none: "0px"
  toggle: "7px"
spacing:
  page-w: "128px"
  page-h: "64px"
  row: "8px"
  cell: "6px"
  focus: "2px"
  label-gutter: "4px"
  scroll: "3px"
  activity: "9px"
components:
  page:
    backgroundColor: "{colors.pit}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    width: "{spacing.page-w}"
    height: "{spacing.page-h}"
  status-row:
    backgroundColor: "{colors.pit}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    height: "{spacing.row}"
    padding: "0"
  toggle-on:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.pit}"
    rounded: "{rounded.toggle}"
    size: "7px"
    width: "7px"
    height: "7px"
  toggle-off:
    backgroundColor: "{colors.pit}"
    textColor: "{colors.ink}"
    rounded: "{rounded.toggle}"
    size: "7px"
    width: "7px"
    height: "7px"
  focus-rail:
    backgroundColor: "{colors.ink}"
    width: "{spacing.focus}"
    height: "{spacing.row}"
  activity-scan:
    backgroundColor: "{colors.ink}"
    width: "3px"
    height: "1px"
  warn-mark:
    backgroundColor: "{colors.ink}"
    width: "3px"
    height: "3px"
  empty-state:
    backgroundColor: "{colors.pit}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
  lifecycle-frame:
    backgroundColor: "{colors.pit}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    width: "{spacing.page-w}"
    height: "{spacing.page-h}"
---

# Design System: Shield XL Light Console

## Overview

**Creative North Star: "The Night Desk"**

This is a lighting desk in the dark. The SSD1322 is the only page. The operator’s hands are on K1–K3 and E1–E3; the screen reports. It is an instrument, not an app. Norns grammar tells you how to read the page: PLAY versus MENU, physical control names, one 128×64 frame for every screen.

Density is the point. Eight rows of 8 px, a 5×7 bitmap in 6×8 cells (~21 columns), uppercase labels, no chrome. The Mac window is a scaled copy of that framebuffer, not a second interface.

Confirmed rejections: do not become a dashboard, Material, or a Mac-native layout. Stay 1-bit unless a real hierarchy need appears. Do not invent greys, glows, or a palette because the panel can do 4-bit greyscale.

**Key Characteristics:**
- One physical page: 128×64, every screen
- 1-bit ink on pit black
- Instrument first: keys and encoders are the UI
- Norns reading grammar without being Norns OS
- STATIC CONTROL / STATIC STATUS / MOVEMENT as the only visual verbs

## Colors

Two values. Full-on panel emission versus off. The Mac simulator may tint ink as phosphor; that preview is not a second palette.

### Primary
- **OLED Ink** (`{colors.ink}`): every glyph, rail, filled toggle, scrollbar thumb, warn square, and activity scan. Hardware packing is full-on (`0xFF`). Whatever the SSD1322 emits at full on is this color.

### Neutral
- **Pit** (`{colors.pit}`): the unlit panel. Every frame starts here. Hardware packing is off (`0x00`).

**The 1-Bit Rule.** There is no grey, no glow, no accent. Warn is still ink: a 3×3 square beside the word. If you need a third color, you are off the Night Desk.

**The OLED Ink Rule.** Do not lock a web hex as brand. Simulator `(210, 220, 160)` is a Mac preview of phosphor, not identity.

## Typography

**Display Font:** Shield XL wordmark (custom 13-row geometric caps, 16 px PLAY header band)
**Body Font:** none (body copy does not exist)
**Label/Mono Font:** Shield XL 5×7 bitmap in 6×8 cells

**Character:** All operator type is uppercase, clipped, bitmap. Letters fold to the 5×7 set; unknown glyphs become `?`. This is not a webfont and must not be replaced with Inter, SF, or a display serif.

### Hierarchy
- **Display** (wordmark, 13 px cap, 16 px band): PLAY identity only (`LIGHT CTRL`). Not used as a page title elsewhere.
- **Label** (400, 5×7 / 7 px in an 8 px row): every screen label, value, menu row, lifecycle sentence. Vocab words clip at 12 characters on status rows. Lists clip to the field width; overflow on the focused row may marquee.

**The Vocab Rule.** Editable booleans are only `ON` / `OFF`. Observed words live in `light_console/ui/vocab.py` (`READY`, `FAILED`, `NETWORK`, `STANDALONE`, …). Do not invent sentence case, icons-as-type, or title case marketing lines.

**The Twenty-One Column Rule.** A row is ~21 cells. Prefer a shorter word over a smaller font. Marquee is for the focused field, not decoration.

## Layout

The spatial model is one page frame, defined in `light_console/display/layout.py`:

- Canvas: 128×64
- Row: 8 px; 8 rows total
- Header: 8 px (PLAY uses a 16 px wordmark band instead)
- Content: 7 rows from y=8, except PLAY live rows from y=16
- Focus gutter: 2 px left rail
- Label origin: x=4
- Right reserved: 3 px scrollbar; 9 px activity slot on live status rows

No breakpoints. No fluid grid. The Mac simulator scales integer pixels (`scale` 6) and may draw a development grid; that grid is not part of the product page.

**The One Page Rule.** Every screen is this frame. Do not add a sidebar, tab bar, modal, or a second resolution.

## Elevation & Depth

Flat-by-default. No shadows. Depth is focus and location only: a 2 px left rail on the focused row, and a 3 px dotted-track scrollbar whose thumb is “where I am,” not chrome. Invert is banned; it would flip filled/outline toggles into lies.

**The No Invert Rule.** Never invert a row or the page to show selection.

## Shapes

No rounded rectangles. The only disks are 7×7 bitmap toggles: filled circle = enabled choice, outline = disabled choice. Warn is a 3×3 ink square. The focus rail is a 2×8 bar. The activity mark is a 1 px-high, 3 px-wide scan. Scrollbar track is dotted 1 px, thumb filled.

**The Circle Means Choice Rule.** Disks are for operator-chosen toggles only. Status is a word, not a LED.

## Components

Doctrine: **STATIC CONTROL = what I chose. STATIC STATUS = what the system is. MOVEMENT = what is happening now.** Circles, rails, and the scan are the vocabulary; nothing else.

### Page header
- **Shape:** 8 px title row, 1 px rule under the row
- **Type:** label, clipped to 20 characters
- **PLAY exception:** wordmark band instead of a text header

### Status row
- **Shape:** 8 px row; label left, vocab word right-aligned
- **Warn:** 3×3 ink square left of the word for `FAILED`, `LOST`, `OFFLINE`, `AP FAILED`, `BRIDGE FAILED`
- **Motion:** optional 9 px activity slot; a 3 px scan at 0.16 s/frame, wrap, never reverse. Idle draws nothing.
- **Focus:** 2 px rail when the row is a focus target

### Toggles
- **Shape:** 7×7 circle at x=4
- **On:** filled (chosen / NETWORK filled, etc.)
- **Off:** outline
- **Label:** uppercase, to the right of a 4 px gap
- **Observed subordinate:** second line under the setting, not a focus target

### Lists
- **Shape:** same 8 px rows, rail + scrollbar, no invert
- **Empty:** centered `NO DEVICES` (or the page’s empty word) on content row 3
- **Marquee:** focused row only

### Wordmark
- **Shape:** custom 1-bit `LIGHT CTRL` in the top 16 px of PLAY
- **Tracking:** letter gap 2 px, word gap 8 px, `CT` pair kern −1

### Lifecycle frame
- **Shape:** full pit, one centered label (`STARTING UP` / `SHUTTING DOWN`), nothing else

### Navigation (physical)
- **K1:** PLAY ↔ MENU from any menu depth
- **MENU:** E1 select, K3 enter, K2 back; E2/E3 do not move the cursor
- **PLAY:** E1/E2/E3 are live parameters; no pointer, no hover

### Activity scan
- **When:** live signal progressing now (nonzero cached DMX for PLAY OUTPUT)
- **When not:** configured, armed, or “node reachable”
- **Idle:** omit. Do not draw a parked dash.

## Do's and Don'ts

### Do:
- **Do** design every screen as 128×64 with 8 px rows and the 5×7 label face.
- **Do** use OLED Ink on Pit only; warn with a 3×3 square plus a vocab word.
- **Do** show choice as filled/outline 7 px circles and selection as a 2 px rail.
- **Do** reserve movement for “happening now”; keep control and status static.
- **Do** keep the Mac window a scaled copy of the same framebuffer.

### Don't:
- **Don't** introduce a web/dashboard/Material layout or a second Mac UI.
- **Don't** add greys, glows, drop shadows, or a 4-bit ramp “because the panel can.”
- **Don't** invert rows to show focus.
- **Don't** use sentence-case body copy, webfonts, or icons-as-navigation.
- **Don't** treat activity/ACTIVE as reachability of AIR2DMX or LIGHT-CONTROL.
