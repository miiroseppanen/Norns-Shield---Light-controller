# Show UI

OLED **SHOWS** lists logical shows (metadata), not `.qxw` files to load.

```
SHOWS
> SHOW A
  SHOW B
```

E1 moves the cursor. K3 activates that logical show. QLC is not restarted and no workspace is loaded. The confirmation screen is:

```
SHOW
SHOW A
ACTIVE
```

SCENES / CHASERS / PLAY E2–E3 then list only that show's functions. PLAY GO still requires live QLC id+name match. If the master workspace is not loaded in QLC, GO is `NO PROJECT`.

The multi-workspace `current.qxw` / `LOAD SHOW?` / `AUTO LOAD NYI` model is **SUPERSEDED**. See [`docs/master-workspace.md`](master-workspace.md).
