# QLC+ version

CURRENT:

- QLC+ **5.2.2** arm64
- `/usr/bin/qlcplus-qml`
- `QT_QPA_PLATFORM=offscreen`
- Web **9999**
- WebSocket `/qlcplusWS`

Host: `shieldxl-light`. systemd: `qlcplus.service` (`-w --open` test workspace).

QML modules required for `--open` without SEGV:

- `qml6-module-qtquick-controls`
- `qml6-module-qtquick-layouts`
- `qml6-module-qtquick-dialogs`

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/qlcplus-qml -w
```

Proof: [`research/phase-03d-qlc522-install-proof.md`](../research/phase-03d-qlc522-install-proof.md).
