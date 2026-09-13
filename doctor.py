import os
import shutil
import psutil
import socket
from typing import List, Dict, Any
import adapters

def run_diagnostics() -> Dict[str, Any]:
    checks = []
    
    # 1. Network & LAN
    lan_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
        checks.append({
            "name": "Network & LAN Reachability",
            "status": "ok",
            "message": f"Bound to global LAN IP {lan_ip}:9120"
        })
    except Exception as e:
        checks.append({
            "name": "Network & LAN Reachability",
            "status": "warn",
            "message": f"Local loopback fallback: {e}"
        })

    # 2. PTY & Terminal Subsystem
    try:
        import pty, fcntl, termios
        m, s = pty.openpty()
        os.close(m)
        os.close(s)
        checks.append({
            "name": "PTY Engine & POSIX Terminal",
            "status": "ok",
            "message": "pseudo-terminal subsystem functional"
        })
    except Exception as e:
        checks.append({
            "name": "PTY Engine & POSIX Terminal",
            "status": "error",
            "message": f"PTY allocation failure: {e}"
        })

    # 3. Agent Discovery Subsystem
    all_agents = adapters.get_all_agents()
    installed = [a for a in all_agents if a["installed"]]
    running = [a for a in all_agents if a["running_count"] > 0]
    checks.append({
        "name": "Agent Discovery Engine",
        "status": "ok" if len(installed) >= 3 else "warn",
        "message": f"Found {len(installed)} installed agents ({len(running)} active)"
    })

    # 4. Storage & Disk Headroom
    disk = psutil.disk_usage("/")
    free_gb = round(disk.free / (1024**3), 1)
    if disk.percent > 95:
        checks.append({
            "name": "Disk Storage Headroom",
            "status": "warn",
            "message": f"Disk utilization at {disk.percent}% ({free_gb} GB free). Consider pruning ~/.cache or temporary files."
        })
    else:
        checks.append({
            "name": "Disk Storage Headroom",
            "status": "ok",
            "message": f"{disk.percent}% used ({free_gb} GB free)"
        })

    # 5. System RAM
    mem = psutil.virtual_memory()
    used_gb = round(mem.used / (1024**3), 1)
    total_gb = round(mem.total / (1024**3), 1)
    checks.append({
        "name": "System Memory",
        "status": "ok" if mem.percent < 90 else "warn",
        "message": f"{mem.percent}% used ({used_gb} / {total_gb} GB)"
    })

    # 6. Runtimes (Python & Node)
    python_ok = shutil.which("python3") is not None
    node_ok = shutil.which("node") is not None
    git_ok = shutil.which("git") is not None
    checks.append({
        "name": "Core Developer Toolchains",
        "status": "ok" if (python_ok and node_ok and git_ok) else "warn",
        "message": f"Python3: {'available' if python_ok else 'missing'} | Node.js: {'available' if node_ok else 'missing'} | Git: {'available' if git_ok else 'missing'}"
    })

    overall = "ok"
    if any(c["status"] == "error" for c in checks):
        overall = "error"
    elif any(c["status"] == "warn" for c in checks):
        overall = "warn"

    return {
        "overall": overall,
        "checks": checks
    }
