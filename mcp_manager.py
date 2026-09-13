import json
import os
from pathlib import Path
from typing import List, Dict, Any

def get_mcp_servers() -> List[Dict[str, Any]]:
    servers = []
    
    # 1. Claude Code MCP Config (~/.claude.json)
    claude_cfg = Path("/home/jewboy420/.claude.json")
    if claude_cfg.exists():
        try:
            data = json.loads(claude_cfg.read_text())
            mcp_dict = data.get("mcpServers", {})
            for name, cfg in mcp_dict.items():
                servers.append({
                    "name": name,
                    "agent": "Claude Code",
                    "agent_id": "claude",
                    "command": cfg.get("command", ""),
                    "args": cfg.get("args", []),
                    "transport": "stdio" if "command" in cfg else "sse",
                    "env_keys": list(cfg.get("env", {}).keys()),
                    "status": "configured",
                    "source": "~/.claude.json"
                })
        except Exception:
            pass

    # 2. Gemini / Antigravity MCP Config (~/.gemini/config/mcp_config.json)
    gemini_cfg = Path("/home/jewboy420/.gemini/config/mcp_config.json")
    if gemini_cfg.exists():
        try:
            data = json.loads(gemini_cfg.read_text())
            mcp_dict = data.get("mcpServers", {})
            for name, cfg in mcp_dict.items():
                servers.append({
                    "name": name,
                    "agent": "Gemini / Antigravity",
                    "agent_id": "antigravity",
                    "command": cfg.get("command", ""),
                    "args": cfg.get("args", []),
                    "transport": cfg.get("transport", "stdio"),
                    "env_keys": list(cfg.get("env", {}).keys()),
                    "status": "active" if name == "blender" else "configured",
                    "source": "~/.gemini/config/mcp_config.json"
                })
        except Exception:
            pass

    # 3. Dedicated Project MCP Servers (e.g. blender-mcp-server, horus, geovision)
    known_local_mcps = [
        {
            "name": "blender-mcp",
            "agent": "Multi-Agent Universal",
            "agent_id": "all",
            "command": "python3 /home/jewboy420/blender-mcp-server/server.py",
            "args": ["--port", "8765"],
            "transport": "stdio",
            "env_keys": ["BLENDER_PATH"],
            "status": "ready",
            "source": "~/blender-mcp-server"
        },
        {
            "name": "geovision-tools",
            "agent": "Geovision Agent",
            "agent_id": "geovision",
            "command": "python3 /home/jewboy420/geovision/mcp_geovision_server.py",
            "args": [],
            "transport": "stdio",
            "env_keys": [],
            "status": "ready",
            "source": "~/geovision"
        },
        {
            "name": "hermes-tools",
            "agent": "Hermes Agent",
            "agent_id": "hermes",
            "command": "/home/jewboy420/hermes-env/bin/python /home/jewboy420/.hermes/hermes-agent/mcp_serve.py",
            "args": [],
            "transport": "stdio",
            "env_keys": ["OPENCODE_ZEN_API_KEY"],
            "status": "ready",
            "source": "~/.hermes"
        }
    ]

    existing_names = {s["name"] for s in servers}
    for m in known_local_mcps:
        if m["name"] not in existing_names:
            servers.append(m)

    return servers
