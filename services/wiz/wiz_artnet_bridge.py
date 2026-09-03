#!/usr/bin/env python3
import fcntl, json, os, socket, struct, tempfile, threading, time

ARTNET_UNIVERSE=0
ARTNET_PORT=6454
WIZ_PORT=38899
# Dedicated WiZ NIC. "" = legacy default-route + limited broadcast 255.255.255.255.
WIZ_INTERFACE="wlan1"
SIOCGIFADDR=0x8915
SIOCGIFBRDADDR=0x8919
SIOCGIFNETMASK=0x891b
START_CHANNEL=1
CHANNELS_PER_FIXTURE=6
WIZ_MAX_HZ=5.0
MIN_SEND_INTERVAL=1.0/WIZ_MAX_HZ
KEEPALIVE_INTERVAL=5.0
ACK_TIMEOUT=0.80
RETRIES=2
RETRY_DELAY=0.06
DISCOVERY_INTERVAL=30.0
FAST_DISCOVERY_INTERVAL=2.0
DISCOVERY_TIMEOUT=1.5
MIN_TEMP_K=2200
MAX_TEMP_K=6500
OFF_DELAY_MS=120
DEBUG_DMX=True

latest_dmx=bytearray(512)
dmx_lock=threading.Lock()
devices={}
devices_lock=threading.Lock()
fixture_order=[]
fixture_ips={}
fixtures_path=None
fixtures_lock=threading.Lock()
workers={}
workers_lock=threading.Lock()
wiz_src_ip=None
wiz_broadcast="255.255.255.255"

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

def dmx_span(index):
    start=START_CHANNEL+index*CHANNELS_PER_FIXTURE
    return start, start+CHANNELS_PER_FIXTURE-1

def parse_fixture_macs(path, data):
    fixtures=data.get("fixtures")
    if not isinstance(fixtures,list) or not fixtures:
        raise SystemExit(f"No fixtures listed in {path}")
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
            raise SystemExit(f"Fixture {i+1} in {path} has no mac")
        if slot is not None and int(slot)!=i+1:
            raise SystemExit(f"{path}: list order is slot order; entry {i+1} has slot {slot}")
        if mac in seen:
            raise SystemExit(f"Duplicate mac {mac} in {path}")
        seen.add(mac)
        macs.append(mac)
        if ip:
            ips[mac]=ip
    return macs, ips

def fixtures_document(macs):
    fixtures=[]
    for i,mac in enumerate(macs):
        start,end=dmx_span(i)
        entry={"slot":i+1,"mac":mac,"dmx":f"{start}-{end}"}
        ip=fixture_ips.get(mac)
        if ip:
            entry["ip"]=ip
        fixtures.append(entry)
    return {"start_channel":START_CHANNEL,"channels_per_fixture":CHANNELS_PER_FIXTURE,"fixtures":fixtures}

def save_known_fixtures(path, macs):
    directory=os.path.dirname(path) or "."
    fd,tmp=tempfile.mkstemp(prefix=".fixtures.",suffix=".tmp",dir=directory)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(fixtures_document(macs),f,indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

def log_fixture_map(macs, path):
    print(f"Loaded {len(macs)} fixtures from {path}",flush=True)
    for i,mac in enumerate(macs):
        start,end=dmx_span(i)
        ip=fixture_ips.get(mac)
        extra=f" last-ip {ip}" if ip else ""
        print(f"  WiZ{i+1} {mac} DMX {start}-{end}{extra}",flush=True)

def load_known_fixtures():
    global fixtures_path, fixture_ips
    searched=fixture_config_paths()
    for path in searched:
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            data=json.load(f)
        macs,ips=parse_fixture_macs(path, data)
        fixtures_path=path
        fixture_ips=ips
        log_fixture_map(macs, path)
        return macs
    raise SystemExit("No fixtures.json found. Looked in: "+", ".join(searched))

def persist_fixture_ips():
    if not fixtures_path:
        return
    try:
        save_known_fixtures(fixtures_path, list(fixture_order))
    except OSError as e:
        print(f"[MAP] persist failed: {e}",flush=True)

def remember_discovered_ips(found):
    persist=False
    with fixtures_lock:
        known=set(fixture_order)
        for mac,info in found.items():
            ip=(info or {}).get("ip")
            if not mac or not ip or mac not in known:
                continue
            if fixture_ips.get(mac)==ip:
                continue
            fixture_ips[mac]=ip
            persist=True
        if persist:
            persist_fixture_ips()

def verify_remembered_ip(mac, ip):
    resp=wiz_exchange(ip,"getPilot",{},timeout=ACK_TIMEOUT)
    if resp is None:
        return None
    result=resp.get("result") or {}
    got=normalize_mac(result.get("mac"))
    if got!=mac:
        return None
    return {"ip":ip,"rssi":result.get("rssi"),"last_seen":time.time()}

def restore_remembered_ips(macs):
    for i,mac in enumerate(macs):
        ip=fixture_ips.get(mac)
        if not ip:
            continue
        info=verify_remembered_ip(mac, ip)
        if info:
            with devices_lock:
                devices[mac]=info
            print(f"[RESTORE] WiZ{i+1} {mac} verified at {ip}",flush=True)
        else:
            print(f"[RESTORE MISS] WiZ{i+1} remembered {ip}",flush=True)

def enroll_new_fixtures(found_macs):
    global fixture_order
    if not fixtures_path:
        return
    with fixtures_lock:
        known=set(fixture_order)
        newcomers=sorted(mac for mac in found_macs if mac and mac not in known)
        if not newcomers:
            return
        last_end=dmx_span(len(fixture_order)+len(newcomers)-1)[1]
        if last_end>512:
            print(f"[MAP] skip enroll {newcomers}; would exceed DMX 512",flush=True)
            return
        updated=list(fixture_order)+newcomers
        for mac in newcomers:
            info=found_macs.get(mac) if isinstance(found_macs,dict) else None
            ip=(info or {}).get("ip")
            if ip:
                fixture_ips[mac]=ip
        try:
            save_known_fixtures(fixtures_path, updated)
        except OSError as e:
            print(f"[MAP] persist failed: {e}",flush=True)
            return
        fixture_order=updated
        base=len(updated)-len(newcomers)
        for offset,mac in enumerate(newcomers):
            start,end=dmx_span(base+offset)
            print(f"[MAP] enrolled {mac} as WiZ{base+offset+1} DMX {start}-{end}",flush=True)
            ensure_worker(mac, base+offset+1)

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
    msg={"method":method,"params":params or {}}
    payload=json.dumps(msg,separators=(",",":")).encode()
    s=open_wiz_socket(timeout)
    try:
        s.sendto(payload,(ip,WIZ_PORT))
        data,addr=s.recvfrom(4096)
        if addr[0]!=ip: return None
        return json.loads(data.decode())
    except (socket.timeout,OSError,ValueError):
        return None
    finally:
        s.close()

def setpilot_with_retry(ip, params):
    for attempt in range(RETRIES+1):
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
    if WIZ_INTERFACE and not refresh_wiz_network():
        print(f"[DISCOVERY] {WIZ_INTERFACE} has no IPv4; skip",flush=True)
        return {}
    dest=wiz_broadcast
    payload=json.dumps({"method":"getPilot","params":{}},separators=(",",":")).encode()
    s=open_wiz_socket(DISCOVERY_TIMEOUT,broadcast=True)
    found={}
    try:
        s.sendto(payload,(dest,WIZ_PORT))
        deadline=time.monotonic()+DISCOVERY_TIMEOUT
        while time.monotonic()<deadline:
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

def discovery_loop():
    last_miss_log=0.0
    while True:
        found=discover_wiz()
        if found:
            with devices_lock:
                for mac,info in found.items():
                    old=devices.get(mac)
                    devices[mac]=info
                    if old is None:
                        print(f"[DISCOVERY] found {mac} at {info['ip']} rssi={info.get('rssi')}",flush=True)
                    elif old.get("ip")!=info["ip"]:
                        print(f"[DISCOVERY] {mac} IP changed {old.get('ip')} -> {info['ip']}",flush=True)
            remember_discovered_ips(found)
            enroll_new_fixtures(found)
        elif not all_known_found():
            now=time.monotonic()
            if now-last_miss_log>=30:
                last_miss_log=now
                print("[DISCOVERY] no WiZ replies; lamps not on WIZ-LIGHTS yet",flush=True)
        time.sleep(DISCOVERY_INTERVAL if all_known_found() else FAST_DISCOVERY_INTERVAL)

def keepalive_loop():
    while True:
        with fixtures_lock:
            order=list(fixture_order)
        with devices_lock:
            snapshot=dict(devices)
        for mac in order:
            info=snapshot.get(mac)
            if not info: continue
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
        time.sleep(KEEPALIVE_INTERVAL)

def artnet_listener():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    s.bind(("0.0.0.0",ARTNET_PORT))
    print(f"Listening Art-Net UDP/{ARTNET_PORT}, universe {ARTNET_UNIVERSE}",flush=True)
    seen=0
    while True:
        data,_=s.recvfrom(2048)
        if len(data)<18 or data[:8]!=b"Art-Net\x00": continue
        if struct.unpack("<H",data[8:10])[0]!=0x5000: continue
        if struct.unpack("<H",data[14:16])[0]!=ARTNET_UNIVERSE: continue
        length=struct.unpack(">H",data[16:18])[0]
        payload=data[18:18+length]
        if not payload: continue
        with dmx_lock:
            n=min(len(payload),512)
            latest_dmx[:n]=payload[:n]
            ch=tuple(latest_dmx[0:6])
        seen+=1
        if DEBUG_DMX and (seen==1 or seen%50==0):
            print(f"[DEBUG ARTNET] n={seen} len={length} ch1-6={ch}",flush=True)

def build_on_params(master,r,g,b,white,temp):
    if white>0:
        effective=round(master*white/255.0)
        if effective<=0: return None
        return {"state":True,"temp":dmx_to_temp(temp),"dimming":level_to_wiz_dimming(effective)}
    return {"state":True,"r":int(r),"g":int(g),"b":int(b),"dimming":level_to_wiz_dimming(master)}

class FixtureWorker:
    def __init__(self, mac, slot):
        self.mac=mac
        self.slot=slot
        self.base=(slot-1)*CHANNELS_PER_FIXTURE
        threading.Thread(target=self.run,name=f"wiz{slot}",daemon=True).start()

    def run(self):
        last_sent=None
        last_send_time=-999.0
        zero_since=None
        off_delay=OFF_DELAY_MS/1000.0
        prev_seen=None
        while True:
            try:
                time.sleep(0.02)
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
                master,r,g,b,white,temp=state
                prev=last_sent
                since=now-last_send_time
                if master==0:
                    if zero_since is None:
                        zero_since=now
                    if now-zero_since>=off_delay and prev!=state and since>=MIN_SEND_INTERVAL:
                        if DEBUG_DMX:
                            print(f"[DEBUG TX] WiZ{self.slot} OFF {state}",flush=True)
                        t=time.monotonic()
                        ok=setpilot_with_retry(info["ip"],{"state":False})
                        if ok:
                            last_sent=state
                            last_send_time=time.monotonic()
                            with devices_lock:
                                cur=devices.get(self.mac)
                                if cur: cur["last_seen"]=time.time()
                            print(f"[OFF] WiZ{self.slot} t={t:.3f}",flush=True)
                    continue
                zero_since=None
                if prev==state or since<MIN_SEND_INTERVAL:
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
                    last_sent=state
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
        return worker

def output_loop():
    print(f"WiZ coalescing max {WIZ_MAX_HZ:g} cmd/s",flush=True)
    print(f"Keepalive {KEEPALIVE_INTERVAL:g}s, ACK {ACK_TIMEOUT*1000:.0f}ms, retries {RETRIES}",flush=True)
    print("Per-fixture WiZ workers enabled",flush=True)
    while True:
        with fixtures_lock:
            order=list(fixture_order)
        for i,mac in enumerate(order):
            ensure_worker(mac, i+1)
        time.sleep(0.5)

def main():
    global fixture_order
    print("Art-Net -> WiZ bridge 6CH v5 KEEPALIVE",flush=True)
    fixture_order=load_known_fixtures()
    if WIZ_INTERFACE:
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            if refresh_wiz_network():
                print(f"WiZ interface {WIZ_INTERFACE} src {wiz_src_ip} broadcast {wiz_broadcast}",flush=True)
                break
            print(f"[WARN] waiting for {WIZ_INTERFACE} IPv4 (LIGHT-CONTROL not required)",flush=True)
            time.sleep(1)
        else:
            print(f"[WARN] {WIZ_INTERFACE} still has no IPv4; discovery will retry",flush=True)
    else:
        print("WiZ interface unset; using default routing and 255.255.255.255",flush=True)
    restore_remembered_ips(fixture_order)
    threading.Thread(target=discovery_loop,daemon=True).start()
    threading.Thread(target=keepalive_loop,daemon=True).start()
    threading.Thread(target=artnet_listener,daemon=True).start()
    output_loop()

if __name__=="__main__":
    main()
