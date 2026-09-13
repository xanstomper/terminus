import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import psutil

# Ensure user directories are in PATH for discovery and child executions
USER_PATHS = [
    str(Path.home() / ".local" / "bin"),
    str(Path.home() / ".npm-global" / "bin"),
    str(Path.home() / "hermes-env" / "bin"),
    str(Path.home() / ".opencode" / "bin"),
    "/usr/local/bin",
    "/usr/bin",
    "/bin"
]
for p in USER_PATHS:
    if p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{p}:{os.environ.get('PATH', '')}"

# Recognized coding agents and terminal AI tools
AGENT_DEFINITIONS = [
    {
        "id": "claude",
        "name": "Claude Code",
        "binaries": [
            "/home/jewboy420/.local/bin/claude",
            "claude"
        ],
        "version_cmd": ["claude", "--version"],
        "launch_cmd": "claude",
        "resume_cmd": "claude -c",
        "process_patterns": ["claude", "claude-code"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "SESSION_RESUME"],
        "description": "Anthropic agentic coding assistant CLI with codebase reasoning",
        "category": "autonomous-coder"
    },
    {
        "id": "hermes",
        "name": "Hermes Agent",
        "binaries": [
            "/home/jewboy420/hermes-env/bin/hermes",
            "hermes"
        ],
        "version_cmd": ["/home/jewboy420/hermes-env/bin/hermes", "--version"],
        "launch_cmd": "/home/jewboy420/hermes-env/bin/hermes",
        "resume_cmd": "/home/jewboy420/hermes-env/bin/hermes -c",
        "process_patterns": ["hermes"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "SESSION_RESUME", "API"],
        "description": "Autonomous developer agent with OpenCode models and Discord gateway",
        "category": "autonomous-coder"
    },
    {
        "id": "antigravity",
        "name": "Antigravity",
        "binaries": [
            "/home/jewboy420/.local/bin/agy",
            "agy"
        ],
        "version_cmd": ["/home/jewboy420/.local/bin/agy", "--version"],
        "launch_cmd": "agy",
        "resume_cmd": "agy -c",
        "process_patterns": ["agy"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "SESSION_RESUME"],
        "description": "Google Antigravity AI development agent CLI",
        "category": "autonomous-coder"
    },
    {
        "id": "mochi",
        "name": "Mochi",
        "binaries": [
            "/home/jewboy420/.npm-global/bin/mochi",
            "/home/jewboy420/mochi/dist/mochi-bin",
            "/home/jewboy420/mochi/bin/mochi",
            "mochi"
        ],
        "version_cmd": ["mochi", "--version"],
        "launch_cmd": "mochi",
        "resume_cmd": "mochi resume",
        "process_patterns": ["mochi", "mochi-bin"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "SESSION_RESUME", "CHECKPOINTS"],
        "description": "Minimal autonomous coding agent with memory, planning, and checkpoints",
        "category": "autonomous-coder"
    },
    {
        "id": "codex",
        "name": "Codex",
        "binaries": [
            "/home/jewboy420/.local/bin/codex",
            "codex"
        ],
        "version_cmd": ["codex", "--version"],
        "launch_cmd": "codex",
        "resume_cmd": "codex exec",
        "process_patterns": ["codex"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT"],
        "description": "OpenAI Codex CLI coding assistant and code reviewer",
        "category": "code-assistant"
    },
    {
        "id": "cline",
        "name": "Cline",
        "binaries": [
            "/home/jewboy420/.npm-global/bin/cline",
            "/home/jewboy420/.npm-global/lib/node_modules/@cline/cli-linux-x64/bin/cline",
            "cline"
        ],
        "version_cmd": ["cline", "--version"],
        "launch_cmd": "cline",
        "resume_cmd": "cline",
        "process_patterns": ["cline"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "API"],
        "description": "Autonomous coding assistant for terminal and desktop IDEs",
        "category": "autonomous-coder"
    },
    {
        "id": "jcode",
        "name": "J-Code",
        "binaries": [
            "/home/jewboy420/.local/bin/jcode",
            "jcode"
        ],
        "version_cmd": ["jcode", "version"],
        "launch_cmd": "jcode repl",
        "resume_cmd": "jcode connect",
        "process_patterns": ["jcode", "jcode-linux"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "SESSION_RESUME"],
        "description": "Coding agent utilizing Claude Max or ChatGPT Pro subscriptions",
        "category": "autonomous-coder"
    },
    {
        "id": "gemini",
        "name": "Gemini CLI",
        "binaries": [
            "/home/jewboy420/.npm-global/bin/gemini",
            "gemini"
        ],
        "version_cmd": ["gemini", "--version"],
        "launch_cmd": "gemini",
        "resume_cmd": None,
        "process_patterns": ["gemini"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT"],
        "description": "Official Google Gemini developer CLI tools",
        "category": "cli-tools"
    },
    {
        "id": "pi",
        "name": "Pi Coding Agent",
        "binaries": [
            "/home/jewboy420/.npm-global/bin/pi",
            "pi"
        ],
        "version_cmd": ["pi", "--version"],
        "launch_cmd": "pi",
        "resume_cmd": None,
        "process_patterns": ["pi"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT"],
        "description": "Autonomous programming assistant",
        "category": "code-assistant"
    },
    {
        "id": "opencode",
        "name": "OpenCode",
        "binaries": [
            "/home/jewboy420/.opencode/bin/opencode",
            "opencode"
        ],
        "version_cmd": ["opencode", "--version"],
        "launch_cmd": "opencode",
        "resume_cmd": None,
        "process_patterns": ["opencode"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT"],
        "description": "OpenCode agent interface",
        "category": "code-assistant"
    },
    {
        "id": "roo",
        "name": "Roo Code",
        "binaries": [
            "/home/jewboy420/.npm-global/bin/roo",
            "/home/jewboy420/.npm-global/bin/roo-cline",
            "roo",
            "roo-cline",
            "roocode"
        ],
        "version_cmd": ["roo", "--version"],
        "launch_cmd": "roo",
        "resume_cmd": "roo resume",
        "process_patterns": ["roo", "roo-cline"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "SESSION_RESUME"],
        "description": "Autonomous coding agent based on Cline with multi-mode architecture",
        "category": "autonomous-coder"
    },
    {
        "id": "aider",
        "name": "Aider",
        "binaries": [
            "/home/jewboy420/.local/bin/aider",
            "/home/jewboy420/hermes-env/bin/aider",
            "aider"
        ],
        "version_cmd": ["aider", "--version"],
        "launch_cmd": "aider",
        "resume_cmd": "aider --restore",
        "process_patterns": ["aider"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "GIT_INTEGRATION"],
        "description": "AI pair programming in your terminal with Git repo map integration",
        "category": "autonomous-coder"
    },
    {
        "id": "kimi",
        "name": "Kimi Code",
        "binaries": [
            "/home/jewboy420/.local/bin/kimi",
            "kimi",
            "kimi-cli"
        ],
        "version_cmd": ["kimi", "--version"],
        "launch_cmd": "kimi",
        "resume_cmd": None,
        "process_patterns": ["kimi"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT"],
        "description": "Moonshot Kimi coding agent with long-context reasoning",
        "category": "code-assistant"
    },
    {
        "id": "qwen",
        "name": "Qwen Code",
        "binaries": [
            "/home/jewboy420/.local/bin/qwen",
            "qwen",
            "qwen-code"
        ],
        "version_cmd": ["qwen", "--version"],
        "launch_cmd": "qwen",
        "resume_cmd": None,
        "process_patterns": ["qwen"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT"],
        "description": "Alibaba Qwen Code terminal assistant and code generator",
        "category": "code-assistant"
    },
    {
        "id": "goose",
        "name": "Goose",
        "binaries": [
            "/home/jewboy420/.local/bin/goose",
            "goose"
        ],
        "version_cmd": ["goose", "--version"],
        "launch_cmd": "goose session",
        "resume_cmd": "goose session resume",
        "process_patterns": ["goose"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "SESSION_RESUME", "MCP"],
        "description": "Block's open-source extensible AI developer agent with MCP support",
        "category": "autonomous-coder"
    },
    {
        "id": "openhands",
        "name": "OpenHands",
        "binaries": [
            "/home/jewboy420/.local/bin/openhands",
            "openhands",
            "opendevin"
        ],
        "version_cmd": ["openhands", "--version"],
        "launch_cmd": "openhands",
        "resume_cmd": None,
        "process_patterns": ["openhands", "opendevin"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "CONTAINER_AWARE"],
        "description": "All-Hands autonomous software development agent",
        "category": "autonomous-coder"
    },
    {
        "id": "continue",
        "name": "Continue CLI",
        "binaries": [
            "/home/jewboy420/.npm-global/bin/continue",
            "continue",
            "cn"
        ],
        "version_cmd": ["continue", "--version"],
        "launch_cmd": "continue",
        "resume_cmd": None,
        "process_patterns": ["continue"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "MCP"],
        "description": "Open-source AI code assistant CLI with custom models",
        "category": "code-assistant"
    },
    {
        "id": "cursor",
        "name": "Cursor CLI",
        "binaries": [
            "/home/jewboy420/.local/bin/cursor",
            "cursor",
            "cursor-agent"
        ],
        "version_cmd": ["cursor", "--version"],
        "launch_cmd": "cursor",
        "resume_cmd": None,
        "process_patterns": ["cursor"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT"],
        "description": "Cursor terminal integration and agentic command tools",
        "category": "cli-tools"
    },
    {
        "id": "codebuff",
        "name": "Codebuff",
        "binaries": [
            "/home/jewboy420/.npm-global/bin/codebuff",
            "/home/jewboy420/.local/bin/codebuff",
            "/usr/local/bin/codebuff",
            "codebuff",
            "cb"
        ],
        "version_cmd": ["codebuff", "--version"],
        "launch_cmd": "codebuff",
        "resume_cmd": "codebuff",
        "process_patterns": ["codebuff", "cb"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "SESSION_RESUME"],
        "description": "AI coding agent by CodebuffAI",
        "category": "autonomous-coder"
    },
    {
        "id": "crush",
        "name": "Crush",
        "binaries": [
            "/usr/bin/crush",
            "/usr/local/bin/crush",
            "/home/jewboy420/.local/bin/crush",
            "crush"
        ],
        "version_cmd": ["crush", "--version"],
        "launch_cmd": "crush",
        "resume_cmd": "crush",
        "process_patterns": ["crush"],
        "capabilities": ["PTY", "INTERACTIVE", "PROMPT", "SESSION_RESUME"],
        "description": "Glamorous terminal-first AI assistant by Charmbracelet",
        "category": "autonomous-coder"
    }
]

# Cache detected versions to avoid repeated spawning
_version_cache: Dict[str, str] = {}
_cache_ts: float = 0


def discover_agent_binary(binaries: List[str]) -> Optional[str]:
    for b in binaries:
        if os.path.exists(b) and os.access(b, os.X_OK):
            return b
        found = shutil.which(b)
        if found:
            return found
    return None


def get_agent_version(agent_id: str, version_cmd: List[str], bin_path: Optional[str] = None) -> str:
    global _cache_ts
    if time.time() - _cache_ts > 60:
        _version_cache.clear()
        _cache_ts = time.time()
        
    if agent_id in _version_cache:
        return _version_cache[agent_id]
        
    actual_bin = bin_path or discover_agent_binary([version_cmd[0]])
    if not actual_bin:
        return "Not found"
        
    cmd = [actual_bin] + version_cmd[1:]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.5, stdin=subprocess.DEVNULL)
        raw = res.stdout.strip() or res.stderr.strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        v = "Unknown"
        # Look for a line containing 'version' or digits
        for l in lines:
            if "version" in l.lower() or any(c.isdigit() for c in l):
                v = l
                break
        if v == "Unknown" and lines:
            v = lines[0]
        if len(v) > 50:
            v = v[:47] + "..."
        _version_cache[agent_id] = v
        return v
    except Exception:
        return "Installed"


def get_running_agent_processes() -> Dict[str, List[Dict[str, Any]]]:
    """Scans system processes to find running instances of all known agents."""
    running_by_agent: Dict[str, List[Dict[str, Any]]] = {a["id"]: [] for a in AGENT_DEFINITIONS}
    
    try:
        for p in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_percent', 'create_time', 'username']):
            try:
                cmd = " ".join(p.info.get('cmdline') or []).lower()
                pname = (p.info.get('name') or "").lower()
                
                # Check each agent definition
                for a in AGENT_DEFINITIONS:
                    matched = False
                    for pattern in a["process_patterns"]:
                        pat = pattern.lower()
                        if pat in pname or f"/{pat}" in cmd or f" {pat}" in cmd or cmd.startswith(pat):
                            matched = True
                            break
                    
                    # Avoid false positives (e.g. grep, editors, terminus itself)
                    if matched and "terminus" not in cmd and "grep" not in cmd and "python3 -c" not in cmd:
                        running_by_agent[a["id"]].append({
                            "pid": p.info['pid'],
                            "name": p.info['name'],
                            "cpu": round(p.info['cpu_percent'] or 0.0, 1),
                            "mem": round(p.info['memory_percent'] or 0.0, 1),
                            "uptime_sec": int(time.time() - (p.info['create_time'] or time.time())),
                            "cmd": " ".join(p.info.get('cmdline') or [])[:120]
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
        
    return running_by_agent


def get_all_agents() -> List[Dict[str, Any]]:
    """Returns all discovered agents with installation, version, and running status."""
    from concurrent.futures import ThreadPoolExecutor

    running_map = get_running_agent_processes()
    agent_bins = {a["id"]: discover_agent_binary(a["binaries"]) for a in AGENT_DEFINITIONS}

    def fetch_ver(a):
        bin_path = agent_bins[a["id"]]
        if not bin_path:
            return a["id"], None
        return a["id"], get_agent_version(a["id"], a["version_cmd"], bin_path=bin_path)

    with ThreadPoolExecutor(max_workers=8) as ex:
        ver_results = dict(ex.map(fetch_ver, AGENT_DEFINITIONS))

    results = []
    for a in AGENT_DEFINITIONS:
        bin_path = agent_bins[a["id"]]
        installed = bin_path is not None
        version = ver_results.get(a["id"]) if installed else None
        running_procs = running_map.get(a["id"], [])
        
        results.append({
            "id": a["id"],
            "name": a["name"],
            "installed": installed,
            "path": bin_path,
            "version": version,
            "launch_cmd": a["launch_cmd"],
            "resume_cmd": a["resume_cmd"],
            "capabilities": a["capabilities"],
            "description": a["description"],
            "category": a["category"],
            "running_count": len(running_procs),
            "processes": running_procs
        })
        
    return results


def get_agent_adapter(agent_id: str) -> Optional[Dict[str, Any]]:
    if not agent_id:
        return None
    aid = agent_id.lower()
    for a in AGENT_DEFINITIONS:
        if a["id"] == aid or (aid == "agy" and a["id"] == "antigravity") or (aid == "sh" and a["id"] == "shell"):
            return a
    return None
