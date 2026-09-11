"""Operator-facing status words. Editable booleans are only ON/OFF."""

ON = "ON"
OFF = "OFF"
OK = "OK"
RUNNING = "RUNNING"
STARTING = "STARTING"
STOPPING = "STOPPING"
STOPPED = "STOPPED"
ACTIVE = "ACTIVE"
IDLE = "IDLE"
SEEN = "SEEN"
LOST = "LOST"
OFFLINE = "OFFLINE"
FAILED = "FAILED"
DISCONNECTED = "DISCONNECTED"
APPLYING = "APPLYING"
STANDALONE = "STANDALONE"
SWITCHING = "SWITCHING"
NETWORK = "NETWORK"

EDITABLE = frozenset({ON, OFF})
OBSERVED = frozenset(
    {
        OK,
        RUNNING,
        STARTING,
        STOPPING,
        STOPPED,
        ACTIVE,
        IDLE,
        SEEN,
        LOST,
        OFFLINE,
        FAILED,
        DISCONNECTED,
        APPLYING,
        STANDALONE,
        SWITCHING,
        NETWORK,
    }
)
