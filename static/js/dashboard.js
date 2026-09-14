// Terminus - The endpoint you can reach anywhere
// Universal Agent Control Plane, Diagnostics & Persistent Multi-Terminal

document.addEventListener("DOMContentLoaded", () => {
  // --------------------------------------------------
  // Per-Tab Isolated Terminal Architecture
  // --------------------------------------------------
  // Map of sessionId -> {
  //   id, title, cwd, agentId,
  //   container, term, fitAddon, socket,
  //   isConnecting, reconnectTimer, heartbeatTimer,
  //   lastPongTime, receivedBytes, lastCols, lastRows,
  //   isDisposed, status, statusLabel
  // }
  const terminalTabs = new Map();

  let ctrlLatched = false;
  let currentSessionId = localStorage.getItem("terminus_active_session") || "term-main";
  let activeSessions = [
    { id: currentSessionId, title: "Shell" }
  ];
  let cmdHistory = JSON.parse(localStorage.getItem("terminus_cmd_history") || "[]");
  let cmdHistoryIndex = -1;

  // Cached data
  let cachedProjects = [];
  let currentProjectSort = "recent";
  let currentProjectSearch = "";
  let cachedAgents = [];
  let currentAgentSearch = "";

  // DOM Elements
  const terminalViewport = document.getElementById("terminal-viewport");
  const tabsContainer = document.getElementById("tabs-container");
  const indicatorDot = document.getElementById("indicator-dot");
  const indicatorText = document.getElementById("indicator-text");
  const commandField = document.getElementById("command-field");
  const commandForm = document.getElementById("command-form");

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Nav Views
  const navBtns = document.querySelectorAll("[data-view-target]");
  const viewPanels = document.querySelectorAll(".view-panel");

  // Telemetry DOM
  const telemCpu = document.getElementById("telem-cpu");
  const telemMem = document.getElementById("telem-mem");
  const telemDisk = document.getElementById("telem-disk");
  const hostPill = document.getElementById("host-pill");
  const hostPillText = document.getElementById("host-pill-text");

  // Toast Container
  const toastContainer = document.getElementById("toast-container");

  function showToast(message) {
    if (!toastContainer) return;
    const t = document.createElement("div");
    t.className = "toast";
    t.textContent = message;
    toastContainer.appendChild(t);
    setTimeout(() => {
      t.style.opacity = "0";
      t.style.transition = "opacity 0.2s";
      setTimeout(() => t.remove(), 200);
    }, 2400);
  }

  // --------------------------------------------------
  // Helper: Active Tab Lookup
  // --------------------------------------------------
  function getActiveTab() {
    return terminalTabs.get(currentSessionId) || null;
  }

  // --------------------------------------------------
  // Per-Tab Factory & Lifecycle
  // --------------------------------------------------
  function getOrCreateTerminalTab(sessionId, title = "Shell", cwd = null, agentId = null) {
    if (terminalTabs.has(sessionId)) {
      const existing = terminalTabs.get(sessionId);
      if (title && !existing.title) existing.title = title;
      if (cwd && !existing.cwd) existing.cwd = cwd;
      if (agentId && !existing.agentId) existing.agentId = agentId;
      return existing;
    }

    // 1. Create dedicated DOM container inside viewport
    const container = document.createElement("div");
    container.className = "terminal-tab-instance";
    container.id = `tab-inst-${sessionId}`;
    container.style.display = (sessionId === currentSessionId) ? "block" : "none";
    terminalViewport.appendChild(container);

    // 2. Configure xterm instance
    // Note: lineHeight: 1.0 and letterSpacing: 0 fix ASCII art gaps & broken box-drawing borders!
    const isMobile = window.innerWidth < 768;
    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "bar",
      cursorWidth: 2,
      fontSize: isMobile ? 12 : 13,
      lineHeight: 1.08,
      letterSpacing: 0,
      fontFamily: '"JetBrains Mono", "Cascadia Code", "Fira Code", "SF Mono", Menlo, Monaco, Consolas, monospace',
      theme: {
        background: "#09090b",
        foreground: "#f4f4f6",
        cursor: "#f4f4f6",
        cursorAccent: "#09090b",
        selectionBackground: "rgba(255, 255, 255, 0.16)",
        black: "#18181b",
        red: "#ef4444",
        green: "#10b981",
        yellow: "#f59e0b",
        blue: "#3b82f6",
        magenta: "#a855f7",
        cyan: "#06b6d4",
        white: "#f4f4f6",
        brightBlack: "#52525b",
        brightRed: "#f87171",
        brightGreen: "#34d399",
        brightYellow: "#fbbf24",
        brightBlue: "#60a5fa",
        brightMagenta: "#c084fc",
        brightCyan: "#22d3ee",
        brightWhite: "#ffffff"
      },
      allowTransparency: true,
      scrollback: 10000,
      tabStopWidth: 4,
      convertEol: true,
      customGlyphs: true,
      smoothScrollDuration: 0,
      fastScrollModifier: "alt",
      fastScrollSensitivity: 5
    });

    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);

    if (typeof WebLinksAddon !== "undefined" && WebLinksAddon.WebLinksAddon) {
      term.loadAddon(new WebLinksAddon.WebLinksAddon());
    }

    term.open(container);

    // 3. Tab State Structure
    const tabObj = {
      id: sessionId,
      title: title,
      cwd: cwd,
      agentId: agentId,
      container: container,
      term: term,
      fitAddon: fitAddon,
      socket: null,
      isConnecting: false,
      reconnectTimer: null,
      heartbeatTimer: null,
      lastPongTime: Date.now(),
      receivedBytes: 0,
      lastCols: 0,
      lastRows: 0,
      isDisposed: false,
      status: "reconnecting",
      statusLabel: "Connecting..."
    };

    terminalTabs.set(sessionId, tabObj);

    // Terminal data event -> sends input to this specific tab's socket
    term.onData((data) => {
      sendTerminalInput(data, tabObj);
    });

    // Touch and click within container ensures helper textarea focus
    container.addEventListener("click", () => ensureKeyboardFocus(tabObj));
    container.addEventListener("touchend", () => ensureKeyboardFocus(tabObj));

    // Connect this tab's dedicated WebSocket
    connectTabWebSocket(tabObj);

    return tabObj;
  }

  // --------------------------------------------------
  // Dedicated Per-Tab WebSocket Connection & Sync
  // --------------------------------------------------
  function connectTabWebSocket(tab) {
    if (tab.isDisposed || tab.isConnecting) return;
    if (tab.socket && (tab.socket.readyState === WebSocket.OPEN || tab.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    tab.isConnecting = true;
    updateTabStatus(tab, "reconnecting", tab.receivedBytes > 0 ? "Resuming..." : "Connecting...");

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/terminal/${encodeURIComponent(tab.id)}`;

    let ws = null;
    try {
      ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      tab.socket = ws;
    } catch (err) {
      handleTabDisconnect(tab);
      return;
    }

    ws.onopen = () => {
      if (tab.isDisposed) {
        try { ws.close(); } catch (e) {}
        return;
      }
      tab.isConnecting = false;
      tab.lastPongTime = Date.now();
      updateTabStatus(tab, "online", "Connected");

      // Only request stream synchronization if reconnecting after having received bytes
      if (tab.receivedBytes > 0) {
        try {
          ws.send(JSON.stringify({
            type: "sync",
            offset: tab.receivedBytes
          }));
        } catch (e) {}
      }

      if (tab.id === currentSessionId) {
        safeFitTab(tab);
        ensureKeyboardFocus(tab);
      }
      startTabHeartbeat(tab);
    };

    ws.onmessage = (event) => {
      if (tab.isDisposed) return;
      tab.lastPongTime = Date.now();

      if (event.data instanceof ArrayBuffer) {
        const u8 = new Uint8Array(event.data);
        tab.receivedBytes += u8.byteLength;
        tab.term.write(u8);
      } else if (typeof event.data === "string") {
        if (event.data.startsWith("{") && event.data.endsWith("}")) {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === "init" || msg.type === "sync_ack") {
              if (typeof msg.totalBytes === "number") {
                tab.receivedBytes = msg.totalBytes;
              }
              return;
            }
            if (msg.type === "pong") {
              // Heartbeat verified - do not trigger unnecessary sync!
              return;
            }
            if (msg.type === "exit") {
              tab.term.write("\r\n\x1b[90m[Process ended]\x1b[0m\r\n");
              return;
            }
          } catch (e) {}
        }
        tab.term.write(event.data);
      }
    };

    ws.onclose = () => handleTabDisconnect(tab);
    ws.onerror = () => handleTabDisconnect(tab);
  }

  function handleTabDisconnect(tab) {
    if (tab.isDisposed) return;
    tab.isConnecting = false;
    stopTabHeartbeat(tab);
    updateTabStatus(tab, "reconnecting", "Reconnecting...");

    if (!tab.reconnectTimer) {
      tab.reconnectTimer = setTimeout(() => {
        tab.reconnectTimer = null;
        if (!tab.isDisposed) {
          connectTabWebSocket(tab);
        }
      }, 1800);
    }
  }

  function startTabHeartbeat(tab) {
    stopTabHeartbeat(tab);
    tab.heartbeatTimer = setInterval(() => {
      if (tab.isDisposed) return;
      if (!tab.socket || tab.socket.readyState !== WebSocket.OPEN) {
        handleTabDisconnect(tab);
        return;
      }
      if (Date.now() - tab.lastPongTime > 30000) {
        try { tab.socket.close(); } catch (e) {}
        handleTabDisconnect(tab);
        return;
      }
      try {
        tab.socket.send(JSON.stringify({ type: "ping" }));
      } catch (e) {
        handleTabDisconnect(tab);
      }
    }, 12000);
  }

  function stopTabHeartbeat(tab) {
    if (tab.heartbeatTimer) {
      clearInterval(tab.heartbeatTimer);
      tab.heartbeatTimer = null;
    }
  }

  function updateTabStatus(tab, state, label) {
    tab.status = state;
    tab.statusLabel = label;
    if (tab.id === currentSessionId) {
      if (indicatorDot) indicatorDot.className = "indicator-dot " + state;
      if (indicatorText) indicatorText.textContent = label;
    }
  }

  // --------------------------------------------------
  // Keyboard Focus & Sizing
  // --------------------------------------------------
  function ensureKeyboardFocus(targetTab = null) {
    const tab = targetTab || getActiveTab();
    if (!tab || !tab.term) return;
    try {
      tab.term.focus();
      const helper = tab.container.querySelector(".xterm-helper-textarea");
      if (helper) {
        helper.setAttribute("autocapitalize", "none");
        helper.setAttribute("autocorrect", "off");
        helper.setAttribute("autocomplete", "off");
        helper.setAttribute("spellcheck", "false");
        helper.setAttribute("inputmode", "text");
        helper.focus();
      }
    } catch (e) {}
  }

  function safeFitTab(tab) {
    if (!tab || !tab.fitAddon || !tab.term || tab.container.style.display === "none") return;
    try {
      tab.fitAddon.fit();
      sendTabResize(tab);
    } catch (e) {}
  }

  function safeFitActiveTab() {
    const tab = getActiveTab();
    if (tab) safeFitTab(tab);
  }

  function sendTabResize(tab) {
    if (!tab || !tab.socket || tab.socket.readyState !== WebSocket.OPEN || !tab.term) return;
    const cols = tab.term.cols;
    const rows = tab.term.rows;
    if (cols <= 0 || rows <= 0) return;
    if (tab.lastCols === cols && tab.lastRows === rows) return; // Prevent SIGWINCH spamming
    tab.lastCols = cols;
    tab.lastRows = rows;
    try {
      tab.socket.send(JSON.stringify({
        type: "resize",
        cols: cols,
        rows: rows
      }));
    } catch (e) {}
  }

  function sendTerminalInput(data, targetTab = null) {
    const tab = targetTab || getActiveTab();
    if (!tab || !tab.socket || tab.socket.readyState !== WebSocket.OPEN) return;

    if (ctrlLatched) {
      ctrlLatched = false;
      document.getElementById("btn-ctrl-key")?.classList.remove("active-latch");
      if (data.length === 1) {
        const code = data.toUpperCase().charCodeAt(0);
        if (code >= 65 && code <= 90) {
          data = String.fromCharCode(code - 64);
        }
      }
    }

    try {
      tab.socket.send(data);
    } catch (e) {}
  }

  // Viewport touch & click handlers
  terminalViewport?.addEventListener("click", () => ensureKeyboardFocus());
  terminalViewport?.addEventListener("touchend", () => ensureKeyboardFocus());
  document.querySelector(".terminal-workspace")?.addEventListener("click", () => ensureKeyboardFocus());

  window.addEventListener("resize", safeFitActiveTab);
  window.addEventListener("orientationchange", () => setTimeout(safeFitActiveTab, 150));

  // --------------------------------------------------
  // Mobile Background Resume & Reconnect All Tabs
  // --------------------------------------------------
  function checkAndReconnectAllTabs() {
    terminalTabs.forEach((tab) => {
      if (!tab.isDisposed) {
        if (!tab.socket || tab.socket.readyState !== WebSocket.OPEN) {
          if (tab.reconnectTimer) {
            clearTimeout(tab.reconnectTimer);
            tab.reconnectTimer = null;
          }
          connectTabWebSocket(tab);
        } else {
          try {
            tab.socket.send(JSON.stringify({ type: "ping" }));
          } catch (e) {
            handleTabDisconnect(tab);
          }
        }
      }
    });
    setTimeout(() => {
      safeFitActiveTab();
      ensureKeyboardFocus();
    }, 120);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") checkAndReconnectAllTabs();
  });
  window.addEventListener("pageshow", checkAndReconnectAllTabs);
  window.addEventListener("focus", checkAndReconnectAllTabs);
  window.addEventListener("online", checkAndReconnectAllTabs);

  // --------------------------------------------------
  // Tactile Virtual Keypad
  // --------------------------------------------------
  document.querySelectorAll("[data-term-key]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const key = btn.getAttribute("data-term-key");
      handleHardwareKey(key, btn);
    });
  });

  function handleHardwareKey(key, btn) {
    switch (key) {
      case "ESC":
        sendTerminalInput("\x1b");
        break;
      case "TAB":
        sendTerminalInput("\t");
        break;
      case "CTRL":
        ctrlLatched = !ctrlLatched;
        btn.classList.toggle("active-latch", ctrlLatched);
        break;
      case "UP":
        sendTerminalInput("\x1b[A");
        break;
      case "DOWN":
        sendTerminalInput("\x1b[B");
        break;
      case "LEFT":
        sendTerminalInput("\x1b[D");
        break;
      case "RIGHT":
        sendTerminalInput("\x1b[C");
        break;
      case "CTRL_C":
        sendTerminalInput("\x03");
        break;
      case "CTRL_D":
        sendTerminalInput("\x04");
        break;
      case "CTRL_Z":
        sendTerminalInput("\x1a");
        break;
      case "CTRL_L":
        sendTerminalInput("\x0c");
        break;
      case "CMD_CLEAR":
        sendTerminalInput("clear\n");
        break;
      case "FOCUS":
        ensureKeyboardFocus();
        break;
      default:
        sendTerminalInput(key);
    }
  }

  // --------------------------------------------------
  // Mobile Command Entry Field
  // --------------------------------------------------
  if (commandForm && commandField) {
    commandForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const val = commandField.value;
      if (!val && val !== "") return;

      sendTerminalInput(val + "\n");

      if (val.trim()) {
        cmdHistory.unshift(val.trim());
        if (cmdHistory.length > 60) cmdHistory.pop();
        localStorage.setItem("terminus_cmd_history", JSON.stringify(cmdHistory));
      }
      cmdHistoryIndex = -1;
      commandField.value = "";
      ensureKeyboardFocus();
    });

    commandField.addEventListener("keydown", (e) => {
      if (e.key === "ArrowUp") {
        if (cmdHistoryIndex < cmdHistory.length - 1) {
          cmdHistoryIndex++;
          commandField.value = cmdHistory[cmdHistoryIndex] || "";
        }
        e.preventDefault();
      } else if (e.key === "ArrowDown") {
        if (cmdHistoryIndex > 0) {
          cmdHistoryIndex--;
          commandField.value = cmdHistory[cmdHistoryIndex] || "";
        } else if (cmdHistoryIndex === 0) {
          cmdHistoryIndex = -1;
          commandField.value = "";
        }
        e.preventDefault();
      }
    });
  }

  // --------------------------------------------------
  // Fluid Gooey Navigation & Tab Engine
  // --------------------------------------------------
  // Fluid Gooey Navigation & Tab Engine
  // --------------------------------------------------
  function updateGooeyNav(targetBtn = null) {
    const nav = document.getElementById("view-nav");
    const pill = document.getElementById("gooey-nav-pill");
    if (!nav || !pill) return;

    const btn = targetBtn || nav.querySelector(".nav-btn.active");
    if (!btn || btn.offsetParent === null) {
      pill.style.opacity = "0";
      return;
    }

    const left = btn.offsetLeft;
    const top = btn.offsetTop;
    const width = btn.offsetWidth;
    const height = btn.offsetHeight;

    if (width <= 0 || height <= 0) return;

    pill.style.opacity = "1";
    pill.style.transform = `translate3d(${left}px, ${top}px, 0)`;
    pill.style.width = `${width}px`;
    pill.style.height = `${height}px`;
  }

  function updateGooeyTabs(targetTab = null) {
    const container = document.getElementById("tabs-container");
    const pill = document.getElementById("gooey-tab-pill");
    if (!container || !pill) return;

    const tab = targetTab || container.querySelector(".terminal-tab.active");
    if (!tab || tab.offsetParent === null) {
      pill.style.opacity = "0";
      return;
    }

    const left = tab.offsetLeft;
    const top = tab.offsetTop;
    const width = tab.offsetWidth;
    const height = tab.offsetHeight;

    if (width <= 0 || height <= 0) return;

    pill.style.opacity = "1";
    pill.style.transform = `translate3d(${left}px, ${top}px, 0)`;
    pill.style.width = `${width}px`;
    pill.style.height = `${height}px`;
  }

  // --------------------------------------------------
  // View Switcher (Terminal, Dashboard, Agents, Activity, MCP, Projects, Files, Processes, Ports, Logs, Doctor)
  // --------------------------------------------------
  navBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-view-target");
      switchView(target);
    });
    btn.addEventListener("mouseenter", () => updateGooeyNav(btn));
  });

  const viewNavEl = document.getElementById("view-nav");
  if (viewNavEl) {
    viewNavEl.addEventListener("mouseleave", () => updateGooeyNav());
    viewNavEl.addEventListener("scroll", () => updateGooeyNav(), { passive: true });
  }

  const tabsContainerEl = document.getElementById("tabs-container");
  if (tabsContainerEl) {
    tabsContainerEl.addEventListener("mouseleave", () => updateGooeyTabs());
    tabsContainerEl.addEventListener("scroll", () => updateGooeyTabs(), { passive: true });
  }

  window.addEventListener("resize", () => {
    updateGooeyNav();
    updateGooeyTabs();
  });

  function switchView(viewId) {
    navBtns.forEach((b) => {
      const isActive = b.getAttribute("data-view-target") === viewId;
      b.classList.toggle("active", isActive);
      if (isActive) {
        b.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
      }
    });
    viewPanels.forEach((p) => {
      p.classList.toggle("active-view", p.id === viewId);
    });

    requestAnimationFrame(() => updateGooeyNav());

    try {
      if (viewId === "view-terminal") {
        safeFitActiveTab();
        ensureKeyboardFocus();
      } else if (viewId === "view-workspace") {
        initWorkspaceView();
      } else if (viewId === "view-dashboard") {
        loadDashboardView();
      } else if (viewId === "view-communicator") {
        loadCommunicatorView();
      } else if (viewId === "view-hermes") {
        loadHermesView();
      } else if (viewId === "view-skills") {
        loadSkillsView();
      } else if (viewId === "view-memory") {
        loadMemoryView();
      } else if (viewId === "view-cron") {
        loadCronView();
      } else if (viewId === "view-agents") {
        loadAgentsView();
      } else if (viewId === "view-activity") {
        loadActivityView();
      } else if (viewId === "view-mcp") {
        loadMcpView();
      } else if (viewId === "view-files") {
        loadFilesView();
      } else if (viewId === "view-projects") {
        loadProjectsView();
      } else if (viewId === "view-processes") {
        loadProcessesView();
      } else if (viewId === "view-ports") {
        loadPortsView();
      } else if (viewId === "view-logs") {
        loadLogsView();
      } else if (viewId === "view-doctor") {
        loadDoctorView();
      }
    } catch (err) {
      console.error("View switch error for " + viewId, err);
    }
  }
  window.switchView = switchView;

  // --------------------------------------------------
  // Multi-Tab Management
  // --------------------------------------------------
  function renderTabs() {
    if (!tabsContainer) return;
    tabsContainer.innerHTML = '<div class="gooey-tab-pill" id="gooey-tab-pill"></div>';
    activeSessions.forEach((sess) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = `terminal-tab ${sess.id === currentSessionId ? "active" : ""}`;

      const tabTitle = document.createElement("span");
      tabTitle.textContent = sess.title || "Shell";
      tab.appendChild(tabTitle);

      if (activeSessions.length > 1) {
        const closeIcon = document.createElement("span");
        closeIcon.className = "tab-close-icon";
        closeIcon.innerHTML = `
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        `;
        closeIcon.addEventListener("click", (e) => {
          e.stopPropagation();
          closeTab(sess.id);
        });
        tab.appendChild(closeIcon);
      }

      tab.addEventListener("mouseenter", () => updateGooeyTabs(tab));
      tab.addEventListener("click", () => {
        switchTab(sess.id);
      });

      tabsContainer.appendChild(tab);
    });

    requestAnimationFrame(() => updateGooeyTabs());
  }

  function switchTab(sid) {
    currentSessionId = sid;
    localStorage.setItem("terminus_active_session", sid);

    // Make sure tab instance exists
    const tabMeta = activeSessions.find(s => s.id === sid);
    const targetTab = getOrCreateTerminalTab(sid, tabMeta?.title || "Shell", tabMeta?.cwd, tabMeta?.agent_id);

    // Toggle DOM visibility for every tab instance
    terminalTabs.forEach((tab, id) => {
      if (id === sid) {
        tab.container.style.display = "block";
        safeFitTab(tab);
        ensureKeyboardFocus(tab);
        updateTabStatus(tab, tab.status || "online", tab.statusLabel || "Connected");
      } else {
        tab.container.style.display = "none";
      }
    });

    renderTabs();
  }
  window.switchTab = switchTab;

  async function createTab(title = "Shell", initialCmd = null, cwd = null, agentId = null) {
    const newId = "term-" + Math.random().toString(36).substring(2, 7);
    activeSessions.push({ id: newId, title: title, cwd: cwd, agent_id: agentId });
    renderTabs();

    try {
      await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: newId, title: title, initial_cmd: initialCmd, cwd: cwd, agent_id: agentId })
      });
    } catch (e) {}

    getOrCreateTerminalTab(newId, title, cwd, agentId);
    switchTab(newId);
    showToast(`Session: ${title}`);
  }
  window.createTab = createTab;

  async function openProject(projectPath, agentId = null) {
    try {
      const res = await fetch("/api/projects/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: projectPath, agent_id: agentId })
      });
      if (!res.ok) {
        showToast("Failed to open project");
        return;
      }
      const data = await res.json();
      const existingMeta = activeSessions.find(s => s.id === data.session_id);
      if (!existingMeta) {
        activeSessions.push({ id: data.session_id, title: data.title, cwd: data.cwd, agent_id: data.agent_id });
        renderTabs();
      }
      getOrCreateTerminalTab(data.session_id, data.title, data.cwd, data.agent_id);
      switchView("view-terminal");
      switchTab(data.session_id);
      showToast(data.existing ? `Resumed: ${data.title}` : `Opened: ${data.title}`);
    } catch (e) {
      showToast("Error opening project");
    }
  }
  window.openProject = openProject;

  function closeTab(sid) {
    if (activeSessions.length <= 1) return;
    const tab = terminalTabs.get(sid);
    if (tab) {
      tab.isDisposed = true;
      if (tab.reconnectTimer) clearTimeout(tab.reconnectTimer);
      if (tab.heartbeatTimer) clearInterval(tab.heartbeatTimer);
      try { tab.socket?.close(); } catch (e) {}
      try { tab.term?.dispose(); } catch (e) {}
      tab.container?.remove();
      terminalTabs.delete(sid);
    }

    activeSessions = activeSessions.filter((s) => s.id !== sid);
    fetch(`/api/sessions/${encodeURIComponent(sid)}`, { method: "DELETE" }).catch(() => {});

    if (currentSessionId === sid) {
      currentSessionId = activeSessions[0].id;
      switchTab(currentSessionId);
    } else {
      renderTabs();
    }
  }

  // Session launcher modal
  const newSessionModal = document.getElementById("new-session-modal");
  document.getElementById("btn-new-tab")?.addEventListener("click", () => {
    newSessionModal?.classList.add("open");
  });

  document.querySelectorAll("[data-quick-launch]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const agentId = btn.getAttribute("data-quick-launch");
      const title = btn.getAttribute("data-title") || "Agent";
      const cmd = btn.getAttribute("data-cmd") || agentId;
      newSessionModal?.classList.remove("open");
      switchView("view-terminal");
      createTab(title, cmd, null, agentId);
    });
  });

  // --------------------------------------------------
  // View: Dashboard (Home Control Plane)
  // --------------------------------------------------
  async function loadDashboardView() {
    try {
      const [telemRes, sessRes, actRes] = await Promise.all([
        fetch("/api/telemetry"),
        fetch("/api/sessions"),
        fetch("/api/activity?limit=6")
      ]);

      if (telemRes.ok) {
        const data = await telemRes.json();
        const dHost = document.getElementById("dash-hostname");
        const dOs = document.getElementById("dash-os");
        const dCpu = document.getElementById("dash-cpu");
        const dCores = document.getElementById("dash-cpu-cores");
        const dMem = document.getElementById("dash-mem");
        const dMemSub = document.getElementById("dash-mem-sub");
        const dGpu = document.getElementById("dash-gpu");
        const dDisk = document.getElementById("dash-disk");
        const dDiskSub = document.getElementById("dash-disk-sub");
        const dActiveCount = document.getElementById("dash-active-count");
        const dAgentsSub = document.getElementById("dash-agents-sub");

        if (dHost) dHost.textContent = data.hostname || "localhost";
        if (dOs) dOs.textContent = `${data.os || "Linux"} (Kernel ${data.kernel || ""})`;
        if (dCpu) dCpu.textContent = `${data.cpu}%`;
        if (dCores) dCores.textContent = `${data.cpu_cores} Cores Active (Load: ${data.load_avg?.join(", ")})`;
        if (dMem) dMem.textContent = `${data.memory.percent}%`;
        if (dMemSub) dMemSub.textContent = `${data.memory.used_gb} GB / ${data.memory.total_gb} GB`;
        if (dGpu) dGpu.textContent = data.gpu || "Hardware Acceleration Active";
        if (dDisk) dDisk.textContent = `${data.disk.percent}%`;
        if (dDiskSub) dDiskSub.textContent = `${data.disk.free_gb} GB Free / ${data.disk.total_gb} GB`;
        if (dActiveCount) dActiveCount.textContent = `${data.active_sessions} Active`;
        if (dAgentsSub) dAgentsSub.textContent = `${data.running_agents_count} Running / ${data.total_agents_count} Discovered`;
      }

      // Render Active Sessions
      if (sessRes.ok) {
        const sessData = await sessRes.json();
        const sessList = document.getElementById("dash-active-sessions-list");
        const sessCount = document.getElementById("dash-active-sessions-count");
        const sList = sessData.sessions || [];
        if (sessCount) sessCount.textContent = `${sList.length} Active`;

        if (sessList) {
          sessList.innerHTML = "";
          if (sList.length === 0) {
            sessList.innerHTML = `<div style="text-align:center; padding: 24px; color:var(--text-muted); font-size:0.8rem;">No active terminal sessions</div>`;
          } else {
            sList.forEach((s) => {
              const item = document.createElement("div");
              item.className = "dash-session-item";
              const isCurr = s.id === currentSessionId;
              const agentTag = s.agent_id ? s.agent_id.toUpperCase() : "SHELL";
              item.innerHTML = `
                <div class="dash-session-left">
                  <span class="indicator-dot ${isCurr ? 'online' : 'connected'}" style="width:7px; height:7px;"></span>
                  <div>
                    <div class="dash-session-title">${s.title}</div>
                    <div class="dash-session-sub">${s.cwd} · <span class="badge-status installed" style="font-size:0.65rem; padding:1px 4px;">${agentTag}</span></div>
                  </div>
                </div>
                <div style="display:flex; gap:6px;">
                  <button class="action-btn btn-primary-action" style="padding:2px 8px; font-size:0.72rem;" data-open-sid="${s.id}">Switch</button>
                  <button class="action-btn" style="padding:2px 8px; font-size:0.72rem; color:var(--accent-rose);" data-close-sid="${s.id}">Close</button>
                </div>
              `;
              item.querySelector("[data-open-sid]")?.addEventListener("click", () => {
                switchView("view-terminal");
                switchTab(s.id);
              });
              item.querySelector("[data-close-sid]")?.addEventListener("click", () => {
                closeTab(s.id);
                loadDashboardView();
              });
              sessList.appendChild(item);
            });
          }
        }
      }

      // Render Dashboard Activity stream preview
      if (actRes.ok) {
        const actData = await actRes.json();
        const actBox = document.getElementById("dash-activity-stream");
        if (actBox) {
          actBox.innerHTML = "";
          const acts = actData.activities || [];
          if (acts.length === 0) {
            actBox.innerHTML = `<div style="text-align:center; padding: 24px; color:var(--text-muted); font-size:0.8rem;">No recent agent events</div>`;
          } else {
            acts.forEach((a) => {
              const el = document.createElement("div");
              el.className = "dash-activity-item";
              const monoClass = `mono-${(a.agent || 'sh').substring(0, 2).toLowerCase()}`;
              el.innerHTML = `
                <div style="display:flex; align-items:center; gap:8px;">
                  ${getAgentIconHtml(a.agent, 20)}
                  <div>
                    <div style="font-weight:600; font-size:0.8rem; color:var(--text-primary);">${a.title}</div>
                    <div style="font-size:0.72rem; color:var(--text-muted);">${a.details || a.path || ""}</div>
                  </div>
                </div>
                <div style="font-family:var(--font-mono); font-size:0.7rem; color:var(--text-dim); white-space:nowrap;">${a.time_str}</div>
              `;
              actBox.appendChild(el);
            });
          }
        }
      }
    } catch (e) {}
  }

  document.getElementById("btn-dashboard-refresh")?.addEventListener("click", loadDashboardView);

  // --------------------------------------------------
  // Universal Sessions & Agent History Hub
  // --------------------------------------------------
  const sessionPickerModal = document.getElementById("session-picker-modal");
  const sessionPickerSearch = document.getElementById("session-picker-search");
  const sessionPickerItems = document.getElementById("session-picker-items");
  let currentSessionFilter = "all";

  const quickAgentMeta = {
    shell: { title: "Shell", cmd: null, id: null },
    claude: { title: "Claude Code", cmd: "claude", id: "claude" },
    hermes: { title: "Hermes", cmd: "/home/jewboy420/hermes-env/bin/hermes", id: "hermes" },
    agy: { title: "Antigravity", cmd: "agy", id: "agy" },
    mochi: { title: "Mochi", cmd: "mochi", id: "mochi" },
    codex: { title: "Codex", cmd: "codex", id: "codex" },
    cline: { title: "Cline", cmd: "cline", id: "cline" },
    roo: { title: "Roo Code", cmd: "roo", id: "roo" },
    aider: { title: "Aider", cmd: "aider", id: "aider" },
    opencode: { title: "OpenCode", cmd: "opencode", id: "opencode" },
    gemini: { title: "Gemini CLI", cmd: "gemini", id: "gemini" },
    jcode: { title: "J-Code", cmd: "jcode repl", id: "jcode" },
    pi: { title: "Pi", cmd: "pi", id: "pi" },
    codebuff: { title: "Codebuff", cmd: "codebuff", id: "codebuff" },
    crush: { title: "Crush", cmd: "crush", id: "crush" }
  };

  // Quick Agent Launch buttons in modal (both .session-agent-pill and legacy .quick-agent-btn)
  document.querySelectorAll(".session-agent-pill, .quick-agent-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-quick-agent");
      const meta = quickAgentMeta[key] || { title: "Shell", cmd: null, id: null };
      closeSessionPicker();
      switchView("view-terminal");
      createTab(meta.title, meta.cmd, null, meta.id);
    });
  });

  // Filter pills
  document.querySelectorAll("#session-filter-pills .filter-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll("#session-filter-pills .filter-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentSessionFilter = pill.getAttribute("data-filter") || "all";
      renderSessionPicker();
    });
  });

  function openSessionPicker() {
    if (!sessionPickerModal) return;
    sessionPickerModal.classList.add("open");
    if (sessionPickerSearch) {
      sessionPickerSearch.value = "";
      sessionPickerSearch.focus();
    }
    renderSessionPicker();
  }
  window.openSessionPicker = openSessionPicker;

  function closeSessionPicker() {
    sessionPickerModal?.classList.remove("open");
    if (document.querySelector(".view-panel.active-view")?.id === "view-terminal") {
      ensureKeyboardFocus();
    }
  }

  // --------------------------------------------------
  // Session Transcript & Conversation Viewer Modal
  // --------------------------------------------------
  const sessionTranscriptModal = document.getElementById("session-transcript-modal");
  const transcriptTitleEl = document.getElementById("transcript-title");
  const transcriptMetaEl = document.getElementById("transcript-meta");
  const transcriptMonogramEl = document.getElementById("transcript-monogram");
  const transcriptContentEl = document.getElementById("transcript-content");
  const transcriptFilterInput = document.getElementById("transcript-filter-input");

  let activeTranscriptData = {
    sessionId: null,
    title: null,
    agentId: null,
    cwd: null,
    fullBuffer: ""
  };

  async function openSessionTranscript(sessionId, sessionTitle, agentId, cwd, isArchived = false) {
    if (!sessionTranscriptModal) return;
    sessionTranscriptModal.classList.add("open");

    if (transcriptMonogramEl) {
      transcriptMonogramEl.innerHTML = `<img src="/static/img/agents/${(agentId || 'shell').toLowerCase()}.svg" class="agent-icon" alt="${escapeHtml(agentId || 'Agent')}" onerror="this.style.display='none'; this.parentElement.innerText='${(agentId || 'SH').substring(0, 2).toUpperCase()}';" />`;
      transcriptMonogramEl.className = `agent-monogram ${getAgentMonogramClass(agentId)}`;
    }
    if (transcriptTitleEl) transcriptTitleEl.textContent = `${sessionTitle} — Conversation & Log`;
    if (transcriptMetaEl) transcriptMetaEl.textContent = `Path: ${cwd || "/home/jewboy420"} · ${isArchived ? "Archived Record" : "Active Terminal Session"}`;
    if (transcriptFilterInput) transcriptFilterInput.value = "";
    if (transcriptContentEl) transcriptContentEl.textContent = "Loading conversation transcript...";

    activeTranscriptData = {
      sessionId,
      title: sessionTitle,
      agentId,
      cwd,
      fullBuffer: ""
    };

    try {
      const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/buffer`);
      if (!res.ok) {
        if (transcriptContentEl) transcriptContentEl.textContent = "Failed to load conversation buffer.";
        return;
      }
      const data = await res.json();
      const rawText = data.buffer || "No terminal output recorded.";
      const cleanText = rawText.replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '');
      activeTranscriptData.fullBuffer = cleanText;
      if (transcriptContentEl) {
        transcriptContentEl.textContent = cleanText || "Empty session transcript.";
        transcriptContentEl.scrollTop = transcriptContentEl.scrollHeight;
      }
      if (transcriptMetaEl) {
        const sizeKb = ((data.total_bytes || cleanText.length) / 1024).toFixed(1);
        transcriptMetaEl.textContent = `${cwd || "/home/jewboy420"} · ${sizeKb} KB · ${data.is_active ? "● Live Active" : "○ Archived"}`;
      }
    } catch (err) {
      if (transcriptContentEl) transcriptContentEl.textContent = "Error fetching transcript: " + err.message;
    }
  }

  transcriptFilterInput?.addEventListener("input", () => {
    const q = (transcriptFilterInput.value || "").toLowerCase();
    if (!transcriptContentEl || !activeTranscriptData.fullBuffer) return;
    if (!q) {
      transcriptContentEl.textContent = activeTranscriptData.fullBuffer;
      return;
    }
    const lines = activeTranscriptData.fullBuffer.split("\n");
    const matching = lines.filter(l => l.toLowerCase().includes(q));
    transcriptContentEl.textContent = matching.length > 0 ? matching.join("\n") : `No lines matching "${q}"`;
  });

  document.getElementById("btn-copy-transcript")?.addEventListener("click", () => {
    if (!activeTranscriptData.fullBuffer) return;
    navigator.clipboard.writeText(activeTranscriptData.fullBuffer).then(() => {
      showToast("Transcript copied to clipboard!");
    }).catch(() => {
      showToast("Failed to copy transcript");
    });
  });

  document.getElementById("btn-download-transcript")?.addEventListener("click", () => {
    if (!activeTranscriptData.fullBuffer) return;
    const blob = new Blob([activeTranscriptData.fullBuffer], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const safeTitle = (activeTranscriptData.title || "session").replace(/[^a-zA-Z0-9_-]/g, "_");
    a.download = `terminus-${safeTitle}-${activeTranscriptData.sessionId}.log`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast("Exported conversation log");
  });

  document.getElementById("btn-relaunch-from-transcript")?.addEventListener("click", async () => {
    const sid = activeTranscriptData.sessionId;
    if (!sid) return;
    sessionTranscriptModal?.classList.remove("open");
    closeSessionPicker();
    switchView("view-terminal");

    try {
      const res = await fetch(`/api/sessions/${encodeURIComponent(sid)}/relaunch`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        activeSessions.push({ id: data.session_id, title: data.title, cwd: data.cwd, agent_id: data.agent_id });
        renderTabs();
        getOrCreateTerminalTab(data.session_id, data.title, data.cwd, data.agent_id);
        switchTab(data.session_id);
        showToast(`Relaunched: ${data.title}`);
      } else {
        const meta = quickAgentMeta[activeTranscriptData.agentId] || { title: activeTranscriptData.title, cmd: null, id: null };
        createTab(activeTranscriptData.title || meta.title, meta.cmd, activeTranscriptData.cwd, activeTranscriptData.agentId);
      }
    } catch (e) {
      const meta = quickAgentMeta[activeTranscriptData.agentId] || { title: activeTranscriptData.title, cmd: null, id: null };
      createTab(activeTranscriptData.title || meta.title, meta.cmd, activeTranscriptData.cwd, activeTranscriptData.agentId);
    }
  });

  async function renderSessionPicker() {
    if (!sessionPickerItems) return;
    const q = (sessionPickerSearch?.value || "").toLowerCase().trim();

    sessionPickerItems.innerHTML = `<div style="color:var(--text-muted); padding:16px; text-align:center;">Scanning sessions and agent transcripts...</div>`;

    try {
      const res = await fetch("/api/sessions");
      if (!res.ok) return;
      const data = await res.json();
      const activeList = data.sessions || [];
      const historyList = data.history || [];

      // Update counters
      const countActiveEl = document.getElementById("count-active");
      if (countActiveEl) countActiveEl.textContent = activeList.length;
      const countArchivedEl = document.getElementById("count-archived");
      if (countArchivedEl) countArchivedEl.textContent = historyList.length;

      // Sync activeSessions in memory
      if (activeList.length > 0) {
        activeSessions = activeList.map(s => ({
          id: s.id,
          title: s.title,
          cwd: s.cwd,
          agent_id: s.agent_id
        }));
        renderTabs();
      }

      // Combine both active and historical sessions
      const allSessions = [
        ...activeList.map(s => ({ ...s, is_active: true })),
        ...historyList.map(h => ({ ...h, is_active: false }))
      ];

      // Apply filter
      let filtered = allSessions.filter(s => {
        // Category filter
        if (currentSessionFilter === "active" && !s.is_active) return false;
        if (currentSessionFilter === "archived" && s.is_active) return false;
        if (["claude", "hermes", "agy", "mochi", "codex", "cline", "codebuff", "crush", "shell"].includes(currentSessionFilter)) {
          const aid = (s.agent_id || "shell").toLowerCase();
          if (currentSessionFilter === "shell") {
            if (aid !== "shell" && aid !== "sh" && aid !== "" && s.agent_id) return false;
          } else {
            if (!aid.includes(currentSessionFilter)) return false;
          }
        }

        // Search text filter
        if (!q) return true;
        const matchesTitle = (s.title || "").toLowerCase().includes(q);
        const matchesId = (s.id || "").toLowerCase().includes(q);
        const matchesCwd = (s.cwd || "").toLowerCase().includes(q);
        const matchesAgent = (s.agent_id || "").toLowerCase().includes(q);
        const matchesSnippet = (s.snippet || "").toLowerCase().includes(q);
        return matchesTitle || matchesId || matchesCwd || matchesAgent || matchesSnippet;
      });

      sessionPickerItems.innerHTML = "";
      if (filtered.length === 0) {
        sessionPickerItems.innerHTML = `<div style="text-align:center; padding:32px 16px; color:var(--text-muted); font-size:0.82rem;">
          No sessions found matching current filter "${currentSessionFilter}"
        </div>`;
        return;
      }

      filtered.forEach((sess) => {
        const card = document.createElement("div");
        const isCurrent = sess.id === currentSessionId && sess.is_active;
        card.className = `session-picker-card ${isCurrent ? "active" : ""}`;

        const agentCode = (sess.agent_id || "sh").substring(0, 2).toLowerCase();
        const monoClass = `mono-${agentCode}`;
        const agentBadge = (sess.agent_id || "SHELL").toUpperCase();
        const sizeStr = sess.total_bytes ? `${(sess.total_bytes / 1024).toFixed(1)} KB` : "";

        // Format date or relative time
        let timeLabel = "";
        if (sess.is_active) {
          timeLabel = `<span class="badge-status running" style="font-size:0.65rem; padding:1px 6px;">● Active</span>`;
        } else {
          let closedDate = sess.closed_at ? new Date(sess.closed_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Past";
          timeLabel = `<span class="badge-status" style="font-size:0.65rem; padding:1px 6px; background:rgba(255,255,255,0.06); color:var(--text-muted);">○ Closed ${closedDate}</span>`;
        }

        const snippetHtml = sess.snippet ? `
          <div class="session-snippet-preview" title="Recent conversation / terminal snippet">
            ${escapeHtml(sess.snippet)}
          </div>
        ` : "";

        card.innerHTML = `
          <div class="session-card-header">
            <div class="session-card-info">
              ${getAgentIconHtml(sess.agent_id, 28)}
              <div style="flex:1; overflow:hidden;">
                <div class="session-title-edit-wrap">
                  <span class="session-title-text" id="title-text-${sess.id}">${escapeHtml(sess.title)}</span>
                  <button type="button" class="action-btn" style="padding:1px 5px; font-size:0.65rem;" data-rename-sid="${sess.id}" title="Rename session">Rename</button>
                  <span class="badge-status installed" style="font-size:0.65rem; padding:1px 5px;">${agentBadge}</span>
                  ${timeLabel}
                </div>
                <div class="session-sub-meta">
                  <span style="overflow:hidden; text-overflow:ellipsis;">${escapeHtml(sess.cwd || "/home/jewboy420")}</span>
                  ${sizeStr ? `<span>· ${sizeStr}</span>` : ""}
                  ${sess.clients ? `<span>· ${sess.clients} client(s)</span>` : ""}
                </div>
              </div>
            </div>

            <div class="session-picker-actions">
              ${sess.is_active ? `
                <button class="action-btn btn-primary-action" data-switch-sid="${sess.id}" style="padding:3px 10px; font-size:0.74rem;">Resume</button>
                <button class="action-btn" data-transcript-sid="${sess.id}" style="padding:3px 8px; font-size:0.74rem;" title="View conversation & logs">Transcript</button>
                <button class="action-btn" data-duplicate-sid="${sess.id}" style="padding:3px 8px; font-size:0.74rem;" title="Duplicate session">Clone</button>
                <button class="action-btn" data-export-sid="${sess.id}" style="padding:3px 8px; font-size:0.74rem;" title="Download transcript log">Export</button>
                ${activeSessions.length > 1 ? `<button class="action-btn" data-kill-sid="${sess.id}" style="padding:3px 8px; font-size:0.74rem; color:var(--accent-rose);" title="Close tab">Close</button>` : ""}
              ` : `
                <button class="action-btn btn-primary-action" data-relaunch-sid="${sess.id}" style="padding:3px 10px; font-size:0.74rem;">Relaunch</button>
                <button class="action-btn" data-transcript-sid="${sess.id}" style="padding:3px 8px; font-size:0.74rem;" title="View past conversation">Conversation</button>
                <button class="action-btn" data-export-sid="${sess.id}" style="padding:3px 8px; font-size:0.74rem;" title="Download past transcript">Export</button>
                <button class="action-btn" data-delete-history-sid="${sess.id}" style="padding:3px 8px; font-size:0.74rem; color:var(--text-muted);" title="Delete from history">Delete</button>
              `}
            </div>
          </div>
          ${snippetHtml}
        `;

        // Card click / Resume button: actually open that session/conversation/chat with corresponding agent!
        const doResume = async (e) => {
          if (e) e.stopPropagation();
          closeSessionPicker();
          switchView("view-terminal");
          showToast(`Resuming ${sess.title}...`);

          try {
            const res = await fetch(`/api/sessions/${encodeURIComponent(sess.id)}/resume`, { method: "POST" });
            if (res.ok) {
              const data = await res.json();
              const targetSid = data.session_id;
              let existing = activeSessions.find(s => s.id === targetSid);
              if (!existing) {
                activeSessions.push({ id: targetSid, title: data.title, cwd: data.cwd, agent_id: data.agent_id });
                renderTabs();
              } else {
                existing.title = data.title;
                existing.cwd = data.cwd;
                existing.agent_id = data.agent_id;
                renderTabs();
              }
              getOrCreateTerminalTab(targetSid, data.title, data.cwd, data.agent_id);
              switchTab(targetSid);
              return;
            }
          } catch (err) {}

          // Fallback direct switch
          if (!activeSessions.find(s => s.id === sess.id)) {
            activeSessions.push({ id: sess.id, title: sess.title, cwd: sess.cwd, agent_id: sess.agent_id });
            renderTabs();
          }
          getOrCreateTerminalTab(sess.id, sess.title, sess.cwd, sess.agent_id);
          switchTab(sess.id);
        };

        card.addEventListener("click", doResume);
        card.querySelector("[data-switch-sid]")?.addEventListener("click", doResume);
        card.querySelector("[data-relaunch-sid]")?.addEventListener("click", doResume);

        // Transcript button
        card.querySelector("[data-transcript-sid]")?.addEventListener("click", (e) => {
          e.stopPropagation();
          openSessionTranscript(sess.id, sess.title, sess.agent_id, sess.cwd, !sess.is_active);
        });

        // Rename button
        card.querySelector("[data-rename-sid]")?.addEventListener("click", (e) => {
          e.stopPropagation();
          const titleTextEl = card.querySelector(`#title-text-${sess.id}`);
          if (!titleTextEl) return;
          const currentName = titleTextEl.textContent;
          const input = document.createElement("input");
          input.type = "text";
          input.className = "session-title-input";
          input.value = currentName;
          titleTextEl.replaceWith(input);
          input.focus();

          const saveRename = async () => {
            const newName = input.value.trim();
            if (newName && newName !== currentName) {
              try {
                await fetch(`/api/sessions/${encodeURIComponent(sess.id)}/rename`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ title: newName })
                });
                sess.title = newName;
                const activeMeta = activeSessions.find(s => s.id === sess.id);
                if (activeMeta) activeMeta.title = newName;
                renderTabs();
                showToast(`Renamed to "${newName}"`);
              } catch (err) {}
            }
            renderSessionPicker();
          };

          input.addEventListener("keydown", (ke) => {
            if (ke.key === "Enter") saveRename();
            if (ke.key === "Escape") renderSessionPicker();
          });
          input.addEventListener("blur", saveRename);
        });

        // Duplicate button
        card.querySelector("[data-duplicate-sid]")?.addEventListener("click", async (e) => {
          e.stopPropagation();
          try {
            const dRes = await fetch(`/api/sessions/${encodeURIComponent(sess.id)}/duplicate`, { method: "POST" });
            if (dRes.ok) {
              const dData = await dRes.json();
              activeSessions.push({ id: dData.session_id, title: dData.title, cwd: dData.cwd, agent_id: dData.agent_id });
              renderTabs();
              getOrCreateTerminalTab(dData.session_id, dData.title, dData.cwd, dData.agent_id);
              closeSessionPicker();
              switchView("view-terminal");
              switchTab(dData.session_id);
              showToast(`Cloned: ${dData.title}`);
            }
          } catch (err) {}
        });

        // Export button
        card.querySelector("[data-export-sid]")?.addEventListener("click", async (e) => {
          e.stopPropagation();
          try {
            const bRes = await fetch(`/api/sessions/${encodeURIComponent(sess.id)}/buffer`);
            if (bRes.ok) {
              const bData = await bRes.json();
              const blob = new Blob([bData.buffer || ""], { type: "text/plain;charset=utf-8" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              const safeTitle = (sess.title || "session").replace(/[^a-zA-Z0-9_-]/g, "_");
              a.download = `terminus-${safeTitle}-${sess.id}.log`;
              document.body.appendChild(a);
              a.click();
              a.remove();
              URL.revokeObjectURL(url);
              showToast("Exported terminal transcript");
            }
          } catch (err) {}
        });

        // Kill active session
        card.querySelector("[data-kill-sid]")?.addEventListener("click", (e) => {
          e.stopPropagation();
          closeTab(sess.id);
          renderSessionPicker();
        });

        // Delete from history
        card.querySelector("[data-delete-history-sid]")?.addEventListener("click", async (e) => {
          e.stopPropagation();
          try {
            await fetch(`/api/sessions/${encodeURIComponent(sess.id)}/history`, { method: "DELETE" });
            showToast("Removed from history");
            renderSessionPicker();
          } catch (err) {}
        });

        sessionPickerItems.appendChild(card);
      });
    } catch (e) {
      sessionPickerItems.innerHTML = `<div style="color:var(--accent-rose); padding:16px; text-align:center;">Failed to load sessions</div>`;
    }
  }

  sessionPickerSearch?.addEventListener("input", renderSessionPicker);
  document.getElementById("btn-open-session-picker")?.addEventListener("click", openSessionPicker);
  document.getElementById("btn-subbar-sessions")?.addEventListener("click", openSessionPicker);

  // --------------------------------------------------
  // Split-Screen Dual Terminal Matrix
  // --------------------------------------------------
  let isSplitActive = false;
  let secondarySessionId = null;
  let secondaryTab = null;

  const terminalWorkspace = document.getElementById("terminal-workspace");
  const btnSplitToggle = document.getElementById("btn-split-toggle");
  const splitSecondarySelect = document.getElementById("split-secondary-select");
  const splitSecondaryBody = document.getElementById("terminal-viewport-secondary-body");

  function toggleSplitView() {
    isSplitActive = !isSplitActive;
    if (terminalWorkspace) {
      terminalWorkspace.classList.toggle("split-active", isSplitActive);
    }
    if (btnSplitToggle) {
      btnSplitToggle.innerHTML = isSplitActive
        ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 3v18"/></svg><span>Single View</span>`
        : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="12" y1="3" x2="12" y2="21"/></svg><span>Split Dual</span>`;
    }

    if (isSplitActive) {
      populateSecondaryDropdown();
      const other = activeSessions.find(s => s.id !== currentSessionId);
      if (other) {
        attachSecondarySession(other.id);
      } else if (activeSessions.length === 1) {
        createTab("Secondary Shell").then(() => {
          populateSecondaryDropdown();
        });
      }
    } else {
      detachSecondarySession();
    }

    setTimeout(() => {
      safeFitActiveTab();
      if (secondaryTab) safeFitTab(secondaryTab);
    }, 120);
  }
  window.toggleSplitView = toggleSplitView;

  function populateSecondaryDropdown() {
    if (!splitSecondarySelect) return;
    splitSecondarySelect.innerHTML = `<option value="">Select Session...</option>`;
    activeSessions.forEach(s => {
      if (s.id !== currentSessionId) {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = `${s.title} (${(s.agent_id || 'sh').toUpperCase()})`;
        if (s.id === secondarySessionId) opt.selected = true;
        splitSecondarySelect.appendChild(opt);
      }
    });
  }

  function attachSecondarySession(sid) {
    if (!sid || sid === currentSessionId) return;
    secondarySessionId = sid;
    const tabMeta = activeSessions.find(s => s.id === sid);
    secondaryTab = getOrCreateTerminalTab(sid, tabMeta?.title || "Secondary", tabMeta?.cwd, tabMeta?.agent_id);

    if (splitSecondaryBody && secondaryTab.container) {
      splitSecondaryBody.appendChild(secondaryTab.container);
      secondaryTab.container.style.display = "block";
      safeFitTab(secondaryTab);
    }
  }

  function detachSecondarySession() {
    if (secondaryTab && secondaryTab.container && terminalViewport) {
      terminalViewport.appendChild(secondaryTab.container);
      if (secondaryTab.id !== currentSessionId) {
        secondaryTab.container.style.display = "none";
      }
    }
    secondarySessionId = null;
    secondaryTab = null;
  }

  btnSplitToggle?.addEventListener("click", toggleSplitView);
  splitSecondarySelect?.addEventListener("change", (e) => {
    if (e.target.value) attachSecondarySession(e.target.value);
  });

  // --------------------------------------------------
  // View: Universal Skill Tree & Cross-Agent Bridge
  // --------------------------------------------------
  let cachedSkillsTree = null;
  let currentSkillOrigin = "all";
  let currentSkillSearch = "";

  async function loadSkillsView(force = false) {
    const root = document.getElementById("skills-tree-root");
    const countSub = document.getElementById("skills-count-subtitle");
    if (!root) return;

    if (force || !cachedSkillsTree) {
      root.innerHTML = `<div style="color:var(--text-muted); padding:32px; text-align:center;">Discovering skills across Hermes, Antigravity, and Claude...</div>`;
      try {
        const url = force ? "/api/skills?force=true" : "/api/skills";
        const res = await fetch(url);
        if (!res.ok) return;
        cachedSkillsTree = await res.json();
      } catch (e) {
        root.innerHTML = `<div style="color:var(--accent-rose); padding:24px; text-align:center;">Error scanning skill tree</div>`;
        return;
      }
    }

    if (countSub && cachedSkillsTree) {
      countSub.textContent = `${cachedSkillsTree.total_skills} specialized capability modules across ${cachedSkillsTree.total_categories} categories — usable by any agent`;
    }

    renderSkillsTree();
  }
  window.loadSkillsView = loadSkillsView;

  function renderSkillsTree() {
    const root = document.getElementById("skills-tree-root");
    if (!root || !cachedSkillsTree) return;

    const tree = cachedSkillsTree.tree || {};
    const q = currentSkillSearch.toLowerCase().trim();
    root.innerHTML = "";

    let totalVisible = 0;

    Object.entries(tree).forEach(([category, skills]) => {
      let matched = skills.filter(s => {
        const matchOrigin = currentSkillOrigin === "all" || s.origin.toLowerCase().includes(currentSkillOrigin.toLowerCase());
        const matchQ = !q ||
          s.name.toLowerCase().includes(q) ||
          s.title.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q) ||
          (s.tags && s.tags.some(t => t.toLowerCase().includes(q))) ||
          (s.scripts && s.scripts.some(sc => sc.name.toLowerCase().includes(q)));
        return matchOrigin && matchQ;
      });

      if (matched.length === 0) return;
      totalVisible += matched.length;

      const block = document.createElement("div");
      block.className = "skill-category-block";

      const header = document.createElement("div");
      header.className = "skill-category-header";
      header.innerHTML = `
        <div class="skill-cat-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
          </svg>
          <span>${category}</span>
        </div>
        <span class="skill-cat-count">${matched.length} skill${matched.length > 1 ? 's' : ''}</span>
      `;

      const grid = document.createElement("div");
      grid.className = "skills-cards-grid";

      matched.forEach((s) => {
        const card = document.createElement("div");
        card.className = "skill-card";

        const originClass = `skill-origin-${(s.origin || 'universal').toLowerCase().replace(/\s+/g, '')}`;

        card.innerHTML = `
          <div>
            <div class="skill-card-top">
              <div class="skill-name">${s.title}</div>
              <span class="skill-origin-pill ${originClass}">${s.origin}</span>
            </div>
            <div class="skill-desc">${s.description}</div>
            <div class="skill-tags-row">
              ${(s.tags || []).slice(0, 4).map(t => `<span class="skill-tag">#${t}</span>`).join('')}
              ${s.scripts && s.scripts.length > 0 ? `<span class="skill-tag" style="background:rgba(59,130,246,0.15); color:var(--accent-blue);">${s.scripts.length} script${s.scripts.length > 1 ? 's' : ''}</span>` : ''}
            </div>
          </div>
          <div class="skill-card-actions">
            <button class="action-btn btn-primary-action" data-inspect-skill="${s.id}" style="padding:3px 8px; font-size:0.72rem; flex:1;">Inspect</button>
            <button class="action-btn" data-inject-skill="${s.id}" style="padding:3px 8px; font-size:0.72rem;" title="Inject into active terminal tab">Inject</button>
          </div>
        `;

        card.addEventListener("click", () => inspectSkill(s.id));
        card.querySelector("[data-inspect-skill]")?.addEventListener("click", (e) => {
          e.stopPropagation();
          inspectSkill(s.id);
        });
        card.querySelector("[data-inject-skill]")?.addEventListener("click", (e) => {
          e.stopPropagation();
          injectSkillIntoSession(s.id, currentSessionId);
        });

        grid.appendChild(card);
      });

      header.addEventListener("click", () => {
        const isCollapsed = grid.style.display === "none";
        grid.style.display = isCollapsed ? "grid" : "none";
      });

      block.appendChild(header);
      block.appendChild(grid);
      root.appendChild(block);
    });

    if (totalVisible === 0) {
      root.innerHTML = `<div style="text-align:center; padding:36px; color:var(--text-muted); font-size:0.85rem;">No skills matching criteria</div>`;
    }
  }

  // Skill Inspector Modal
  const skillInspectorModal = document.getElementById("skill-inspector-modal");
  let currentlyInspectedSkillId = null;

  async function inspectSkill(skillId) {
    currentlyInspectedSkillId = skillId;
    if (!skillInspectorModal) return;
    skillInspectorModal.classList.add("open");

    const tTitle = document.getElementById("inspect-skill-title");
    const tOrigin = document.getElementById("inspect-origin-pill");
    const tDesc = document.getElementById("inspect-skill-desc");
    const tMd = document.getElementById("inspect-skill-markdown");
    const tScriptsWrap = document.getElementById("inspect-scripts-wrap");
    const tScriptsList = document.getElementById("inspect-scripts-list");

    if (tTitle) tTitle.textContent = "Loading skill...";
    if (tMd) tMd.textContent = "Fetching documentation...";
    if (tScriptsWrap) tScriptsWrap.style.display = "none";

    try {
      const res = await fetch(`/api/skills/details?id=${encodeURIComponent(skillId)}`);
      if (!res.ok) return;
      const data = await res.json();

      if (tTitle) tTitle.textContent = data.title || data.name;
      if (tOrigin) {
        tOrigin.textContent = (data.origin || "UNIVERSAL").toUpperCase();
        tOrigin.className = `skill-origin-pill skill-origin-${(data.origin || 'universal').toLowerCase().replace(/\s+/g, '')}`;
      }
      if (tDesc) tDesc.textContent = data.description || "";
      if (tMd) tMd.textContent = data.content || "(No documentation content)";

      if (data.scripts && data.scripts.length > 0 && tScriptsWrap && tScriptsList) {
        tScriptsWrap.style.display = "block";
        tScriptsList.innerHTML = "";
        data.scripts.forEach(sc => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "action-btn";
          btn.style.padding = "2px 8px";
          btn.style.fontSize = "0.72rem";
          btn.textContent = `▶ ${sc.name}`;
          btn.title = `Run ${sc.name} in terminal`;
          btn.addEventListener("click", () => {
            skillInspectorModal.classList.remove("open");
            switchView("view-terminal");
            sendTerminalInput(`python3 "${sc.path}" || bash "${sc.path}"\n`);
          });
          tScriptsList.appendChild(btn);
        });
      }
    } catch (e) {
      if (tMd) tMd.textContent = "Error reading skill documentation";
    }
  }

  async function injectSkillIntoSession(skillId, sessionId) {
    try {
      const res = await fetch("/api/skills/inject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill_id: skillId, session_id: sessionId })
      });
      if (res.ok) {
        showToast("Skill instructions injected into active session!");
        skillInspectorModal?.classList.remove("open");
        switchView("view-terminal");
      }
    } catch (e) {
      showToast("Error injecting skill");
    }
  }

  async function bridgeSkill(skillId, targetAgent) {
    try {
      const res = await fetch("/api/skills/bridge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill_id: skillId, target_agent: targetAgent })
      });
      if (res.ok) {
        const data = await res.json();
        showToast(data.message || `Exported skill to ${targetAgent}`);
      }
    } catch (e) {
      showToast(`Error bridging skill to ${targetAgent}`);
    }
  }

  document.getElementById("btn-inject-active-session")?.addEventListener("click", () => {
    if (currentlyInspectedSkillId) injectSkillIntoSession(currentlyInspectedSkillId, currentSessionId);
  });
  document.getElementById("btn-bridge-antigravity")?.addEventListener("click", () => {
    if (currentlyInspectedSkillId) bridgeSkill(currentlyInspectedSkillId, "antigravity");
  });
  document.getElementById("btn-bridge-hermes")?.addEventListener("click", () => {
    if (currentlyInspectedSkillId) bridgeSkill(currentlyInspectedSkillId, "hermes");
  });
  document.getElementById("btn-bridge-project")?.addEventListener("click", () => {
    if (currentlyInspectedSkillId) bridgeSkill(currentlyInspectedSkillId, "project");
  });

  document.getElementById("skills-search-input")?.addEventListener("input", (e) => {
    currentSkillSearch = e.target.value;
    renderSkillsTree();
  });

  document.querySelectorAll("#skills-origin-filters button").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#skills-origin-filters button").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentSkillOrigin = btn.getAttribute("data-skill-origin") || "all";
      renderSkillsTree();
    });
  });

  document.getElementById("btn-rescan-skills")?.addEventListener("click", () => loadSkillsView(true));

  // --------------------------------------------------
  // View: Universal Multi-Agent Memory & Context Hub
  // --------------------------------------------------
  async function loadMemoryView() {
    const grid = document.getElementById("memory-cards-grid");
    const q = (document.getElementById("memory-search-input")?.value || "").trim();
    const agent = document.getElementById("memory-agent-select")?.value || "all";
    if (!grid) return;

    grid.innerHTML = `<div style="color:var(--text-muted); padding:24px;">Loading shared memories and agent knowledge...</div>`;

    try {
      const url = `/api/memory?query=${encodeURIComponent(q)}&agent=${encodeURIComponent(agent)}`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      const mems = data.memories || [];

      grid.innerHTML = "";
      if (mems.length === 0) {
        grid.innerHTML = `
          <div style="grid-column: 1 / -1; padding:36px; background:var(--bg-surface); border:1px dashed var(--border-subtle); border-radius:8px; text-align:center;">
            <div style="font-weight:600; color:var(--text-primary); margin-bottom:6px;">No Shared Memories Stored</div>
            <div style="font-size:0.8rem; color:var(--text-muted); max-width:480px; margin:0 auto;">
              Add shared memories or architectural guidelines so Claude Code, Hermes, Antigravity, and Mochi share identical context.
            </div>
          </div>
        `;
        return;
      }

      mems.forEach(m => {
        const card = document.createElement("div");
        card.className = "memory-card";
        card.innerHTML = `
          <div>
            <div class="memory-header">
              <div>
                <div class="memory-title">${m.title}</div>
                <div style="font-size:0.7rem; color:var(--text-muted); font-family:var(--font-mono);">${m.agent_origin} · ${m.time_str}</div>
              </div>
              <button class="action-btn" style="padding:2px 6px; font-size:0.68rem; color:var(--accent-rose);" data-delete-mem="${m.id}" title="Delete memory">Delete</button>
            </div>
            <div class="memory-content">${m.content}</div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; gap:4px; flex-wrap:wrap;">
              ${(m.tags || []).map(t => `<span class="skill-tag">#${t}</span>`).join('')}
            </div>
            <button class="action-btn" style="padding:2px 8px; font-size:0.7rem;" data-copy-mem="${m.id}">Copy</button>
          </div>
        `;

        card.querySelector("[data-delete-mem]")?.addEventListener("click", async () => {
          if (!confirm(`Delete memory "${m.title}"?`)) return;
          try {
            await fetch(`/api/memory/${encodeURIComponent(m.id)}`, { method: "DELETE" });
            showToast("Deleted memory");
            loadMemoryView();
          } catch (e) {}
        });

        card.querySelector("[data-copy-mem]")?.addEventListener("click", () => {
          navigator.clipboard?.writeText(m.content).then(() => showToast("Copied memory to clipboard"));
        });

        grid.appendChild(card);
      });
    } catch (e) {
      grid.innerHTML = `<div style="color:var(--accent-rose); padding:24px;">Failed to load memories</div>`;
    }
  }
  window.loadMemoryView = loadMemoryView;

  const addMemoryModal = document.getElementById("add-memory-modal");
  document.getElementById("btn-open-add-memory")?.addEventListener("click", () => {
    addMemoryModal?.classList.add("open");
  });
  document.getElementById("btn-refresh-memory")?.addEventListener("click", loadMemoryView);
  document.getElementById("memory-search-input")?.addEventListener("input", () => {
    clearTimeout(window._memSearchTimer);
    window._memSearchTimer = setTimeout(loadMemoryView, 250);
  });
  document.getElementById("memory-agent-select")?.addEventListener("change", loadMemoryView);

  document.getElementById("add-memory-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = document.getElementById("new-mem-title")?.value || "";
    const content = document.getElementById("new-mem-content")?.value || "";
    const origin = document.getElementById("new-mem-origin")?.value || "User / Manual";
    const rawTags = document.getElementById("new-mem-tags")?.value || "";
    const tags = rawTags.split(",").map(t => t.trim()).filter(Boolean);

    try {
      const res = await fetch("/api/memory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, content, agent_origin: origin, tags })
      });
      if (res.ok) {
        addMemoryModal?.classList.remove("open");
        showToast(`Saved memory: "${title}"`);
        loadMemoryView();
        document.getElementById("add-memory-form").reset();
      }
    } catch (e) {}
  });

  // --------------------------------------------------
  // View: Universal Autonomous Cron & Multi-Agent Scheduler
  // --------------------------------------------------
  async function loadCronView() {
    const list = document.getElementById("cron-jobs-list");
    if (!list) return;
    list.innerHTML = `<div style="color:var(--text-muted); padding:24px;">Loading autonomous agent tasks...</div>`;

    try {
      const res = await fetch("/api/cron");
      if (!res.ok) return;
      const data = await res.json();
      const jobs = data.jobs || [];

      list.innerHTML = "";
      if (jobs.length === 0) {
        list.innerHTML = `<div style="text-align:center; padding:36px; color:var(--text-muted);">No scheduled tasks configured</div>`;
        return;
      }

      jobs.forEach(j => {
        const card = document.createElement("div");
        card.className = "cron-card";

        const statusPill = j.last_status === "success"
          ? `<span class="badge-status installed" style="font-size:0.68rem;">Passed</span>`
          : (j.last_status === "failed" ? `<span class="badge-status" style="color:var(--accent-rose); font-size:0.68rem;">Failed</span>` : `<span class="badge-status" style="color:var(--text-dim); font-size:0.68rem;">Pending</span>`);

        const toggleBtnText = j.enabled ? "Enabled" : "Disabled";
        const toggleBtnClass = j.enabled ? "btn-primary-action" : "";

        card.innerHTML = `
          <div class="cron-info-block">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="cron-name">${j.name}</span>
              <span class="badge-status running" style="font-size:0.65rem; padding:1px 5px;">${j.agent_name || j.agent_id}</span>
              ${statusPill}
            </div>
            <div class="cron-meta-row">
              <span>Schedule: <strong>${j.schedule}</strong></span>
              <span>·</span>
              <span>Last Run: ${j.last_run_str}</span>
              <span>·</span>
              <span>Target: ${j.cwd}</span>
            </div>
            <div class="cron-cmd-preview" title="${j.prompt_or_cmd}">$ ${j.prompt_or_cmd}</div>
          </div>
          <div class="cron-controls">
            <button class="action-btn ${toggleBtnClass}" style="padding:4px 10px; font-size:0.75rem;" data-toggle-cron="${j.id}">${toggleBtnText}</button>
            <button class="action-btn btn-primary-action" style="padding:4px 10px; font-size:0.75rem;" data-run-cron="${j.id}">Run Now</button>
            <button class="action-btn" style="padding:4px 8px; font-size:0.75rem; color:var(--accent-rose);" data-delete-cron="${j.id}">Delete</button>
          </div>
        `;

        card.querySelector("[data-toggle-cron]")?.addEventListener("click", async () => {
          try {
            await fetch(`/api/cron/${encodeURIComponent(j.id)}/toggle`, { method: "POST" });
            loadCronView();
          } catch (e) {}
        });

        card.querySelector("[data-run-cron]")?.addEventListener("click", async () => {
          showToast(`Executing task: ${j.name}...`);
          try {
            const rRes = await fetch(`/api/cron/${encodeURIComponent(j.id)}/run`, { method: "POST" });
            const rData = await rRes.json();
            showToast(rData.success ? `Task completed successfully!` : `Task failed (code ${rData.exit_code})`);
            loadCronView();
          } catch (e) {
            showToast("Error running task");
          }
        });

        card.querySelector("[data-delete-cron]")?.addEventListener("click", async () => {
          if (!confirm(`Delete task "${j.name}"?`)) return;
          try {
            await fetch(`/api/cron/${encodeURIComponent(j.id)}`, { method: "DELETE" });
            showToast("Deleted task");
            loadCronView();
          } catch (e) {}
        });

        list.appendChild(card);
      });
    } catch (e) {
      list.innerHTML = `<div style="color:var(--accent-rose); padding:24px;">Failed to load cron jobs</div>`;
    }
  }
  window.loadCronView = loadCronView;

  const addCronModal = document.getElementById("add-cron-modal");
  document.getElementById("btn-open-add-cron")?.addEventListener("click", () => {
    addCronModal?.classList.add("open");
  });
  document.getElementById("btn-refresh-cron")?.addEventListener("click", loadCronView);

  document.getElementById("add-cron-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("new-cron-name")?.value || "";
    const agent_id = document.getElementById("new-cron-agent")?.value || "bash";
    const schedule = document.getElementById("new-cron-schedule")?.value || "Hourly";
    const prompt_or_cmd = document.getElementById("new-cron-cmd")?.value || "";
    const cwd = document.getElementById("new-cron-cwd")?.value || "/home/jewboy420";

    try {
      const res = await fetch("/api/cron", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, agent_id, prompt_or_cmd, schedule, cwd })
      });
      if (res.ok) {
        addCronModal?.classList.remove("open");
        showToast(`Scheduled task: "${name}"`);
        loadCronView();
        document.getElementById("add-cron-form").reset();
      }
    } catch (e) {}
  });

  // --------------------------------------------------
  // View: Activity Monitor
  // --------------------------------------------------
  async function loadActivityView() {
    const listEl = document.getElementById("activity-timeline-list");
    if (!listEl) return;
    listEl.innerHTML = `<div style="text-align:center; padding:24px; color:var(--text-muted); font-size:0.82rem;">Loading unified agent activity stream...</div>`;

    try {
      const res = await fetch("/api/activity?limit=60");
      if (!res.ok) return;
      const data = await res.json();
      const acts = data.activities || [];

      listEl.innerHTML = "";
      if (acts.length === 0) {
        listEl.innerHTML = `<div style="text-align:center; padding:36px; color:var(--text-muted);">No activity recorded yet</div>`;
        return;
      }

      acts.forEach((a) => {
        const row = document.createElement("div");
        row.className = "activity-timeline-row";
        const monoClass = `mono-${(a.agent || 'sh').substring(0, 2).toLowerCase()}`;
        row.innerHTML = `
          <div class="activity-left">
            ${getAgentIconHtml(a.agent, 24)}
            <div>
              <div class="activity-title">${a.title}</div>
              <div class="activity-meta">
                <span>${a.agent_name || a.agent}</span>
                <span>·</span>
                <span class="badge-status installed" style="font-size:0.65rem; padding:1px 5px;">${a.action}</span>
                ${a.path ? `<span>·</span><span style="font-family:var(--font-mono);">${a.path}</span>` : ""}
              </div>
              ${a.details ? `<div class="activity-details">${a.details}</div>` : ""}
            </div>
          </div>
          <div class="activity-time">${a.time_str}</div>
        `;
        listEl.appendChild(row);
      });
    } catch (e) {
      listEl.innerHTML = `<div style="color:var(--accent-rose); padding:24px; text-align:center;">Failed to load activity</div>`;
    }
  }

  document.getElementById("btn-refresh-activity")?.addEventListener("click", loadActivityView);

  // --------------------------------------------------
  // View: Model Context Protocol (MCP) Registry
  // --------------------------------------------------
  async function loadMcpView() {
    const grid = document.getElementById("mcp-servers-grid");
    if (!grid) return;
    grid.innerHTML = `<div style="color:var(--text-muted); padding:24px;">Scanning MCP servers and multi-agent resource bridges...</div>`;

    try {
      const res = await fetch("/api/mcp");
      if (!res.ok) return;
      const data = await res.json();
      const servers = data.servers || [];

      grid.innerHTML = "";
      if (servers.length === 0) {
        grid.innerHTML = `
          <div style="grid-column: 1 / -1; padding: 32px; background: var(--bg-surface); border: 1px dashed var(--border-subtle); border-radius: 8px; text-align: center;">
            <div style="font-weight:600; color:var(--text-primary); margin-bottom:6px;">No MCP Servers Discovered</div>
            <div style="font-size:0.8rem; color:var(--text-muted); max-width:480px; margin:0 auto;">
              Configure MCP servers in ~/.claude.json, ~/.gemini/config/mcp_config.json, or ~/.hermes/config.yaml to enable unified tools and cross-agent resources.
            </div>
          </div>
        `;
        return;
      }

      servers.forEach((s) => {
        const card = document.createElement("div");
        card.className = "mcp-card";
        const statusBadge = s.status === "active"
          ? `<span class="badge-status running">● Active</span>`
          : `<span class="badge-status installed">Configured</span>`;

        card.innerHTML = `
          <div class="mcp-card-header">
            <div>
              <div class="mcp-name">${s.name}</div>
              <div class="mcp-agent-sub">${s.agent}</div>
            </div>
            ${statusBadge}
          </div>
          <div class="mcp-body">
            <div class="mcp-prop-row">
              <span class="mcp-prop-label">Transport</span>
              <span class="mcp-prop-val">${s.transport.toUpperCase()}</span>
            </div>
            <div class="mcp-prop-row">
              <span class="mcp-prop-label">Source</span>
              <span class="mcp-prop-val">${s.source}</span>
            </div>
            <div class="mcp-cmd-box" title="${s.command} ${(s.args || []).join(' ')}">
              ${s.command} ${(s.args || []).join(' ')}
            </div>
          </div>
        `;
        grid.appendChild(card);
      });
    } catch (e) {
      grid.innerHTML = `<div style="color:var(--accent-rose); padding:24px;">Error scanning MCP registry</div>`;
    }
  }

  document.getElementById("btn-refresh-mcp")?.addEventListener("click", loadMcpView);

  // --------------------------------------------------
  // View: Agent Control Plane (All 18+ Agents)
  // --------------------------------------------------
  async function loadAgentsView() {
    const grid = document.getElementById("agents-grid");
    if (!grid) return;
    try {
      const res = await fetch("/api/agents");
      if (!res.ok) return;
      const data = await res.json();
      cachedAgents = data.agents || [];
      renderAgentsGrid();
    } catch (e) {}
  }

  function renderAgentsGrid() {
    const grid = document.getElementById("agents-grid");
    if (!grid) return;

    let list = cachedAgents.slice();
    if (currentAgentSearch) {
      const q = currentAgentSearch.toLowerCase().trim();
      list = list.filter(a =>
        a.name.toLowerCase().includes(q) ||
        a.id.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        (a.capabilities && a.capabilities.some(c => c.toLowerCase().includes(q)))
      );
    }

    grid.innerHTML = "";
    if (list.length === 0) {
      grid.innerHTML = `<div style="grid-column: 1 / -1; padding:36px; text-align:center; color:var(--text-muted); font-size:0.85rem;">No coding agents matching search</div>`;
      return;
    }

    list.forEach((a) => {
      const card = document.createElement("div");
      card.className = "agent-card";

      const statusBadge = a.running_count > 0
        ? `<span class="badge-status running">● Running (${a.running_count})</span>`
        : (a.installed ? `<span class="badge-status installed">Installed</span>` : `<span class="badge-status" style="color:var(--text-dim)">Not found</span>`);

      const monoClass = `mono-${a.id.substring(0, 2).toLowerCase()}`;

      card.innerHTML = `
        <div>
          <div class="agent-card-top">
            <div style="display:flex; align-items:center; gap:8px;">
              ${getAgentIconHtml(a.id, 28)}
              <div>
                <div class="agent-name">${a.name}</div>
                <div class="agent-version">${a.version || (a.installed ? "Installed" : "Not Found")}</div>
              </div>
            </div>
            ${statusBadge}
          </div>
          <div class="agent-desc">${a.description}</div>
          <div class="agent-capabilities" style="display:flex; flex-wrap:wrap; gap:4px; margin-top:8px;">
            ${(a.capabilities || []).map(c => `<span class="project-lang-pill" style="font-size:0.65rem;">${c}</span>`).join('')}
          </div>
        </div>
        <div class="agent-card-actions">
          ${a.installed ? `
            <button class="action-btn btn-primary-action" data-action="launch" data-agent="${a.id}" data-name="${a.name}">Launch</button>
            ${a.resume_cmd ? `<button class="action-btn" data-action="resume" data-agent="${a.id}" data-name="${a.name}">Resume</button>` : ""}
          ` : `<button class="action-btn" disabled style="opacity:0.4">Not Installed</button>`}
        </div>
      `;

      card.querySelectorAll("[data-action]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const action = btn.getAttribute("data-action");
          const aid = btn.getAttribute("data-agent");
          const aname = btn.getAttribute("data-name");
          launchAgentSession(aid, aname, action);
        });
      });

      grid.appendChild(card);
    });
  }

  const agentsSearchInput = document.getElementById("agents-search-input");
  agentsSearchInput?.addEventListener("input", (e) => {
    currentAgentSearch = e.target.value;
    renderAgentsGrid();
  });

  async function launchAgentSession(agentId, agentName, mode = "launch") {
    try {
      const res = await fetch("/api/agents/launch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId, mode: mode })
      });
      if (!res.ok) {
        showToast(`Failed to launch ${agentName}`);
        return;
      }
      const data = await res.json();

      activeSessions.push({ id: data.session_id, title: data.title, agent_id: data.agent_id });
      renderTabs();
      getOrCreateTerminalTab(data.session_id, data.title, null, data.agent_id);
      switchView("view-terminal");
      switchTab(data.session_id);
      showToast(`Launched ${agentName}`);
    } catch (e) {
      showToast(`Error launching ${agentName}`);
    }
  }
  window.launchAgentSession = launchAgentSession;

  // --------------------------------------------------
  // View: Files (File Browser & Code Viewer)
  // --------------------------------------------------
  let currentBrowsePath = "";
  async function loadFilesView(targetPath = "") {
    const listEl = document.getElementById("files-items-list");
    const breadcrumbsEl = document.getElementById("files-breadcrumbs");
    if (!listEl) return;

    try {
      const res = await fetch(`/api/files?path=${encodeURIComponent(targetPath)}`);
      if (!res.ok) return;
      const data = await res.json();
      currentBrowsePath = data.current_path;

      // Breadcrumbs
      if (breadcrumbsEl) {
        breadcrumbsEl.innerHTML = "";
        data.breadcrumbs.forEach((b, idx) => {
          const crumb = document.createElement("span");
          crumb.style.cursor = "pointer";
          crumb.style.color = idx === data.breadcrumbs.length - 1 ? "var(--text-primary)" : "var(--text-muted)";
          crumb.textContent = b.name;
          crumb.addEventListener("click", () => loadFilesView(b.path));
          breadcrumbsEl.appendChild(crumb);
          if (idx < data.breadcrumbs.length - 1) {
            const sep = document.createElement("span");
            sep.textContent = " / ";
            sep.style.color = "var(--border-strong)";
            breadcrumbsEl.appendChild(sep);
          }
        });
      }

      // Entries
      listEl.innerHTML = "";
      if (data.parent_path) {
        const upRow = document.createElement("div");
        upRow.className = "file-row";
        upRow.innerHTML = `
          <span style="display:flex; align-items:center; gap:6px; color:var(--text-muted);">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
            <span>.. (parent directory)</span>
          </span>`;
        upRow.addEventListener("click", () => loadFilesView(data.parent_path));
        listEl.appendChild(upRow);
      }

      data.entries.forEach((item) => {
        const row = document.createElement("div");
        row.className = "file-row";

        let iconSvg = '';
        if (item.is_dir) {
          iconSvg = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>`;
        } else if (item.kind === "code") {
          iconSvg = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent-blue)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>`;
        } else if (item.kind === "config") {
          iconSvg = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent-amber)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>`;
        } else {
          iconSvg = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>`;
        }

        row.innerHTML = `
          <span style="display:flex; align-items:center; gap:8px; overflow:hidden; text-overflow:ellipsis;">
            ${iconSvg}
            <span>${item.name}</span>
          </span>
          <span style="font-family:var(--font-mono); font-size:0.7rem; color:var(--text-muted);">${item.is_dir ? "" : formatBytes(item.size)}</span>
        `;

        row.addEventListener("click", () => {
          if (item.is_dir) {
            loadFilesView(item.path);
          } else {
            document.querySelectorAll(".file-row").forEach(r => r.classList.remove("active"));
            row.classList.add("active");
            previewFile(item.path, item.name);
          }
        });

        listEl.appendChild(row);
      });
    } catch (e) {}
  }
  window.loadFilesView = loadFilesView;

  async function previewFile(filePath, fileName) {
    const previewEl = document.getElementById("files-code-preview");
    const previewTitle = document.getElementById("preview-filename");
    if (!previewEl) return;

    if (previewTitle) previewTitle.textContent = fileName;
    previewEl.textContent = "Loading content...";

    try {
      const res = await fetch(`/api/files/content?path=${encodeURIComponent(filePath)}`);
      if (!res.ok) {
        previewEl.textContent = "Unable to preview file";
        return;
      }
      const data = await res.json();
      previewEl.textContent = data.content || "(Empty file)";
    } catch (e) {
      previewEl.textContent = "Error reading file";
    }
  }

  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  const filesSearchInput = document.getElementById("files-search-input");
  filesSearchInput?.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    document.querySelectorAll("#files-items-list .file-row").forEach(row => {
      const text = row.textContent.toLowerCase();
      if (text.includes("parent directory")) return;
      row.style.display = (!q || text.includes(q)) ? "flex" : "none";
    });
  });

  document.getElementById("btn-open-folder-term")?.addEventListener("click", () => {
    if (currentBrowsePath) {
      switchView("view-terminal");
      createTab(currentBrowsePath.split("/").pop() || "Folder", null, currentBrowsePath);
    }
  });

  // --------------------------------------------------
  // View: Process Manager
  // --------------------------------------------------
  async function loadProcessesView() {
    const tableBody = document.getElementById("process-table-body");
    if (!tableBody) return;
    try {
      const res = await fetch("/api/processes");
      if (!res.ok) return;
      const data = await res.json();

      tableBody.innerHTML = "";
      if (data.processes.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color: var(--text-muted)">No active agent processes running</td></tr>`;
        return;
      }

      data.processes.forEach((p) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td style="font-family: var(--font-mono); font-weight:600; color:var(--text-primary)">${p.pid}</td>
          <td><strong>${p.name}</strong></td>
          <td style="font-family: var(--font-mono); color:var(--accent-blue)">${p.cpu}%</td>
          <td style="font-family: var(--font-mono)">${p.mem}%</td>
          <td style="font-family: var(--font-mono); font-size:0.75rem">${p.runtime}</td>
          <td style="font-family: var(--font-mono); font-size:0.75rem; max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap" title="${p.cmd}">${p.cmd}</td>
          <td>
            <button class="action-btn" style="color:var(--accent-rose); border-color: rgba(244,63,94,0.3); padding:2px 8px; font-size:0.72rem" data-kill-pid="${p.pid}">Kill</button>
          </td>
        `;

        row.querySelector("[data-kill-pid]")?.addEventListener("click", () => {
          killProcess(p.pid);
        });

        tableBody.appendChild(row);
      });
    } catch (e) {}
  }

  async function killProcess(pid) {
    if (!confirm(`Are you sure you want to terminate process ${pid}?`)) return;
    try {
      await fetch(`/api/processes/${pid}/kill`, { method: "POST" });
      showToast(`Terminated PID ${pid}`);
      setTimeout(loadProcessesView, 400);
    } catch (e) {}
  }

  document.getElementById("btn-refresh-processes")?.addEventListener("click", loadProcessesView);

  // --------------------------------------------------
  // View: Project Workspace Manager
  // --------------------------------------------------
  async function loadProjectsView(forceRescan = false) {
    const tbody = document.getElementById("projects-table-body");
    const countLabel = document.getElementById("projects-count-label");
    if (!tbody) return;

    if (forceRescan || cachedProjects.length === 0) {
      if (countLabel) countLabel.textContent = forceRescan ? "Deep scanning file system for Git repositories..." : "Scanning repositories...";
      try {
        const url = forceRescan ? "/api/projects?refresh=true" : "/api/projects";
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          cachedProjects = data.projects || [];
        }
      } catch (e) {
        if (countLabel) countLabel.textContent = "Error scanning projects";
      }
    }

    renderProjectsTable();
  }

  function renderProjectsTable() {
    const tbody = document.getElementById("projects-table-body");
    const countLabel = document.getElementById("projects-count-label");
    const dirtyBadge = document.getElementById("dirty-count-badge");
    if (!tbody) return;

    // Filter
    let list = cachedProjects.slice();
    const dirtyCount = list.filter(p => p.dirty).length;
    if (dirtyBadge) {
      dirtyBadge.textContent = dirtyCount;
      dirtyBadge.style.display = dirtyCount > 0 ? "inline-block" : "none";
    }

    if (currentProjectSearch) {
      const q = currentProjectSearch.toLowerCase().trim();
      list = list.filter(p =>
        p.name.toLowerCase().includes(q) ||
        p.rel_path.toLowerCase().includes(q) ||
        (p.lang && p.lang.toLowerCase().includes(q)) ||
        (p.branch && p.branch.toLowerCase().includes(q))
      );
    }

    // Sort
    if (currentProjectSort === "recent") {
      list.sort((a, b) => (b.mtime || 0) - (a.mtime || 0));
    } else if (currentProjectSort === "alpha") {
      list.sort((a, b) => a.name.localeCompare(b.name));
    } else if (currentProjectSort === "lang") {
      list.sort((a, b) => (a.lang || "").localeCompare(b.lang || "") || a.name.localeCompare(b.name));
    } else if (currentProjectSort === "dirty") {
      list = list.filter(p => p.dirty);
      list.sort((a, b) => (b.mtime || 0) - (a.mtime || 0));
    }

    if (countLabel) {
      countLabel.textContent = `${cachedProjects.length} repositories discovered across machine (${list.length} shown)`;
    }

    tbody.innerHTML = "";
    if (list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:36px; color:var(--text-muted); font-size:0.82rem;">No matching repositories found</td></tr>`;
      return;
    }

    list.forEach((proj) => {
      const row = document.createElement("tr");
      row.className = "project-row";

      const dirtyTag = proj.dirty
        ? `<span class="project-dirty-tag"><span class="project-dirty-dot"></span>${proj.modified_count || 1} uncommitted</span>`
        : `<span class="project-dirty-tag clean"><span class="project-dirty-dot clean"></span>clean</span>`;

      const lastAgentDisplay = proj.last_agent ? (proj.last_agent.charAt(0).toUpperCase() + proj.last_agent.slice(1)) : "Shell";

      row.innerHTML = `
        <td>
          <div class="project-repo-name">${proj.name}</div>
          <div class="project-path-sub">${proj.rel_path}</div>
        </td>
        <td>
          <div class="project-branch-tag">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="6" y1="3" x2="6" y2="15"></line>
              <circle cx="18" cy="6" r="3"></circle>
              <circle cx="6" cy="18" r="3"></circle>
              <path d="M18 9a9 9 0 0 1-9 9"></path>
            </svg>
            <span>${proj.branch}</span>
          </div>
          <div>${dirtyTag}</div>
        </td>
        <td>
          <span class="project-lang-pill">${proj.lang}</span>
        </td>
        <td>
          <span class="project-agent-pill">${lastAgentDisplay}</span>
        </td>
        <td>
          <div class="project-row-actions">
            <button class="btn-open-proj" data-open-proj="${proj.path}" title="Open repository in terminal or resume active session">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>
              <span>Open</span>
            </button>
            <button class="quick-agent-btn" data-agent-launch="claude" data-proj="${proj.path}" title="Launch Claude Code in ${proj.name}">CC</button>
            <button class="quick-agent-btn" data-agent-launch="hermes" data-proj="${proj.path}" title="Launch Hermes Agent in ${proj.name}">HE</button>
            <button class="quick-agent-btn" data-agent-launch="mochi" data-proj="${proj.path}" title="Launch Mochi in ${proj.name}">MO</button>
            <button class="quick-agent-btn" data-agent-launch="agy" data-proj="${proj.path}" title="Launch Antigravity in ${proj.name}">AG</button>
          </div>
        </td>
      `;

      row.querySelector("[data-open-proj]")?.addEventListener("click", () => {
        openProject(proj.path);
      });

      row.querySelectorAll("[data-agent-launch]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const agentId = btn.getAttribute("data-agent-launch");
          openProject(proj.path, agentId);
        });
      });

      tbody.appendChild(row);
    });
  }

  const projSearchInput = document.getElementById("project-search-input");
  const projSearchClear = document.getElementById("project-search-clear");

  projSearchInput?.addEventListener("input", (e) => {
    currentProjectSearch = e.target.value;
    if (projSearchClear) {
      projSearchClear.style.display = currentProjectSearch ? "block" : "none";
    }
    renderProjectsTable();
  });

  projSearchClear?.addEventListener("click", () => {
    if (projSearchInput) projSearchInput.value = "";
    currentProjectSearch = "";
    projSearchClear.style.display = "none";
    renderProjectsTable();
  });

  document.querySelectorAll("#project-sort-controls .segment-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#project-sort-controls .segment-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentProjectSort = btn.getAttribute("data-sort") || "recent";
      renderProjectsTable();
    });
  });

  document.getElementById("btn-rescan-projects")?.addEventListener("click", () => {
    loadProjectsView(true);
  });

  // --------------------------------------------------
  // View: Ports
  // --------------------------------------------------
  async function loadPortsView() {
    const tbody = document.getElementById("ports-table-body");
    if (!tbody) return;
    try {
      const res = await fetch("/api/ports");
      if (!res.ok) return;
      const data = await res.json();

      tbody.innerHTML = "";
      data.ports.forEach((p) => {
        const row = document.createElement("tr");
        const accessUrl = `http://${hostPillText.textContent.split(":")[0]}:${p.port}`;
        row.innerHTML = `
          <td style="font-family:var(--font-mono); font-weight:700; color:var(--accent-blue)">:${p.port}</td>
          <td><span class="badge-status installed">${p.tag}</span></td>
          <td><strong>${p.process}</strong></td>
          <td style="font-family:var(--font-mono); font-size:0.75rem">${p.pid || "-"}</td>
          <td style="font-family:var(--font-mono); font-size:0.75rem">${p.address}</td>
          <td>
            ${p.is_public ? `<a href="${accessUrl}" target="_blank" class="action-btn" style="text-decoration:none; padding:2px 8px; font-size:0.72rem">Open ↗</a>` : `<span style="color:var(--text-dim); font-size:0.72rem">Local Only</span>`}
          </td>
        `;
        tbody.appendChild(row);
      });
    } catch (e) {}
  }

  document.getElementById("btn-refresh-ports")?.addEventListener("click", loadPortsView);

  // --------------------------------------------------
  // View: Logs Stream
  // --------------------------------------------------
  const logSourceSelect = document.getElementById("log-source-select");
  const logSearchInput = document.getElementById("log-search-input");
  const logsBox = document.getElementById("logs-stream-box");

  async function loadLogsView() {
    if (!logsBox) return;
    const source = logSourceSelect ? logSourceSelect.value : "terminus";
    const query = logSearchInput ? logSearchInput.value : "";

    logsBox.textContent = "Fetching log stream...";

    try {
      const res = await fetch(`/api/logs?source=${encodeURIComponent(source)}&query=${encodeURIComponent(query)}&lines=120`);
      if (!res.ok) {
        logsBox.textContent = "Failed to load logs";
        return;
      }
      const data = await res.json();
      if (data.lines.length === 0) {
        logsBox.textContent = "No log lines matching criteria";
        return;
      }
      logsBox.innerHTML = "";
      data.lines.forEach((line) => {
        const div = document.createElement("div");
        div.className = "log-line";
        div.textContent = line;
        logsBox.appendChild(div);
      });
      logsBox.scrollTop = logsBox.scrollHeight;
    } catch (e) {
      logsBox.textContent = "Error loading logs";
    }
  }

  logSourceSelect?.addEventListener("change", loadLogsView);
  logSearchInput?.addEventListener("input", () => {
    clearTimeout(window._logSearchDebounce);
    window._logSearchDebounce = setTimeout(loadLogsView, 300);
  });
  document.getElementById("btn-refresh-logs")?.addEventListener("click", loadLogsView);

  // --------------------------------------------------
  // View: Doctor Diagnostics
  // --------------------------------------------------
  async function loadDoctorView() {
    const grid = document.getElementById("doctor-grid");
    const summaryEl = document.getElementById("doctor-summary");
    if (!grid) return;

    grid.innerHTML = `<div style="color:var(--text-muted); padding:24px;">Running full machine diagnostics...</div>`;

    try {
      const res = await fetch("/api/doctor");
      if (!res.ok) return;
      const data = await res.json();

      grid.innerHTML = "";
      if (summaryEl) {
        summaryEl.textContent = data.overall === "ok"
          ? "All systems nominal. Machine is fully tuned for agent orchestration."
          : "Diagnostics completed with recommendations below.";
      }

      data.checks.forEach((c) => {
        const card = document.createElement("div");
        card.className = "doctor-card";
        const badgeClass = c.status === "ok" ? "ok" : (c.status === "warn" ? "warn" : "error");
        const badgeText = c.status === "ok" ? "PASSED" : (c.status === "warn" ? "NOTICE" : "FAILED");

        card.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
            <div style="font-weight:600; font-size:0.9rem; color:var(--text-primary)">${c.name}</div>
            <span class="doctor-status-badge ${badgeClass}">${badgeText}</span>
          </div>
          <div style="font-size:0.78rem; color:var(--text-secondary); line-height:1.4;">${c.message}</div>
        `;
        grid.appendChild(card);
      });
    } catch (e) {}
  }

  document.getElementById("btn-run-doctor")?.addEventListener("click", loadDoctorView);

  // --------------------------------------------------
  // Global Raycast / Linear Command Palette (Ctrl+K / Cmd+K)
  // --------------------------------------------------
  const paletteOverlay = document.getElementById("command-palette");
  const paletteInput = document.getElementById("palette-input");
  const paletteResults = document.getElementById("palette-results");

  const PALETTE_COMMANDS = [
    { title: "Linked Multi-Terminal Workspace Matrix", cat: "Views", action: () => switchView("view-workspace") },
    { title: "Multi-Agent Orchestrator & Broadcast", cat: "Views", action: () => switchView("view-communicator") },
    { title: "Control Plane Overview (Dashboard)", cat: "Views", action: () => switchView("view-dashboard") },
    { title: "Open Terminal (Persistent PTY)", cat: "Views", action: () => switchView("view-terminal") },
    { title: "Session Switcher & Process Manager", cat: "Terminal", action: openSessionPicker },
    { title: "Toggle Split Dual Screen", cat: "Terminal", action: toggleSplitView },
    { title: "Universal Skill Tree (170+ Skills)", cat: "Views", action: () => switchView("view-skills") },
    { title: "Multi-Agent Memory & Context Hub", cat: "Views", action: () => switchView("view-memory") },
    { title: "Universal Autonomous Cron Scheduler", cat: "Views", action: () => switchView("view-cron") },
    { title: "Agent Discovery Engine", cat: "Views", action: () => switchView("view-agents") },
    { title: "Live Agent Activity Monitor", cat: "Views", action: () => switchView("view-activity") },
    { title: "Model Context Protocol (MCP) Registry", cat: "Views", action: () => switchView("view-mcp") },
    { title: "Browse Project Repositories", cat: "Views", action: () => switchView("view-projects") },
    { title: "File Explorer & Code Previewer", cat: "Views", action: () => switchView("view-files") },
    { title: "Process & Runaway Loop Manager", cat: "Views", action: () => switchView("view-processes") },
    { title: "Listening Ports & Dev Servers", cat: "Views", action: () => switchView("view-ports") },
    { title: "Unified Log Stream", cat: "Views", action: () => switchView("view-logs") },
    { title: "Run Terminus Doctor Diagnostics", cat: "Diagnostics", action: () => switchView("view-doctor") },
    { title: "Rescan All Machine Skills", cat: "Skills", action: () => { switchView("view-skills"); loadSkillsView(true); } },
    { title: "Add Shared Cross-Agent Memory", cat: "Memory", action: () => addMemoryModal?.classList.add("open") },
    { title: "Schedule New Autonomous Agent Task", cat: "Tasks", action: () => addCronModal?.classList.add("open") },
    { title: "New Standard Shell Tab", cat: "Terminal", action: () => { switchView("view-terminal"); createTab("Shell"); } },
    { title: "Clear Active Terminal Screen", cat: "Terminal", action: () => { sendTerminalInput("clear\n"); } },
    { title: "Launch Claude Code", cat: "Agents", action: () => launchAgentSession("claude", "Claude Code") },
    { title: "Launch Hermes Agent", cat: "Agents", action: () => launchAgentSession("hermes", "Hermes") },
    { title: "Launch Antigravity", cat: "Agents", action: () => launchAgentSession("antigravity", "Antigravity") },
    { title: "Launch Mochi", cat: "Agents", action: () => launchAgentSession("mochi", "Mochi") },
    { title: "Launch Codex CLI", cat: "Agents", action: () => launchAgentSession("codex", "Codex K") },
    { title: "Launch Cline", cat: "Agents", action: () => launchAgentSession("cline", "Cline") },
    { title: "Launch Roo Code", cat: "Agents", action: () => launchAgentSession("roo", "Roo Code") },
    { title: "Launch Aider", cat: "Agents", action: () => launchAgentSession("aider", "Aider") },
    { title: "Launch OpenCode", cat: "Agents", action: () => launchAgentSession("opencode", "OpenCode") },
    { title: "Launch Gemini CLI", cat: "Agents", action: () => launchAgentSession("gemini", "Gemini CLI") },
    { title: "Launch Goose", cat: "Agents", action: () => launchAgentSession("goose", "Goose") },
    { title: "Launch J-Code", cat: "Agents", action: () => launchAgentSession("jcode", "J-Code") },
    { title: "Launch Codebuff", cat: "Agents", action: () => launchAgentSession("codebuff", "Codebuff") },
    { title: "Launch Crush (Charmbracelet)", cat: "Agents", action: () => launchAgentSession("crush", "Crush") },
    { title: "Copy LAN Access URL", cat: "Network", action: () => hostPill?.click() }
  ];

  function openPalette() {
    if (!paletteOverlay) return;
    paletteOverlay.classList.add("open");
    if (paletteInput) {
      paletteInput.value = "";
      renderPaletteResults("");
      paletteInput.focus();
    }
  }

  function closePalette() {
    paletteOverlay?.classList.remove("open");
    if (document.querySelector(".view-panel.active-view")?.id === "view-terminal") {
      ensureKeyboardFocus();
    }
  }

  function renderPaletteResults(query) {
    if (!paletteResults) return;
    paletteResults.innerHTML = "";
    const q = query.toLowerCase().trim();
    let filtered = PALETTE_COMMANDS.filter(c => !q || c.title.toLowerCase().includes(q) || c.cat.toLowerCase().includes(q));

    // Dynamic project search in palette
    if (q && cachedProjects && cachedProjects.length > 0) {
      const matchedProjects = cachedProjects
        .filter(p => p.name.toLowerCase().includes(q) || p.rel_path.toLowerCase().includes(q))
        .slice(0, 6)
        .map(p => ({
          title: `${p.name} (${p.rel_path})`,
          cat: "Repositories",
          action: () => openProject(p.path)
        }));
      filtered = filtered.concat(matchedProjects);
    }

    let lastCat = null;
    filtered.forEach((cmd, idx) => {
      if (cmd.cat !== lastCat) {
        lastCat = cmd.cat;
        const catEl = document.createElement("div");
        catEl.className = "palette-category";
        catEl.textContent = cmd.cat;
        paletteResults.appendChild(catEl);
      }

      const item = document.createElement("div");
      item.className = `palette-item ${idx === 0 ? "active" : ""}`;
      item.innerHTML = `
        <span>${cmd.title}</span>
        <span style="font-family:var(--font-mono); font-size:0.7rem; color:var(--text-muted);">⏎ Run</span>
      `;

      item.addEventListener("click", () => {
        closePalette();
        cmd.action();
      });

      paletteResults.appendChild(item);
    });
  }

  paletteInput?.addEventListener("input", (e) => {
    renderPaletteResults(e.target.value);
  });

  paletteInput?.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closePalette();
    } else if (e.key === "Enter") {
      const activeItem = paletteResults.querySelector(".palette-item.active");
      if (activeItem) activeItem.click();
    }
  });

  paletteOverlay?.addEventListener("click", (e) => {
    if (e.target === paletteOverlay) closePalette();
  });

  document.getElementById("btn-open-palette")?.addEventListener("click", openPalette);

  // Global Keybindings (Ctrl+K, Ctrl+O, Alt+S, / for search)
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (paletteOverlay?.classList.contains("open")) {
        closePalette();
      } else {
        openPalette();
      }
    } else if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === "o" || e.key.toLowerCase() === "p")) {
      e.preventDefault();
      openSessionPicker();
    } else if (e.altKey && e.key.toLowerCase() === "s") {
      e.preventDefault();
      toggleSplitView();
    } else if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
      const activePanel = document.querySelector(".view-panel.active-view");
      if (activePanel?.id === "view-projects") {
        e.preventDefault();
        projSearchInput?.focus();
      } else if (activePanel?.id === "view-agents") {
        e.preventDefault();
        agentsSearchInput?.focus();
      } else if (activePanel?.id === "view-skills") {
        e.preventDefault();
        document.getElementById("skills-search-input")?.focus();
      } else if (activePanel?.id === "view-memory") {
        e.preventDefault();
        document.getElementById("memory-search-input")?.focus();
      }
    }
  });

  // --------------------------------------------------
  // Global Telemetry Polling
  // --------------------------------------------------
  async function fetchTelemetry() {
    try {
      const res = await fetch("/api/telemetry");
      if (!res.ok) return;
      const data = await res.json();

      if (telemCpu) telemCpu.textContent = `${data.cpu}%`;
      if (telemMem) telemMem.textContent = `${data.memory.percent}%`;
      if (telemDisk) telemDisk.textContent = `${data.disk.percent}%`;
      if (hostPillText) hostPillText.textContent = `${data.lan_ip}:${data.port}`;
    } catch (e) {}
  }

  hostPill?.addEventListener("click", () => {
    const url = `http://${hostPillText.textContent}`;
    navigator.clipboard?.writeText(url).then(() => {
      showToast(`Copied ${url} to clipboard`);
    });
  });

  // Modal Close buttons
  document.querySelectorAll(".modal-close-btn, [data-modal-close]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".modal-overlay").forEach((m) => m.classList.remove("open"));
    });
  });

  // --------------------------------------------------
  // Boot & Initial Session Synchronization
  // --------------------------------------------------
  async function boot() {
    try {
      const res = await fetch("/api/sessions");
      if (res.ok) {
        const data = await res.json();
        if (data.sessions && data.sessions.length > 0) {
          activeSessions = data.sessions.map(s => ({
            id: s.id,
            title: s.title,
            cwd: s.cwd,
            agent_id: s.agent_id
          }));
          if (!activeSessions.find(s => s.id === currentSessionId)) {
            currentSessionId = activeSessions[0].id;
          }
        }
      }
    } catch (e) {}

    renderTabs();

    // Initialize all active sessions so their PTY instances and sockets are live
    activeSessions.forEach((s) => {
      getOrCreateTerminalTab(s.id, s.title, s.cwd, s.agent_id);
    });

    switchTab(currentSessionId);
    setTimeout(() => {
      updateGooeyNav();
      updateGooeyTabs();
    }, 80);

    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => {
        safeFitActiveTab();
        terminalTabs.forEach((tab) => {
          try {
            if (tab.term) {
              if (tab.term._core && tab.term._core._charSizeService) {
                tab.term._core._charSizeService.measure();
              }
              if (tab.fitAddon) {
                tab.fitAddon.fit();
              }
              tab.term.refresh(0, tab.term.rows - 1);
            }
          } catch (e) {}
        });
        updateGooeyNav();
        updateGooeyTabs();
      });
    }

    fetchTelemetry();
    setInterval(fetchTelemetry, 6000);

    // Warm projects, agents, skills, memory, cron in background
    fetch("/api/projects").then(r => r.json()).then(d => {
      cachedProjects = d.projects || [];
    }).catch(() => {});

    fetch("/api/agents").then(r => r.json()).then(d => {
      cachedAgents = d.agents || [];
    }).catch(() => {});

    fetch("/api/skills").then(r => r.json()).then(d => {
      cachedSkillsTree = d;
    }).catch(() => {});

    fetch("/api/memory").catch(() => {});
    fetch("/api/cron").catch(() => {});
    fetchTunnelStatus();
  }

  // --------------------------------------------------
  // Terminal Themes & Subbar Enhancements
  // --------------------------------------------------
  const TERMINAL_THEMES = {
    midnight: {
      background: "#09090b",
      foreground: "#f4f4f6",
      cursor: "#f4f4f6",
      cursorAccent: "#09090b",
      selectionBackground: "rgba(255, 255, 255, 0.18)",
      black: "#18181b",
      red: "#ef4444",
      green: "#10b981",
      yellow: "#f59e0b",
      blue: "#3b82f6",
      magenta: "#a855f7",
      cyan: "#06b6d4",
      white: "#f4f4f6",
      brightBlack: "#52525b",
      brightRed: "#f87171",
      brightGreen: "#34d399",
      brightYellow: "#fbbf24",
      brightBlue: "#60a5fa",
      brightMagenta: "#c084fc",
      brightCyan: "#22d3ee",
      brightWhite: "#ffffff"
    },
    tokyonight: {
      background: "#1a1b26",
      foreground: "#c0caf5",
      cursor: "#c0caf5",
      cursorAccent: "#1a1b26",
      selectionBackground: "#33467c",
      black: "#15161e",
      red: "#f7768e",
      green: "#9ece6a",
      yellow: "#e0af68",
      blue: "#7aa2f7",
      magenta: "#bb9af7",
      cyan: "#7dcfff",
      white: "#a9b1d6",
      brightBlack: "#414868",
      brightRed: "#f7768e",
      brightGreen: "#9ece6a",
      brightYellow: "#e0af68",
      brightBlue: "#7aa2f7",
      brightMagenta: "#bb9af7",
      brightCyan: "#7dcfff",
      brightWhite: "#c0caf5"
    },
    catppuccin: {
      background: "#1e1e2e",
      foreground: "#cdd6f4",
      cursor: "#f5e0dc",
      cursorAccent: "#1e1e2e",
      selectionBackground: "#585b70",
      black: "#45475a",
      red: "#f38ba8",
      green: "#a6e3a1",
      yellow: "#f9e2af",
      blue: "#89b4fa",
      magenta: "#f5c2e7",
      cyan: "#94e2d5",
      white: "#bac2de",
      brightBlack: "#585b70",
      brightRed: "#f38ba8",
      brightGreen: "#a6e3a1",
      brightYellow: "#f9e2af",
      brightBlue: "#89b4fa",
      brightMagenta: "#f5c2e7",
      brightCyan: "#94e2d5",
      brightWhite: "#a6adc8"
    },
    monokai: {
      background: "#272822",
      foreground: "#f8f8f2",
      cursor: "#f8f8f0",
      cursorAccent: "#272822",
      selectionBackground: "#49483e",
      black: "#272822",
      red: "#f92672",
      green: "#a6e22e",
      yellow: "#f4bf75",
      blue: "#66d9ef",
      magenta: "#ae81ff",
      cyan: "#a1efe4",
      white: "#f8f8f2",
      brightBlack: "#75715e",
      brightRed: "#f92672",
      brightGreen: "#a6e22e",
      brightYellow: "#f4bf75",
      brightBlue: "#66d9ef",
      brightMagenta: "#ae81ff",
      brightCyan: "#a1efe4",
      brightWhite: "#f9f8f5"
    },
    cyberpunk: {
      background: "#08080c",
      foreground: "#00ffcc",
      cursor: "#ffe600",
      cursorAccent: "#08080c",
      selectionBackground: "rgba(255, 0, 85, 0.35)",
      black: "#12131a",
      red: "#ff0055",
      green: "#00ffcc",
      yellow: "#ffe600",
      blue: "#00b8ff",
      magenta: "#ff00a0",
      cyan: "#00f0ff",
      white: "#f0f0f5",
      brightBlack: "#4b4d61",
      brightRed: "#ff3377",
      brightGreen: "#33ffdd",
      brightYellow: "#ffea33",
      brightBlue: "#33c6ff",
      brightMagenta: "#ff33b3",
      brightCyan: "#33f3ff",
      brightWhite: "#ffffff"
    }
  };

  const themePicker = document.getElementById("term-theme-picker");
  const savedTheme = localStorage.getItem("terminus_terminal_theme") || "midnight";
  if (themePicker) {
    themePicker.value = savedTheme;
    themePicker.addEventListener("change", () => {
      const selected = themePicker.value;
      localStorage.setItem("terminus_terminal_theme", selected);
      const th = TERMINAL_THEMES[selected] || TERMINAL_THEMES.midnight;
      terminalTabs.forEach(t => {
        if (t.term) t.term.options.theme = th;
      });
      showToast(`Terminal theme: ${selected}`);
    });
  }

  // Clear Terminal
  document.getElementById("btn-term-clear")?.addEventListener("click", () => {
    const active = terminalTabs.get(currentSessionId);
    if (active && active.term) {
      active.term.clear();
      showToast("Terminal buffer cleared");
    }
  });

  // Download Log
  document.getElementById("btn-term-download")?.addEventListener("click", async () => {
    try {
      const res = await fetch(`/api/sessions/${encodeURIComponent(currentSessionId)}/buffer`);
      if (res.ok) {
        const data = await res.json();
        const blob = new Blob([data.buffer || ""], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `terminus-${currentSessionId}.log`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        showToast("Exported terminal session log");
      }
    } catch (e) {
      showToast("Failed to export log");
    }
  });

  // --------------------------------------------------
  // Remote Access & Cloudflare Tunnel Hub
  // --------------------------------------------------
  const remoteTunnelModal = document.getElementById("remote-tunnel-modal");
  const remoteStatusDot = document.getElementById("remote-status-dot");
  const tunnelModalDot = document.getElementById("tunnel-modal-dot");
  const tunnelStatusText = document.getElementById("tunnel-status-text");
  const tunnelUptimeText = document.getElementById("tunnel-uptime-text");
  const btnToggleTunnel = document.getElementById("btn-toggle-tunnel");
  const tunnelOnlineSection = document.getElementById("tunnel-online-section");
  const tunnelPublicUrlInput = document.getElementById("tunnel-public-url-input");
  const tunnelQrImg = document.getElementById("tunnel-qr-img");
  let isTunnelOnline = false;

  async function updateTunnelStatus(data) {
    isTunnelOnline = !!data.is_running;
    if (remoteStatusDot) {
      remoteStatusDot.className = `indicator-dot ${isTunnelOnline ? "online" : "offline"}`;
      remoteStatusDot.style.background = isTunnelOnline ? "var(--accent-emerald)" : "var(--accent-amber)";
    }
    if (tunnelModalDot) {
      tunnelModalDot.className = `indicator-dot ${isTunnelOnline ? "online" : "offline"}`;
      tunnelModalDot.style.background = isTunnelOnline ? "var(--accent-emerald)" : "var(--accent-rose)";
    }
    if (tunnelStatusText) {
      tunnelStatusText.textContent = isTunnelOnline ? "Tunnel Active & Encrypted" : "Tunnel Offline";
    }
    if (tunnelUptimeText) {
      tunnelUptimeText.textContent = isTunnelOnline 
        ? `Live public URL active (Uptime: ${data.uptime_seconds || 0}s)`
        : "Zero-config encrypted Cloudflare HTTPS endpoint";
    }
    if (btnToggleTunnel) {
      btnToggleTunnel.textContent = isTunnelOnline ? "Stop Tunnel" : "Start Tunnel";
      btnToggleTunnel.className = isTunnelOnline ? "action-btn" : "action-btn btn-primary-action";
    }
    if (tunnelOnlineSection) {
      tunnelOnlineSection.style.display = isTunnelOnline ? "flex" : "none";
    }
    if (tunnelPublicUrlInput && data.public_url) {
      tunnelPublicUrlInput.value = data.public_url;
    }
    if (tunnelQrImg && data.qr_code) {
      tunnelQrImg.src = data.qr_code;
    }
  }

  async function fetchTunnelStatus() {
    try {
      const res = await fetch("/api/tunnel/status");
      if (res.ok) {
        const data = await res.json();
        updateTunnelStatus(data);
      }
    } catch (e) {}
  }

  document.getElementById("btn-open-remote-tunnel")?.addEventListener("click", () => {
    remoteTunnelModal?.classList.add("open");
    fetchTunnelStatus();
  });

  btnToggleTunnel?.addEventListener("click", async () => {
    btnToggleTunnel.disabled = true;
    btnToggleTunnel.textContent = "Connecting...";
    try {
      const endpoint = isTunnelOnline ? "/api/tunnel/stop" : "/api/tunnel/start";
      const res = await fetch(endpoint, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        updateTunnelStatus(data);
        showToast(isTunnelOnline ? "Cloudflare Tunnel online!" : "Tunnel disconnected");
      }
    } catch (e) {
      showToast("Tunnel request failed: " + e.message);
    } finally {
      btnToggleTunnel.disabled = false;
    }
  });

  document.getElementById("btn-copy-tunnel-url")?.addEventListener("click", () => {
    if (tunnelPublicUrlInput?.value) {
      navigator.clipboard.writeText(tunnelPublicUrlInput.value).then(() => {
        showToast("Copied public HTTPS URL to clipboard!");
      });
    }
  });

  document.getElementById("btn-copy-lan-url")?.addEventListener("click", () => {
    navigator.clipboard.writeText(`http://${hostPillText.textContent}`).then(() => {
      showToast("Copied LAN address to clipboard!");
    });
  });

  // --------------------------------------------------
  // View: Omni-Communicator (Multi-Agent Broadcast)
  // --------------------------------------------------
  let activeCommTarget = "all";

  async function loadCommunicatorView() {
    try {
      const [histRes, presRes, pipeRes] = await Promise.all([
        fetch("/api/communicator/history"),
        fetch("/api/communicator/presets"),
        fetch("/api/communicator/pipelines")
      ]);

      // Render presets
      if (presRes.ok) {
        const presData = await presRes.json();
        const presetGrid = document.getElementById("comm-preset-grid");
        if (presetGrid) {
          presetGrid.innerHTML = "";
          (presData.presets || []).forEach(p => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "comm-preset-btn";
            btn.innerHTML = `<span class="badge-status installed" style="font-size:0.65rem; padding:1px 5px;">[${p.badge || "DIRECTIVE"}]</span> <span>${escapeHtml(p.title)}</span>`;
            btn.addEventListener("click", () => {
              const input = document.getElementById("comm-prompt-input");
              if (input) {
                input.value = p.prompt;
                input.focus();
              }
            });
            presetGrid.appendChild(btn);
          });
        }
      }

      // Render Collaborative Multi-Agent Pipelines
      if (pipeRes.ok) {
        const pipeData = await pipeRes.json();
        const pipeGrid = document.getElementById("comm-pipeline-grid");
        if (pipeGrid) {
          pipeGrid.innerHTML = "";
          (pipeData.pipelines || []).forEach(pipe => {
            const card = document.createElement("div");
            card.className = "comm-pipeline-card";
            const stepsHtml = (pipe.stages || []).map(s => `<span class="pipeline-step-badge">${s.title || s.agent}: ${escapeHtml(s.action || s.prompt || '')}</span>`).join('');
            card.innerHTML = `
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div class="pipeline-title">${escapeHtml(pipe.title)}</div>
                <button type="button" class="action-btn btn-primary-action" data-run-pipe="${pipe.id}" style="padding:2px 8px; font-size:0.70rem;">Load Pipeline</button>
              </div>
              <div class="pipeline-desc">${escapeHtml(pipe.description)}</div>
              <div class="pipeline-steps">${stepsHtml}</div>
            `;
            card.querySelector("[data-run-pipe]")?.addEventListener("click", () => {
              const firstStage = pipe.stages?.[0];
              const input = document.getElementById("comm-prompt-input");
              if (input && firstStage) {
                input.value = `[PIPELINE: ${pipe.title}]\n${firstStage.action || pipe.description}`;
                input.focus();
                showToast(`Loaded pipeline: ${pipe.title}`);
              }
            });
            pipeGrid.appendChild(card);
          });
        }
      }

      // Render History / Stream
      if (histRes.ok) {
        const histData = await histRes.json();
        renderCommHistory(histData.history || []);
      }
    } catch (e) {}
  }

  function renderCommHistory(items) {
    const list = document.getElementById("comm-stream-list");
    const countEl = document.getElementById("comm-feed-count");
    if (countEl) countEl.textContent = `${items.length} Messages`;
    if (!list) return;

    list.innerHTML = "";
    if (items.length === 0) {
      list.innerHTML = `<div style="text-align:center; padding:32px 16px; color:var(--text-muted); font-size:0.8rem;">
        No broadcast messages dispatched yet. Type a prompt on the left to broadcast to all agents!
      </div>`;
      return;
    }

    items.slice().reverse().forEach(item => {
      const card = document.createElement("div");
      card.className = "comm-msg-card";
      const targetLabel = item.target === "all" ? "ALL ACTIVE" : item.target.toUpperCase();
      const hasResponse = item.response && item.response.trim();

      card.innerHTML = `
        <div class="comm-msg-header">
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge-status installed" style="font-size:0.65rem; padding:1px 6px;">${targetLabel}</span>
            <span style="font-size:0.72rem; color:var(--text-muted);">${item.time_str || ""}</span>
          </div>
          <button type="button" class="action-btn" data-relay-msg style="padding:1px 6px; font-size:0.68rem;" title="Copy prompt back into input">Reuse</button>
        </div>
        <div class="comm-msg-content">${escapeHtml(item.message)}</div>
        ${hasResponse ? `
          <div class="comm-response-box">
            ${escapeHtml(item.response)}
          </div>
        ` : ""}
      `;

      card.querySelector("[data-relay-msg]")?.addEventListener("click", () => {
        const input = document.getElementById("comm-prompt-input");
        if (input) {
          input.value = item.message;
          input.focus();
        }
      });

      list.appendChild(card);
    });
  }

  // Target selection pills
  document.querySelectorAll("#comm-target-pills .filter-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll("#comm-target-pills .filter-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      activeCommTarget = pill.getAttribute("data-comm-target") || "all";
    });
  });

  async function dispatchCommMessage() {
    const input = document.getElementById("comm-prompt-input");
    const msg = (input?.value || "").trim();
    if (!msg) return;

    const btn = document.getElementById("btn-comm-dispatch");
    if (btn) btn.disabled = true;

    try {
      if (activeCommTarget === "hermes_direct") {
        showToast("Querying Solo Hermes...");
        const res = await fetch("/api/communicator/hermes_direct", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: msg })
        });
        if (res.ok) {
          showToast("Solo Hermes response received!");
          input.value = "";
          loadCommunicatorView();
        }
      } else {
        const res = await fetch("/api/communicator/broadcast", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: msg, target: activeCommTarget })
        });
        if (res.ok) {
          const data = await res.json();
          showToast(`Dispatched to: ${data.dispatched_to.join(", ")}`);
          input.value = "";
          loadCommunicatorView();
        }
      }
    } catch (e) {
      showToast("Dispatch error: " + e.message);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  document.getElementById("btn-comm-dispatch")?.addEventListener("click", dispatchCommMessage);
  document.getElementById("comm-prompt-input")?.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      dispatchCommMessage();
    }
  });

  document.getElementById("btn-comm-quick-hermes")?.addEventListener("click", async () => {
    const input = document.getElementById("comm-prompt-input");
    const prompt = (input?.value || "").trim();
    if (!prompt) {
      showToast("Please enter a prompt for Solo Hermes");
      return;
    }
    showToast("Querying Solo Hermes...");
    try {
      const res = await fetch("/api/communicator/hermes_direct", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt })
      });
      if (res.ok) {
        showToast("Solo Hermes replied!");
        loadCommunicatorView();
      }
    } catch (e) {}
  });

  document.getElementById("btn-clear-comm-history")?.addEventListener("click", () => {
    fetch("/api/communicator/clear", { method: "POST" }).catch(() => {});
    renderCommHistory([]);
    showToast("Cleared communicator history");
  });

  // ==================================================
  // LINKED MULTI-TERMINAL WORKSPACE MATRIX ENGINE
  // ==================================================
  const workspaceState = {
    layout: "2x2",
    linkAll: true,
    isInitialized: false,
    panes: [
      { id: "pane-1", defaultAgent: "claude", title: "Claude Code", linked: true, sessionId: null, term: null, fitAddon: null, socket: null, container: null },
      { id: "pane-2", defaultAgent: "antigravity", title: "Antigravity", linked: true, sessionId: null, term: null, fitAddon: null, socket: null, container: null },
      { id: "pane-3", defaultAgent: "hermes", title: "Hermes Agent", linked: true, sessionId: null, term: null, fitAddon: null, socket: null, container: null },
      { id: "pane-4", defaultAgent: "shell", title: "Interactive Shell", linked: true, sessionId: null, term: null, fitAddon: null, socket: null, container: null }
    ]
  };

  const PRESET_CONFIGS = {
    dual_coder: { layout: "1x2", agents: ["claude", "antigravity"] },
    quad_matrix: { layout: "2x2", agents: ["claude", "antigravity", "hermes", "shell"] },
    trio_pipeline: { layout: "1+2", agents: ["claude", "mochi", "shell"] },
    stacked_pair: { layout: "2x1", agents: ["claude", "shell"] },
    single_focus: { layout: "1x1", agents: ["claude"] }
  };

  async function initWorkspaceView() {
    initChatWorkspaceView();
    const grid = document.getElementById("workspace-grid");
    if (!grid) return;

    if (!workspaceState.isInitialized) {
      workspaceState.isInitialized = true;
      setupWorkspaceControls();
      await renderWorkspacePanes();
    } else {
      setTimeout(() => fitAllWorkspacePanes(), 60);
    }
  }

  function setupWorkspaceControls() {
    // Layout switcher buttons
    document.querySelectorAll("#ws-layout-btns .ws-layout-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const layout = btn.getAttribute("data-layout");
        setWorkspaceLayout(layout);
      });
    });

    // Preset selector dropdown
    const presetSelect = document.getElementById("ws-preset-select");
    presetSelect?.addEventListener("change", (e) => {
      applyWorkspacePreset(e.target.value);
    });

    // Link All toggle button
    const linkAllBtn = document.getElementById("btn-ws-link-all");
    linkAllBtn?.addEventListener("click", () => {
      workspaceState.linkAll = !workspaceState.linkAll;
      linkAllBtn.classList.toggle("active", workspaceState.linkAll);
      updateWorkspaceBadge();
      showToast(workspaceState.linkAll ? "Cluster link active: input will mirror across linked panes" : "Cluster link disabled: panes isolated");
    });

    // Refit all panes button
    document.getElementById("btn-ws-fit-all")?.addEventListener("click", () => {
      fitAllWorkspacePanes();
      showToast("Refit all workspace panes");
    });

    // Parallel Dispatch Modal triggers
    document.getElementById("btn-ws-open-dispatch")?.addEventListener("click", openParallelDispatchModal);
    document.getElementById("btn-ws-execute-dispatch")?.addEventListener("click", executeParallelDispatch);

    // Pipe Output Modal triggers
    document.getElementById("btn-ws-open-pipe")?.addEventListener("click", () => openPipeModal());
    document.getElementById("ws-pipe-form")?.addEventListener("submit", executePipe);

    // Linked Input Bar
    const linkedInput = document.getElementById("ws-linked-input");
    const linkedSend = document.getElementById("btn-ws-linked-send");

    const broadcastInput = () => {
      const val = (linkedInput?.value || "").trim();
      if (!val) return;
      broadcastToLinkedPanes(val + "\n");
      linkedInput.value = "";
    };

    linkedSend?.addEventListener("click", broadcastInput);
    linkedInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        broadcastInput();
      }
    });

    // Strategy template buttons in Parallel Dispatch Modal
    document.querySelectorAll(".ws-dispatch-preset").forEach(btn => {
      btn.addEventListener("click", () => {
        applyDispatchTemplate(btn.getAttribute("data-template"));
      });
    });
  }

  function setWorkspaceLayout(layout) {
    workspaceState.layout = layout;
    const grid = document.getElementById("workspace-grid");
    if (!grid) return;

    const cssClass = layout === "1+2" ? "layout-1-2" : `layout-${layout}`;
    grid.className = `workspace-grid ${cssClass}`;

    document.querySelectorAll("#ws-layout-btns .ws-layout-btn").forEach(b => {
      b.classList.toggle("active", b.getAttribute("data-layout") === layout);
    });

    let maxVisible = 4;
    if (layout === "1x1") maxVisible = 1;
    else if (layout === "1x2" || layout === "2x1") maxVisible = 2;
    else if (layout === "1+2") maxVisible = 3;
    else if (layout === "2x2") maxVisible = 4;

    workspaceState.panes.forEach((pane, idx) => {
      const paneEl = document.getElementById(`ws-pane-card-${pane.id}`);
      if (paneEl) {
        paneEl.style.display = idx < maxVisible ? "flex" : "none";
      }
    });

    updateWorkspaceBadge();
    setTimeout(() => fitAllWorkspacePanes(), 70);
  }

  function applyWorkspacePreset(presetKey) {
    const cfg = PRESET_CONFIGS[presetKey];
    if (!cfg) return;
    setWorkspaceLayout(cfg.layout);
    cfg.agents.forEach((ag, idx) => {
      if (workspaceState.panes[idx]) {
        workspaceState.panes[idx].defaultAgent = ag;
      }
    });
    showToast(`Applied preset: ${presetKey.replace('_', ' ').toUpperCase()}`);
  }

  async function renderWorkspacePanes() {
    const grid = document.getElementById("workspace-grid");
    if (!grid) return;
    grid.innerHTML = "";

    let activeSessionsList = [];
    try {
      const res = await fetch("/api/sessions");
      if (res.ok) {
        const d = await res.json();
        activeSessionsList = d.sessions || [];
      }
    } catch (e) {}

    for (let i = 0; i < workspaceState.panes.length; i++) {
      const pane = workspaceState.panes[i];
      const card = document.createElement("div");
      card.className = `workspace-pane ${pane.linked ? "linked" : ""}`;
      card.id = `ws-pane-card-${pane.id}`;

      let assignedSession = null;
      const match = activeSessionsList.find(s => s.agent_id === pane.defaultAgent || s.title?.toLowerCase().includes(pane.defaultAgent));
      if (match) {
        assignedSession = match;
      } else {
        assignedSession = {
          id: `ws-${pane.defaultAgent}-${Date.now().toString().slice(-4)}-${i+1}`,
          title: pane.title,
          agent_id: pane.defaultAgent
        };
      }
      pane.sessionId = assignedSession.id;

      const monoClass = getAgentMonogramClass(pane.defaultAgent);
      const monoText = getAgentMonogramText(pane.defaultAgent);

      card.innerHTML = `
        <div class="workspace-pane-header">
          <div class="pane-header-left">
            ${getAgentIconHtml(pane.defaultAgent, 18)}
            <select class="pane-session-select" data-pane-session="${pane.id}">
              <option value="${assignedSession.id}" selected>${escapeHtml(assignedSession.title)}</option>
              <optgroup label="Switch to Active Session">
                ${activeSessionsList.map(s => `<option value="${s.id}">${escapeHtml(s.title)}</option>`).join('')}
              </optgroup>
              <optgroup label="Launch New Agent Tab">
                <option value="NEW:claude">+ Launch Claude Code</option>
                <option value="NEW:antigravity">+ Launch Antigravity</option>
                <option value="NEW:hermes">+ Launch Hermes</option>
                <option value="NEW:mochi">+ Launch Mochi</option>
                <option value="NEW:codex">+ Launch Codex</option>
                <option value="NEW:cline">+ Launch Cline</option>
                <option value="NEW:shell">+ Launch Shell</option>
              </optgroup>
            </select>
            <span class="indicator-dot" style="width:6px; height:6px; background:var(--accent-emerald);"></span>
          </div>
          <div class="pane-header-right">
            <button type="button" class="action-btn pane-link-btn ${pane.linked ? "btn-primary-action" : ""}" data-pane-link="${pane.id}" style="padding:1px 7px; font-size:0.68rem;" title="Toggle input clustering for this pane">
              ${pane.linked ? "Linked" : "Unlinked"}
            </button>
            <button type="button" class="action-btn" data-pane-pipe="${pane.id}" style="padding:1px 6px; font-size:0.68rem;" title="Pipe this pane output to another agent">Pipe →</button>
            <button type="button" class="action-btn" data-pane-clear="${pane.id}" style="padding:1px 6px; font-size:0.68rem;" title="Clear pane buffer">Clear</button>
            <button type="button" class="action-btn" data-pane-max="${pane.id}" style="padding:1px 6px; font-size:0.68rem;" title="Maximize / Restore pane">Max</button>
          </div>
        </div>
        <div class="workspace-pane-body" id="ws-pane-body-${pane.id}"></div>
      `;

      grid.appendChild(card);

      const linkBtn = card.querySelector(`[data-pane-link="${pane.id}"]`);
      linkBtn?.addEventListener("click", () => {
        pane.linked = !pane.linked;
        card.classList.toggle("linked", pane.linked);
        linkBtn.classList.toggle("btn-primary-action", pane.linked);
        linkBtn.textContent = pane.linked ? "Linked" : "Unlinked";
        updateWorkspaceBadge();
      });

      card.querySelector(`[data-pane-pipe="${pane.id}"]`)?.addEventListener("click", () => {
        openPipeModal(pane.sessionId);
      });

      card.querySelector(`[data-pane-clear="${pane.id}"]`)?.addEventListener("click", () => {
        if (pane.term) pane.term.clear();
      });

      const maxBtn = card.querySelector(`[data-pane-max="${pane.id}"]`);
      maxBtn?.addEventListener("click", () => {
        const isMax = card.classList.toggle("maximized");
        maxBtn.textContent = isMax ? "Restore" : "Max";
        setTimeout(() => fitPane(pane), 50);
      });

      const sessSelect = card.querySelector(`[data-pane-session="${pane.id}"]`);
      sessSelect?.addEventListener("change", async (e) => {
        const val = e.target.value;
        if (val.startsWith("NEW:")) {
          const newAgent = val.split(":")[1];
          const tab = createTab(newAgent.toUpperCase(), null, null, newAgent);
          pane.sessionId = tab.id;
          pane.defaultAgent = newAgent;
          connectPaneWebSocket(pane, tab.id);
        } else {
          pane.sessionId = val;
          connectPaneWebSocket(pane, val);
        }
      });

      const bodyEl = card.querySelector(`#ws-pane-body-${pane.id}`);
      mountPaneTerminal(pane, bodyEl);
    }

    setWorkspaceLayout(workspaceState.layout);
  }

  function mountPaneTerminal(pane, container) {
    if (pane.term) {
      try { pane.term.dispose(); } catch (e) {}
    }
    container.innerHTML = "";

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "bar",
      cursorWidth: 2,
      fontSize: 12,
      lineHeight: 1.08,
      letterSpacing: 0,
      fontFamily: '"JetBrains Mono", "Cascadia Code", "Fira Code", monospace',
      theme: {
        background: "#09090b",
        foreground: "#f4f4f6",
        cursor: "#22d3ee",
        selectionBackground: "rgba(6, 182, 212, 0.25)"
      },
      allowTransparency: true,
      scrollback: 5000
    });

    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(container);

    pane.term = term;
    pane.fitAddon = fitAddon;
    pane.container = container;

    term.onData(data => {
      sendPaneInput(pane, data);
    });

    container.addEventListener("click", () => {
      document.querySelectorAll(".workspace-pane").forEach(p => p.classList.remove("active-focus"));
      document.getElementById(`ws-pane-card-${pane.id}`)?.classList.add("active-focus");
      term.focus();
    });

    connectPaneWebSocket(pane, pane.sessionId);
  }

  function connectPaneWebSocket(pane, sessionId) {
    if (!sessionId) return;
    if (pane.socket) {
      try { pane.socket.close(); } catch (e) {}
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/terminal/${encodeURIComponent(sessionId)}`;
    let ws = null;

    try {
      ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      pane.socket = ws;
    } catch (e) {
      return;
    }

    ws.onopen = () => {
      fitPane(pane);
    };

    ws.onmessage = (event) => {
      if (!pane.term) return;
      if (event.data instanceof ArrayBuffer) {
        pane.term.write(new Uint8Array(event.data));
      } else if (typeof event.data === "string") {
        if (!event.data.startsWith("{") || !event.data.endsWith("}")) {
          pane.term.write(event.data);
        }
      }
    };

    ws.onerror = () => {};
    ws.onclose = () => {};
  }

  function sendPaneInput(sourcePane, data) {
    if (sourcePane.socket && sourcePane.socket.readyState === WebSocket.OPEN) {
      sourcePane.socket.send(data);
    }

    if (workspaceState.linkAll && sourcePane.linked) {
      workspaceState.panes.forEach(p => {
        if (p.id !== sourcePane.id && p.linked && p.socket && p.socket.readyState === WebSocket.OPEN) {
          p.socket.send(data);
        }
      });
    }
  }

  function broadcastToLinkedPanes(text) {
    let sentCount = 0;
    workspaceState.panes.forEach(p => {
      if (p.linked && p.socket && p.socket.readyState === WebSocket.OPEN) {
        p.socket.send(text);
        sentCount++;
      }
    });
    showToast(`Broadcast sent to ${sentCount} linked pane${sentCount !== 1 ? 's' : ''}`);
  }

  function fitPane(pane) {
    if (!pane || !pane.fitAddon || !pane.term || !pane.container) return;
    try {
      pane.fitAddon.fit();
      if (pane.socket && pane.socket.readyState === WebSocket.OPEN) {
        pane.socket.send(JSON.stringify({
          type: "resize",
          cols: pane.term.cols,
          rows: pane.term.rows
        }));
      }
    } catch (e) {}
  }

  function fitAllWorkspacePanes() {
    workspaceState.panes.forEach(p => fitPane(p));
  }

  function updateWorkspaceBadge() {
    const badge = document.getElementById("ws-linked-badge");
    if (!badge) return;
    if (!workspaceState.linkAll) {
      badge.textContent = "ISOLATED (CLUSTER OFF)";
      badge.style.color = "var(--text-muted)";
      badge.style.borderColor = "var(--border-subtle)";
      return;
    }
    const linkedCount = workspaceState.panes.filter(p => p.linked).length;
    badge.textContent = `LINKED (${linkedCount} PANES)`;
    badge.style.color = "var(--accent-cyan)";
    badge.style.borderColor = "rgba(6, 182, 212, 0.4)";
  }

  function getAgentMonogramClass(agentId) {
    const raw = (agentId || "shell").toLowerCase();
    const map = {
      claude: "mono-cc",
      antigravity: "mono-ag",
      agy: "mono-ag",
      hermes: "mono-he",
      mochi: "mono-mo",
      codex: "mono-cx",
      cline: "mono-cl",
      roo: "mono-rc",
      aider: "mono-ai",
      opencode: "mono-oc",
      gemini: "mono-gm",
      jcode: "mono-jc",
      pi: "mono-pi",
      codebuff: "mono-cb",
      crush: "mono-cr",
      goose: "mono-mo",
      continue: "mono-cx",
      cursor: "mono-sh",
      kimi: "mono-cx",
      qwen: "mono-gm",
      openhands: "mono-he",
      shell: "mono-sh",
      bash: "mono-sh",
      zsh: "mono-sh"
    };
    return map[raw] || "mono-sh";
  }

  function getAgentMonogramText(agentId) {
    const raw = (agentId || "shell").toLowerCase();
    const map = {
      claude: "CC",
      antigravity: "AG",
      agy: "AG",
      hermes: "HE",
      mochi: "MO",
      codex: "CX",
      cline: "CL",
      roo: "RC",
      aider: "AI",
      opencode: "OC",
      gemini: "GM",
      jcode: "JC",
      pi: "PI",
      codebuff: "CB",
      crush: "CR",
      goose: "GS",
      continue: "CN",
      cursor: "CU",
      kimi: "KM",
      qwen: "QW",
      openhands: "OH",
      shell: "SH",
      bash: "SH",
      zsh: "SH"
    };
    return map[raw] || (raw.substring(0, 2).toUpperCase() || "SH");
  }

  function getAgentIconHtml(agentId, size = 18, fallbackText = null) {
    const raw = (agentId || "shell").toLowerCase();
    const iconMap = {
      claude: "claude.svg",
      hermes: "hermes.svg",
      antigravity: "antigravity.svg",
      agy: "antigravity.svg",
      mochi: "mochi.svg",
      codex: "codex.svg",
      cline: "cline.svg",
      jcode: "jcode.svg",
      gemini: "gemini.svg",
      pi: "pi.svg",
      opencode: "opencode.svg",
      roo: "roo.svg",
      aider: "aider.svg",
      kimi: "kimi.svg",
      qwen: "qwen.svg",
      goose: "goose.svg",
      openhands: "openhands.svg",
      continue: "continue.svg",
      cursor: "cursor.svg",
      codebuff: "codebuff.svg",
      crush: "crush.svg",
      shell: "shell.svg",
      bash: "shell.svg",
      zsh: "shell.svg"
    };
    const iconFile = iconMap[raw] || "shell.svg";
    const monoClass = getAgentMonogramClass(raw);
    const fallback = fallbackText || getAgentMonogramText(raw);
    return `<span class="agent-monogram ${monoClass}" style="width:${size}px; height:${size}px;" title="${escapeHtml(agentId || 'Agent')}">
      <img src="/static/img/agents/${iconFile}" class="agent-icon" alt="${escapeHtml(raw)}" onerror="this.style.display='none'; this.parentElement.innerText='${fallback}';" />
    </span>`;
  }

  function openParallelDispatchModal() {
    const modal = document.getElementById("workspace-dispatch-modal");
    const list = document.getElementById("ws-dispatch-panes-list");
    if (!modal || !list) return;

    list.innerHTML = "";
    const activePanes = workspaceState.panes.filter(p => {
      const el = document.getElementById(`ws-pane-card-${p.id}`);
      return el && el.style.display !== "none";
    });

    activePanes.forEach((pane, idx) => {
      const card = document.createElement("div");
      card.style.background = "var(--bg-surface)";
      card.style.border = "1px solid var(--border-subtle)";
      card.style.borderRadius = "6px";
      card.style.padding = "10px 12px";

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <div style="display:flex; align-items:center; gap:6px;">
            ${getAgentIconHtml(pane.defaultAgent, 18)}
            <span style="font-size:0.78rem; font-weight:600; color:var(--text-primary);">${pane.title} (Pane ${idx + 1})</span>
          </div>
          <span style="font-size:0.70rem; color:var(--text-muted); font-family:var(--font-mono);">${pane.sessionId || 'session'}</span>
        </div>
        <textarea class="command-field ws-dispatch-field" data-dispatch-pane="${pane.id}" rows="2" style="width:100%; font-size:0.76rem; resize:vertical;" placeholder="Enter instruction specifically for ${pane.title}..."></textarea>
      `;
      list.appendChild(card);
    });

    modal.classList.add("open");
    const firstField = list.querySelector("textarea");
    if (firstField) firstField.focus();
  }

  function applyDispatchTemplate(templateType) {
    const fields = document.querySelectorAll(".ws-dispatch-field");
    if (fields.length === 0) return;

    if (templateType === "consensus") {
      fields.forEach((f) => {
        f.value = `Synthesize an independent implementation strategy and solve the core logic for the specified objective. Compare edge cases and code structures.`;
      });
    } else if (templateType === "fullstack") {
      if (fields[0]) fields[0].value = "Design the REST API endpoints, schemas, and data models for this feature.";
      if (fields[1]) fields[1].value = "Construct the interactive user interface, reactive state, and styling for this feature.";
      if (fields[2]) fields[2].value = "Implement integration tests and verification checks for both endpoints and UI.";
      if (fields[3]) fields[3].value = "Review documentation, write unit tests, and verify system performance.";
    } else if (templateType === "audit_fix") {
      if (fields[0]) fields[0].value = "Audit recent git diffs and error logs for vulnerabilities, defects, and bugs.";
      if (fields[1]) fields[1].value = "Implement precise patches addressing the findings from the audit.";
      if (fields[2]) fields[2].value = "Run unit test suites and verify patch stability.";
      if (fields[3]) fields[3].value = "Generate git commit message and format summary.";
    } else if (templateType === "broadcast") {
      const firstVal = fields[0]?.value || "";
      if (firstVal) {
        fields.forEach(f => { f.value = firstVal; });
      }
    }
  }

  async function executeParallelDispatch() {
    const fields = document.querySelectorAll(".ws-dispatch-field");
    const dispatches = [];

    fields.forEach(f => {
      const paneId = f.getAttribute("data-dispatch-pane");
      const prompt = f.value.trim();
      const pane = workspaceState.panes.find(p => p.id === paneId);
      if (pane && prompt) {
        dispatches.push({
          session_id: pane.sessionId,
          agent: pane.defaultAgent,
          prompt: prompt
        });
      }
    });

    if (dispatches.length === 0) {
      showToast("Please enter at least one prompt to dispatch");
      return;
    }

    try {
      const res = await fetch("/api/workspaces/parallel_dispatch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dispatches })
      });
      if (res.ok) {
        const d = await res.json();
        showToast(`Parallel dispatched to ${d.results?.length || dispatches.length} agents!`);
        document.getElementById("workspace-dispatch-modal")?.classList.remove("open");
      }
    } catch (e) {
      showToast("Parallel dispatch failed: " + e.message);
    }
  }

  function openPipeModal(preselectedSourceId = null) {
    const modal = document.getElementById("workspace-pipe-modal");
    const srcSelect = document.getElementById("ws-pipe-source");
    const dstSelect = document.getElementById("ws-pipe-target");
    if (!modal || !srcSelect || !dstSelect) return;

    srcSelect.innerHTML = "";
    dstSelect.innerHTML = "";

    const activePanes = workspaceState.panes.filter(p => {
      const el = document.getElementById(`ws-pane-card-${p.id}`);
      return el && el.style.display !== "none";
    });

    activePanes.forEach((p, idx) => {
      const isSelectedSrc = preselectedSourceId ? p.sessionId === preselectedSourceId : idx === 0;
      const isSelectedDst = preselectedSourceId ? p.sessionId !== preselectedSourceId : idx === 1;

      const optSrc = document.createElement("option");
      optSrc.value = p.sessionId;
      optSrc.textContent = `${p.title} (${p.sessionId})`;
      if (isSelectedSrc) optSrc.selected = true;
      srcSelect.appendChild(optSrc);

      const optDst = document.createElement("option");
      optDst.value = p.sessionId;
      optDst.textContent = `${p.title} (${p.sessionId})`;
      if (isSelectedDst) optDst.selected = true;
      dstSelect.appendChild(optDst);
    });

    modal.classList.add("open");
  }

  async function executePipe(e) {
    if (e) e.preventDefault();
    const src = document.getElementById("ws-pipe-source")?.value;
    const dst = document.getElementById("ws-pipe-target")?.value;
    const lines = parseInt(document.getElementById("ws-pipe-lines")?.value || "50", 10);
    const prefix = document.getElementById("ws-pipe-prefix")?.value || "";

    if (!src || !dst) {
      showToast("Select both source and target terminals");
      return;
    }
    if (src === dst) {
      showToast("Source and target cannot be the same terminal");
      return;
    }

    try {
      const res = await fetch("/api/workspaces/pipe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_session_id: src,
          target_session_id: dst,
          lines: lines,
          prompt_prefix: prefix
        })
      });
      if (res.ok) {
        const d = await res.json();
        showToast(`Piped ${d.source} -> ${d.target} (${d.bytes_piped} bytes)`);
        document.getElementById("workspace-pipe-modal")?.classList.remove("open");
      } else {
        const err = await res.json();
        showToast(err.detail || "Pipe failed");
      }
    } catch (e) {
      showToast("Pipe error: " + e.message);
    }
  }

  // --------------------------------------------------
  // View: Solo Hermes & Model Control Plane
  // --------------------------------------------------
  async function loadHermesView() {
    try {
      const res = await fetch("/api/hermes/status");
      if (!res.ok) return;
      const data = await res.json();

      const modelEl = document.getElementById("hermes-stat-model");
      const providerEl = document.getElementById("hermes-stat-provider");
      const dashEl = document.getElementById("hermes-stat-dashboard");
      const discordEl = document.getElementById("hermes-stat-discord");

      if (modelEl) modelEl.textContent = data.current_model || "kimi-k2.7-code";
      if (providerEl) providerEl.textContent = `${(data.provider || "FreeInference").toUpperCase()} Provider`;
      if (dashEl) dashEl.textContent = data.is_dashboard_running ? "Online (Port 9119)" : "Offline";
      if (discordEl) discordEl.textContent = data.discord_enabled ? "Enabled (Live)" : "Disabled";

      // Render model switcher cards
      const grid = document.getElementById("hermes-model-grid");
      if (grid) {
        grid.innerHTML = "";
        (data.available_models || []).forEach(m => {
          const card = document.createElement("div");
          const isActive = data.current_model === m.id;
          card.className = `hermes-model-card ${isActive ? "active" : ""}`;
          card.innerHTML = `
            <div>
              <div class="hermes-model-title">${escapeHtml(m.name)}</div>
              <div class="hermes-model-sub">${m.context} Context · <span style="color:#f59e0b;">${m.provider}</span></div>
            </div>
            <button type="button" class="action-btn ${isActive ? "btn-primary-action" : ""}" style="padding:4px 10px; font-size:0.72rem;">
              ${isActive ? "Active" : "Select"}
            </button>
          `;

          card.querySelector("button")?.addEventListener("click", async () => {
            showToast(`Switching to ${m.name}...`);
            try {
              const switchRes = await fetch("/api/hermes/model", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ model_id: m.id })
              });
              if (switchRes.ok) {
                showToast(`Hermes model switched to: ${m.name}`);
                loadHermesView();
              }
            } catch (e) {
              showToast("Failed to switch model");
            }
          });

          grid.appendChild(card);
        });
      }
    } catch (e) {}
  }

  document.getElementById("btn-launch-hermes-term")?.addEventListener("click", () => {
    switchView("view-terminal");
    createTab("Hermes Agent", "/home/jewboy420/hermes-env/bin/hermes", null, "hermes");
  });

  document.getElementById("btn-hermes-direct-submit")?.addEventListener("click", async () => {
    const input = document.getElementById("hermes-direct-input");
    const output = document.getElementById("hermes-direct-output");
    const prompt = (input?.value || "").trim();
    if (!prompt) return;

    if (output) output.textContent = "Querying Solo Hermes with FreeInference...";
    try {
      const res = await fetch("/api/communicator/hermes_direct", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt })
      });
      if (res.ok) {
        const data = await res.json();
        if (output) output.textContent = data.result?.output || "No output returned.";
      }
    } catch (e) {
      if (output) output.textContent = "Error: " + e.message;
    }
  });

  // --------------------------------------------------
  // View: ChatGPT / Codex IDE & Team Leader Harness
  // --------------------------------------------------
  const chatState = {
    isInitialized: false,
    activeThreadId: null,
    threads: [],
    isStreaming: false,
    currentProvider: "opencode-zen",
    currentModel: "opencode/deepseek-v4-flash-free"
  };

  function formatChatMarkdown(text) {
    if (!text) return "";
    let safe = escapeHtml(text);
    
    // Code blocks ```lang\ncode\n```
    safe = safe.replace(/```([a-zA-Z0-9_-]+)?\n([\s\S]*?)```/g, (match, lang, code) => {
      const language = lang || 'code';
      return `<div style="position:relative; margin:8px 0;"><div style="display:flex; justify-content:space-between; align-items:center; background:#18181c; padding:4px 10px; border-top-left-radius:6px; border-top-right-radius:6px; border:1px solid var(--border-subtle); border-bottom:none; font-size:0.68rem; color:var(--text-muted); font-family:var(--font-mono); font-weight:600;"><span>${language}</span><button type="button" class="action-btn" style="padding:1px 6px; font-size:0.65rem;" onclick="navigator.clipboard.writeText(this.parentElement.nextElementSibling.innerText); showToast('Code copied to clipboard');">Copy</button></div><pre style="margin:0; border-top-left-radius:0; border-top-right-radius:0;"><code>${code}</code></pre></div>`;
    });

    // Inline code
    safe = safe.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.08); padding:1px 4px; border-radius:3px; font-family:var(--font-mono); font-size:0.82em;">$1</code>');

    // Bold
    safe = safe.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Action tags [ACTION:...]
    safe = safe.replace(/\[ACTION:([a-zA-Z0-9_]+)\s+([^\]]+)\]/g, (match, action, params) => {
      return `<div class="chat-action-card"><div class="action-card-header"><div style="display:flex; align-items:center; gap:5px;"><span class="indicator-dot" style="background:var(--accent-blue);"></span><span>AUTONOMOUS ACTION: ${escapeHtml(action)}</span></div></div><div class="action-card-body">${escapeHtml(params)}</div></div>`;
    });

    // Tool results
    safe = safe.replace(/\[TOOL RESULT for ([^\]]+)\]:\n([\s\S]*?)(?=(\n\n|$))/g, (match, tool, result) => {
      return `<div class="chat-action-card" style="border-color:rgba(16,185,129,0.3); background:rgba(16,185,129,0.04);"><div class="action-card-header" style="background:rgba(16,185,129,0.1); color:#34d399;"><div style="display:flex; align-items:center; gap:5px;"><span class="indicator-dot" style="background:var(--accent-emerald);"></span><span>TOOL RESULT: ${escapeHtml(tool)}</span></div></div><div class="action-card-body" style="color:#d1fae5;">${escapeHtml(result)}</div></div>`;
    });

    // Newlines
    safe = safe.replace(/\n/g, '<br>');
    return safe;
  }

  async function initChatWorkspaceView() {
    if (chatState.isInitialized) return;
    chatState.isInitialized = true;

    // Mode Toggle (Chat IDE vs Terminal Matrix)
    document.querySelectorAll("#chat-view-mode-toggle button").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#chat-view-mode-toggle button").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const mode = btn.getAttribute("data-workspace-mode");
        const chatShell = document.getElementById("chat-ide-shell");
        const matrixCont = document.getElementById("workspace-matrix-container");
        if (mode === "matrix") {
          if (chatShell) chatShell.style.display = "none";
          if (matrixCont) {
            matrixCont.style.display = "flex";
            setTimeout(() => fitAllWorkspacePanes(), 60);
          }
        } else {
          if (chatShell) chatShell.style.display = "flex";
          if (matrixCont) matrixCont.style.display = "none";
        }
      });
    });

    // Inspector toggle
    const inspector = document.getElementById("chat-inspector");
    document.getElementById("btn-toggle-chat-inspector")?.addEventListener("click", () => {
      inspector?.classList.toggle("collapsed");
    });
    document.getElementById("btn-close-chat-inspector")?.addEventListener("click", () => {
      inspector?.classList.add("collapsed");
    });

    // Model select
    const modelSelect = document.getElementById("chat-active-model-select");
    modelSelect?.addEventListener("change", (e) => {
      const val = e.target.value;
      const parts = val.split(":");
      chatState.currentProvider = parts[0];
      chatState.currentModel = parts.slice(1).join(":");
      showToast(`Model set to: ${chatState.currentModel}`);
    });

    // New thread button
    document.getElementById("btn-new-chat-thread")?.addEventListener("click", () => {
      createNewChatThread();
    });

    // Starter prompts
    document.querySelectorAll(".welcome-prompt-card").forEach(card => {
      card.addEventListener("click", () => {
        const prompt = card.getAttribute("data-starter");
        const input = document.getElementById("chat-input-textarea");
        if (input) {
          input.value = prompt;
          input.focus();
          sendChatMessage();
        }
      });
    });

    // Textarea enter
    const chatInput = document.getElementById("chat-input-textarea");
    chatInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });

    // Send button
    document.getElementById("btn-chat-send")?.addEventListener("click", sendChatMessage);

    // Attach skill button -> open GitHub Skills Modal
    document.getElementById("btn-chat-attach-skill")?.addEventListener("click", () => {
      openGitHubHubModal("skills");
    });
    document.getElementById("btn-open-github-skills-modal")?.addEventListener("click", () => {
      openGitHubHubModal("skills");
    });
    document.getElementById("btn-open-github-mcps-modal")?.addEventListener("click", () => {
      openGitHubHubModal("mcps");
    });

    // Config modal trigger
    document.getElementById("btn-open-chat-config")?.addEventListener("click", () => {
      document.getElementById("chat-config-modal")?.classList.add("open");
    });

    // Config form submit
    document.getElementById("chat-config-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const p = document.getElementById("config-provider-select")?.value;
      const url = document.getElementById("config-endpoint-url")?.value;
      const key = document.getElementById("config-api-key")?.value;
      const model = document.getElementById("config-model-id")?.value;
      
      if (p) chatState.currentProvider = p;
      if (model) chatState.currentModel = model;
      
      showToast(`Configuration updated: ${chatState.currentProvider} · ${chatState.currentModel}`);
      document.getElementById("chat-config-modal")?.classList.remove("open");
    });

    // Init subcomponents
    initGitHubHub();
    await loadChatThreads();
    updateChatFleetMini();
    populateInspectorContext();
  }

  async function loadChatThreads() {
    try {
      const res = await fetch("/api/chat/threads");
      if (!res.ok) return;
      chatState.threads = await res.json();
      
      if (chatState.threads.length === 0) {
        await createNewChatThread("Autonomous Orchestrator Session");
      } else {
        renderChatThreads();
        switchChatThread(chatState.threads[0].id);
      }
    } catch (e) {}
  }

  function renderChatThreads() {
    const list = document.getElementById("chat-threads-list");
    if (!list) return;
    list.innerHTML = "";

    chatState.threads.forEach(t => {
      const el = document.createElement("div");
      el.className = `chat-thread-item ${t.id === chatState.activeThreadId ? "active" : ""}`;
      el.innerHTML = `
        <span class="thread-item-title">${escapeHtml(t.title)}</span>
        <div class="thread-item-actions">
          <button type="button" class="action-btn icon-only" data-del-thread="${t.id}" style="height:20px; width:20px; font-size:0.65rem;" title="Delete Thread">✕</button>
        </div>
      `;

      el.addEventListener("click", (e) => {
        if (e.target.closest("[data-del-thread]")) return;
        switchChatThread(t.id);
      });

      el.querySelector("[data-del-thread]")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        await deleteChatThread(t.id);
      });

      list.appendChild(el);
    });
  }

  async function createNewChatThread(title = "New Chat Session") {
    try {
      const res = await fetch("/api/chat/threads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          provider_id: chatState.currentProvider,
          model_id: chatState.currentModel
        })
      });
      if (res.ok) {
        const thread = await res.json();
        chatState.threads.unshift(thread);
        renderChatThreads();
        switchChatThread(thread.id);
      }
    } catch (e) {
      showToast("Failed to create thread");
    }
  }

  async function deleteChatThread(threadId) {
    try {
      const res = await fetch(`/api/chat/threads/${threadId}`, { method: "DELETE" });
      if (res.ok) {
        chatState.threads = chatState.threads.filter(t => t.id !== threadId);
        renderChatThreads();
        if (chatState.activeThreadId === threadId) {
          if (chatState.threads.length > 0) {
            switchChatThread(chatState.threads[0].id);
          } else {
            createNewChatThread();
          }
        }
      }
    } catch (e) {}
  }

  async function switchChatThread(threadId) {
    chatState.activeThreadId = threadId;
    const thread = chatState.threads.find(t => t.id === threadId);
    
    const titleEl = document.getElementById("chat-active-thread-title");
    if (titleEl && thread) titleEl.textContent = thread.title;

    renderChatThreads();

    const container = document.getElementById("chat-messages-container");
    if (!container) return;

    try {
      const res = await fetch(`/api/chat/threads/${threadId}/messages`);
      if (res.ok) {
        const messages = await res.json();
        renderChatMessages(messages);
      }
    } catch (e) {}
  }

  function renderChatMessages(messages) {
    const container = document.getElementById("chat-messages-container");
    if (!container) return;

    const nonSystem = (messages || []).filter(m => m.role !== "system");
    if (nonSystem.length === 0) {
      container.innerHTML = `
        <div class="chat-welcome-hero" id="chat-welcome-hero">
          <div class="welcome-logo-badge">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
            </svg>
          </div>
          <div class="welcome-hero-title">Terminus Team Leader Harness</div>
          <div class="welcome-hero-desc">
            Universal AI engineering leader. State any goal, and the Harness will autonomously select models, dispatch coding agents (Claude, Hermes, Antigravity), pull skills from GitHub, and execute tests without manual terminal input.
          </div>
          <div class="welcome-prompts-grid">
            <div class="welcome-prompt-card" data-starter="Audit this repository for security vulnerabilities and race conditions, then generate patches.">
              <div class="prompt-card-label">Security Audit & Patch</div>
              <div class="prompt-card-sub">Dispatch Claude & Antigravity to audit code and apply surgical fixes.</div>
            </div>
            <div class="welcome-prompt-card" data-starter="Search GitHub for a comprehensive test-driven development skill, install it, and inject it into Hermes.">
              <div class="prompt-card-label">Pull GitHub Skill</div>
              <div class="prompt-card-sub">Scrape and pull live skills from GitHub repositories.</div>
            </div>
            <div class="welcome-prompt-card" data-starter="Design and implement a fullstack feature: schema, backend API endpoint, and UI components.">
              <div class="prompt-card-label">Fullstack Autonomous Slice</div>
              <div class="prompt-card-sub">Coordinate backend, database, and UI agent workers in parallel.</div>
            </div>
            <div class="welcome-prompt-card" data-starter="Execute the test suite, analyze failing traces, and fix broken assertions.">
              <div class="prompt-card-label">Self-Healing Test Runner</div>
              <div class="prompt-card-sub">Run bash test runner and iteratively repair code until 100% green.</div>
            </div>
          </div>
        </div>
      `;
      // Re-attach starter prompt clicks
      container.querySelectorAll(".welcome-prompt-card").forEach(card => {
        card.addEventListener("click", () => {
          const prompt = card.getAttribute("data-starter");
          const input = document.getElementById("chat-input-textarea");
          if (input) {
            input.value = prompt;
            input.focus();
            sendChatMessage();
          }
        });
      });
      return;
    }

    container.innerHTML = "";
    nonSystem.forEach(m => {
      appendChatMessageToDOM(m.role, m.content);
    });
    container.scrollTop = container.scrollHeight;
  }

  function appendChatMessageToDOM(role, content) {
    const container = document.getElementById("chat-messages-container");
    if (!container) return null;

    // Hide welcome hero if present
    const hero = document.getElementById("chat-welcome-hero");
    if (hero) hero.style.display = "none";

    const isUser = role === "user";
    const row = document.createElement("div");
    row.className = `chat-msg-row ${isUser ? "user-row" : "assistant-row"}`;

    const avatar = isUser
      ? `<div class="chat-avatar user-avatar">YOU</div>`
      : `<div class="chat-avatar assistant-avatar">${getAgentIconHtml('claude', 18)}</div>`;

    row.innerHTML = `
      ${!isUser ? avatar : ""}
      <div class="chat-bubble">
        ${formatChatMarkdown(content)}
      </div>
      ${isUser ? avatar : ""}
    `;

    container.appendChild(row);
    container.scrollTop = container.scrollHeight;
    return row;
  }

  async function sendChatMessage() {
    const input = document.getElementById("chat-input-textarea");
    if (!input || chatState.isStreaming) return;

    const message = input.value.trim();
    if (!message) return;

    input.value = "";
    input.style.height = "auto";

    // 1. Append User Bubble
    appendChatMessageToDOM("user", message);

    // 2. Append Assistant Bubble with live cursor
    chatState.isStreaming = true;
    const sendBtn = document.getElementById("btn-chat-send");
    if (sendBtn) sendBtn.disabled = true;

    const assistantRow = appendChatMessageToDOM("assistant", "");
    const bubbleEl = assistantRow?.querySelector(".chat-bubble");
    if (bubbleEl) {
      bubbleEl.innerHTML = `<span class="indicator-dot" style="background:var(--accent-cyan); animation:blink 1s infinite;"></span> <span style="color:var(--text-muted); font-size:0.75rem;">Team Leader Harness orchestrating solution...</span>`;
    }

    let accumulatedText = "";

    try {
      const targetAgent = document.getElementById("chat-target-agent-select")?.value || "all";
      const fullPrompt = targetAgent !== "all" ? `[@${targetAgent.toUpperCase()}]: ${message}` : message;

      const res = await fetch("/api/harness/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: chatState.activeThreadId,
          message: fullPrompt,
          provider_id: chatState.currentProvider,
          model_id: chatState.currentModel
        })
      });

      if (!res.ok) {
        if (bubbleEl) bubbleEl.innerHTML = `<span style="color:var(--accent-rose);">Error connecting to model: HTTP ${res.status}</span>`;
        chatState.isStreaming = false;
        if (sendBtn) sendBtn.disabled = false;
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop(); // keep remainder

        for (const block of lines) {
          const cleanLine = block.trim();
          if (cleanLine.startsWith("data: ")) {
            try {
              const data = JSON.parse(cleanLine.substring(6));
              if (data.type === "tool_start") {
                const streamPane = document.getElementById("inspector-agent-stream");
                if (streamPane) {
                  streamPane.textContent = `[HARNESS RUNNING TOOL]: ${data.action}...\n${JSON.stringify(data.details, null, 2)}`;
                }
              } else if (data.type === "tool_end") {
                const streamPane = document.getElementById("inspector-agent-stream");
                if (streamPane) {
                  streamPane.textContent = `[HARNESS TOOL COMPLETED]: ${data.action}\n${data.result}`;
                }
              } else if (data.content) {
                accumulatedText += data.content;
                if (bubbleEl) {
                  bubbleEl.innerHTML = formatChatMarkdown(accumulatedText);
                  const container = document.getElementById("chat-messages-container");
                  if (container) container.scrollTop = container.scrollHeight;
                }
              }
            } catch (e) {}
          }
        }
      }
    } catch (e) {
      if (bubbleEl) bubbleEl.innerHTML = `<span style="color:var(--accent-rose);">Streaming error: ${escapeHtml(e.message)}</span>`;
    } finally {
      chatState.isStreaming = false;
      if (sendBtn) sendBtn.disabled = false;
      updateChatFleetMini();
    }
  }

  async function updateChatFleetMini() {
    const box = document.getElementById("chat-fleet-mini");
    if (!box) return;

    try {
      const res = await fetch("/api/agents");
      if (!res.ok) return;
      const agents = await res.json();

      box.innerHTML = "";
      agents.slice(0, 8).forEach(a => {
        const pill = document.createElement("div");
        pill.className = `fleet-mini-pill ${a.installed ? "running" : ""}`;
        pill.innerHTML = `
          ${getAgentIconHtml(a.id, 13)}
          <span>${escapeHtml(a.name)}</span>
        `;
        pill.title = `${a.name}: ${a.installed ? "Installed / Ready" : "Not Found"}`;
        box.appendChild(pill);
      });
    } catch (e) {}
  }

  async function populateInspectorContext() {
    const skillsList = document.getElementById("inspector-skills-list");
    const mcpList = document.getElementById("inspector-mcp-list");

    try {
      const [sRes, mRes] = await Promise.all([
        fetch("/api/skills"),
        fetch("/api/mcp")
      ]);

      if (sRes.ok && skillsList) {
        const sData = await sRes.json();
        const skills = (sData.skills || []).slice(0, 5);
        skillsList.innerHTML = skills.map(s => `
          <div class="inspector-item">
            <span style="font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(s.title)}</span>
            <span style="font-size:0.62rem; color:var(--accent-blue);">${s.origin}</span>
          </div>
        `).join("");
      }

      if (mRes.ok && mcpList) {
        const mcps = await mRes.json();
        mcpList.innerHTML = (mcps || []).slice(0, 4).map(m => `
          <div class="inspector-item">
            <span style="font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(m.name)}</span>
            <span style="font-size:0.62rem; color:#10b981;">${m.status || "ready"}</span>
          </div>
        `).join("");
      }
    } catch (e) {}
  }

  // --------------------------------------------------
  // GitHub Hub: Skills & MCP Scraper / Puller
  // --------------------------------------------------
  function initGitHubHub() {
    let currentType = "skills";

    document.querySelectorAll("#github-hub-type-toggle button").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#github-hub-type-toggle button").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentType = btn.getAttribute("data-hub-type");
        searchGitHubHub(currentType, document.getElementById("github-hub-search")?.value || "");
      });
    });

    document.getElementById("btn-github-search-run")?.addEventListener("click", () => {
      searchGitHubHub(currentType, document.getElementById("github-hub-search")?.value || "");
    });

    document.getElementById("github-hub-search")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        searchGitHubHub(currentType, e.target.value);
      }
    });
  }

  function openGitHubHubModal(type = "skills") {
    const modal = document.getElementById("github-hub-modal");
    if (!modal) return;
    
    // Set active toggle
    document.querySelectorAll("#github-hub-type-toggle button").forEach(b => {
      b.classList.toggle("active", b.getAttribute("data-hub-type") === type);
    });

    modal.classList.add("open");
    searchGitHubHub(type, "");
  }

  async function searchGitHubHub(type, query) {
    const grid = document.getElementById("github-cards-grid");
    if (!grid) return;
    grid.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-muted); font-size:0.8rem;">Querying GitHub &amp; community repositories...</div>`;

    const endpoint = type === "skills" ? `/api/skills/github/search?q=${encodeURIComponent(query)}` : `/api/mcp/github/search?q=${encodeURIComponent(query)}`;

    try {
      const res = await fetch(endpoint);
      if (!res.ok) throw new Error("Search failed");
      const items = await res.json();
      renderGitHubCards(items, type);
    } catch (e) {
      grid.innerHTML = `<div style="text-align:center; padding:30px; color:var(--accent-rose); font-size:0.8rem;">Search error: ${escapeHtml(e.message)}</div>`;
    }
  }

  function renderGitHubCards(items, type) {
    const grid = document.getElementById("github-cards-grid");
    if (!grid) return;

    if (!items || items.length === 0) {
      grid.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-muted); font-size:0.8rem;">No GitHub packages found matching query.</div>`;
      return;
    }

    grid.innerHTML = "";
    items.forEach(item => {
      const card = document.createElement("div");
      card.className = "github-card";

      const stars = item.stars ? `<span class="github-stars-tag">★ ${item.stars.toLocaleString()}</span>` : "";
      const cat = item.category || "General";

      card.innerHTML = `
        <div>
          <div class="github-card-header">
            <span class="github-card-title">${escapeHtml(item.title || item.name)}</span>
            ${stars}
          </div>
          <div style="font-size:0.65rem; color:var(--accent-blue); margin-bottom:6px; font-weight:600;">${escapeHtml(cat)} · ${escapeHtml(item.author || item.repo || 'Verified')}</div>
          <div class="github-card-desc">${escapeHtml(item.description || '')}</div>
        </div>
        <div class="github-card-actions">
          <span style="font-family:var(--font-mono); font-size:0.65rem; color:var(--text-dim); overflow:hidden; text-overflow:ellipsis; max-width:140px;">${escapeHtml(item.name)}</span>
          <button type="button" class="action-btn btn-primary-action btn-install-gh" style="height:26px; padding:0 10px; font-size:0.72rem;">Install</button>
        </div>
      `;

      card.querySelector(".btn-install-gh")?.addEventListener("click", async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.textContent = "Pulling...";

        const target = document.getElementById("github-install-target")?.value || "all";

        try {
          if (type === "skills") {
            const installRes = await fetch("/api/skills/github/install", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ skill_id: item.id, target })
            });
            if (installRes.ok) {
              btn.textContent = "Installed!";
              btn.style.background = "var(--accent-emerald)";
              btn.style.color = "#000";
              showToast(`Installed skill '${item.name}' into ${target} agents`);
              populateInspectorContext();
            } else {
              btn.textContent = "Failed";
              btn.disabled = false;
            }
          } else {
            const installRes = await fetch("/api/mcp/github/install", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ mcp_id: item.id })
            });
            if (installRes.ok) {
              btn.textContent = "Installed!";
              btn.style.background = "var(--accent-emerald)";
              btn.style.color = "#000";
              showToast(`Installed MCP server '${item.name}' into Claude & Antigravity`);
              populateInspectorContext();
            } else {
              btn.textContent = "Failed";
              btn.disabled = false;
            }
          }
        } catch (err) {
          btn.textContent = "Error";
          btn.disabled = false;
          showToast(`Install error: ${err.message}`);
        }
      });

      grid.appendChild(card);
    });
  }

  boot();
});
