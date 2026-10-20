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

Import writes Name and UID from `config/machine-profile.yaml` (not ALSA client numbers):

```xml
<Input Plugin="MIDI" Name="Launchpad Mini MIDI 1" UID="1-1.2:0" Line="1" Profile="Novation Launchpad Mini"/>
<Feedback Plugin="MIDI" Name="Launchpad Mini MIDI 1" UID="1-1.2:0" Line="1"/>
```

UID + Name are the identity QLC matches. `Line` is fallback only and may not stay `1` if QLC re-enumerates.

Only bindings intended for this Launchpad are rewritten (`Profile="Novation Launchpad Mini"`, or Feedback `Name="None"` next to that Input). Other MIDI devices are left alone.

`qlcplus.service` runs `python3 -m light_console.midi_wait` for up to 12s before `qlcplus-qml -w`. If the pad is still missing it starts QLC anyway. Late plug-in still needs `sudo systemctl restart qlcplus` (password required). There is no USB-triggered automatic restart.

## Loaded production example (do not copy)

`siirtyma-startup.qxw` (111450 bytes, WebAccess upload 2026-09-03) stored:

```xml
<Input Plugin="MIDI" Name="None" UID="None" Line="0" Profile="Novation Launchpad Mini"/>
<Feedback Plugin="MIDI" Name="None" UID="None" Line="0"/>
```

That is why a project with Launchpad VC mappings still opened Midi Through. The Shield image has profiles `Novation Launchpad` and `Novation Launchpad Mini MK3`, not `Novation Launchpad Mini`. VC widgets still carry numeric `Channel` values; the missing profile name does not remove those mappings.

Art-Net in the same file is machine routing (`outputIP` production Pi / PKNight) and is rewritten to `127.0.0.1` Line 0 on import. Do not load the unpatched source as the live engine if real outputs must stay off.

`prepare_for_shield` scans the **entire** workspace string for forbidden addresses. Virtual Console label captions that contain `192.168.88.248` still reject import after IO rewrite. That is separate from MIDI patching.

## WebAccess project load protocol (5.2.2)

The browser **Load project** button is not a WebSocket API and does not open a server path.

Verified from `/usr/share/qlcplus/web/webaccess-v5.html` + `webaccess-v5.js` and QLC `webaccessbase.cpp`:

1. Hidden form `POST /loadProject` `enctype=multipart/form-data`
2. File input `name="qlcprj"` `accept=".qxw"`
3. Button click → file picker → native form submit
4. QLC `extractMultipartFilePayload()` takes the first MIME part as workspace XML
5. HTTP 200 HTML `Loading project...` which polls `QLC+API|isProjectLoaded` then navigates to `/`

## Why `/loadProject` is not used

QLC+ 5.2.2 WebAccess **Load project** is `POST /loadProject` with multipart field `qlcprj` carrying the `.qxw` **bytes**. That is the real browser protocol.

On this appliance (`qlcplus-qml -w`, `QT_QPA_PLATFORM=offscreen`) that ingest is **unsafe for Light Console**:

- workspace XML is accepted
- offscreen QML then runs Virtual Console / `Refresh 2D view`
- HTTP `:9999` and `/qlcplusWS` stop serving

Light Console must not call `/loadProject`. There is no retry around it.

## Startup autoload (`-9` / `--openlast`)

QSettings file `/home/light/.config/qlcplus/Q Light Controller Plus.conf` had **no** `workspace/recent*` keys under a normal `-w` run.

One bounded trial (2026-09-03): wrote `[workspace] recent0=/home/light/shows/show-a.qxw`, stopped `qlcplus.service`, launched `/usr/bin/qlcplus-qml -w -9` offscreen for 20s. `show-a.qxw` is loopback-only (2057 bytes). The process stayed up, ingested Art-Net `127.0.0.1` / Generic Smoke, logged `Refresh 2D view...`, and **never bound `:9999`**. Trial PID was SIGTERM'd. systemd was restored to `qlcplus-qml -w` only. `-9` was not added to the unit.

QLC 5.2.2 `main.cpp` loads the workspace **before** starting WebAccess. `-9` is the same `loadWorkspace()` class as a positional file. Startup autoload is **UNSUPPORTED** here.

## Architecture (Milestone 0.8)

**SHOWS:** OLED lists named `.qxw` files in `/home/light/shows`. Confirm copies the file onto `master.qxw` (prepare_for_shield + live U2) and bounces `qlcplus.service`. Still no `/loadProject` and no `-9`.

**Current appliance:** Shield-safe copy of production `siirtyma-startup.qxw` as `/home/light/shows/master.qxw`. QLC starts `-w -o` that file. See [`docs/production-parity.md`](production-parity.md) and [`docs/boot-sequence.md`](boot-sequence.md).

```
SOURCE .qxw
     |
     v
 IMPORT / PATCH  (MIDI + loopback Art-Net)
     |
     v
 MASTER QLC WORKSPACE
     |
     v
 QLC ENGINE  (qlcplus-qml -w -o master.qxw)
     |
     v
 startup helper + Light Console status
```
