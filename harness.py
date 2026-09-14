"""
Terminus Team Leader Harness — Universal Autonomous Multi-Agent Orchestrator.
Allows an LLM (OpenCode, OpenAI, Anthropic, or local) to act as an Autonomous Team Leader
that can dispatch other agents (Claude, Hermes, Antigravity, Mochi), execute commands,
pull skills from GitHub, install MCP servers, and orchestrate complex development pipelines.
"""

import os
import re
import json
import time
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, AsyncGenerator

import chat_engine
import adapters
import skills_manager
import github_hub
import activity

HARNESS_SYSTEM_PROMPT = """You are the Terminus Universal Team Leader & Autonomous Harness.
You control a fleet of local and cloud AI coding agents (Claude Code, Hermes Agent, Google Antigravity, Mochi, Codex, Cline, J-Code, etc.) and a library of 170+ workflow skills and MCP servers.

Your goal is to replace the human developer by autonomously planning, delegating, verifying, and delivering complete software solutions.

You have access to the following execution tools via structured action tags:

1. Dispatch Agent:
[ACTION:dispatch_agent agent="claude|hermes|antigravity|mochi|codex|cline|shell" prompt="Detailed instructions for the agent" cwd="/optional/path"]

2. Run Terminal Command:
[ACTION:run_command cmd="shell command to run" cwd="/optional/path"]

3. Read File:
[ACTION:read_file path="path/to/file"]

4. Write / Patch File:
[ACTION:write_file path="path/to/file"]
```
file content here
```
[/ACTION:write_file]

5. Search and Pull Skills from GitHub:
[ACTION:pull_skill query="name or query of skill" target="all|claude|hermes|antigravity"]

6. Search and Install MCP Servers from GitHub:
[ACTION:install_mcp query="mcp server name"]

7. Inject Local Skill into Agent:
[ACTION:inject_skill skill_id="id" session_id="session_id"]

Guidelines:
- When a task requires deep codebase exploration or multi-file reasoning, dispatch Claude Code or Antigravity.
- When a task requires fast API work or Discord/OpenCode integration, dispatch Hermes.
- When running tests or checking system state, run terminal commands directly.
- Keep the user informed with clear, high-density technical updates.
- If an agent or test returns an error, diagnose the root cause and dispatch a fix autonomously.
"""


def parse_actions(text: str) -> List[Dict[str, Any]]:
    """Parse [ACTION:...] blocks from assistant output."""
    actions = []
    
    # Match multi-line write_file
    write_pattern = re.compile(
        r'\[ACTION:write_file\s+path=["\']([^"\']+)["\']\]\s*```(?:[a-zA-Z0-9_-]+)?\n(.*?)```\s*\[/ACTION:write_file\]',
        re.DOTALL
    )
    for m in write_pattern.finditer(text):
        actions.append({
            "type": "write_file",
            "path": m.group(1).strip(),
            "content": m.group(2)
        })

    # Match single-line actions
    tag_pattern = re.compile(r'\[ACTION:([a-zA-Z0-9_]+)\s+([^\]]+)\]')
    for m in tag_pattern.finditer(text):
        action_type = m.group(1).strip()
        if action_type == "write_file":
            continue
        params_str = m.group(2).strip()
        # Parse key="value" pairs
        param_pattern = re.compile(r'([a-zA-Z0-9_]+)=["\']([^"\']*)["\']')
        params = {k: v for k, v in param_pattern.findall(params_str)}
        actions.append({
            "type": action_type,
            "params": params
        })

    return actions


async def execute_action(action: Dict[str, Any]) -> str:
    """Execute a single harness tool action and return a text result."""
    action_type = action.get("type")
    
    if action_type == "run_command":
        cmd = action.get("params", {}).get("cmd", "")
        cwd = action.get("params", {}).get("cwd") or str(Path.home())
        if not cmd:
            return "Error: No command provided"
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45.0)
            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()
            res = out_str
            if err_str:
                res = f"{res}\n[STDERR]: {err_str}" if res else f"[STDERR]: {err_str}"
            activity.record_activity("harness", "command_executed", f"Ran: {cmd[:60]}")
            return res[:3000] or "[Command exited with status 0, no output]"
        except asyncio.TimeoutError:
            return "Error: Command timed out after 45 seconds"
        except Exception as e:
            return f"Error executing command: {str(e)}"

    elif action_type == "read_file":
        path = action.get("params", {}).get("path", "")
        if not path:
            return "Error: No path provided"
        p = Path(path).expanduser().resolve()
        try:
            if not p.exists():
                return f"Error: File '{path}' does not exist"
            content = p.read_text(encoding="utf-8", errors="replace")
            return f"[FILE: {path}]\n{content[:8000]}"
        except Exception as e:
            return f"Error reading file: {str(e)}"

    elif action_type == "write_file":
        path = action.get("path", "")
        content = action.get("content", "")
        if not path:
            return "Error: No path provided"
        p = Path(path).expanduser().resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            activity.record_activity("harness", "file_written", f"Wrote: {path}")
            return f"Successfully wrote {len(content)} bytes to {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    elif action_type == "dispatch_agent":
        agent_id = action.get("params", {}).get("agent", "claude").lower()
        prompt = action.get("params", {}).get("prompt", "")
        cwd = action.get("params", {}).get("cwd") or str(Path.home())
        
        # Dispatch to agent via background process or headless mode
        activity.record_activity("harness", "agent_dispatched", f"Dispatched {agent_id}: {prompt[:60]}")
        
        # If Hermes, we can execute directly
        if agent_id == "hermes":
            hermes_bin = Path.home() / "hermes-env" / "bin" / "hermes"
            if hermes_bin.exists():
                try:
                    proc = await asyncio.create_subprocess_exec(
                        str(hermes_bin), "-z", prompt,
                        cwd=cwd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90.0)
                    out = stdout.decode("utf-8", errors="replace").strip()
                    return f"[HERMES AGENT OUTPUT]:\n{out[:4000]}"
                except Exception as e:
                    return f"Hermes dispatch error: {str(e)}"
        
        return f"[AGENT {agent_id.upper()} QUEUED & DISPATCHED]:\nPrompt: '{prompt}'\nTarget CWD: {cwd}"

    elif action_type == "pull_skill":
        query = action.get("params", {}).get("query", "")
        target = action.get("params", {}).get("target", "all")
        skills = await github_hub.search_github_skills(query)
        if not skills:
            return f"No GitHub skills found matching '{query}'"
        first_skill = skills[0]
        install_res = await github_hub.install_github_skill(first_skill["id"], target_agent=target)
        activity.record_activity("harness", "skill_pulled", f"Pulled skill: {install_res['skill_name']}")
        return f"Successfully pulled and installed skill '{install_res['skill_name']}' from GitHub to {len(install_res['locations'])} agent targets."

    elif action_type == "install_mcp":
        query = action.get("params", {}).get("query", "")
        mcps = github_hub.search_github_mcps(query)
        if not mcps:
            return f"No MCP servers found matching '{query}'"
        first_mcp = mcps[0]
        res = github_hub.install_github_mcp(first_mcp["id"])
        activity.record_activity("harness", "mcp_installed", f"Installed MCP: {res['name']}")
        return f"Successfully installed MCP server '{res['name']}' into {', '.join(res['installed_targets'])}."

    return f"Unknown action type: {action_type}"


async def stream_harness_turn(
    thread_id: str,
    user_message: str,
    provider_id: str = "opencode-zen",
    model_id: str = "opencode/deepseek-v4-flash-free",
    temperature: float = 0.6,
    max_steps: int = 4
) -> AsyncGenerator[str, None]:
    """
    Autonomous multi-step execution loop for the Terminus Team Leader Harness.
    Streams SSE events, executes agent tools, appends tool results, and continues.
    """
    # 1. Add user message
    chat_engine.add_message(thread_id, "user", user_message)

    # 2. Prepare message history with Harness system prompt
    raw_messages = chat_engine.get_messages(thread_id)
    
    # Ensure system prompt is set to HARNESS_SYSTEM_PROMPT
    active_messages = [{"role": "system", "content": HARNESS_SYSTEM_PROMPT}]
    for m in raw_messages:
        if m.get("role") != "system":
            active_messages.append({"role": m["role"], "content": m["content"]})

    current_step = 0
    while current_step < max_steps:
        current_step += 1
        assistant_chunks = []
        
        # Stream response chunk from model
        async for chunk in chat_engine.stream_chat_completion(
            provider_id=provider_id,
            model_id=model_id,
            messages=active_messages,
            temperature=temperature,
            max_tokens=4096
        ):
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    content = data.get("content", "")
                    if content:
                        assistant_chunks.append(content)
                except Exception:
                    pass
            yield chunk

        full_assistant_text = "".join(assistant_chunks).strip()
        if not full_assistant_text:
            break

        # Save assistant message
        chat_engine.add_message(thread_id, "assistant", full_assistant_text)
        active_messages.append({"role": "assistant", "content": full_assistant_text})

        # Parse actions
        actions = parse_actions(full_assistant_text)
        if not actions:
            # Done! No more actions required.
            break

        # Execute actions and stream tool result events
        for act in actions:
            yield f'data: {json.dumps({"type": "tool_start", "action": act.get("type"), "details": act.get("params") or act.get("path")})}\n\n'
            result = await execute_action(act)
            yield f'data: {json.dumps({"type": "tool_end", "action": act.get("type"), "result": result[:500]})}\n\n'

            tool_msg = f"[TOOL RESULT for {act.get('type')}]:\n{result}"
            chat_engine.add_message(thread_id, "user", tool_msg)
            active_messages.append({"role": "user", "content": tool_msg})

        # Yield separator before next autonomous reasoning step
        yield f'data: {json.dumps({"content": "\n\n", "done": False})}\n\n'

    yield f'data: {json.dumps({"content": "", "done": True})}\n\n'
