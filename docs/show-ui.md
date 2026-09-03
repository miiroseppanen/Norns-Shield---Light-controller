# Show UI

OLED **SHOWS** lists `/home/light/shows/*.qxw`. K3 opens `LOAD SHOW?`. K2 cancels. K3 currently marks the **selected** file only.

## current vs ACTIVE

| Name | Meaning |
|------|---------|
| `current.qxw` | Light Console **intended** show (symlink). Updated when the operator confirms `LOAD SHOW?`. |
| ACTIVE | Independently verified as loaded in the QLC engine (`getFunctionsList` id+name matches that file). |

They are not the same during startup, a load attempt, a failed load, or a QLC restart. GO still requires a live id+name match. Pointing `current.qxw` at a file is not enough to GO.

## Automatic QLC load

**Unsupported** on this offscreen 5.2.2 appliance. `/loadProject` and `-w -9` (`--openlast` via QSettings `workspace/recent0`) both ingest `show-a.qxw` then fail to serve HTTP/WebSocket (`Refresh 2D view`). Do not add `-9` to `qlcplus.service`.

**Recommendation: one master QLC workspace**, loaded once, left running. SHOWS should later filter function groups inside that file rather than swapping `.qxw` at runtime.

SHOWS still shows:

```
AUTO LOAD NYI
LOAD IN QLC WEB
```

Load a safe imported show in the QLC browser. Do not load production workspaces with real Art-Net destinations.

See [`docs/show-projects.md`](show-projects.md) and [`research/phase-06-show-project-ui.md`](../research/phase-06-show-project-ui.md).
