import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

MEMORY_FILE = Path.home() / ".terminus" / "memory.json"

DEFAULT_MEMORIES = [
    {
        "id": "mem-arch-001",
        "title": "Machine & Agent Runtime Architecture",
        "content": "Host machine 'jewboy420' running Linux with Intel UHD Graphics and 16 GB RAM. Installed coding agents: Claude Code, Hermes (in ~/hermes-env), Antigravity (agy), Mochi, Codex K, Cline, J-Code, OpenCode. Terminus control plane runs on port 9120 and Hermes dashboard runs on port 9119.",
        "agent_origin": "Terminus Core",
        "tags": ["architecture", "machine", "agents", "network"],
        "timestamp": time.time() - 7200,
        "is_system": True
    },
    {
        "id": "mem-opencode-002",
        "title": "OpenCode Provider Configuration",
        "content": "Hermes and OpenCode tools use opencode.ai/zen/v1 and opencode.ai/go/v1. Free model: opencode/deepseek-v4-flash-free. Full credentials stored in ~/.hermes/.env.",
        "agent_origin": "Hermes Agent",
        "tags": ["opencode", "models", "api-keys"],
        "timestamp": time.time() - 3600,
        "is_system": False
    },
    {
        "id": "mem-mcp-003",
        "title": "Multi-Agent MCP Resource Bridges",
        "content": "Universal MCP servers active: blender-mcp (port 8765), geovision-tools, and hermes-tools. Configured in ~/.claude.json, ~/.gemini/config/mcp_config.json, and ~/.hermes/config.yaml.",
        "agent_origin": "Universal MCP",
        "tags": ["mcp", "blender", "tools", "bridge"],
        "timestamp": time.time() - 1800,
        "is_system": False
    }
]

def load_memories() -> List[Dict[str, Any]]:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not MEMORY_FILE.exists():
        save_memories(DEFAULT_MEMORIES)
        return DEFAULT_MEMORIES.copy()
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return DEFAULT_MEMORIES.copy()

def save_memories(memories: List[Dict[str, Any]]) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(memories, indent=2), encoding="utf-8")

def get_all_memories(query: Optional[str] = None, agent: Optional[str] = None) -> List[Dict[str, Any]]:
    mems = load_memories()
    now = time.time()

    # Format human time
    for m in mems:
        diff = now - m.get("timestamp", now)
        if diff < 60:
            m["time_str"] = "Just now"
        elif diff < 3600:
            m["time_str"] = f"{int(diff // 60)}m ago"
        elif diff < 86400:
            m["time_str"] = f"{int(diff // 3600)}h ago"
        else:
            m["time_str"] = time.strftime("%b %d %Y", time.localtime(m["timestamp"]))

    if query:
        q = query.lower().strip()
        mems = [m for m in mems if q in m["title"].lower() or q in m["content"].lower() or any(q in t.lower() for t in m.get("tags", []))]

    if agent and agent.lower() != "all":
        a = agent.lower()
        mems = [m for m in mems if a in m["agent_origin"].lower()]

    mems.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return mems

def add_memory(title: str, content: str, agent_origin: str = "User / Shared", tags: List[str] = None) -> Dict[str, Any]:
    mems = load_memories()
    new_id = f"mem-{int(time.time() * 1000) % 1000000}"
    entry = {
        "id": new_id,
        "title": title.strip(),
        "content": content.strip(),
        "agent_origin": agent_origin.strip(),
        "tags": tags or ["shared"],
        "timestamp": time.time(),
        "is_system": False
    }
    mems.insert(0, entry)
    save_memories(mems)
    return entry

def delete_memory(memory_id: str) -> bool:
    mems = load_memories()
    initial_len = len(mems)
    mems = [m for m in mems if m["id"] != memory_id]
    if len(mems) < initial_len:
        save_memories(mems)
        return True
    return False

def get_shared_context_summary() -> str:
    mems = load_memories()
    lines = ["# Cross-Agent Shared Memory Bank:"]
    for m in mems:
        lines.append(f"- [{m['agent_origin']}] {m['title']}: {m['content']}")
    return "\n".join(lines)
