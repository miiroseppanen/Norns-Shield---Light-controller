# Master workspace

Runtime appliance file: `/home/light/shows/master.qxw`  
Repo production-safe copy: `qlc/projects/siirtyma-shield.qxw`  
Empty merge template (unit tests): `qlc/projects/master.qxw`

## Cold boot

Production Pi pattern, same QLC 5.2.2 binary:

```
/usr/bin/qlcplus-qml -w -o /home/light/shows/master.qxw
```

`-o/--open` is a boolean flag. The path is the positional workspace. WebAccess may take **minutes** after Virtual Console refresh. Do not use `-9` or POST `/loadProject`.

Interactive SHOWS switching copies a named `.qxw` onto `master.qxw` and restarts QLC. Do not POST `/loadProject`.

```
SOURCE production .qxw
     |
     v
 Shield patch (MIDI UID, Art-Net loopback, caption IPs)
     |
     v
 /home/light/shows/master.qxw
     |
     v
 qlcplus-qml -w -o <that file>
     |
     v
 startup chaser + Light Console status
```
