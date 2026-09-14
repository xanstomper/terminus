"""
Terminus Chat Engine — Structured conversation API with SSE streaming.
Provides a ChatGPT/Codex IDE-style interface for talking to AI models directly,
without requiring a PTY terminal. Supports multiple LLM providers.
"""

import os
import json
import time
import uuid
import asyncio
import httpx
from pathlib import Path
from typing import Dict, List, Optional, Any, AsyncGenerator

# ── Storage ──────────────────────────────────────────────────
CHAT_DIR = Path.home() / ".terminus" / "chat"
THREADS_FILE = CHAT_DIR / "threads.json"
CHAT_DIR.mkdir(parents=True, exist_ok=True)

# ── Provider Registry ────────────────────────────────────────
PROVIDERS = {
    "opencode-zen": {
        "name": "OpenCode Zen",
        "base_url": "https://opencode.ai/zen/v1",
        "env_key": "OPENCODE_ZEN_API_KEY",
        "models": [
            {"id": "opencode/deepseek-v4-flash-free", "name": "DeepSeek V4 Flash (Free)", "context": 131072},
            {"id": "opencode/deepseek-v4-flash", "name": "DeepSeek V4 Flash", "context": 131072},
            {"id": "opencode/opencode-zen-3.5", "name": "OpenCode Zen 3.5", "context": 131072},
            {"id": "opencode/gpt-5.4-nano", "name": "GPT 5.4 Nano", "context": 131072},
        ]
    },
    "opencode-go": {
        "name": "OpenCode Go",
        "base_url": "https://opencode.ai/go/v1",
        "env_key": "OPENCODE_GO_API_KEY",
        "models": [
            {"id": "opencode-go/deepseek-v4-flash", "name": "DeepSeek V4 Flash (Go)", "context": 131072},
            {"id": "opencode-go/deepseek-v4-flash-free", "name": "DeepSeek V4 Flash Free (Go)", "context": 131072},
        ]
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "models": [
            {"id": "gpt-4o", "name": "GPT-4o", "context": 128000},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context": 128000},
            {"id": "o3-mini", "name": "o3-mini", "context": 200000},
        ]
    },
    "anthropic": {
        "name": "Anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        "models": [
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "context": 200000},
            {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "context": 200000},
        ]
    },
    "ollama": {
        "name": "Ollama (Local)",
        "base_url": "http://localhost:11434/v1",
        "env_key": None,
        "models": []  # Dynamically discovered
    },
}


def _load_env_keys() -> Dict[str, str]:
    """Load API keys from ~/.hermes/.env and environment."""
    keys = {}
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if v:
                    keys[k] = v
    # Also check OS environment
    for provider in PROVIDERS.values():
        env_key = provider.get("env_key")
        if env_key and env_key not in keys:
            val = os.environ.get(env_key)
            if val:
                keys[env_key] = val
    return keys


def get_api_key(provider_id: str) -> Optional[str]:
    """Get API key for a provider."""
    provider = PROVIDERS.get(provider_id)
    if not provider or not provider.get("env_key"):
        return None
    keys = _load_env_keys()
    return keys.get(provider["env_key"])


def get_available_providers() -> List[Dict]:
    """Return providers with their availability status."""
    keys = _load_env_keys()
    result = []
    for pid, p in PROVIDERS.items():
        has_key = True
        if p.get("env_key"):
            has_key = p["env_key"] in keys
        result.append({
            "id": pid,
            "name": p["name"],
            "available": has_key,
            "models": p["models"],
        })
    return result


# ── Thread Storage ───────────────────────────────────────────
def _load_threads() -> List[Dict]:
    if THREADS_FILE.exists():
        try:
            return json.loads(THREADS_FILE.read_text())
        except Exception:
            return []
    return []


def _save_threads(threads: List[Dict]):
    THREADS_FILE.write_text(json.dumps(threads, indent=2))


def _load_messages(thread_id: str) -> List[Dict]:
    msg_file = CHAT_DIR / f"{thread_id}.json"
    if msg_file.exists():
        try:
            return json.loads(msg_file.read_text())
        except Exception:
            return []
    return []


def _save_messages(thread_id: str, messages: List[Dict]):
    msg_file = CHAT_DIR / f"{thread_id}.json"
    msg_file.write_text(json.dumps(messages, indent=2))


def list_threads() -> List[Dict]:
    return _load_threads()


def create_thread(title: str = "New Chat", provider_id: str = "opencode-zen",
                   model_id: str = "opencode/deepseek-v4-flash-free",
                   system_prompt: str = "") -> Dict:
    threads = _load_threads()
    thread = {
        "id": f"chat-{uuid.uuid4().hex[:12]}",
        "title": title,
        "provider_id": provider_id,
        "model_id": model_id,
        "system_prompt": system_prompt,
        "created_at": time.time(),
        "updated_at": time.time(),
        "message_count": 0,
    }
    threads.insert(0, thread)
    _save_threads(threads)
    # Initialize with system prompt if provided
    if system_prompt:
        _save_messages(thread["id"], [
            {"role": "system", "content": system_prompt, "timestamp": time.time()}
        ])
    else:
        _save_messages(thread["id"], [])
    return thread


def get_thread(thread_id: str) -> Optional[Dict]:
    threads = _load_threads()
    for t in threads:
        if t["id"] == thread_id:
            return t
    return None


def update_thread(thread_id: str, updates: Dict) -> Optional[Dict]:
    threads = _load_threads()
    for t in threads:
        if t["id"] == thread_id:
            t.update(updates)
            t["updated_at"] = time.time()
            _save_threads(threads)
            return t
    return None


def delete_thread(thread_id: str) -> bool:
    threads = _load_threads()
    new_threads = [t for t in threads if t["id"] != thread_id]
    if len(new_threads) == len(threads):
        return False
    _save_threads(new_threads)
    msg_file = CHAT_DIR / f"{thread_id}.json"
    if msg_file.exists():
        msg_file.unlink()
    return True


def get_messages(thread_id: str) -> List[Dict]:
    return _load_messages(thread_id)


def add_message(thread_id: str, role: str, content: str) -> Dict:
    messages = _load_messages(thread_id)
    msg = {
        "id": f"msg-{uuid.uuid4().hex[:10]}",
        "role": role,
        "content": content,
        "timestamp": time.time(),
    }
    messages.append(msg)
    _save_messages(thread_id, messages)
    # Update thread message count
    threads = _load_threads()
    for t in threads:
        if t["id"] == thread_id:
            t["message_count"] = len([m for m in messages if m["role"] != "system"])
            t["updated_at"] = time.time()
            break
    _save_threads(threads)
    return msg


def delete_messages_after(thread_id: str, message_id: str) -> int:
    """Delete all messages after a given message (for edit/retry)."""
    messages = _load_messages(thread_id)
    idx = None
    for i, m in enumerate(messages):
        if m.get("id") == message_id:
            idx = i
            break
    if idx is None:
        return 0
    removed = len(messages) - idx - 1
    messages = messages[:idx + 1]
    _save_messages(thread_id, messages)
    return removed


# ── LLM Streaming ────────────────────────────────────────────
async def stream_chat_completion(
    provider_id: str,
    model_id: str,
    messages: List[Dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> AsyncGenerator[str, None]:
    """
    Stream chat completion from an LLM provider.
    Yields SSE-formatted chunks: data: {"content": "...", "done": false}
    """
    provider = PROVIDERS.get(provider_id)
    if not provider:
        yield f'data: {json.dumps({"error": f"Unknown provider: {provider_id}"})}\n\n'
        return

    api_key = get_api_key(provider_id)

    base_url = provider["base_url"]
    headers = {"Content-Type": "application/json"}

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Build OpenAI-compatible request
    clean_messages = []
    for m in messages:
        if m.get("role") and m.get("content"):
            clean_messages.append({"role": m["role"], "content": m["content"]})

    payload = {
        "model": model_id,
        "messages": clean_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    error_body = ""
                    async for chunk in response.aiter_text():
                        error_body += chunk
                    yield f'data: {json.dumps({"error": f"API error {response.status_code}: {error_body[:500]}"})}\n\n'
                    return

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            yield f'data: {json.dumps({"content": "", "done": True})}\n\n'
                            return
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield f'data: {json.dumps({"content": content, "done": False})}\n\n'
                        except json.JSONDecodeError:
                            continue

        yield f'data: {json.dumps({"content": "", "done": True})}\n\n'

    except httpx.ConnectError as e:
        yield f'data: {json.dumps({"error": f"Connection failed: {str(e)}"})}\n\n'
    except httpx.ReadTimeout:
        yield f'data: {json.dumps({"error": "Request timed out after 120s"})}\n\n'
    except Exception as e:
        yield f'data: {json.dumps({"error": f"Unexpected error: {str(e)}"})}\n\n'
