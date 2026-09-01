# Installation

**Do not run this against the production lighting Pi or the Norns SD card.**

Milestone 0.1 is Mac-only:

```bash
cd shieldxl-light-console
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[sim,dev]"
python -m simulator.run
```

## Later (new microSD, explicit permission)

```bash
./scripts/install.sh --check      # inspect only
./scripts/install.sh --install    # app + venv + unit file; no network edits
./scripts/install.sh --configure-network   # print plan; apply only with confirm
```

`--configure-network` is a stub until a network milestone is approved.

Back up any config file the installer would overwrite (`scripts/backup-config.sh`).
