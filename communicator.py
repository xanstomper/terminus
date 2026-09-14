"""
Terminus Omni-Communicator — Universal Multi-Agent Broadcast & Communication Hub
Coordinates prompt dispatching, cross-agent relays, and direct Hermes / OpenCode chat.
"""

import os
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

TERMINUS_DIR = Path.home() / ".terminus"
TERMINUS_DIR.mkdir(parents=True, exist_ok=True)
COMM_HISTORY_FILE = TERMINUS_DIR / "communicator_history.json"

DEFAULT_PRESETS = [
    {
        "id": "code_review",
        "title": "Code Review & Security Audit",
        "icon": "🛡️",
        "prompt": "Review recent git diffs, detect potential vulnerabilities, performance bottlenecks, and suggest clean architectural improvements."
    },
    {
        "id": "bug_patch",
        "title": "Bug Hunt & Auto-Patch",
        "icon": "🐛",
        "prompt": "Inspect the most recent error logs or failing tests, isolate the root cause, and implement a minimal robust fix."
    },
    {
        "id": "write_tests",
        "title": "Generate Unit & Integration Tests",
        "icon": "🧪",
        "prompt": "Analyze untested code paths in the repository and write comprehensive, edge-case resilient tests."
    },
    {
        "id": "git_commit",
        "title": "Smart Git Commit & Summary",
        "icon": "🚀",
        "prompt": "Check git status and diff, format a standard conventional commit message, and stage modified project files."
    },
    {
        "id": "explain_arch",
        "title": "Explain System Architecture",
        "icon": "🗺️",
        "prompt": "Analyze the codebase structure, explain key modules, entry points, and data flows in concise markdown."
    },
    {
        "id": "hermes_eval",
        "title": "Hermes Autonomous Loop",
        "icon": "⚡",
        "prompt": "Inspect project workspace, list pending TODOs, and autonomously implement the highest priority task."
    }
]


def load_history() -> List[Dict[str, Any]]:
    if not COMM_HISTORY_FILE.exists():
        return []
    try:
        with open(COMM_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history: List[Dict[str, Any]]):
    try:
        with open(COMM_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[-100:], f, indent=2)
    except Exception:
        pass


def record_message(sender: str, target: str, message: str, response: Optional[str] = None) -> Dict[str, Any]:
    history = load_history()
    entry = {
        "id": f"msg-{int(time.time() * 1000)}",
        "sender": sender,
        "target": target,
        "message": message,
        "response": response,
        "timestamp": time.time(),
        "time_str": time.strftime("%H:%M:%S")
    }
    history.append(entry)
    save_history(history)
    return entry


def execute_solo_hermes(prompt: str) -> Dict[str, Any]:
    """
    Executes a direct headless Hermes prompt using the configured hermes-env.
    """
    hermes_bin = Path.home() / "hermes-env" / "bin" / "hermes"
    if not hermes_bin.exists():
        hermes_bin = Path("hermes")

    cmd = [str(hermes_bin), "-z", prompt]
    try:
        start_t = time.time()
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path.home())
        )
        duration = round(time.time() - start_t, 2)
        output = res.stdout if res.returncode == 0 else (res.stderr or res.stdout)
        return {
            "success": res.returncode == 0,
            "output": output.strip() or "No response from Hermes.",
            "duration": duration,
            "error": None if res.returncode == 0 else res.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "Hermes command timed out after 120 seconds.",
            "duration": 120,
            "error": "Timeout"
        }
    except Exception as e:
        return {
            "success": False,
            "output": f"Failed to invoke Hermes: {str(e)}",
            "duration": 0,
            "error": str(e)
        }
