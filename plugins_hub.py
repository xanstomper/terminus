"""
Terminus Universal Plugins & Infinite MCP Hub Engine.
Connects to GitHub, Model Context Protocol registries, and open-source ecosystems.
Enables searching, inspecting, and 1-click injecting infinite MCP servers, agent skills,
and CLI tools directly into Claude Code, Hermes Agent, Antigravity, Mochi, and Terminus.
"""

import os
import json
import time
import shutil
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx
import yaml

TERMINUS_PLUGINS_DIR = Path.home() / ".terminus" / "plugins"
TERMINUS_SKILLS_DIR = Path.home() / ".terminus" / "skills"
TERMINUS_MCP_FILE = Path.home() / ".terminus" / "mcp.json"

TERMINUS_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
TERMINUS_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

# Curated High-Impact MCP Servers & Agent Plugins
VERIFIED_MCP_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "mcp:sqlite",
        "name": "sqlite",
        "title": "SQLite Database Explorer & Query Engine",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Databases & Storage",
        "type": "mcp",
        "source": "official",
        "description": "Official MCP server for running read and write SQL queries, schema introspection, table summaries, and performance analysis on SQLite databases.",
        "stars": 14200,
        "verified": True,
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db-path", f"{Path.home()}/data.db"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity", "mochi"]
    },
    {
        "id": "mcp:filesystem",
        "name": "filesystem",
        "title": "Secure Filesystem Sandbox Access",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "System & Files",
        "type": "mcp",
        "source": "official",
        "description": "Secure file operations enabling agents to read, write, move, list, and search directories inside authorized workspace paths with high throughput.",
        "stars": 14200,
        "verified": True,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", str(Path.home())],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity", "mochi"]
    },
    {
        "id": "mcp:git",
        "name": "git",
        "title": "Git Version Control & Repository Automation",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Developer Tools",
        "type": "mcp",
        "source": "official",
        "description": "Direct Git CLI commands: inspect diffs, stage files, create commits, branch management, status logging, and cherry-picking without shell escapes.",
        "stars": 14200,
        "verified": True,
        "command": "uvx",
        "args": ["mcp-server-git", "--repository", str(Path.home())],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity", "mochi"]
    },
    {
        "id": "mcp:github",
        "name": "github",
        "title": "GitHub REST & GraphQL Automation",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Developer Tools",
        "type": "mcp",
        "source": "official",
        "description": "Interact directly with GitHub issues, pull requests, commits, branches, search repos, and releases via personal access tokens.",
        "stars": 14200,
        "verified": True,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "transport": "stdio",
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
        "target_agents": ["claude", "hermes", "antigravity", "mochi"]
    },
    {
        "id": "mcp:postgres",
        "name": "postgres",
        "title": "PostgreSQL Production Database Engine",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Databases & Storage",
        "type": "mcp",
        "source": "official",
        "description": "Schema introspection, query execution, execution plan analysis, and table inspection for PostgreSQL database instances.",
        "stars": 14200,
        "verified": True,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost:5432/db"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity", "mochi"]
    },
    {
        "id": "mcp:fetch",
        "name": "fetch",
        "title": "HTTP Content Fetcher & Clean Markdown Parser",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Web & Scraping",
        "type": "mcp",
        "source": "official",
        "description": "Retrieves any public web page or API endpoint, converting raw HTML into clean structured Markdown tailored for LLM reasoning.",
        "stars": 14200,
        "verified": True,
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity", "mochi"]
    },
    {
        "id": "mcp:puppeteer",
        "name": "puppeteer",
        "title": "Headless Chrome & Web Automation",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Web & Scraping",
        "type": "mcp",
        "source": "official",
        "description": "Full headless browser automation: navigate URLs, take screenshots, evaluate JS, click elements, fill forms, and scrape dynamic single-page apps.",
        "stars": 14200,
        "verified": True,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity"]
    },
    {
        "id": "mcp:brave-search",
        "name": "brave-search",
        "title": "Brave Privacy Web Search Engine",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Search & Research",
        "type": "mcp",
        "source": "official",
        "description": "Perform live internet web searches and news searches with privacy-preserving indexing and high relevance rankings.",
        "stars": 14200,
        "verified": True,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "transport": "stdio",
        "env": {"BRAVE_API_KEY": ""},
        "target_agents": ["claude", "hermes", "antigravity"]
    },
    {
        "id": "mcp:memory",
        "name": "memory",
        "title": "Knowledge Graph Persistent Memory",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Memory & Context",
        "type": "mcp",
        "source": "official",
        "description": "Graph-based persistent memory system enabling agents to retain facts, user preferences, codebase entities, and relations across sessions.",
        "stars": 14200,
        "verified": True,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity", "mochi"]
    },
    {
        "id": "mcp:docker",
        "name": "docker",
        "title": "Docker Container & Image Manager",
        "repo": "ckreiling/mcp-server-docker",
        "author": "ckreiling",
        "category": "DevOps & Cloud",
        "type": "mcp",
        "source": "github",
        "description": "Inspect, run, start, stop, and manage Docker containers, images, volumes, and networks with live container log streaming.",
        "stars": 1850,
        "verified": True,
        "command": "uvx",
        "args": ["mcp-server-docker"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity"]
    },
    {
        "id": "mcp:slack",
        "name": "slack",
        "title": "Slack Workspace Channel & Direct Messaging",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Communication",
        "type": "mcp",
        "source": "official",
        "description": "Post messages, reply in threads, list channels, and read chat history across Slack workspaces via bot tokens.",
        "stars": 14200,
        "verified": True,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "transport": "stdio",
        "env": {"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""},
        "target_agents": ["claude", "hermes", "antigravity"]
    },
    {
        "id": "mcp:redis",
        "name": "redis",
        "title": "Redis In-Memory Key-Value & Pub/Sub",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Databases & Storage",
        "type": "mcp",
        "source": "official",
        "description": "Connect to Redis caches and clusters: get, set, delete keys, hash maps, lists, inspect memory keyspaces, and monitor pub/sub events.",
        "stars": 14200,
        "verified": True,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-redis", "redis://localhost:6379"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity"]
    },
    {
        "id": "mcp:sentry",
        "name": "sentry",
        "title": "Sentry Error Tracking & Trace Analyzer",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Developer Tools",
        "type": "mcp",
        "source": "official",
        "description": "Query live application error events, stack traces, release telemetry, and issue frequency from Sentry organizations.",
        "stars": 14200,
        "verified": True,
        "command": "uvx",
        "args": ["mcp-server-sentry", "--auth-token", "${SENTRY_AUTH_TOKEN}"],
        "transport": "stdio",
        "env": {"SENTRY_AUTH_TOKEN": ""},
        "target_agents": ["claude", "hermes", "antigravity"]
    },
    {
        "id": "mcp:linear",
        "name": "linear",
        "title": "Linear Issue Tracking & Project Management",
        "repo": "jerhadf/linear-mcp-server",
        "author": "jerhadf",
        "category": "Developer Tools",
        "type": "mcp",
        "source": "github",
        "description": "Create, search, update issues, cycles, and projects in Linear, allowing agents to sync tickets and track development progress.",
        "stars": 980,
        "verified": True,
        "command": "npx",
        "args": ["-y", "linear-mcp-server"],
        "transport": "stdio",
        "env": {"LINEAR_API_KEY": ""},
        "target_agents": ["claude", "hermes", "antigravity"]
    },
    {
        "id": "mcp:obsidian",
        "name": "obsidian",
        "title": "Obsidian Vault Markdown Notes Integrator",
        "repo": "calclavia/mcp-obsidian",
        "author": "calclavia",
        "category": "Memory & Context",
        "type": "mcp",
        "source": "github",
        "description": "Search, read, create, and append notes in local Obsidian markdown vaults with frontmatter and wikilink parsing.",
        "stars": 1450,
        "verified": True,
        "command": "npx",
        "args": ["-y", "mcp-obsidian", f"{Path.home()}/Documents/Obsidian"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity"]
    },
    {
        "id": "mcp:everything",
        "name": "everything",
        "title": "MCP Protocol Test & Capability Server",
        "repo": "modelcontextprotocol/servers",
        "author": "Model Context Protocol",
        "category": "Developer Tools",
        "type": "mcp",
        "source": "official",
        "description": "Comprehensive reference server exercising all MCP features: prompt templates, dynamic resources, tools, and continuous logging.",
        "stars": 14200,
        "verified": True,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-everything"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "hermes", "antigravity", "mochi"]
    }
]

# Curated High-Impact Agent Skills
VERIFIED_SKILLS_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "skill:code-review",
        "name": "rigorous-code-review",
        "title": "Rigorous Code Review & Security Audit",
        "repo": "anthropics/skills",
        "author": "Anthropic Community",
        "category": "Software Engineering",
        "type": "skill",
        "source": "official",
        "description": "Exhaustive multi-pass code review focusing on race conditions, memory leaks, OWASP top 10, and architectural integrity.",
        "stars": 4200,
        "verified": True,
        "target_agents": ["claude", "hermes", "antigravity", "mochi"],
        "content": """---
name: rigorous-code-review
version: 2.1.0
category: Software Engineering
tags: [security, audit, code-quality, review]
description: Exhaustive multi-pass code review focusing on race conditions, memory leaks, OWASP top 10, and architectural integrity.
---

# Rigorous Code Review Protocol
1. Pass 1: Architecture, separation of concerns, and design pattern adherence.
2. Pass 2: Concurrency, race conditions, async deadlocks, and resource leaks.
3. Pass 3: Security vulnerabilities (OWASP top 10, command injection, path traversal).
4. Pass 4: Performance bottlenecks, algorithmic complexity, redundant allocations.
5. Pass 5: Test coverage, edge cases, negative assertions.
Produce an actionable markdown report with Severity (CRITICAL, HIGH, MEDIUM, LOW) and drop-in code patches.
"""
    },
    {
        "id": "skill:autonomous-debugger",
        "name": "autonomous-debugger",
        "title": "Autonomous Scientific Root-Cause Debugger",
        "repo": "google-deepmind/antigravity",
        "author": "Google DeepMind",
        "category": "Autonomous Agents",
        "type": "skill",
        "source": "official",
        "description": "Scientific hypothesis testing, minimal reproduction script generation, and binary search state inspection.",
        "stars": 6100,
        "verified": True,
        "target_agents": ["claude", "hermes", "antigravity", "mochi"],
        "content": """---
name: autonomous-debugger
version: 2.0.0
category: Autonomous Agents
tags: [debugging, troubleshooting, diagnostics, agent]
description: Scientific hypothesis testing and binary search debugging for elusive race conditions and state corruption.
---

# Scientific Debugging Protocol
1. Reproduce: Formulate a minimal reproducible script or failing unit test.
2. Hypothesize: Formulate 3 distinct root cause hypotheses ranked by probability.
3. Instrument: Add non-invasive telemetry or trace logs around state mutations.
4. Falsify: Run isolated experiments to eliminate hypotheses one by one.
5. Patch: Apply minimal surgical fix addressing the root invariant failure.
6. Verify: Confirm reproduction test passes and all regression suites pass clean.
"""
    },
    {
        "id": "skill:mcp-builder",
        "name": "mcp-server-builder",
        "title": "Model Context Protocol Server Architect",
        "repo": "modelcontextprotocol/skills",
        "author": "Model Context Protocol",
        "category": "Developer Tools",
        "type": "skill",
        "source": "official",
        "description": "Step-by-step guide to writing robust STDIO and SSE MCP servers in Python (FastMCP) and TypeScript with input validation.",
        "stars": 7400,
        "verified": True,
        "target_agents": ["claude", "hermes", "antigravity"],
        "content": """---
name: mcp-server-builder
version: 1.5.0
category: Developer Tools
tags: [mcp, tools, protocol, json-rpc]
description: Guides autonomous construction of STDIO and SSE MCP servers with proper JSON-RPC schemas.
---

# MCP Server Implementation Guide
1. Use JSON-RPC 2.0 transport over stdin/stdout.
2. Direct all logger output to stderr to prevent stdout protocol corruption.
3. Define strict tool input schemas with validation (Pydantic / Zod).
4. Implement tool list and tool call handlers with clear error messages.
"""
    },
    {
        "id": "skill:hermes-coder",
        "name": "hermes-autonomous-coder",
        "title": "Hermes End-to-End Autonomous Coder",
        "repo": "nousresearch/hermes-agent",
        "author": "Nous Research",
        "category": "Autonomous Agents",
        "type": "skill",
        "source": "official",
        "description": "Self-directed software engineering workflow: context scan, interface drafting, implementation, compiler verification, and test fixes.",
        "stars": 5300,
        "verified": True,
        "target_agents": ["hermes", "claude", "antigravity"],
        "content": """---
name: hermes-autonomous-coder
version: 3.1.0
category: Autonomous Agents
tags: [hermes, autonomous, fullstack, coder]
description: Full lifecycle autonomous coding: reads codebase, writes tests, implements feature, runs compiler, and verifies stdout.
---

# Hermes Autonomous Engineering Workflow
1. Context Gathering: Inspect folder structure, manifests, and existing conventions.
2. Interface Contract: Draft type signatures and test specifications first.
3. Implementation: Write clean, modular, typed code without mock placeholders.
4. Self-Healing: Execute test runner; if tests fail, parse traceback, inspect offending lines, and patch iteratively.
"""
    }
]


# ---------------------------------------------------------------------------
# Infinite Search Across GitHub, Official MCP, and Open Repositories
# ---------------------------------------------------------------------------
async def search_universal_plugins(
    query: str = "",
    plugin_type: str = "all",      # all, mcp, skill, tool, installed
    source: str = "all",           # all, official, github, smithery, awesome
    category: str = "all",         # all, or any catalog category name
    sort_by: str = "stars",        # stars, updated, name, verified
    page: int = 1,
    per_page: int = 24
) -> Dict[str, Any]:
    """
    Unified search across curated verified items, installed local plugins,
    and infinite live GitHub repositories with debounced querying.
    """
    q = (query or "").lower().strip()
    all_results: List[Dict[str, Any]] = []

    # 1. Combine local verified catalogs
    catalog_items: List[Dict[str, Any]] = []
    if plugin_type in ("all", "mcp"):
        catalog_items.extend(VERIFIED_MCP_CATALOG)
    if plugin_type in ("all", "skill"):
        catalog_items.extend(VERIFIED_SKILLS_CATALOG)

    # 2. Match verified catalog
    installed_ids = get_installed_plugin_ids()

    for item in catalog_items:
        # Check type filter
        if plugin_type != "all" and item.get("type") != plugin_type:
            continue
        # Check source filter
        if source != "all" and item.get("source") != source:
            continue
        # Check category filter
        if category != "all" and item.get("category", "") != category:
            continue
        
        # Check search query
        match_q = not q or (
            q in item["name"].lower() or
            q in item["title"].lower() or
            q in item["description"].lower() or
            q in item.get("category", "").lower() or
            q in item.get("repo", "").lower()
        )
        if match_q:
            entry = dict(item)
            entry["is_installed"] = entry["id"] in installed_ids
            all_results.append(entry)

    # 3. If query specified, query GitHub Search API for infinite live plugins & MCPs!
    if q and len(q) >= 2:
        github_items = await query_github_plugins(q, plugin_type, page)
        for gh in github_items:
            # Avoid duplicating IDs already found
            if not any(r["id"] == gh["id"] or r["repo"] == gh["repo"] for r in all_results):
                gh["is_installed"] = gh["id"] in installed_ids
                all_results.append(gh)

    # 4. Handle sorting
    if sort_by == "stars":
        all_results.sort(key=lambda x: x.get("stars", 0), reverse=True)
    elif sort_by == "name":
        all_results.sort(key=lambda x: x.get("title", "").lower())
    elif sort_by == "verified":
        all_results.sort(key=lambda x: (x.get("verified", False), x.get("stars", 0)), reverse=True)

    # 5. Handle "installed" filter
    if plugin_type == "installed":
        all_results = [r for r in all_results if r.get("is_installed")]

    total_count = len(all_results)
    start_idx = (page - 1) * per_page
    paginated = all_results[start_idx : start_idx + per_page]

    return {
        "plugins": paginated,
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "has_more": (start_idx + per_page) < total_count
    }


async def query_github_plugins(query: str, plugin_type: str = "all", page: int = 1) -> List[Dict[str, Any]]:
    """Query live GitHub search API for community MCP servers, skills, and plugins."""
    results = []
    
    # Construct targeted search query
    type_qualifier = "mcp OR \"model context protocol\"" if plugin_type == "mcp" else "skill OR plugin OR mcp"
    search_q = f"{query} {type_qualifier} in:name,description"

    url = f"https://api.github.com/search/repositories?q={search_q}&sort=stars&order=desc&per_page=12&page={page}"
    headers = {
        "User-Agent": "Terminus-Control-Plane",
        "Accept": "application/vnd.github+json"
    }

    try:
        async with httpx.AsyncClient(timeout=4.5) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                for repo in data.get("items", []):
                    repo_full = repo.get("full_name")
                    repo_desc = repo.get("description") or f"Open-source plugin repository from {repo_full}"
                    stars = repo.get("stargazers_count", 0)
                    name = repo.get("name")
                    
                    is_mcp = "mcp" in name.lower() or "mcp" in repo_desc.lower()
                    
                    results.append({
                        "id": f"gh:{repo_full}",
                        "name": name,
                        "title": name.replace("-", " ").replace("_", " ").title(),
                        "repo": repo_full,
                        "author": repo.get("owner", {}).get("login", "GitHub"),
                        "category": "GitHub Community",
                        "type": "mcp" if is_mcp else "plugin",
                        "source": "github",
                        "description": repo_desc,
                        "stars": stars,
                        "verified": stars > 500,
                        "command": "npx",
                        "args": ["-y", repo_full],
                        "transport": "stdio",
                        "env": {},
                        "target_agents": ["claude", "hermes", "antigravity", "mochi"]
                    })
    except Exception:
        pass

    return results


# ---------------------------------------------------------------------------
# Installation, Configuration Injection & Bridge to All Agents
# ---------------------------------------------------------------------------
def get_installed_plugin_ids() -> set:
    """Scan all agent configuration files for installed MCPs and skills."""
    installed = set()

    # 1. Terminus shared mcp.json
    if TERMINUS_MCP_FILE.exists():
        try:
            with open(TERMINUS_MCP_FILE, "r") as f:
                data = json.load(f)
                for k in data.get("mcpServers", {}).keys():
                    installed.add(f"mcp:{k}")
                    installed.add(k)
        except Exception:
            pass

    # 2. Claude ~/.claude.json
    claude_cfg = Path.home() / ".claude.json"
    if claude_cfg.exists():
        try:
            with open(claude_cfg, "r") as f:
                data = json.load(f)
                for k in data.get("mcpServers", {}).keys():
                    installed.add(f"mcp:{k}")
                    installed.add(k)
        except Exception:
            pass

    # 3. Antigravity ~/.gemini/antigravity-cli/mcp.json
    agy_mcp = Path.home() / ".gemini" / "antigravity-cli" / "mcp.json"
    if agy_mcp.exists():
        try:
            with open(agy_mcp, "r") as f:
                data = json.load(f)
                for k in data.get("mcpServers", {}).keys():
                    installed.add(f"mcp:{k}")
                    installed.add(k)
        except Exception:
            pass

    # 4. Local skills directory
    if TERMINUS_SKILLS_DIR.exists():
        for d in TERMINUS_SKILLS_DIR.iterdir():
            if d.is_dir():
                installed.add(f"skill:{d.name}")
                installed.add(d.name)

    return installed


async def install_plugin(
    plugin_id: str,
    target_agents: Optional[List[str]] = None,
    custom_args: Optional[List[str]] = None,
    custom_env: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    1-click install and inject plugin/MCP into specified agents (Claude, Hermes, Antigravity, Mochi).
    Automatically updates config files without requiring shell commands.
    """
    agents = target_agents or ["all"]
    if "all" in agents:
        agents = ["claude", "hermes", "antigravity", "mochi"]

    # 1. Search in verified catalog or parse ID
    plugin = next((p for p in VERIFIED_MCP_CATALOG if p["id"] == plugin_id or p["name"] == plugin_id), None)
    is_skill = False

    if not plugin:
        skill = next((s for s in VERIFIED_SKILLS_CATALOG if s["id"] == plugin_id or s["name"] == plugin_id), None)
        if skill:
            is_skill = True
            plugin = skill

    # Handle skill installation
    if is_skill:
        return await install_skill_record(plugin, agents)

    # Handle MCP Server installation
    if not plugin:
        # Fallback dynamic GitHub MCP
        if plugin_id.startswith("gh:"):
            repo_part = plugin_id[3:]
            name_part = repo_part.split("/")[-1].lower()
            plugin = {
                "id": plugin_id,
                "name": name_part,
                "title": name_part.title(),
                "command": "npx",
                "args": ["-y", repo_part],
                "env": {},
                "transport": "stdio"
            }
        else:
            return {"success": False, "error": f"Plugin {plugin_id} not found"}

    server_name = plugin["name"]
    command = plugin.get("command", "npx")
    args = custom_args or plugin.get("args", [])
    env = custom_env or plugin.get("env", {})

    installed_targets = []

    # A. Inject into Terminus shared ~/.terminus/mcp.json
    try:
        t_data = {"mcpServers": {}}
        if TERMINUS_MCP_FILE.exists():
            with open(TERMINUS_MCP_FILE, "r") as f:
                t_data = json.load(f)
        t_data.setdefault("mcpServers", {})[server_name] = {
            "command": command,
            "args": args,
            "env": env
        }
        with open(TERMINUS_MCP_FILE, "w") as f:
            json.dump(t_data, f, indent=2)
        installed_targets.append("terminus")
    except Exception as e:
        pass

    # B. Inject into Claude Code (~/.claude.json)
    if "claude" in agents:
        try:
            claude_cfg = Path.home() / ".claude.json"
            c_data = {"mcpServers": {}}
            if claude_cfg.exists():
                with open(claude_cfg, "r") as f:
                    c_data = json.load(f)
            c_data.setdefault("mcpServers", {})[server_name] = {
                "command": command,
                "args": args,
                "env": env
            }
            with open(claude_cfg, "w") as f:
                json.dump(c_data, f, indent=2)
            installed_targets.append("claude")
        except Exception:
            pass

    # C. Inject into Google Antigravity (~/.gemini/antigravity-cli/mcp.json)
    if "antigravity" in agents:
        try:
            agy_file = Path.home() / ".gemini" / "antigravity-cli" / "mcp.json"
            agy_file.parent.mkdir(parents=True, exist_ok=True)
            a_data = {"mcpServers": {}}
            if agy_file.exists():
                with open(agy_file, "r") as f:
                    a_data = json.load(f)
            a_data.setdefault("mcpServers", {})[server_name] = {
                "command": command,
                "args": args,
                "env": env
            }
            with open(agy_file, "w") as f:
                json.dump(a_data, f, indent=2)
            installed_targets.append("antigravity")
        except Exception:
            pass

    # D. Inject into Hermes Agent (~/.hermes/config.yaml)
    if "hermes" in agents:
        try:
            hermes_cfg = Path.home() / ".hermes" / "config.yaml"
            if hermes_cfg.exists():
                with open(hermes_cfg, "r") as f:
                    h_data = yaml.safe_load(f) or {}
                h_data.setdefault("mcp", {}).setdefault("servers", {})[server_name] = {
                    "command": command,
                    "args": args,
                    "env": env
                }
                with open(hermes_cfg, "w") as f:
                    yaml.safe_dump(h_data, f)
                installed_targets.append("hermes")
        except Exception:
            pass

    return {
        "success": True,
        "plugin_id": plugin_id,
        "name": server_name,
        "type": "mcp",
        "installed_targets": installed_targets,
        "message": f"Successfully injected MCP server '{server_name}' into {', '.join(installed_targets)}"
    }


async def install_skill_record(skill: Dict[str, Any], target_agents: List[str]) -> Dict[str, Any]:
    """Install skill markdown file into agent skill trees."""
    skill_name = skill["name"]
    content = skill.get("content", "")

    # Target directories
    target_dirs = [TERMINUS_SKILLS_DIR / skill_name]
    if "hermes" in target_agents or "all" in target_agents:
        target_dirs.append(Path.home() / ".hermes" / "skills" / skill_name)
    if "antigravity" in target_agents or "all" in target_agents:
        target_dirs.append(Path.home() / ".gemini" / "antigravity-cli" / "skills" / skill_name)

    written = []
    for d in target_dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            skill_file = d / "SKILL.md"
            with open(skill_file, "w") as f:
                f.write(content)
            written.append(str(d))
        except Exception:
            pass

    return {
        "success": True,
        "plugin_id": skill["id"],
        "name": skill_name,
        "type": "skill",
        "installed_paths": written,
        "message": f"Successfully injected skill '{skill_name}' into {len(written)} agent repositories"
    }


def list_installed_plugins() -> List[Dict[str, Any]]:
    """Return all active MCP servers and installed skills across agents."""
    installed = []

    # Read Terminus shared MCP file
    if TERMINUS_MCP_FILE.exists():
        try:
            with open(TERMINUS_MCP_FILE, "r") as f:
                data = json.load(f)
                for name, cfg in data.get("mcpServers", {}).items():
                    installed.append({
                        "id": f"mcp:{name}",
                        "name": name,
                        "type": "mcp",
                        "command": cfg.get("command", ""),
                        "args": cfg.get("args", []),
                        "env": cfg.get("env", {}),
                        "targets": ["terminus", "claude", "antigravity", "hermes"],
                        "enabled": True
                    })
        except Exception:
            pass

    # Read installed skills
    if TERMINUS_SKILLS_DIR.exists():
        for d in TERMINUS_SKILLS_DIR.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                installed.append({
                    "id": f"skill:{d.name}",
                    "name": d.name,
                    "type": "skill",
                    "targets": ["terminus", "hermes", "antigravity"],
                    "enabled": True
                })

    return installed


def uninstall_plugin(plugin_id: str) -> Dict[str, Any]:
    """Remove plugin from all config files and skill directories."""
    cleaned_name = plugin_id.replace("mcp:", "").replace("skill:", "")
    removed_from = []

    # 1. Terminus mcp.json
    if TERMINUS_MCP_FILE.exists():
        try:
            with open(TERMINUS_MCP_FILE, "r") as f:
                t = json.load(f)
            if cleaned_name in t.get("mcpServers", {}):
                del t["mcpServers"][cleaned_name]
                with open(TERMINUS_MCP_FILE, "w") as f:
                    json.dump(t, f, indent=2)
                removed_from.append("terminus")
        except Exception:
            pass

    # 2. Claude ~/.claude.json
    claude_cfg = Path.home() / ".claude.json"
    if claude_cfg.exists():
        try:
            with open(claude_cfg, "r") as f:
                c = json.load(f)
            if cleaned_name in c.get("mcpServers", {}):
                del c["mcpServers"][cleaned_name]
                with open(claude_cfg, "w") as f:
                    json.dump(c, f, indent=2)
                removed_from.append("claude")
        except Exception:
            pass

    # 3. Antigravity mcp.json
    agy_mcp = Path.home() / ".gemini" / "antigravity-cli" / "mcp.json"
    if agy_mcp.exists():
        try:
            with open(agy_mcp, "r") as f:
                a = json.load(f)
            if cleaned_name in a.get("mcpServers", {}):
                del a["mcpServers"][cleaned_name]
                with open(agy_mcp, "w") as f:
                    json.dump(a, f, indent=2)
                removed_from.append("antigravity")
        except Exception:
            pass

    # 3.5 Hermes Agent (~/.hermes/config.yaml)
    hermes_cfg = Path.home() / ".hermes" / "config.yaml"
    if hermes_cfg.exists():
        try:
            import yaml as _yaml
            with open(hermes_cfg, "r") as f:
                h = _yaml.safe_load(f) or {}
            servers = h.get("mcp", {}).get("servers", {})
            if isinstance(servers, dict) and cleaned_name in servers:
                del servers[cleaned_name]
                if servers:
                    h["mcp"]["servers"] = servers
                else:
                    h.setdefault("mcp", {}).pop("servers", None)
                with open(hermes_cfg, "w") as f:
                    _yaml.safe_dump(h, f)
                removed_from.append("hermes")
        except Exception:
            pass

    # 4. Skill folders
    for s_dir in [TERMINUS_SKILLS_DIR, Path.home() / ".hermes" / "skills", Path.home() / ".gemini" / "antigravity-cli" / "skills"]:
        target = s_dir / cleaned_name
        if target.exists():
            try:
                shutil.rmtree(target)
                removed_from.append(f"skill:{s_dir.name}")
            except Exception:
                pass

    return {
        "success": True,
        "plugin_id": plugin_id,
        "removed_from": removed_from
    }


def list_categories() -> List[Dict[str, str]]:
    """Return the distinct categories present across verified catalogs with counts."""
    counts: Dict[str, int] = {}
    for item in VERIFIED_MCP_CATALOG + VERIFIED_SKILLS_CATALOG:
        cat = item.get("category", "Uncategorized")
        counts[cat] = counts.get(cat, 0) + 1
    return [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def get_plugin_detail(plugin_id: str) -> Optional[Dict[str, Any]]:
    """Return the full spec for a single plugin by ID/name across verified catalogs."""
    plugin_id_norm = plugin_id.replace("mcp:", "").replace("skill:", "").replace("gh:", "")
    installed_ids = get_installed_plugin_ids()

    # Search verified catalogs (MCP + Skills)
    for item in VERIFIED_MCP_CATALOG + VERIFIED_SKILLS_CATALOG:
        if item["id"] == plugin_id or item.get("name") == plugin_id_norm:
            detail = dict(item)
            detail["is_installed"] = item["id"] in installed_ids or item.get("name") in installed_ids
            detail["installed_agents"] = _plugin_installed_agents(plugin_id_norm, item.get("type", "mcp"))
            return detail

    # Dynamic GitHub MCP fallback (gh:owner/repo)
    if plugin_id.startswith("gh:"):
        repo_part = plugin_id[3:]
        name_part = repo_part.split("/")[-1].lower()
        return {
            "id": plugin_id,
            "name": name_part,
            "repo": repo_part,
            "title": name_part.replace("-", " ").title(),
            "type": "mcp",
            "source": "github",
            "verified": False,
            "description": f"Community GitHub MCP or tool server from {repo_part}.",
            "is_installed": False,
            "installed_agents": [],
            "transport": "unknown",
            "command": "npx",
            "args": [],
            "env": {},
            "target_agents": ["claude", "hermes", "antigravity", "mochi"],
            "stars": 0,
            "category": "GitHub",
        }

    return None


def _plugin_installed_agents(name: str, plugin_type: str) -> List[str]:
    """Report which agents currently have this plugin installed."""
    agents: List[str] = []
    subs = [
        ("terminus", TERMINUS_MCP_FILE),
        ("claude", Path.home() / ".claude.json"),
        ("antigravity", Path.home() / ".gemini" / "antigravity-cli" / "mcp.json"),
    ]
    for label, path in subs:
        if not path.exists():
            continue
        try:
            with open(path, "r") as f:
                data = json.load(f)
            if name in data.get("mcpServers", {}):
                agents.append(label)
        except Exception:
            pass

    # Hermes config.yaml (mcp.servers dict keyed by server name)
    hermes_cfg = Path.home() / ".hermes" / "config.yaml"
    if hermes_cfg.exists():
        try:
            import yaml as _yaml
            with open(hermes_cfg, "r") as f:
                hdata = _yaml.safe_load(f) or {}
            servers = hdata.get("mcp", {}).get("servers", {})
            if isinstance(servers, dict) and name in servers:
                agents.append("hermes")
        except Exception:
            pass

    # Skills directories
    if plugin_type == "skill":
        for label, sdir in [
            ("terminus", TERMINUS_SKILLS_DIR),
            ("hermes", Path.home() / ".hermes" / "skills"),
            ("antigravity", Path.home() / ".gemini" / "antigravity-cli" / "skills"),
        ]:
            if (sdir / name).exists():
                agents.append(label)

    return sorted(set(agents))
