# Terminus — "The endpoint you can reach anywhere"

Universal Machine-Level Agent Control Plane, Persistent PTY Engine & Multi-Agent Orchestrator.

```
Your Phone / Mobile Browser / Laptop (LAN & Remote)
    │
    ▼
Terminus Control Plane (Port 9120)
    │
    ▼
PTY Engine & Universal Agent Discovery Adapters
    ├── Claude Code (claude)
    ├── Hermes Agent (hermes)
    ├── Antigravity (agy)
    ├── Mochi (mochi)
    ├── Codex (codex)
    ├── Cline (cline)
    ├── Roo Code (roo)
    ├── Aider (aider)
    ├── OpenCode (opencode)
    ├── Gemini CLI (gemini)
    ├── J-Code (jcode)
    ├── Pi (pi)
    ├── Codebuff (codebuff)
    ├── Crush by Charmbracelet (crush)
    └── Standard Shell (bash / zsh)
```

---

## Overview

**Terminus** is a high-performance, single-binary-feel web control plane that gives you full interactive terminal access and deep multi-agent workflow orchestration from any browser, desktop, phone, or tablet.

### Key Capabilities

1. **Fluid Gooey Dynamic Island Navigation:**
   - 14 integrated views: **Terminal**, **Dashboard**, **Skills**, **Memory**, **Cron**, **Agents**, **Activity**, **MCP**, **Projects**, **Files**, **Processes**, **Ports**, **Logs**, and **Doctor**.
   - Sleek responsive fluid navigation bar designed to fit 100% on desktop viewports without scrolling, with an automatic low-profile horizontal scrollbar when windowed.

2. **Universal Sessions & Agent History Hub (`⌘O` / `Ctrl+O`):**
   - Manage all live terminal sessions and browse full archived conversation histories.
   - Quick Launch Agent Bar featuring instant 1-click launchers for **Claude Code, Hermes, Antigravity, Mochi, Codex, Cline, Roo Code, Aider, OpenCode, Gemini CLI, J-Code, Pi, Codebuff, Crush, and Shell**.
   - Live conversation transcript viewer with search, export, copy, and 1-click resume.

3. **Persistent Background PTY Engine:**
   - Real pseudo-terminals backed by Python `ptyprocess`.
   - Survives browser closes, phone screen locks, and reconnections with zero loss of session state or scrollback buffer.

4. **Universal Skill Tree & Cross-Agent Bridge (170+ Skills):**
   - Discovers skills from Antigravity, Hermes, and Claude Code across 20 categories.
   - 1-click prompt injection and directory bridging.

5. **Universal Multi-Agent Shared Memory Hub:**
   - Shared persistent knowledge bank (`~/.terminus/memory.json`) shared across all coding agents.

6. **Autonomous Multi-Agent Task & Cron Scheduler:**
   - Recurring and scheduled background task runner (`~/.terminus/cron.json`) executing commands across all agents with live output streaming.

7. **Raycast / Linear Command Palette (`⌘K` / `Ctrl+K`):**
   - Spotlight-style fuzzy search across all views, active sessions, discovered agents, and system diagnostics.

8. **Process & Port Discovery:**
   - Real-time dev server listening port discovery (`3000`, `5173`, `8000`, `9119`, `9120`, etc.).
   - Process manager with live CPU/RAM utilization and 1-tap termination of runaway processes.

9. **Terminus Doctor:**
   - Real-time diagnostics for PTY allocation, memory headroom, developer toolchains, and agent discovery.

---

## Quick Start

### 1. Requirements
- Linux / macOS
- Python 3.9+

### 2. Installation
```bash
git clone https://github.com/xanstomper/terminus.git
cd terminus
pip install -r requirements.txt
```

### 3. Run
```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port 9120
```
Or run the background helper script:
```bash
./start-terminus.sh
```

### 4. Systemd Service (Optional)
```bash
mkdir -p ~/.config/systemd/user
cp terminus.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now terminus.service
```

Access at `http://localhost:9120` or `http://YOUR_LAN_IP:9120`.

---

## License
MIT License. Built for universal agentic workflows.
