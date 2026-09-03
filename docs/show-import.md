# Show import

Merge Mac `.qxw` **content** into the Shield master workspace. Never write the source file. Never load or restart QLC.

```
./scripts/import-show.sh --name "SHOW A" --dry-run "/path/to/show-a.qxw"
```

Dry-run prints `SOURCE -> MASTER` fixture and function maps. `--apply` writes `master.qxw` and `<id>.yaml` next to the master (tests / explicit local apply only).

## What is imported

Allowed: `<Fixture>`, Function `Type="Scene"`, Function `Type="Chaser"`.

Rejected: non-empty Virtual Console, Collection/EFX/RGBMatrix/Sequence/Script/Audio/Video/Show functions, malformed XML, forbidden Art-Net leftovers after Shield patch.

Chaser `<Step>` text IDs and Scene `<FixtureVal ID>` are rewritten to the new master IDs. Scenes allocate from 100, chasers from 200, skipping IDs already in master. Fixture IDs allocate from 0.

## What master keeps

The master's `InputOutputMap` is copied through unchanged (then Shield-patched): Launchpad identity and loopback Art-Net. Source MIDI/Art-Net blocks are discarded.

## Logical show metadata

Each apply writes e.g. `show-a.yaml`:

```yaml
id: show-a
name: SHOW A
source: show-a.qxw
scenes:
  - id: 100
    name: Warm
chasers:
  - id: 200
    name: Slow Pulse
```

Runtime GO still requires live QLC id+name match. Names alone are not enough.
