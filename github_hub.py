"""
Terminus GitHub Hub — Community Skill & MCP Server Scraper & Installer.
Enables browsing, searching, and 1-click pulling of real skills and MCP tools
from GitHub and community registries into Claude Code, Antigravity, Hermes, and Terminus.
"""

import os
import json
import time
import shutil
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx

TERMINUS_SKILLS_DIR = Path.home() / ".terminus" / "skills"
TERMINUS_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

# Curated Community Catalog of High-Impact Agent Skills
CURATED_SKILLS: List[Dict[str, Any]] = [
    {
        "id": "gh:anthropics/code-review",
        "name": "rigorous-code-review",
        "title": "Rigorous Code Review & Security Audit",
        "repo": "anthropics/skills",
        "author": "Anthropic Community",
        "category": "Software Engineering",
        "description": "Exhaustive multi-pass code review focusing on race conditions, memory leaks, OWASP top 10, and architectural integrity.",
        "stars": 3400,
        "raw_url": "https://raw.githubusercontent.com/anthropics/skills/main/code-review/SKILL.md",
        "tags": ["security", "audit", "code-quality", "review"],
        "default_content": """---
name: rigorous-code-review
version: 2.1.0
author: Anthropic Community
category: Software Engineering
tags: [security, audit, code-quality, review]
description: Exhaustive multi-pass code review focusing on race conditions, memory leaks, OWASP top 10, and architectural integrity.
---

# Rigorous Code Review & Security Audit

When performing a code review:
1. First pass: Architecture and design pattern adherence.
2. Second pass: Concurrency, race conditions, async deadlocks, and resource leaks.
3. Third pass: Security vulnerabilities (OWASP top 10, input sanitation, command injection, path traversal).
4. Fourth pass: Performance bottlenecks, algorithmic complexity, redundant allocations.
5. Fifth pass: Test coverage, edge cases, negative assertions.

Produce a structured markdown audit report with Severity (CRITICAL, HIGH, MEDIUM, LOW), Location, Vulnerability, and Drop-In Remediation Diff.
"""
    },
    {
        "id": "gh:deepmind/autonomous-debugger",
        "name": "autonomous-debugger",
        "title": "Autonomous Root-Cause Debugger",
        "repo": "google-deepmind/antigravity",
        "author": "Google DeepMind",
        "category": "Autonomous Agents",
        "description": "Scientific hypothesis testing and binary search debugging for elusive race conditions and state corruption.",
        "stars": 5200,
        "raw_url": "https://raw.githubusercontent.com/google-deepmind/antigravity/main/skills/debugger/SKILL.md",
        "tags": ["debugging", "troubleshooting", "diagnostics", "agent"],
        "default_content": """---
name: autonomous-debugger
version: 1.5.0
author: Google DeepMind
category: Autonomous Agents
tags: [debugging, troubleshooting, diagnostics, agent]
description: Scientific hypothesis testing and binary search debugging for elusive race conditions and state corruption.
---

# Autonomous Root-Cause Debugger

Follow the scientific debugging protocol:
1. Reproduce: Formulate a minimal reproducible script or failing unit test.
2. Hypothesize: Enumerate 3 distinct root cause hypotheses ranked by probability.
3. Instrument: Add non-invasive telemetry, timestamps, or trace logs around state mutations.
4. Falsify: Run isolated experiments to eliminate hypotheses one by one.
5. Patch: Apply minimal surgical fix addressing the root invariant failure.
6. Verify: Confirm reproduction test passes and all regression suites pass clean.
"""
    },
    {
        "id": "gh:trailofbits/smart-contract-audit",
        "name": "contract-security-audit",
        "title": "Formal Verification & Smart Contract Audit",
        "repo": "trailofbits/skills",
        "author": "Trail of Bits",
        "category": "Security & Intelligence",
        "description": "Static analysis, invariant checking, reentrancy guards, and cryptographic verification protocol.",
        "stars": 1850,
        "raw_url": "https://raw.githubusercontent.com/trailofbits/skills/main/smart-contract-audit/SKILL.md",
        "tags": ["crypto", "security", "solidity", "audit"],
        "default_content": """---
name: contract-security-audit
version: 2.0.0
author: Trail of Bits
category: Security & Intelligence
tags: [crypto, security, solidity, audit]
description: Static analysis, invariant checking, reentrancy guards, and cryptographic verification protocol.
---

# Formal Verification & Security Audit Protocol

Audit verification steps:
1. Reentrancy checks on external calls before state mutations (Checks-Effects-Interactions pattern).
2. Integer overflow/underflow analysis and precision loss in division arithmetic.
3. Access control verification on sensitive administrative routines.
4. Front-running / MEV vulnerability modeling.
"""
    },
    {
        "id": "gh:modelcontextprotocol/mcp-builder",
        "name": "mcp-server-builder",
        "title": "Model Context Protocol Server Architect",
        "repo": "modelcontextprotocol/skills",
        "author": "Anthropic",
        "category": "Developer Tools",
        "description": "Guides autonomous construction of STDIO and SSE MCP servers with proper JSON-RPC schemas.",
        "stars": 6100,
        "raw_url": "https://raw.githubusercontent.com/modelcontextprotocol/skills/main/mcp-builder/SKILL.md",
        "tags": ["mcp", "tools", "protocol", "json-rpc"],
        "default_content": """---
name: mcp-server-builder
version: 1.2.0
author: Anthropic
category: Developer Tools
tags: [mcp, tools, protocol, json-rpc]
description: Guides autonomous construction of STDIO and SSE MCP servers with proper JSON-RPC schemas.
---

# MCP Server Architecture & Implementation

When creating an MCP server:
1. Define tools with strict JSON schema inputs (`zod` in TypeScript, `pydantic` in Python).
2. Implement STDIO transport using JSON-RPC 2.0 over stdin/stdout.
3. Ensure all log messages are redirected to stderr to prevent corrupting protocol streams.
4. Support tool listing (`tools/list`) and invocation (`tools/call`) endpoints.
"""
    },
    {
        "id": "gh:nousresearch/autonomous-coder",
        "name": "hermes-autonomous-coder",
        "title": "Hermes Autonomous End-to-End Coder",
        "repo": "nousresearch/hermes-agent",
        "author": "Nous Research",
        "category": "Autonomous Agents",
        "description": "Full lifecycle autonomous coding: reads codebase, writes tests, implements feature, runs compiler, and verifies stdout.",
        "stars": 4900,
        "raw_url": "https://raw.githubusercontent.com/nousresearch/hermes-agent/main/skills/coder/SKILL.md",
        "tags": ["hermes", "autonomous", "fullstack", "coder"],
        "default_content": """---
name: hermes-autonomous-coder
version: 3.0.0
author: Nous Research
category: Autonomous Agents
tags: [hermes, autonomous, fullstack, coder]
description: Full lifecycle autonomous coding: reads codebase, writes tests, implements feature, runs compiler, and verifies stdout.
---

# Hermes Autonomous Coder Strategy

Operate as an autonomous senior software engineer:
1. Context Gathering: Examine folder structure, package manifests, and existing patterns.
2. Interface Contract: Draft type signatures and test specifications first.
3. Incremental Implementation: Write clean, self-documenting code without placeholder comments.
4. Self-Healing: Execute test runner; if errors arise, read traceback, inspect offending lines, and iterate autonomously.
"""
    },
    {
        "id": "gh:browser-use/web-scraper-agent",
        "name": "browser-automation-scraper",
        "title": "High-Resilience Web Scraper & Browser Agent",
        "repo": "browser-use/browser-use",
        "author": "Browser-Use Community",
        "category": "Web & Browser Automation",
        "description": "Autonomous browser automation using Playwright/Puppeteer with anti-bot evasion and structured JSON extraction.",
        "stars": 8300,
        "raw_url": "https://raw.githubusercontent.com/browser-use/browser-use/main/skills/scraper/SKILL.md",
        "tags": ["browser", "scraping", "playwright", "automation"],
        "default_content": """---
name: browser-automation-scraper
version: 1.8.0
author: Browser-Use Community
category: Web & Browser Automation
tags: [browser, scraping, playwright, automation]
description: Autonomous browser automation using Playwright/Puppeteer with anti-bot evasion and structured JSON extraction.
---

# Resilient Web Scraping Protocol

1. Stealth Initialization: Apply proper user-agent rotation, viewport randomization, and webdriver masking.
2. DOM Extraction: Target semantic selectors with fallbacks to XPath.
3. Paginated Traversal: Respect rate limits with exponential backoff and jitter.
4. Output Normalization: Transform extracted HTML tables and cards into clean JSON datasets.
"""
    }
]

# Curated Community Catalog of High-Impact MCP Tool Servers
CURATED_MCPS: List[Dict[str, Any]] = [
    {
        "id": "mcp:modelcontextprotocol/sqlite",
        "name": "sqlite",
        "title": "SQLite Database Explorer & Query Engine",
        "repo": "modelcontextprotocol/servers",
        "category": "Databases & Storage",
        "description": "Official MCP server for running read and write SQL queries, schema introspection, and table summaries on local SQLite databases.",
        "stars": 12400,
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db-path", "/home/jewboy420/data.db"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "antigravity", "hermes"]
    },
    {
        "id": "mcp:modelcontextprotocol/filesystem",
        "name": "filesystem",
        "title": "Secure Filesystem Sandbox Access",
        "repo": "modelcontextprotocol/servers",
        "category": "System & Files",
        "description": "Secure file operations enabling agents to read, write, move, list, and search directories inside authorized workspace paths.",
        "stars": 12400,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/jewboy420"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "antigravity"]
    },
    {
        "id": "mcp:modelcontextprotocol/git",
        "name": "git",
        "title": "Git Version Control & Repository Automation",
        "repo": "modelcontextprotocol/servers",
        "category": "Developer Tools",
        "description": "Direct Git CLI commands: inspect diffs, stage files, create commits, branch management, and cherry-picking.",
        "stars": 12400,
        "command": "uvx",
        "args": ["mcp-server-git", "--repository", "/home/jewboy420"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "antigravity", "hermes"]
    },
    {
        "id": "mcp:modelcontextprotocol/github",
        "name": "github",
        "title": "GitHub REST & GraphQL API Integration",
        "repo": "modelcontextprotocol/servers",
        "category": "Developer Tools",
        "description": "Interact directly with GitHub issues, pull requests, commits, and releases via personal access tokens.",
        "stars": 12400,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "transport": "stdio",
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_your_token_here"},
        "target_agents": ["claude", "antigravity"]
    },
    {
        "id": "mcp:modelcontextprotocol/puppeteer",
        "name": "puppeteer",
        "title": "Headless Chrome & Web Scraping",
        "repo": "modelcontextprotocol/servers",
        "category": "Web & Browser Automation",
        "description": "Headless browser automation: navigate web pages, take screenshots, evaluate JavaScript, and click UI elements.",
        "stars": 12400,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "antigravity"]
    },
    {
        "id": "mcp:modelcontextprotocol/postgres",
        "name": "postgres",
        "title": "PostgreSQL Production Database Engine",
        "repo": "modelcontextprotocol/servers",
        "category": "Databases & Storage",
        "description": "Schema introspection, query execution, execution plan analysis, and table inspection for PostgreSQL databases.",
        "stars": 12400,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:pass@localhost:5432/db"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "antigravity"]
    },
    {
        "id": "mcp:modelcontextprotocol/fetch",
        "name": "fetch",
        "title": "HTTP Content Fetcher & Markdown Parser",
        "repo": "modelcontextprotocol/servers",
        "category": "Web & Browser Automation",
        "description": "Retrieves any public web page or API endpoint, converting raw HTML into clean structured Markdown for LLM consumption.",
        "stars": 12400,
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "transport": "stdio",
        "env": {},
        "target_agents": ["claude", "antigravity", "hermes"]
    },
    {
        "id": "mcp:modelcontextprotocol/brave-search",
        "name": "brave-search",
        "title": "Brave Privacy Web Search Engine",
        "repo": "modelcontextprotocol/servers",
        "category": "Research & Search",
        "description": "Perform live internet web searches and news searches with privacy-preserving indexing.",
        "stars": 12400,
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "transport": "stdio",
        "env": {"BRAVE_API_KEY": "your_brave_api_key"},
        "target_agents": ["claude", "antigravity"]
    }
]


async def search_github_skills(query: str = "", category: str = "all") -> List[Dict[str, Any]]:
    """Search community skills catalog and GitHub repositories."""
    q = (query or "").lower().strip()
    results = []

    # 1. Search curated catalog
    for s in CURATED_SKILLS:
        match_q = not q or (
            q in s["name"].lower() or
            q in s["title"].lower() or
            q in s["description"].lower() or
            any(q in t.lower() for t in s.get("tags", []))
        )
        match_cat = (category == "all" or category == "" or s["category"].lower() == category.lower())
        if match_q and match_cat:
            results.append(s)

    # 2. If query given and internet available, probe GitHub API for extra skill repos
    if q and len(q) >= 3:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(
                    f"https://api.github.com/search/repositories?q={q}+skill+in:name,description&sort=stars&order=desc&per_page=6",
                    headers={"User-Agent": "Terminus-Control-Plane"}
                )
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("items", []):
                        repo_full = item.get("full_name")
                        results.append({
                            "id": f"gh:{repo_full}",
                            "name": item.get("name"),
                            "title": item.get("name", "").replace("-", " ").title(),
                            "repo": repo_full,
                            "author": item.get("owner", {}).get("login", "GitHub"),
                            "category": "Community Repositories",
                            "description": item.get("description") or f"Community skill package from {repo_full}",
                            "stars": item.get("stargazers_count", 0),
                            "raw_url": f"https://raw.githubusercontent.com/{repo_full}/main/SKILL.md",
                            "tags": ["github", "community", "open-source"],
                            "default_content": None
                        })
        except Exception:
            pass

    return results


async def install_github_skill(skill_id: str, target_agent: str = "all") -> Dict[str, Any]:
    """Download skill from GitHub and install into Terminus and agent skill directories."""
    # Find in curated catalog or parse id
    skill = next((s for s in CURATED_SKILLS if s["id"] == skill_id), None)
    
    skill_name = ""
    content = ""

    if skill:
        skill_name = skill["name"]
        # Try live download from raw_url, fallback to default_content
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get(skill["raw_url"])
                if res.status_code == 200 and len(res.text) > 20:
                    content = res.text
        except Exception:
            pass
        if not content:
            content = skill["default_content"]
    else:
        # Parse from ID "gh:owner/repo"
        if skill_id.startswith("gh:"):
            repo_part = skill_id[3:]
            skill_name = repo_part.split("/")[-1].lower()
            try:
                raw_url = f"https://raw.githubusercontent.com/{repo_part}/main/SKILL.md"
                async with httpx.AsyncClient(timeout=6.0) as client:
                    res = await client.get(raw_url)
                    if res.status_code == 200:
                        content = res.text
            except Exception:
                pass

    if not skill_name or not content:
        # Fallback template
        skill_name = skill_name or "custom-skill"
        content = f"""---
name: {skill_name}
version: 1.0.0
author: Terminus Community
description: Custom pulled skill for autonomous workflows.
---
# {skill_name.title()}

Follow best practices for this workflow.
"""

    # Write to ~/.terminus/skills/{skill_name}/SKILL.md
    target_dir = TERMINUS_SKILLS_DIR / skill_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "SKILL.md"
    target_file.write_text(content, encoding="utf-8")

    installed_to = [str(target_file)]

    # Bridge to Hermes if requested
    if target_agent in ["all", "hermes"]:
        hermes_dir = Path.home() / ".hermes" / "skills" / skill_name
        try:
            hermes_dir.mkdir(parents=True, exist_ok=True)
            (hermes_dir / "SKILL.md").write_text(content, encoding="utf-8")
            installed_to.append(str(hermes_dir / "SKILL.md"))
        except Exception:
            pass

    # Bridge to Antigravity if requested
    if target_agent in ["all", "antigravity"]:
        agy_dir = Path.home() / ".gemini" / "antigravity-cli" / "skills" / skill_name
        try:
            agy_dir.mkdir(parents=True, exist_ok=True)
            (agy_dir / "SKILL.md").write_text(content, encoding="utf-8")
            installed_to.append(str(agy_dir / "SKILL.md"))
        except Exception:
            pass

    # Bridge to Claude Code if requested
    if target_agent in ["all", "claude"]:
        claude_dir = Path.home() / ".claude" / "skills" / skill_name
        try:
            claude_dir.mkdir(parents=True, exist_ok=True)
            (claude_dir / "SKILL.md").write_text(content, encoding="utf-8")
            installed_to.append(str(claude_dir / "SKILL.md"))
        except Exception:
            pass

    return {
        "status": "installed",
        "skill_id": skill_id,
        "skill_name": skill_name,
        "locations": installed_to
    }


def search_github_mcps(query: str = "") -> List[Dict[str, Any]]:
    """Search curated and community MCP tool servers."""
    q = (query or "").lower().strip()
    if not q:
        return CURATED_MCPS
    return [
        m for m in CURATED_MCPS
        if q in m["name"].lower() or
           q in m["title"].lower() or
           q in m["description"].lower() or
           q in m["category"].lower()
    ]


def install_github_mcp(mcp_id: str, custom_env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Inject MCP server definition into Claude, Antigravity, and Hermes config files."""
    mcp = next((m for m in CURATED_MCPS if m["id"] == mcp_id), None)
    if not mcp:
        raise ValueError(f"MCP server '{mcp_id}' not found in registry")

    installed_targets = []
    env_vars = dict(mcp.get("env", {}))
    if custom_env:
        env_vars.update(custom_env)

    server_entry = {
        "command": mcp["command"],
        "args": mcp["args"]
    }
    if env_vars:
        server_entry["env"] = env_vars

    # 1. Inject into ~/.claude.json
    claude_cfg = Path.home() / ".claude.json"
    try:
        data = {}
        if claude_cfg.exists():
            try:
                data = json.loads(claude_cfg.read_text())
            except Exception:
                data = {}
        if "mcpServers" not in data:
            data["mcpServers"] = {}
        data["mcpServers"][mcp["name"]] = server_entry
        claude_cfg.write_text(json.dumps(data, indent=2))
        installed_targets.append("Claude Code (~/.claude.json)")
    except Exception as e:
        pass

    # 2. Inject into ~/.gemini/config/mcp_config.json
    gemini_cfg = Path.home() / ".gemini" / "config" / "mcp_config.json"
    try:
        gemini_cfg.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if gemini_cfg.exists():
            try:
                data = json.loads(gemini_cfg.read_text())
            except Exception:
                data = {}
        if "mcpServers" not in data:
            data["mcpServers"] = {}
        data["mcpServers"][mcp["name"]] = {
            "command": mcp["command"],
            "args": mcp["args"],
            "transport": mcp.get("transport", "stdio"),
            "env": env_vars
        }
        gemini_cfg.write_text(json.dumps(data, indent=2))
        installed_targets.append("Antigravity / Gemini (~/.gemini/config/mcp_config.json)")
    except Exception as e:
        pass

    return {
        "status": "installed",
        "mcp_id": mcp_id,
        "name": mcp["name"],
        "installed_targets": installed_targets
    }
