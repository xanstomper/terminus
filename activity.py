import time
from typing import List, Dict, Any, Optional

_MAX_ACTIVITIES = 150
_activity_log: List[Dict[str, Any]] = [
    {
        "id": "act-init-1",
        "timestamp": time.time() - 3600,
        "time_str": "1h ago",
        "agent": "claude",
        "agent_name": "Claude Code",
        "action": "session_resumed",
        "title": "Claude Code active on project nemu",
        "details": "Investigating audio subsystem & PTY stream",
        "project": "nemu",
        "path": "/home/jewboy420/nemu",
        "status": "success"
    },
    {
        "id": "act-init-2",
        "timestamp": time.time() - 1800,
        "time_str": "30m ago",
        "agent": "hermes",
        "agent_name": "Hermes Agent",
        "action": "config_loaded",
        "title": "Hermes OpenCode Gateway initialized",
        "details": "Connected to opencode.ai/zen/v1",
        "project": "hermes-agent",
        "path": "/home/jewboy420/.hermes",
        "status": "success"
    },
    {
        "id": "act-init-3",
        "timestamp": time.time() - 900,
        "time_str": "15m ago",
        "agent": "mochi",
        "agent_name": "Mochi",
        "action": "checkpoint_created",
        "title": "Mochi created state checkpoint",
        "details": "Planning step completed for autonomous task",
        "project": "mochi",
        "path": "/home/jewboy420/mochi",
        "status": "success"
    }
]


def record_activity(
    agent: str,
    action: str,
    title: str,
    details: str = "",
    project: Optional[str] = None,
    path: Optional[str] = None,
    status: str = "success"
):
    global _activity_log
    
    # Format relative time
    now = time.time()
    entry = {
        "id": f"act-{int(now * 1000) % 1000000}",
        "timestamp": now,
        "time_str": "Just now",
        "agent": agent.lower(),
        "agent_name": agent.capitalize(),
        "action": action,
        "title": title,
        "details": details,
        "project": project,
        "path": path,
        "status": status
    }
    _activity_log.insert(0, entry)
    if len(_activity_log) > _MAX_ACTIVITIES:
        _activity_log = _activity_log[:_MAX_ACTIVITIES]


def get_activities(limit: int = 50) -> List[Dict[str, Any]]:
    now = time.time()
    result = []
    for item in _activity_log[:limit]:
        diff = now - item["timestamp"]
        if diff < 60:
            time_str = "Just now"
        elif diff < 3600:
            time_str = f"{int(diff // 60)}m ago"
        elif diff < 86400:
            time_str = f"{int(diff // 3600)}h ago"
        else:
            time_str = time.strftime("%b %d %H:%M", time.localtime(item["timestamp"]))
        
        c = dict(item)
        c["time_str"] = time_str
        result.append(c)
    return result
