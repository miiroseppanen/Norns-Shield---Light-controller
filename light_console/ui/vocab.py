"""Operator-facing status words. Editable booleans are only ON/OFF."""

ON = "ON"
OFF = "OFF"
OK = "OK"
RUNNING = "RUNNING"
STARTING = "STARTING"
STOPPING = "STOPPING"
STOPPED = "STOPPED"
ACTIVE = "ACTIVE"
OPEN = "OPEN"
LOAD = "LOAD"
IDLE = "IDLE"
SEEN = "SEEN"
LOST = "LOST"
NEW = "NEW"
UNKNOWN = "UNKNOWN"
OFFLINE = "OFFLINE"
FAILED = "FAILED"
READY = "READY"
DOWN = "DOWN"
DISCONNECTED = "DISCONNECTED"
APPLYING = "APPLYING"
STANDALONE = "STANDALONE"
SWITCHING = "SWITCHING"
NETWORK = "NETWORK"
SCANNING = "SCANNING"

EDITABLE = frozenset({ON, OFF})
OBSERVED = frozenset(
    {
        OK,
        RUNNING,
        STARTING,
        STOPPING,
        STOPPED,
        ACTIVE,
        OPEN,
        LOAD,
        IDLE,
        SEEN,
        LOST,
        NEW,
        UNKNOWN,
        OFFLINE,
        FAILED,
        READY,
        DOWN,
        DISCONNECTED,
        APPLYING,
        STANDALONE,
        SWITCHING,
        NETWORK,
        SCANNING,
    }
)
