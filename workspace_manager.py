"""
Terminus Linked Workspace & Multi-Agent Matrix Manager
Coordinates multi-terminal grid layouts, inter-pane piping,
and simultaneous parallel multi-agent prompt dispatches.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

TERMINUS_DIR = Path.home() / ".terminus"
TERMINUS_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACES_FILE = TERMINUS_DIR / "workspaces.json"

DEFAULT_PRESET_WORKSPACES = [
    {
        "id": "dual_coder",
        "name": "Dual Agent Matrix",
        "description": "Side-by-side pair programming with two autonomous coders",
        "layout": "1x2",
        "panes": [
            {"id": "pane-1", "agent": "claude", "title": "Claude Code", "linked": True},
            {"id": "pane-2", "agent": "antigravity", "title": "Antigravity", "linked": True}
        ]
    },
    {
        "id": "quad_matrix",
        "name": "Quad Agent Command Matrix",
        "description": "4-pane grid running Claude, Antigravity, Hermes, and Shell concurrently",
        "layout": "2x2",
        "panes": [
            {"id": "pane-1", "agent": "claude", "title": "Claude Code", "linked": True},
            {"id": "pane-2", "agent": "antigravity", "title": "Antigravity", "linked": True},
            {"id": "pane-3", "agent": "hermes", "title": "Hermes Agent", "linked": False},
            {"id": "pane-4", "agent": "shell", "title": "Interactive Shell", "linked": False}
        ]
    },
    {
        "id": "trio_pipeline",
        "name": "Master & Workers Trio",
        "description": "Primary architectural agent on left, 2 execution and test terminals on right",
        "layout": "1+2",
        "panes": [
            {"id": "pane-1", "agent": "claude", "title": "Claude Architect", "linked": False},
            {"id": "pane-2", "agent": "mochi", "title": "Mochi Builder", "linked": True},
            {"id": "pane-3", "agent": "shell", "title": "Test & Validation Shell", "linked": True}
        ]
    },
    {
        "id": "stacked_pair",
        "name": "Stacked Horizontal Split",
        "description": "Top-bottom horizontal split for long logs and active code generation",
        "layout": "2x1",
        "panes": [
            {"id": "pane-1", "agent": "claude", "title": "Claude Code", "linked": False},
            {"id": "pane-2", "agent": "shell", "title": "Build & Server Shell", "linked": False}
        ]
    }
]


def load_workspaces() -> List[Dict[str, Any]]:
    if not WORKSPACES_FILE.exists():
        save_workspaces(DEFAULT_PRESET_WORKSPACES)
        return DEFAULT_PRESET_WORKSPACES
    try:
        with open(WORKSPACES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_PRESET_WORKSPACES


def save_workspaces(workspaces: List[Dict[str, Any]]):
    try:
        with open(WORKSPACES_FILE, "w", encoding="utf-8") as f:
            json.dump(workspaces, f, indent=2)
    except Exception:
        pass


def get_workspace(workspace_id: str) -> Optional[Dict[str, Any]]:
    for ws in load_workspaces():
        if ws.get("id") == workspace_id:
            return ws
    return None
