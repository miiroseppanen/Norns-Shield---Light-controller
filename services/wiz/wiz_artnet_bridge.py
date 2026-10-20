#!/usr/bin/env python3
import fcntl, json, os, socket, struct, sys, tempfile, threading, time
from pathlib import Path

_ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0,_ROOT)
try:
    from light_console.fixture_roles import transform_wiz_channels as _transform_wiz_channels
    from light_console.output.live_path import live_controls_cached as _live_controls_cached
    _LIVE_COLOR=True
except Exception as _live_err:
    _LIVE_COLOR=False
    _transform_wiz_channels=None
    _live_controls_cached=None
    print(f"[WARN] live color unavailable: {_live_err!r}",flush=True)

try:
    from light_console.wiz.device_map import (
        WizDeviceMap,
        WizMapCorruptError,
        WizMapError,
        WizMapValidationError,
        load_map,
        load_map_or_last_good,
        CHANNELS_PER_FIXTURE,
        START_CHANNEL,
        DMX_MAX,
        WIZ_MAX_SLOTS,
        dmx_index0,
    )
    _HAS_MAP=True
except Exception as _map_err:
    _HAS_MAP=False
    WizDeviceMap=None
    WizMapCorruptError=WizMapError=WizMapValidationError=Exception
    load_map=load_map_or_last_good=None
    CHANNELS_PER_FIXTURE=6
    START_CHANNEL=1
    DMX_MAX=512
    WIZ_MAX_SLOTS=DMX_MAX//CHANNELS_PER_FIXTURE
    def dmx_index0(slot):
        return (int(slot)-1)*CHANNELS_PER_FIXTURE
    print(f"[WARN] map model unavailable: {_map_err!r}",flush=True)

ARTNET_UNIVERSE=0
ARTNET_PORT=6454
ARTNET_BIND="127.0.0.1"
WIZ_PORT=38899
# Dedicated WiZ NIC. "" = legacy default-route + limited broadcast 255.255.255.255.
WIZ_INTERFACE="wlan1"
SIOCGIFADDR=0x8915
SIOCGIFBRDADDR=0x8919
SIOCGIFNETMASK=0x891b
WIZ_MAX_HZ=5.0
MIN_SEND_INTERVAL=1.0/WIZ_MAX_HZ
KEEPALIVE_INTERVAL=5.0
IDENTIFY_POLL=0.05
IDENTIFY_PARAMS={"state":True,"temp":4000,"dimming":100}
SETPILOT_KEYS=("state","dimming","r","g","b","c","w","temp","sceneId","speed")
ACK_TIMEOUT=0.80
RETRIES=2
RETRY_DELAY=0.06
DISCOVERY_INTERVAL=30.0
FAST_DISCOVERY_INTERVAL=2.0
DISCOVERY_TIMEOUT=1.5
MIN_TEMP_K=2200
MAX_TEMP_K=6500
OFF_DELAY_MS=120
OFF_POLL=0.25
MAP_RELOAD_INTERVAL=2.0
STATUS_PUBLISH_INTERVAL=1.0
DMX_ACTIVITY_HOLD_S=2.0
DEBUG_DMX=True
PRODUCTION_PI_IP="192.168.88.248"
LIGHT_CONTROL_NET=struct.unpack("!I",socket.inet_aton("192.168.88.0"))[0]
LIGHT_CONTROL_MASK=struct.unpack("!I",socket.inet_aton("255.255.255.0"))[0]
BRIDGE_STOPPED="STOPPED"
BRIDGE_READY="READY"
BRIDGE_FAILED="FAILED"

latest_dmx=bytearray(DMX_MAX)
dmx_lock=threading.Lock()
devices={}
devices_lock=threading.Lock()
fixture_order=[]
fixture_slots={}
fixture_enabled={}
fixture_ips={}
fixtures_path=None
map_path=None
map_source=None
fixtures_lock=threading.Lock()
workers={}
workers_lock=threading.Lock()
wiz_src_ip=None
wiz_broadcast="255.255.255.255"
_loop_stop=threading.Event()
_last_status_pub=0.0
_map_mtime=None
_map_fail_mtime=None
_dmx_levels={}
_dmx_last_change={}
_dmx_act_lock=threading.Lock()
identify_lock=threading.Lock()
_identify_mac=""
_identify_snapshot={}
_identify_last_send=0.0

class WizTxForbidden(Exception):
    """WiZ UDP 38899 is forbidden (WIZ OFF, fail-closed, or forbidden dest)."""


def _status_path():
    return os.environ.get("WIZBRIDGE_STATUS","/tmp/light-console.status")

def _observed_path():
    return os.environ.get("WIZBRIDGE_OBSERVED","/tmp/wizbridge.status")

def parse_wiz_enabled_fail_closed(text):
    """Only explicit wiz=on allows TX. Missing/unknown/malformed => OFF."""
    if not isinstance(text,str):
        return False
    found=False
    value=""
    for raw in text.splitlines():
        if "=" not in raw:
            continue
        key,_,val=raw.partition("=")
        if key.strip()=="wiz":
            found=True
            value=val.strip().lower()
    if not found:
        return False
    return value=="on"

def read_wiz_enabled():
    path=_status_path()
    try:
        with open(path,encoding="utf-8") as f:
            text=f.read()
    except (OSError,UnicodeDecodeError):
        return False
    return parse_wiz_enabled_fail_closed(text)

def wiz_tx_allowed():
    """Canonical WiZ UDP gate. Fail closed. All TX paths must consult this."""
    return read_wiz_enabled()

def parse_identify_mac(text):
    """Fail closed: only a compact 12-hex MAC is an identify target."""
    if not isinstance(text,str):
        return ""
    raw=""
    for line in text.splitlines():
        if "=" not in line:
            continue
        key,_,val=line.partition("=")
        if key.strip()=="identify":
            raw=val.strip()
    if not raw:
        return ""
    mac=normalize_mac(raw)
    if not mac or len(mac)!=12:
        return ""
    try:
        int(mac,16)
    except ValueError:
        return ""
    return mac

def read_identify_mac():
    path=_status_path()
    try:
        with open(path,encoding="utf-8") as f:
            text=f.read()
    except (OSError,UnicodeDecodeError):
        return ""
    return parse_identify_mac(text)

def identify_wanted():
    """Identify target only when WiZ TX is armed. Fail closed otherwise."""
    if not wiz_tx_allowed():
        return ""
    return read_identify_mac()

def _ipv4_in_light_control(ip):
    try:
        packed=struct.unpack("!I",socket.inet_aton(str(ip).strip()))[0]
    except OSError:
        return False
    return packed&LIGHT_CONTROL_MASK==LIGHT_CONTROL_NET

def wiz_dest_allowed(ip):
    if not ip:
        return False
    host=str(ip).strip()
    if host==PRODUCTION_PI_IP:
        return False
    if _ipv4_in_light_control(host):
        return False
    return True

def wiz_sendto(sock,payload,dest):
    """Single chokepoint for WiZ UDP 38899 transmissions."""
    if not wiz_tx_allowed():
        raise WizTxForbidden("wiz off")
    ip=dest[0] if isinstance(dest,(tuple,list)) else dest
    if not wiz_dest_allowed(ip):
        raise WizTxForbidden("forbidden dest")
    return sock.sendto(payload,dest)

def normalize_mac(mac):
    return mac.replace(":","").replace("-","").lower() if mac else None

def fixture_config_paths():
    paths=[]
    env=os.environ.get("WIZBRIDGE_FIXTURES")
    if env:
        paths.append(env)
    paths.append(os.path.join(os.path.expanduser("~"),".config","wizbridge","fixtures.json"))
    paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),"config","fixtures.json"))
    return paths

def map_config_paths():
    paths=[]
    env=os.environ.get("WIZBRIDGE_MAP")
    if env:
        paths.append(env)
    paths.append(os.path.join(os.path.expanduser("~"),".config","wizbridge","map.json"))
    return paths

def dmx_span(index):
    start=START_CHANNEL+index*CHANNELS_PER_FIXTURE
    return start, start+CHANNELS_PER_FIXTURE-1

def parse_fixture_macs(path, data):
    fixtures=data.get("fixtures")
    if not isinstance(fixtures,list):
        raise ValueError(f"No fixtures listed in {path}")
    macs=[]
    ips={}
    seen=set()
    for i,item in enumerate(fixtures):
        ip=None
        if isinstance(item,dict):
            mac=normalize_mac(item.get("mac"))
            slot=item.get("slot")
            raw=item.get("ip")
            if raw:
                ip=str(raw).strip() or None
        else:
            mac=normalize_mac(item)
            slot=None
        if not mac:
            raise ValueError(f"Fixture {i+1} in {path} has no mac")
        if slot is not None and int(slot)!=i+1:
            raise ValueError(f"{path}: list order is slot order; entry {i+1} has slot {slot}")
        if mac in seen:
            raise ValueError(f"Duplicate mac {mac} in {path}")
        seen.add(mac)
        macs.append(mac)
        if ip:
            ips[mac]=ip
    return macs, ips

def apply_configured(macs, slots=None, enabled=None, ips=None):
    """Replace configured identity in-memory. Never compact. Never sort by MAC."""
    global fixture_order
    slot_map={}
    enabled_map={}
    if slots is None:
        for i,mac in enumerate(macs):
            slot_map[mac]=i+1
            enabled_map[mac]=True
    else:
        for mac in macs:
            slot_map[mac]=int(slots[mac])
            enabled_map[mac]=True if not enabled else bool(enabled.get(mac,True))
    with fixtures_lock:
        fixture_order=list(macs)
        fixture_slots.clear()
        fixture_slots.update(slot_map)
        fixture_enabled.clear()
        fixture_enabled.update(enabled_map)
        if ips is None:
            stale=[mac for mac in list(fixture_ips) if mac not in slot_map]
            for mac in stale:
                fixture_ips.pop(mac,None)
        else:
            fixture_ips.clear()
            fixture_ips.update(ips)

def apply_device_map(device_map):
    ordered=sorted(device_map.devices,key=lambda item: item.slot)
    macs=[item.id for item in ordered]
    slots={item.id:item.slot for item in ordered}
    enabled={item.id:item.enabled for item in ordered}
    apply_configured(macs,slots=slots,enabled=enabled)
    return macs

def log_fixture_map(macs, path):
    print(f"Loaded {len(macs)} fixtures from {path}",flush=True)
    for mac in macs:
        slot=fixture_slots.get(mac) or (macs.index(mac)+1)
        start,end=dmx_span(slot-1)
        ip=fixture_ips.get(mac)
        extra=f" last-ip {ip}" if ip else ""
        print(f"  WiZ{slot} {mac} DMX {start}-{end}{extra}",flush=True)

def _load_map_file(path):
    if not _HAS_MAP:
        raise WizMapError("map model unavailable")
    try:
        return load_map(Path(path)), "map"
    except (WizMapCorruptError, WizMapValidationError) as exc:
        try:
            device_map, source=load_map_or_last_good(Path(path))
            print(f"[MAP] {path} invalid; using {source}",flush=True)
            return device_map, source
        except Exception:
            raise exc

def load_legacy_fixtures():
    global fixtures_path, map_path, map_source
    searched=fixture_config_paths()
    for path in searched:
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            data=json.load(f)
        macs,ips=parse_fixture_macs(path, data)
        fixtures_path=path
        map_path=None
        map_source="legacy"
        apply_configured(macs, ips=ips)
        log_fixture_map(macs, path)
        return macs
    fixtures_path=None
    map_path=None
    map_source=None
    apply_configured([])
    print("[MAP] no map.json or fixtures.json; configured list empty",flush=True)
    return []

def load_configured_devices():
    """map.json if valid; else read-only fixtures.json. Never writes."""
    global fixtures_path, map_path, map_source, _map_mtime
    for path in map_config_paths():
        if not os.path.isfile(path):
            continue
        try:
            device_map, source=_load_map_file(path)
        except (WizMapCorruptError, WizMapValidationError, WizMapError, OSError, ValueError) as e:
            print(f"[MAP] invalid {path}: {e}; not writing, not using fixtures overlay",flush=True)
            map_path=path
            fixtures_path=None
            map_source="invalid"
            apply_configured([])
            _map_mtime=None
            return []
        map_path=path
        fixtures_path=None
        map_source=source
        macs=apply_device_map(device_map)
        try:
            _map_mtime=os.path.getmtime(path)
        except OSError:
            _map_mtime=None
        log_fixture_map(macs, path)
        return macs
    return load_legacy_fixtures()

def try_reload_map():
    """Reload validated map. Attach first map.json even if none at start."""
    global _map_mtime, _map_fail_mtime, map_source, map_path, fixtures_path
    path=map_path or fixtures_path
    first_attach=False
    if not path:
        for candidate in map_config_paths():
            if os.path.isfile(candidate):
                path=candidate
                first_attach=True
                break
        else:
            return False
    if not os.path.isfile(path):
        return False
    try:
        mtime=os.path.getmtime(path)
    except OSError:
        return False
    if not first_attach and _map_mtime is not None and mtime==_map_mtime:
        return False
    try:
        if first_attach:
            if not _HAS_MAP:
                return False
            device_map=load_map(Path(path))
            apply_device_map(device_map)
            map_path=path
            fixtures_path=None
            map_source="map"
        elif map_path and _HAS_MAP:
            device_map, source=_load_map_file(path)
            apply_device_map(device_map)
            map_source=source
        else:
            with open(path) as f:
                data=json.load(f)
            macs,ips=parse_fixture_macs(path, data)
            apply_configured(macs, ips=ips)
        _map_mtime=mtime
        _map_fail_mtime=None
        log_fixture_map(list(fixture_order), path)
        return True
    except Exception as e:
        if first_attach:
            print(f"[MAP] first map rejected, keeping empty: {e}",flush=True)
            return False
        if _map_fail_mtime!=mtime:
            print(f"[MAP] reload failed, keeping previous: {e}",flush=True)
            _map_fail_mtime=mtime
        return False

def remember_discovered_ips(found):
    """In-memory last-ip for already-configured MACs only. Never persists."""
    with fixtures_lock:
        known=set(fixture_order)
        for mac,info in found.items():
            ip=(info or {}).get("ip")
            if not mac or not ip or mac not in known:
                continue
            fixture_ips[mac]=ip

def verify_remembered_ip(mac, ip):
    if not wiz_tx_allowed():
        return None
    resp=wiz_exchange(ip,"getPilot",{},timeout=ACK_TIMEOUT)
    if resp is None:
        return None
    result=resp.get("result") or {}
    got=normalize_mac(result.get("mac"))
    if got!=mac:
        return None
    return {"ip":ip,"rssi":result.get("rssi"),"last_seen":time.time()}

def restore_remembered_ips(macs):
    if not wiz_tx_allowed():
        return
    for i,mac in enumerate(macs):
        if not wiz_tx_allowed():
            return
        ip=fixture_ips.get(mac)
        if not ip:
            continue
        slot=fixture_slots.get(mac, i+1)
        info=verify_remembered_ip(mac, ip)
        if info:
            with devices_lock:
                devices[mac]=info
            print(f"[RESTORE] WiZ{slot} {mac} verified at {ip}",flush=True)
        else:
            print(f"[RESTORE MISS] WiZ{slot} remembered {ip}",flush=True)

def apply_discovery(found):
    """Transient observation only. Never enroll, never persist identity."""
    if not found:
        return
    with devices_lock:
        for mac,info in found.items():
            old=devices.get(mac)
            devices[mac]=info
            if old is None:
                print(f"[DISCOVERY] found {mac} at {info['ip']} rssi={info.get('rssi')}",flush=True)
            elif old.get("ip")!=info["ip"]:
                print(f"[DISCOVERY] {mac} IP changed {old.get('ip')} -> {info['ip']}",flush=True)
    remember_discovered_ips(found)
    publish_observed_status(force=True)

def ipv4_for_interface(ifname):
    if not ifname:
        return None, None
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    packed=struct.pack("256s", ifname.encode("ascii","ignore")[:15])
    try:
        src=socket.inet_ntoa(fcntl.ioctl(sock.fileno(),SIOCGIFADDR,packed)[20:24])
        mask=socket.inet_ntoa(fcntl.ioctl(sock.fileno(),SIOCGIFNETMASK,packed)[20:24])
        try:
            bcast=socket.inet_ntoa(fcntl.ioctl(sock.fileno(),SIOCGIFBRDADDR,packed)[20:24])
        except OSError:
            bcast=None
        if not bcast or bcast in ("0.0.0.0","255.255.255.255"):
            src_i=struct.unpack("!I",socket.inet_aton(src))[0]
            mask_i=struct.unpack("!I",socket.inet_aton(mask))[0]
            bcast=socket.inet_ntoa(struct.pack("!I",(src_i&mask_i)|(~mask_i&0xFFFFFFFF)))
        return src, bcast
    except OSError:
        return None, None
    finally:
        sock.close()

def refresh_wiz_network():
    global wiz_src_ip, wiz_broadcast
    if not WIZ_INTERFACE:
        wiz_src_ip=None
        wiz_broadcast="255.255.255.255"
        return False
    src,bcast=ipv4_for_interface(WIZ_INTERFACE)
    wiz_src_ip,wiz_broadcast=src,bcast or "255.255.255.255"
    return src is not None

def open_wiz_socket(timeout, broadcast=False):
    """Bind every WiZ packet to wlan1. Never use the default route (LIGHT-CONTROL)."""
    if not wiz_tx_allowed():
        raise WizTxForbidden("wiz off")
    if WIZ_INTERFACE:
        refresh_wiz_network()
        if not wiz_src_ip:
            raise OSError("WiZ interface %s has no IPv4" % WIZ_INTERFACE)
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.settimeout(timeout)
    if broadcast:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    if wiz_src_ip:
        s.bind((wiz_src_ip,0))
    return s

def dmx_to_temp(v):
    return round(MIN_TEMP_K+(MAX_TEMP_K-MIN_TEMP_K)*(v/255.0))

def level_to_wiz_dimming(level):
    if level<=0: return 0
    return round(10+(level-1)*90/254)

def wiz_exchange(ip, method, params=None, timeout=ACK_TIMEOUT):
    if not wiz_tx_allowed():
        return None
    msg={"method":method,"params":params or {}}
    payload=json.dumps(msg,separators=(",",":")).encode()
    try:
        s=open_wiz_socket(timeout)
    except WizTxForbidden:
        return None
    try:
        wiz_sendto(s,payload,(ip,WIZ_PORT))
        data,addr=s.recvfrom(4096)
        if addr[0]!=ip: return None
        return json.loads(data.decode())
    except WizTxForbidden:
        return None
    except (socket.timeout,OSError,ValueError):
        return None
    finally:
        s.close()

def setpilot_with_retry(ip, params):
    if not wiz_tx_allowed():
        return False
    for attempt in range(RETRIES+1):
        if not wiz_tx_allowed():
            return False
        resp=wiz_exchange(ip,"setPilot",params)
        if resp is not None:
            if attempt:
                print(f"[RETRY OK] {ip} attempt {attempt+1}",flush=True)
            return True
        if attempt<RETRIES:
            print(f"[RETRY] {ip} no reply {attempt+1}/{RETRIES}",flush=True)
            time.sleep(RETRY_DELAY)
    print(f"[WARN] {ip} setPilot failed after {RETRIES+1} attempts",flush=True)
    return False

def discover_wiz():
    if not wiz_tx_allowed():
        return {}
    if WIZ_INTERFACE and not refresh_wiz_network():
        print(f"[DISCOVERY] {WIZ_INTERFACE} has no IPv4; skip",flush=True)
        return {}
    dest=wiz_broadcast
    if not wiz_dest_allowed(dest):
        print(f"[DISCOVERY] dest {dest} forbidden; skip",flush=True)
        return {}
    payload=json.dumps({"method":"getPilot","params":{}},separators=(",",":")).encode()
    try:
        s=open_wiz_socket(DISCOVERY_TIMEOUT,broadcast=True)
    except WizTxForbidden:
        return {}
    found={}
    try:
        wiz_sendto(s,payload,(dest,WIZ_PORT))
        deadline=time.monotonic()+DISCOVERY_TIMEOUT
        while time.monotonic()<deadline:
            if not wiz_tx_allowed():
                break
            try:
                data,addr=s.recvfrom(4096)
            except socket.timeout:
                break
            try:
                result=json.loads(data.decode()).get("result",{})
                mac=normalize_mac(result.get("mac"))
                if mac:
                    found[mac]={"ip":addr[0],"rssi":result.get("rssi"),"last_seen":time.time()}
            except Exception:
                pass
    except WizTxForbidden:
        return found
    except OSError as e:
        print(f"[DISCOVERY] send {dest} failed: {e}",flush=True)
    finally:
        s.close()
    return found

def all_known_found():
    """True when every fixture that has a remembered IP is in devices.

    Fixtures never seen on the AP (no last-ip, e.g. unused WiZ7) must not
    force 2s broadcast discovery forever; that floods UDP 38899 and delays
    unicast replies past ACK_TIMEOUT.
    """
    with fixtures_lock:
        needed=[mac for mac in fixture_order if fixture_ips.get(mac)]
        if not needed:
            needed=list(fixture_order)
    with devices_lock:
        return all(mac in devices for mac in needed)

def note_dmx_activity(now=None):
    """Track Art-Net slot changes. Identical idle frames do not refresh the hold."""
    if now is None:
        now=time.time()
    with fixtures_lock:
        order=list(fixture_order)
        slots=dict(fixture_slots)
        enabled=dict(fixture_enabled)
    with dmx_lock:
        buf=bytes(latest_dmx)
    live=set()
    with _dmx_act_lock:
        for mac in order:
            live.add(mac)
            if not enabled.get(mac, True):
                _dmx_levels.pop(mac, None)
                _dmx_last_change.pop(mac, None)
                continue
            slot=int(slots.get(mac) or 0)
            if slot<1 or slot>WIZ_MAX_SLOTS:
                continue
            base=dmx_index0(slot)
            if base<0 or base+CHANNELS_PER_FIXTURE>DMX_MAX:
                continue
            levels=tuple(buf[base:base+CHANNELS_PER_FIXTURE])
            prev=_dmx_levels.get(mac)
            if prev is None:
                _dmx_levels[mac]=levels
                continue
            if levels!=prev:
                _dmx_levels[mac]=levels
                _dmx_last_change[mac]=now
        for mac in [item for item in _dmx_levels if item not in live]:
            _dmx_levels.pop(mac, None)
            _dmx_last_change.pop(mac, None)

def slot_dmx_fields(mac, now=None):
    if now is None:
        now=time.time()
    with fixtures_lock:
        configured=mac in fixture_slots
        enabled=bool(fixture_enabled.get(mac, True))
    if not configured or not enabled:
        return False, None
    with _dmx_act_lock:
        last=_dmx_last_change.get(mac)
    if last is None:
        return False, None
    return (now-last)<DMX_ACTIVITY_HOLD_S, last

def _availability(info, now):
    if not info:
        return "UNKNOWN"
    last=info.get("last_seen")
    if last and now-last<(KEEPALIVE_INTERVAL*2):
        return "ONLINE"
    return "OFFLINE"

def bridge_runtime_state():
    if not wiz_tx_allowed():
        return BRIDGE_STOPPED
    if WIZ_INTERFACE and not wiz_src_ip:
        return BRIDGE_FAILED
    return BRIDGE_READY

def observed_status_document():
    now=time.time()
    with fixtures_lock:
        order=list(fixture_order)
        slots=dict(fixture_slots)
        known=set(order)
    with devices_lock:
        snapshot=dict(devices)
    rows=[]
    seen=set()
    for mac in order:
        info=snapshot.get(mac)
        seen.add(mac)
        active, last_change=slot_dmx_fields(mac, now)
        rows.append({
            "id":mac,
            "observed_ip":None if not info else info.get("ip"),
            "availability":_availability(info, now),
            "last_seen":None if not info else info.get("last_seen"),
            "configured":True,
            "slot":slots.get(mac),
            "discovery":"KNOWN",
            "dmx_active":bool(active),
            "dmx_last_change":last_change,
        })
    extras=sorted(mac for mac in snapshot if mac not in seen)
    for mac in extras:
        info=snapshot.get(mac) or {}
        rows.append({
            "id":mac,
            "observed_ip":info.get("ip"),
            "availability":_availability(info, now),
            "last_seen":info.get("last_seen"),
            "configured":False,
            "slot":None,
            "discovery":"NEW",
            "dmx_active":False,
            "dmx_last_change":None,
        })
    return {
        "state":bridge_runtime_state(),
        "wiz_tx":"on" if wiz_tx_allowed() else "off",
        "interface":WIZ_INTERFACE or "",
        "src_ip":wiz_src_ip,
        "devices":rows,
    }

def _write_bytes_atomic(path, body):
    directory=os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".wizbridge.",suffix=".tmp",dir=directory)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

def publish_observed_status(force=False):
    global _last_status_pub
    now=time.monotonic()
    if not force and now-_last_status_pub<STATUS_PUBLISH_INTERVAL:
        return
    path=_observed_path()
    try:
        body=json.dumps(observed_status_document(),separators=(",",":")).encode("utf-8")+b"\n"
        _write_bytes_atomic(path, body)
        _last_status_pub=now
    except OSError as e:
        print(f"[STATUS] write failed: {e}",flush=True)

def discovery_once():
    if not wiz_tx_allowed():
        publish_observed_status()
        return {}
    try_reload_map()
    if not wiz_tx_allowed():
        return {}
    found=discover_wiz()
    if found:
        apply_discovery(found)
    elif not all_known_found():
        print("[DISCOVERY] no WiZ replies; lamps not on WIZ-LIGHTS yet",flush=True)
    publish_observed_status()
    return found

def discovery_loop():
    last_miss_log=0.0
    last_reload=0.0
    was_on=False
    while not _loop_stop.is_set():
        on=wiz_tx_allowed()
        if on and not was_on:
            with fixtures_lock:
                macs=list(fixture_order)
            restore_remembered_ips(macs)
        was_on=on
        if not on:
            publish_observed_status()
            _loop_stop.wait(OFF_POLL)
            continue
        now=time.monotonic()
        if now-last_reload>=MAP_RELOAD_INTERVAL:
            try_reload_map()
            last_reload=now
        found=discover_wiz()
        if found:
            apply_discovery(found)
        elif not all_known_found():
            if now-last_miss_log>=30:
                last_miss_log=now
                print("[DISCOVERY] no WiZ replies; lamps not on WIZ-LIGHTS yet",flush=True)
        publish_observed_status()
        interval=DISCOVERY_INTERVAL if all_known_found() else FAST_DISCOVERY_INTERVAL
        _loop_stop.wait(interval)

def keepalive_once():
    if not wiz_tx_allowed():
        return
    with fixtures_lock:
        order=list(fixture_order)
    with devices_lock:
        snapshot=dict(devices)
    for mac in order:
        if not wiz_tx_allowed():
            return
        info=snapshot.get(mac)
        if not info: continue
        if read_identify_mac()==mac:
            continue
        last=info.get("last_seen")
        if last and time.time()-last<KEEPALIVE_INTERVAL:
            continue
        resp=wiz_exchange(info["ip"],"getPilot",{},timeout=ACK_TIMEOUT)
        if resp is None:
            print(f"[KEEPALIVE MISS] {mac} {info['ip']}",flush=True)
        else:
            result=resp.get("result",{})
            with devices_lock:
                cur=devices.get(mac)
                if cur:
                    cur["last_seen"]=time.time()
                    if "rssi" in result: cur["rssi"]=result.get("rssi")
    publish_observed_status()

def keepalive_loop():
    while not _loop_stop.is_set():
        if not wiz_tx_allowed():
            _loop_stop.wait(OFF_POLL)
            continue
        keepalive_once()
        _loop_stop.wait(KEEPALIVE_INTERVAL)

def artnet_listener():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    s.bind((ARTNET_BIND,ARTNET_PORT))
    print(f"Listening Art-Net {ARTNET_BIND}:{ARTNET_PORT}, universe {ARTNET_UNIVERSE}",flush=True)
    seen=0
    while not _loop_stop.is_set():
        data,_=s.recvfrom(2048)
        if len(data)<18 or data[:8]!=b"Art-Net\x00": continue
        if struct.unpack("<H",data[8:10])[0]!=0x5000: continue
        if struct.unpack("<H",data[14:16])[0]!=ARTNET_UNIVERSE: continue
        length=struct.unpack(">H",data[16:18])[0]
        payload=data[18:18+length]
        if not payload: continue
        with dmx_lock:
            n=min(len(payload),DMX_MAX)
            latest_dmx[:n]=payload[:n]
            ch=tuple(latest_dmx[0:6])
        note_dmx_activity()
        seen+=1
        if DEBUG_DMX and (seen==1 or seen%50==0):
            print(f"[DEBUG ARTNET] n={seen} len={length} ch1-6={ch}",flush=True)

def build_on_params(master,r,g,b,white,temp):
    if white>0:
        effective=round(master*white/255.0)
        if effective<=0: return None
        return {"state":True,"temp":dmx_to_temp(temp),"dimming":level_to_wiz_dimming(effective)}
    return {"state":True,"r":int(r),"g":int(g),"b":int(b),"dimming":level_to_wiz_dimming(master)}

def _live_sat_hue_wiz():
    if _LIVE_COLOR:
        try:
            c=_live_controls_cached()
            return int(c.sat),int(c.hue)
        except Exception:
            pass
    return 100,0

def capture_pilot_params(result):
    """Keep setPilot-able keys from a getPilot result. Drop discovery fields."""
    if not isinstance(result,dict):
        return None
    out={}
    for key in SETPILOT_KEYS:
        if key in result and result[key] is not None:
            out[key]=result[key]
    if "state" not in out:
        return None
    r=int(out.get("r") or 0)
    g=int(out.get("g") or 0)
    b=int(out.get("b") or 0)
    if out.get("temp") and not (r or g or b):
        for key in ("r","g","b","c","w"):
            out.pop(key,None)
    elif r or g or b:
        out.pop("temp",None)
    return out

def _device_ip(mac):
    with devices_lock:
        info=devices.get(mac)
        if info:
            ip=info.get("ip")
            if ip:
                return str(ip).strip()
    ip=fixture_ips.get(mac)
    return str(ip).strip() if ip else ""

def current_dmx_pilot_params(mac):
    with fixtures_lock:
        slot=fixture_slots.get(mac)
        enabled=fixture_enabled.get(mac,True)
    if not slot or not enabled:
        return None
    slot=int(slot)
    if slot<1 or slot>WIZ_MAX_SLOTS:
        return None
    base=dmx_index0(slot)
    if base<0 or base+CHANNELS_PER_FIXTURE>DMX_MAX:
        return None
    with dmx_lock:
        state=tuple(latest_dmx[base:base+CHANNELS_PER_FIXTURE])
    if len(state)<6:
        return None
    sat,hue=_live_sat_hue_wiz()
    if _LIVE_COLOR:
        try:
            state=_transform_wiz_channels(state,sat,hue)
        except Exception:
            pass
    master,r,g,b,white,temp=state
    if master==0:
        return {"state":False}
    return build_on_params(master,r,g,b,white,temp)

def _restore_identified(mac):
    if not mac or not wiz_tx_allowed():
        return
    ip=_device_ip(mac)
    if not ip or not wiz_dest_allowed(ip):
        with identify_lock:
            _identify_snapshot.pop(mac,None)
        return
    with fixtures_lock:
        configured=mac in fixture_slots
    if configured:
        params=current_dmx_pilot_params(mac)
    else:
        with identify_lock:
            params=_identify_snapshot.pop(mac,None)
    if not params:
        return
    setpilot_with_retry(ip,params)

def _send_identify_white(mac):
    if not mac or not wiz_tx_allowed():
        return False
    ip=_device_ip(mac)
    if not ip or not wiz_dest_allowed(ip):
        return False
    return setpilot_with_retry(ip,IDENTIFY_PARAMS)

def _capture_unconfigured(mac):
    with fixtures_lock:
        if mac in fixture_slots:
            return
    with identify_lock:
        if mac in _identify_snapshot:
            return
    ip=_device_ip(mac)
    if not ip or not wiz_dest_allowed(ip):
        return
    resp=wiz_exchange(ip,"getPilot",{},timeout=ACK_TIMEOUT)
    if not resp:
        return
    params=capture_pilot_params(resp.get("result") or {})
    if params:
        with identify_lock:
            _identify_snapshot[mac]=params

def identify_once():
    """Apply/clear a single-MAC identify override. Not OLED-rate; not a scan."""
    global _identify_mac,_identify_last_send
    wanted=identify_wanted()
    with identify_lock:
        current=_identify_mac
    if wanted==current:
        if wanted and (time.monotonic()-_identify_last_send)>=KEEPALIVE_INTERVAL:
            _send_identify_white(wanted)
            _identify_last_send=time.monotonic()
        return
    with identify_lock:
        _identify_mac=wanted
    if current:
        _restore_identified(current)
    if wanted:
        _capture_unconfigured(wanted)
        _send_identify_white(wanted)
        _identify_last_send=time.monotonic()

def identify_loop():
    while not _loop_stop.is_set():
        try:
            identify_once()
        except Exception as e:
            print(f"[WARN] identify {e!r}",flush=True)
        wait=IDENTIFY_POLL if _identify_mac else OFF_POLL
        if not wiz_tx_allowed():
            wait=OFF_POLL
        _loop_stop.wait(wait)

class FixtureWorker:
    def __init__(self, mac, slot, autostart=True):
        self.mac=mac
        self.slot=slot
        self.base=dmx_index0(slot)
        self._stop=threading.Event()
        if autostart:
            threading.Thread(target=self.run,name=f"wiz{slot}",daemon=True).start()

    def stop(self):
        self._stop.set()

    def run(self):
        last_sent=None
        last_send_time=-999.0
        zero_since=None
        off_delay=OFF_DELAY_MS/1000.0
        prev_seen=None
        was_identifying=False
        while not self._stop.is_set() and not _loop_stop.is_set():
            try:
                if not wiz_tx_allowed():
                    time.sleep(OFF_POLL)
                    continue
                time.sleep(0.02)
                with fixtures_lock:
                    if self.mac not in fixture_slots:
                        continue
                    slot=fixture_slots[self.mac]
                    enabled=fixture_enabled.get(self.mac, True)
                self.slot=slot
                self.base=dmx_index0(slot)
                if not enabled:
                    continue
                if self.base<0 or self.base+CHANNELS_PER_FIXTURE>DMX_MAX:
                    continue
                if read_identify_mac()==self.mac:
                    was_identifying=True
                    continue
                if was_identifying:
                    was_identifying=False
                    last_sent=None
                    last_send_time=-999.0
                with dmx_lock:
                    state=tuple(latest_dmx[self.base:self.base+CHANNELS_PER_FIXTURE])
                if len(state)<6:
                    continue
                if DEBUG_DMX and state!=prev_seen:
                    print(f"[DEBUG TARGET] WiZ{self.slot} old={prev_seen} new={state}",flush=True)
                    prev_seen=state
                with devices_lock:
                    info=devices.get(self.mac)
                if not info:
                    continue
                now=time.monotonic()
                sat,hue=_live_sat_hue_wiz()
                if not wiz_tx_allowed():
                    continue
                if _LIVE_COLOR:
                    try:
                        state=_transform_wiz_channels(state,sat,hue)
                    except Exception:
                        pass
                master,r,g,b,white,temp=state
                prev=last_sent
                since=now-last_send_time
                key=(state,sat,hue)
                if master==0:
                    if zero_since is None:
                        zero_since=now
                    if now-zero_since>=off_delay and prev!=key and since>=MIN_SEND_INTERVAL:
                        if DEBUG_DMX:
                            print(f"[DEBUG TX] WiZ{self.slot} OFF {state}",flush=True)
                        t=time.monotonic()
                        ok=setpilot_with_retry(info["ip"],{"state":False})
                        if ok:
                            last_sent=key
                            last_send_time=time.monotonic()
                            with devices_lock:
                                cur=devices.get(self.mac)
                                if cur: cur["last_seen"]=time.time()
                            print(f"[OFF] WiZ{self.slot} t={t:.3f}",flush=True)
                    continue
                zero_since=None
                if prev==key or since<MIN_SEND_INTERVAL:
                    continue
                params=build_on_params(master,r,g,b,white,temp)
                if not params:
                    continue
                if DEBUG_DMX:
                    print(f"[DEBUG TX] WiZ{self.slot} {state}",flush=True)
                t=time.monotonic()
                mode="CCT" if white>0 else "RGB"
                ok=setpilot_with_retry(info["ip"],params)
                if ok:
                    last_sent=key
                    last_send_time=time.monotonic()
                    with devices_lock:
                        cur=devices.get(self.mac)
                        if cur: cur["last_seen"]=time.time()
                    print(f"[SEND] WiZ{self.slot} {mode} Dim={master} R={r} G={g} B={b} W={white} T={temp} t={t:.3f}",flush=True)
            except Exception as e:
                print(f"[WARN] WiZ{self.slot} worker {e!r}",flush=True)
                time.sleep(0.2)

def ensure_worker(mac, slot):
    with workers_lock:
        worker=workers.get(mac)
        if worker is None:
            worker=FixtureWorker(mac, slot)
            workers[mac]=worker
        elif worker.slot!=slot:
            worker.slot=slot
            worker.base=dmx_index0(slot)
        return worker

def output_loop():
    print(f"WiZ coalescing max {WIZ_MAX_HZ:g} cmd/s",flush=True)
    print(f"Keepalive {KEEPALIVE_INTERVAL:g}s, ACK {ACK_TIMEOUT*1000:.0f}ms, retries {RETRIES}",flush=True)
    print("Per-fixture WiZ workers enabled",flush=True)
    while not _loop_stop.is_set():
        with fixtures_lock:
            order=list(fixture_order)
            slots=dict(fixture_slots)
        for mac in order:
            ensure_worker(mac, slots.get(mac) or (order.index(mac)+1))
        _loop_stop.wait(0.5)

def reset_runtime_for_tests():
    global fixtures_path, map_path, map_source, wiz_src_ip, wiz_broadcast
    global _last_status_pub, _map_mtime, _map_fail_mtime
    global _identify_mac, _identify_snapshot, _identify_last_send
    _loop_stop.clear()
    with devices_lock:
        devices.clear()
    apply_configured([])
    fixtures_path=None
    map_path=None
    map_source=None
    with workers_lock:
        for worker in workers.values():
            worker.stop()
        workers.clear()
    wiz_src_ip=None
    wiz_broadcast="255.255.255.255"
    _last_status_pub=0.0
    _map_mtime=None
    _map_fail_mtime=None
    with identify_lock:
        _identify_mac=""
        _identify_snapshot={}
        _identify_last_send=0.0
    with dmx_lock:
        latest_dmx[:] = bytearray(DMX_MAX)
    with _dmx_act_lock:
        _dmx_levels.clear()
        _dmx_last_change.clear()

def main():
    print("Art-Net -> WiZ bridge 6CH v5 KEEPALIVE",flush=True)
    load_configured_devices()
    if WIZ_INTERFACE:
        deadline=time.monotonic()+60
        while time.monotonic()<deadline and not _loop_stop.is_set():
            if refresh_wiz_network():
                print(f"WiZ interface {WIZ_INTERFACE} src {wiz_src_ip} broadcast {wiz_broadcast}",flush=True)
                break
            print(f"[WARN] waiting for {WIZ_INTERFACE} IPv4 (LIGHT-CONTROL not required)",flush=True)
            time.sleep(1)
        else:
            print(f"[WARN] {WIZ_INTERFACE} still has no IPv4; discovery will retry",flush=True)
    else:
        print("WiZ interface unset; using default routing and 255.255.255.255",flush=True)
    publish_observed_status(force=True)
    threading.Thread(target=discovery_loop,daemon=True).start()
    threading.Thread(target=keepalive_loop,daemon=True).start()
    threading.Thread(target=identify_loop,daemon=True).start()
    threading.Thread(target=artnet_listener,daemon=True).start()
    output_loop()

if __name__=="__main__":
    main()
