import subprocess
import re
from typing import List, Dict, Any

def get_listening_ports() -> List[Dict[str, Any]]:
    ports = []
    seen = set()
    try:
        out = subprocess.check_output(['ss', '-tlpn'], text=True, timeout=2)
        for line in out.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4 and 'LISTEN' in parts[0]:
                addr = parts[3]
                proc = parts[5] if len(parts) > 5 else ''
                
                port_m = re.search(r':(\d+)$', addr)
                if not port_m:
                    continue
                port = int(port_m.group(1))
                if port in seen:
                    continue
                seen.add(port)

                # Process name & PID
                pname = "unknown"
                pid = None
                proc_m = re.search(r'users:\(\(\"([^\"]+)\",pid=(\d+)', proc)
                if proc_m:
                    pname = proc_m.group(1)
                    pid = int(proc_m.group(2))

                is_public = addr.startswith("0.0.0.0") or addr.startswith("*") or addr.startswith("[::]")
                
                # Service tagging
                tag = "Service"
                if port in [3000, 5173, 8080, 8000, 4200, 5000]:
                    tag = "Dev Web Server"
                elif port in [9120]:
                    tag = "Terminus Control Plane"
                elif port in [9119]:
                    tag = "Hermes Dashboard"
                elif port in [5432]:
                    tag = "PostgreSQL"
                elif port in [6379]:
                    tag = "Redis"
                elif port in [5900]:
                    tag = "VNC Server"
                elif port in [25463]:
                    tag = "Cline Hub"

                ports.append({
                    "port": port,
                    "address": addr,
                    "process": pname,
                    "pid": pid,
                    "tag": tag,
                    "is_public": is_public
                })
    except Exception:
        pass

    ports.sort(key=lambda x: x["port"])
    return ports
