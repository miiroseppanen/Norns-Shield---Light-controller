# Show projects

QLC+ workspaces (`.qxw`) mix **show content** with **machine IO**. The Shield import path (`scripts/upload-show.sh` → `prepare_for_shield`) copies the show and rewrites machine fields. It never writes the operator's source file.

## Show-specific vs machine-specific

Verified against QLC+ 5.2.2 workspace XML (`InputOutputMap`, `Fixture`, `Function`, Virtual Console `Input` children).

### Show-specific (preserve on import)

| XML | Role |
|-----|------|
| `<Fixture>` | Fixtures, modes, addresses |
| `<Function>` | Scenes, chasers, and other functions |
| Virtual Console widgets and layout | Buttons, sliders, frames |
| VC widget `<Input Universe="…" Channel="…">` | Which QLC input channel fires the widget |
| Universe `Input` `Profile="…"` | Input profile **name** used when the IO editor mapped the pad |
| Function contents / chaser steps | Look |

### Machine-specific (patch on Shield import)

| XML | Role |
|-----|------|
| `<Input Plugin="MIDI" Name UID Line>` | MIDI input device identity |
| `<Feedback Plugin="MIDI" Name UID Line>` | MIDI LED/feedback device identity |
| `<Output Plugin="ArtNet" Name UID Line>` plus `PluginParameters outputIP` | Art-Net interface and destination |
| Other output plugins / IPs | Universe/plugin routing |
| `<NetworkServer Name="QLC+_…">` | Host-derived network id |

Do **not** treat ALSA client numbers (e.g. 28) as identity. They change across boots.

## QLC+ 5.2.2 MIDI device resolution

On workspace load, `InputOutputMap::setInputPatch` / `setOutputPatch` resolve a device in this order:

1. **UID** — `plugin->inputsUID()` / `outputsUID()` (5.2.2 stable MIDI UIDs; Linux uses a USB path when the plugin can read one)
2. **Name** — exact match against the plugin's current display names (`plugin->inputs()` / `outputs()`)
3. **Line** — the numeric `Line="N"` saved in XML, used only when UID and Name both miss

If UID/Name miss, QLC logs `[IOMAP] !!No match found!!` and **still opens `Line`**. `Line="0"` on this Shield is **Midi Through Port-0**, because the MIDI plugin lists that kernel port first.

`None` is a stored string, not “unset”. `UID="None"` and `Name="None"` are non-empty, fail both matches, and fall through to line 0.

WebAccess `/config` uses the documented messages:

```
QLC+IO|INPUT|<universe>|<Plugin>|<line>
QLC+IO|FB|<universe>|<Plugin>|<line>
QLC+IO|OUTPUT|<universe>|<Plugin>|<line>
```

There is no WebSocket command that selects a MIDI device **by name**. Line indexes are whatever the plugin enumerated in this process.

## Shield MIDI binding

Import writes:

```xml
<Input Plugin="MIDI" Name="Launchpad Mini MIDI 1" UID="" … Profile="(unchanged)"/>
<Feedback Plugin="MIDI" Name="Launchpad Mini MIDI 1" UID="" …/>
```

Empty UID skips step 1 so resolution uses the ALSA **port name**. `Line` is left alone as a last-resort fallback; it is not a client number.

This is not enough if the MIDI plugin never listed the Launchpad. The 5.2.2 ALSA plugin snapshots devices at **qlcplus process start** and does not rescan USB hotplug. `qlcplus.service` must start **after** the pad is already on USB, or `/config` will only offer `MIDI|0` = Midi Through Port-0.

## Loaded production example (do not copy)

`siirtyma-startup.qxw` (111450 bytes, WebAccess upload 2026-09-03) stored:

```xml
<Input Plugin="MIDI" Name="None" UID="None" Line="0" Profile="Novation Launchpad Mini"/>
<Feedback Plugin="MIDI" Name="None" UID="None" Line="0"/>
```

That is why a project with Launchpad VC mappings still opened Midi Through. The Shield image has profiles `Novation Launchpad` and `Novation Launchpad Mini MK3`, not `Novation Launchpad Mini`. VC widgets still carry numeric `Channel` values; the missing profile name does not remove those mappings.

Art-Net in the same file is machine routing (`outputIP` production Pi / PKNight) and is rewritten to `127.0.0.1` Line 0 on import. Do not load the unpatched source as the live engine if real outputs must stay off.

`prepare_for_shield` scans the **entire** workspace string for forbidden addresses. Virtual Console label captions that contain `192.168.88.248` still reject import after IO rewrite. That is separate from MIDI patching.
