# Milestone 0.6 — show UI and MIDI binding (Shield)

Date: 2026-09-03  
Host: `shieldxl-light`  
Software: HEAD after MIDI patcher. QLC+ 5.2.2 `qlcplus.service` `/usr/bin/qlcplus-qml -w`  
QLC process kept loaded (PID 1899 during the MIDI inspect). No reboot, no production Pi, no PKNight/WiZ enable from Light Console.

## 1. Live MIDI graph (unchanged; capture only)

USB: `1235:0036` Focusrite-Novation Launchpad Mini (bus 001 device 004).

ALSA card 3 `Launchpad Mini`. Raw MIDI `hw:3,0,0` name **Launchpad Mini MIDI 1**. Sequencer client **28** port **0** (client number is not a stable identity).

```
client 14: Midi Through Port-0  <->  client 128: qlcplus __QLC__  (both directions)
client 28: Launchpad Mini MIDI 1     (no subscription to/from QLC)
```

`light` is in group `audio`. `/dev/snd/midiC3D0` is `root:audio` 0660. This is not a permission miss.

## 2. Which .qxw QLC actually has

Not `current.qxw` (`light-console-test.qxw`, 792 bytes, no MIDI). WebAccess journal:

```
Workspace XML received. Content-Length: "111660" 111450
```

Mac file `/Users/miiroseppanen/Library/CloudStorage/Dropbox/Valot/Showt/siirtyma-startup.qxw` is **111450** bytes. Creator QLC+ 5.2.2. That is the uploaded workspace. WebAccess did not write a copy under `/home/light`.

## 3. XML vs live IO

Universe 0:

```xml
<Input Plugin="MIDI" Name="None" UID="None" Line="0" Profile="Novation Launchpad Mini"/>
<Feedback Plugin="MIDI" Name="None" UID="None" Line="0"/>
<Output Plugin="ArtNet" Name="192.168.88.254" UID="" Line="1">
  <PluginParameters UniverseChannels="42" outputIP="192.168.88.248"/>
</Output>
```

Universe 1 Art-Net `outputIP="192.168.88.201"` Line 1.

QLC 5.2.2 match order (engine `inputoutputmap.cpp`): UID list, then display name, then saved line. Log at load:

```
[IOMAP] !!No match found!! for input on universe 0 uid: "None" name: "None"
[MIDI] Open Input:  0
[MIDI] open output:  0
[sendFeedBack] Dev: "Midi Through Port-0"
```

`/config` after load (GET only):

| Universe 1 | Selected |
|------------|----------|
| Input | `[MIDI] Midi Through Port-0` (`MIDI\|0`) |
| Feedback | `[MIDI] Midi Through Port-0` (`MIDI\|0`) |
| Output | `[ArtNet] 192.168.88.246` (`ArtNet\|1`) |
| Profile | None |

The MIDI plugin listed **only** `MIDI|0` Midi Through. Launchpad Mini was **not** an option. Documented live retarget is `QLC+IO|INPUT|0|MIDI|<line>` / `QLC+IO|FB|0|MIDI|<line>` from `configuration.js`. There is no name-based IO command, and no Launchpad line to select.

## 4. Why Midi Through (two stacked causes)

1. **XML identity is None/None/Line 0.** Profile name is not used for device match. After UID and Name miss, line 0 opens the first MIDI plugin line.
2. **Launchpad was not in the plugin list.** `qlcplus` ActiveEnterTimestamp 09:44:32. Launchpad USB `midiC3D0` birth 09:57:40. Workspace load 09:58:22. The ALSA MIDI plugin had already enumerated at process start (Midi Through only) and did **not** hotplug the pad 13 minutes later.

Cause 1 alone would still bind Midi Through even if the pad were listed, because Line 0 would remain Midi Through. Cause 2 blocks `/config` and `QLC+IO` from selecting the pad until QLC is started with the pad already present.

Not used: guessing a production device name of `Launchpad Mini MIDI 1` from history. That string **is** the Shield ALSA port name (`amidi -l`). The loaded XML does **not** store it.

## 5. Live routing

Not attempted.

- No QLC MIDI line for Launchpad, so `QLC+IO|INPUT|0|MIDI|1` is not a verified device.
- `aconnect` Launchpad → `qlcplus:__QLC__` would inject notes into the loaded VC map. Universes already have Art-Net Line 1 with destinations `.248` and `.201`. Function activation is not a safe MIDI proof.

Linux-side reception (aseqdump on the Launchpad port only, not subscribed to QLC) is the only safe event proof while this project stays loaded.

## 6. Permanent fix

| Preference | Mechanism | Status |
|------------|-----------|--------|
| A | QLC InputOutputMap Name/UID match | Requires pad listed **and** XML that is not `None`/`None`/`0` |
| B | `prepare_for_shield` MIDI rewrite | Implemented: Name=`Launchpad Mini MIDI 1`, UID empty, Profile preserved. Art-Net Name/UID/Line/outputIP already forced to loopback |
| C | Startup order helper | Documented, not installed: `qlcplus.service` after USB MIDI; do not hardcode client 28 |

Do not adopt `aconnect` as architecture.

## 7. Show vs machine XML

See [`docs/show-projects.md`](../docs/show-projects.md).
