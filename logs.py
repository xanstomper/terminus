import glob
import os
import subprocess
from typing import Dict, List, Any

LOG_SOURCES = {
    "terminus": "Terminus Daemon (systemd)",
    "hermes": "Hermes Agent Log",
    "hermes-errors": "Hermes Errors Log",
    "hermes-gateway": "Hermes Gateway Log",
    "jcode": "J-Code Daily Log",
    "system": "System Messages"
}

def get_log_sources() -> Dict[str, str]:
    return LOG_SOURCES


def fetch_logs(source: str = "terminus", lines: int = 100, query: str = "") -> Dict[str, Any]:
    output = []
    
    try:
        if source == "terminus":
            cmd = ["journalctl", "--user", "-u", "terminus.service", "-n", str(lines), "--no-pager"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            output = res.stdout.splitlines()

        elif source == "hermes":
            path = "/home/jewboy420/.hermes/logs/agent.log"
            if os.path.exists(path):
                cmd = ["tail", "-n", str(lines), path]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                output = res.stdout.splitlines()
            else:
                output = ["No agent.log found at ~/.hermes/logs/agent.log"]

        elif source == "hermes-errors":
            path = "/home/jewboy420/.hermes/logs/errors.log"
            if os.path.exists(path):
                cmd = ["tail", "-n", str(lines), path]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                output = res.stdout.splitlines()
            else:
                output = ["No errors.log found at ~/.hermes/logs/errors.log"]

        elif source == "hermes-gateway":
            path = "/home/jewboy420/.hermes/logs/gateway.log"
            if os.path.exists(path):
                cmd = ["tail", "-n", str(lines), path]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                output = res.stdout.splitlines()
            else:
                output = ["No gateway.log found at ~/.hermes/logs/gateway.log"]

        elif source == "jcode":
            logs = sorted(glob.glob("/home/jewboy420/.jcode/logs/jcode-*.log"))
            if logs:
                latest = logs[-1]
                cmd = ["tail", "-n", str(lines), latest]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                output = res.stdout.splitlines()
            else:
                output = ["No J-code logs found in ~/.jcode/logs/"]

        elif source == "system":
            cmd = ["journalctl", "-n", str(lines), "--no-pager"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            output = res.stdout.splitlines()
    except Exception as e:
        output = [f"Error reading log source {source}: {e}"]

    if query:
        q_lower = query.lower()
        output = [line for line in output if q_lower in line.lower()]

    return {
        "source": source,
        "source_label": LOG_SOURCES.get(source, source),
        "total_lines": len(output),
        "lines": output
    }
