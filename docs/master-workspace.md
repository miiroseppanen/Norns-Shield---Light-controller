# Master workspace

**SUPERSEDED:** treating each imported `.qxw` as a QLC engine swap (`current.qxw`, `/loadProject`, `-9`, positional file). Those paths do not leave WebAccess usable on this offscreen 5.2.2 appliance.

## Canonical file

Repo template: `qlc/projects/master.qxw`  
Runtime path: `/home/light/shows/master.qxw`

Master owns **machine I/O only** until content is merged in:

- Art-Net `127.0.0.1` Line 0
- Launchpad Mini MIDI 1 / UID `1-1.2:0`
- `CurrentWindow="FunctionManager"`
- empty Virtual Console

Imported shows contribute fixtures and Scene/Chaser functions. They do **not** own Art-Net destinations, PKNight, WiZ routing, or Launchpad patches.

```
SOURCE .qxw
     |
     v
 IMPORT / MERGE  (ID remap, dry-run first)
     |
     +---- logical show metadata (.yaml)
     |
     v
 MASTER QLC WORKSPACE
     |
     v
 QLC ENGINE  (must already contain master; see cold boot)
     |
     v
 Light Console runtime control
```

## Cold boot

`qlcplus.service` remains `/usr/bin/qlcplus-qml -w` with **no** workspace path, **no** `-9`, **no** `/loadProject`.

**MASTER COLD-BOOT AUTOLOAD: UNRESOLVED.** QLC+ 5.2.2 headless WebAccess cannot start with a loaded workspace on this image. Do not claim the architecture complete until that is solved by a real QLC/runtime change (not a rejected load experiment).
