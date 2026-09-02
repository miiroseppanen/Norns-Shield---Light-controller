# Installation

**Do not run this against the production lighting Pi or the Norns SD card.**

Hardware bring-up on a **new** microSD is gated: [`milestone-0.2-hardware-bringup.md`](milestone-0.2-hardware-bringup.md). Do not skip PASS/FAIL gates.

Milestone 0.1 is Mac-only:

```bash
cd shieldxl-light-console
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[sim,dev]"
python -m simulator.run
```

## Phase 0 OS flash (Mac, explicit permission)

Identity is discovered each run (`scripts/identify-sd.py`). Do not hardcode a disk number.

```bash
./scripts/flash-raspios-sd.sh --plan    # read-only: target + dd command
./scripts/flash-raspios-sd.sh --write   # only after asserts PASS; no retry on FAIL
```

The write pipeline is `xzcat IMAGE | dd of=/dev/rdiskN bs=4m status=progress` followed by `sync`. Do not add `conv=sync` (on macOS that pads short pipe reads and overwrites the whole card).

## Later (new microSD, explicit permission)

```bash
./scripts/install.sh --check      # inspect only
./scripts/install.sh --install    # app + venv + unit file; no network edits
./scripts/install.sh --configure-network   # print plan; apply only with confirm
```

`--configure-network` is a stub until a network milestone is approved.

Back up any config file the installer would overwrite (`scripts/backup-config.sh`).

## Shield appliance (Milestone 0.4c)

On `shieldxl-light` (not production), already logged in over SSH:

```bash
sudo bash /home/light/light-console/packaging/install-appliance.sh
```

Do not wrap that in another `ssh -t light@shieldxl-light.local …` from the Pi itself.

Installs the shutdown sudoers drop-in and `light-console.service`. QLC+ is a separate unit:

```bash
sudo bash /home/light/light-console/packaging/install-qlc.sh
```

