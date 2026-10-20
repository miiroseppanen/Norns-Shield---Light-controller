# Show UI

OLED **SHOWS** lists named `.qxw` files in `/home/light/shows`. QLC still launches `-o /home/light/shows/master.qxw`. Choosing a file copies it onto `master.qxw` (Shield patch + live U2 preserved) and bounces `qlcplus.service` with start/stop. Light Console does not POST `/loadProject` or use `-9`.

```
SHOWS
* HALLOWEEN UV
  WARM
```

E1 moves the cursor. `*` is the file last opened into QLC. K3 opens:

```
SHOW
HALLOWEEN UV
LOAD
```

K3 confirms and restarts QLC. Already-open files show `OPEN` and do not bounce the engine. K2 back. While QLC is stopping/starting the status is `APPLYING`; failure is `FAILED`.

SCENES / CHASERS stay deferred. PLAY GO still requires live QLC id+name match.

See [`docs/show-projects.md`](show-projects.md) for why `/loadProject` is unused.
