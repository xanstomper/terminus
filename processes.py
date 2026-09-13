import os
import signal
import time
from typing import List, Dict, Any, Optional
import psutil

WATCHED_PATTERNS = [
    "claude", "hermes", "agy", "antigravity", "mochi", "codex", "cline",
    "jcode", "gemini", "pi", "opencode", "node", "python3"
]

def list_agent_processes() -> List[Dict[str, Any]]:
    results = []
    try:
        for p in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_percent', 'create_time', 'username']):
            try:
                # Only current user
                if p.info.get('username') != 'jewboy420':
                    continue
                    
                pname = (p.info.get('name') or "").lower()
                cmd = " ".join(p.info.get('cmdline') or [])
                cmd_lower = cmd.lower()
                
                # Filter out background terminus/system daemon itself
                if "terminus" in cmd_lower or "systemd" in cmd_lower:
                    continue
                    
                matched = any(pat in pname or f"/{pat}" in cmd_lower or f" {pat}" in cmd_lower for pat in WATCHED_PATTERNS)
                if matched:
                    uptime_sec = int(time.time() - (p.info.get('create_time') or time.time()))
                    m, s = divmod(uptime_sec, 60)
                    h, m = divmod(m, 60)
                    runtime_str = f"{h}h {m}m" if h > 0 else f"{m}m {s}s"
                    
                    results.append({
                        "pid": p.info['pid'],
                        "name": p.info['name'],
                        "cmd": cmd[:140] if cmd else p.info['name'],
                        "cpu": round(p.info.get('cpu_percent') or 0.0, 1),
                        "mem": round(p.info.get('memory_percent') or 0.0, 1),
                        "runtime": runtime_str
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
        
    results.sort(key=lambda x: (x["cpu"], x["mem"]), reverse=True)
    return results[:30]


def terminate_process(pid: int, force: bool = False) -> Dict[str, Any]:
    try:
        proc = psutil.Process(pid)
        # Prevent killing self or system init
        if pid <= 1 or proc.username() != 'jewboy420':
            return {"success": False, "error": "Permission denied"}
            
        if force:
            proc.kill()
        else:
            proc.terminate()
        return {"success": True, "pid": pid}
    except psutil.NoSuchProcess:
        return {"success": True, "pid": pid, "already_dead": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
