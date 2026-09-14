"""
Terminus Solo Hermes & FreeInference Integration Hub
Provides real-time model switching, configuration overview, and Hermes service status.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

HERMES_DIR = Path.home() / ".hermes"
HERMES_CONFIG_FILE = HERMES_DIR / "config.yaml"
HERMES_ENV_FILE = HERMES_DIR / ".env"

AVAILABLE_MODELS = [
    {"id": "kimi-k2.7-code", "name": "Moonshot Kimi K2.7 Code", "context": "256k", "provider": "FreeInference"},
    {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "context": "1000k", "provider": "FreeInference"},
    {"id": "glm-5.3-flash", "name": "Zhipu GLM-5.3 Flash", "context": "1000k", "provider": "FreeInference"},
    {"id": "minimax-m3", "name": "MiniMax M3 Pro", "context": "1048k", "provider": "FreeInference"},
    {"id": "qwen3.6-35b", "name": "Alibaba Qwen 3.6 35B", "context": "256k", "provider": "FreeInference"},
    {"id": "opencode/deepseek-v4-flash-free", "name": "OpenCode DeepSeek V4 Free", "context": "128k", "provider": "OpenCode"}
]


def load_hermes_config() -> Dict[str, Any]:
    if not HERMES_CONFIG_FILE.exists():
        return {}
    try:
        with open(HERMES_CONFIG_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def save_hermes_config(cfg: Dict[str, Any]) -> bool:
    try:
        with open(HERMES_CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False)
        return True
    except Exception:
        return False


def get_hermes_status() -> Dict[str, Any]:
    cfg = load_hermes_config()
    current_model = cfg.get("model", {}).get("default") or cfg.get("providers", {}).get("freeinference", {}).get("model", "kimi-k2.7-code")
    provider = cfg.get("model", {}).get("provider", "freeinference")
    discord_cfg = cfg.get("messaging", {}).get("discord", {})

    import subprocess
    is_dashboard_running = False
    try:
        out = subprocess.check_output(["pgrep", "-f", "hermes serve"], text=True)
        is_dashboard_running = bool(out.strip())
    except Exception:
        is_dashboard_running = False

    return {
        "is_configured": bool(cfg),
        "is_dashboard_running": is_dashboard_running,
        "dashboard_port": 9119,
        "dashboard_url": "http://10.0.0.171:9119",
        "current_model": current_model,
        "provider": provider,
        "discord_enabled": discord_cfg.get("enabled", False),
        "available_models": AVAILABLE_MODELS
    }


def set_active_model(model_id: str) -> Dict[str, Any]:
    cfg = load_hermes_config()
    if not cfg:
        cfg = {"model": {}}
    if "model" not in cfg:
        cfg["model"] = {}

    cfg["model"]["default"] = model_id
    if "providers" in cfg and "freeinference" in cfg["providers"]:
        cfg["providers"]["freeinference"]["model"] = model_id

    success = save_hermes_config(cfg)
    return {
        "success": success,
        "new_model": model_id,
        "status": get_hermes_status()
    }
