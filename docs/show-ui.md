# Show UI

OLED **SHOWS** lists `/home/light/shows/*.qxw`. K3 opens `LOAD SHOW?`. K2 cancels. K3 currently marks the **selected** file only.

## current vs ACTIVE

| Name | Meaning |
|------|---------|
| `current.qxw` | Light Console **intended** show (symlink). Updated when the operator confirms `LOAD SHOW?`. |
| ACTIVE | Independently verified as loaded in the QLC engine (`getFunctionsList` id+name matches that file). |

They are not the same during startup, a load attempt, a failed load, or a QLC restart. GO still requires a live id+name match. Pointing `current.qxw` at a file is not enough to GO.

## Automatic QLC load

**Not implemented.** Milestone 0.6C found the WebAccess browser protocol (HTTP POST `/loadProject`, multipart field `qlcprj`, **file contents**). Programmatic POST of `show-a.qxw` ingested the XML then wedged offscreen QML WebAccess (`VC_PAGE|-1` …). Light Console must not POST `/loadProject` until a workspace is proven to leave HTTP :9999 and the WebSocket usable.

SHOWS still shows:

```
AUTO LOAD NYI
LOAD IN QLC WEB
```

Load a safe imported show in the QLC browser. Do not load production workspaces with real Art-Net destinations.

See [`docs/show-projects.md`](show-projects.md) and [`research/phase-06-show-project-ui.md`](../research/phase-06-show-project-ui.md).
