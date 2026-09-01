# QLC+ integration

Show engine: **QLC+ headless**. light-console is a WebSocket client.

## Endpoint (current lighting system)

```
ws://127.0.0.1:9999/qlcplusWS
```

QLC+ must be started with `-w`. light-console does not spawn or restart QLC+.

## Documented commands (QLC+ 5 web API)

Source: https://docs.qlcplus.org/v5/advanced/web-interface/web-api

Messages are `field|field|…` text.

| Need | API |
|------|-----|
| Connect | WebSocket to `/qlcplusWS` |
| Project loaded | `QLC+API\|isProjectLoaded` |
| List functions | `QLC+API\|getFunctionsList` → `id\|name\|…` |
| Type | `QLC+API\|getFunctionType\|<id>` |
| Status | `QLC+API\|getFunctionStatus\|<id>` → Running / Stopped |
| Start/stop | `QLC+API\|setFunctionStatus\|<id>\|<0\|1>` |
| Unsolicited | `FUNCTION\|<id>\|Running` / `Stopped` |
| Widgets | `getWidgetsList`, `getWidgetStatus`, `<widgetId>\|<value>` |
| Cue GO | `<cueListWidgetId>\|NEXT` |
| Grand master | `GM_VALUE\|<0-255>` |
| Keepalive | `POLL` (ignored by QLC) |

### Not assumed

- A first-class “set chaser BPM” command. Use a Speed Dial / slider widget if the show file exposes one. Mark unreliable until tested on QLC+ **5.2.x** on the Pi.
- Automatic project load. `/loadProject` exists but must not be fired from a reconnect loop.

## Disconnect policy

1. OLED: `QLC LOST`
2. Background reconnect with backoff
3. **Never** restart the QLC systemd unit from light-console

## Show layout (do not copy production `.qxw` in 0.1)

| QLC universe | Art-Net | Destination |
|--------------|---------|-------------|
| 0 | universe 0 → 127.0.0.1:6454 | wizbridge |
| 1 | universe 1 | PKNight → DMX |

WiZ fixture map (6 channels each): dimmer, R, G, B, white, CCT. Slot *n* uses DMX `(n-1)*6+1` … `n*6`. Expected lamp count is YAML `wiz.expected`.

0.1: `MockQLCClient` only.
