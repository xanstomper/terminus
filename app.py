import os
import sys
import pty
import fcntl
import termios
import struct
import asyncio
import signal
import socket
import platform
import time
import hmac
import hashlib
import json
import re
import shlex
import threading
from pathlib import Path
from typing import Dict, Set, Optional, Any, List

import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, HTTPException, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import adapters
import processes
import projects
import files
import ports
import logs
import doctor
import activity
import mcp_manager
import skills_manager
import memory_hub
import cron_manager
import tunnel_manager
import communicator
import hermes_hub
import workspace_manager
import chat_engine
import github_hub
import harness


app = FastAPI(title="Terminus - The endpoint you can reach anywhere")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if (STATIC_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=str(STATIC_DIR / "css")), name="css")
if (STATIC_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=str(STATIC_DIR / "js")), name="js")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

COOKIE_NAME = "terminus_session"
AUTH_DURATION = 86400 * 30  # 30 days


# ---------------------------------------------------------
# Security & Authentication
# ---------------------------------------------------------
def create_auth_token(username: str) -> str:
    expires = int(time.time()) + AUTH_DURATION
    payload = f"{username}:{expires}"
    sig = hmac.new(config.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_auth_token(token: Optional[str]) -> bool:
    if not config.AUTH_ENABLED:
        return True
    if not token:
        return False
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        username, expires_str, sig = parts
        expires = int(expires_str)
        if time.time() > expires:
            return False
        expected_payload = f"{username}:{expires}"
        expected_sig = hmac.new(config.SECRET_KEY.encode(), expected_payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except Exception:
        return False


def is_authenticated(request: Request) -> bool:
    if not config.AUTH_ENABLED:
        return True
    # Check both cookie and Authorization header
    token = request.cookies.get(COOKIE_NAME) or request.cookies.get("ag_session")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
    return verify_auth_token(token)


SESSION_HISTORY_FILE = Path.home() / ".terminus" / "sessions_history.json"
BUFFERS_DIR = Path.home() / ".terminus" / "buffers"

def clean_ansi(text: str) -> str:
    ansi_regex = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_regex.sub('', text)

def load_session_history() -> List[Dict[str, Any]]:
    try:
        if SESSION_HISTORY_FILE.exists():
            with open(SESSION_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_session_record(session: "TerminalSession", is_active: bool = True):
    try:
        SESSION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        history = load_session_history()
        now = time.time()
        snippet = session.get_recent_snippet()
        
        found = False
        for rec in history:
            if rec.get("id") == session.session_id:
                rec["title"] = session.title
                rec["agent_id"] = session.agent_id
                rec["cwd"] = session.cwd
                rec["last_active"] = session.last_active
                rec["total_bytes"] = session.total_bytes
                rec["snippet"] = snippet
                rec["is_active"] = is_active
                if not is_active and "closed_at" not in rec:
                    rec["closed_at"] = now
                found = True
                break
        
        if not found:
            history.insert(0, {
                "id": session.session_id,
                "title": session.title,
                "agent_id": session.agent_id,
                "cwd": session.cwd,
                "created_at": session.created_at,
                "last_active": session.last_active,
                "total_bytes": session.total_bytes,
                "snippet": snippet,
                "is_active": is_active,
                "closed_at": None if is_active else now
            })
            
        history = history[:120]
        with open(SESSION_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass

def save_session_buffer(session_id: str, data: bytes):
    try:
        BUFFERS_DIR.mkdir(parents=True, exist_ok=True)
        with open(BUFFERS_DIR / f"{session_id}.log", "wb") as f:
            f.write(data)
    except Exception:
        pass

def get_session_buffer(session_id: str) -> str:
    if session_id in sessions:
        return sessions[session_id].history_buffer.decode("utf-8", errors="replace")
    file_path = BUFFERS_DIR / f"{session_id}.log"
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            pass
    return ""

def mark_session_closed(session_id: str):
    try:
        if SESSION_HISTORY_FILE.exists():
            history = load_session_history()
            for rec in history:
                if rec.get("id") == session_id:
                    rec["is_active"] = False
                    rec["closed_at"] = time.time()
                    break
            with open(SESSION_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
    except Exception:
        pass

# ---------------------------------------------------------
# Robust Persistent PTY Terminal Session
# ---------------------------------------------------------
class TerminalSession:
    def __init__(
        self,
        session_id: str,
        title: str = "Shell",
        agent_id: Optional[str] = None,
        initial_cmd: Optional[str] = None,
        cwd: Optional[str] = None
    ):
        self.session_id = session_id
        self.title = title
        self.agent_id = agent_id
        self.initial_cmd = initial_cmd
        self.cwd = cwd or config.WORKING_DIRECTORY
        
        self.master_fd: Optional[int] = None
        self.child_pid: Optional[int] = None
        self.websockets: Set[WebSocket] = set()
        
        # Buffer and offset tracking for seamless mobile background sync
        self.history_buffer = bytearray()
        self.max_buffer_size = 256 * 1024  # 256 KB ring buffer
        self.total_bytes = 0
        self.history_start_offset = 0
        
        self.created_at = time.time()
        self.last_active = time.time()
        self.is_alive = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        master_fd, slave_fd = pty.openpty()
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Standard initial dimensions (80x24)
        winsize = struct.pack("HHHH", 24, 80, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

        pid = os.fork()
        if pid == 0:
            # Child process
            try:
                os.close(master_fd)
                os.setsid()
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
                os.dup2(slave_fd, 0)
                os.dup2(slave_fd, 1)
                os.dup2(slave_fd, 2)
                if slave_fd > 2:
                    os.close(slave_fd)

                env = os.environ.copy()
                env["TERM"] = "xterm-256color"
                env["COLORTERM"] = "truecolor"
                env["USER"] = "jewboy420"
                env["HOME"] = config.WORKING_DIRECTORY
                
                # Ensure all agent directories are in PATH
                path = env.get("PATH", "")
                essential_paths = [
                    "/home/jewboy420/.local/bin",
                    "/home/jewboy420/.npm-global/bin",
                    "/home/jewboy420/hermes-env/bin",
                    "/home/jewboy420/.opencode/bin",
                    "/home/jewboy420/.gemini/antigravity-cli/bin"
                ]
                for p in essential_paths:
                    if p not in path and os.path.exists(p):
                        path = f"{p}:{path}"
                env["PATH"] = path
                
                target_cwd = self.cwd if os.path.isdir(self.cwd) else config.WORKING_DIRECTORY
                os.chdir(target_cwd)
                
                shell = config.DEFAULT_SHELL
                os.execvpe(shell, [shell, "-l"], env)
            except Exception as e:
                sys.stderr.write(f"Shell exec failed: {e}\n")
                os._exit(1)
        else:
            # Parent process
            os.close(slave_fd)
            self.master_fd = master_fd
            self.child_pid = pid
            self.is_alive = True
            loop.add_reader(self.master_fd, self._on_read)
            
            # If an initial command was requested (e.g. claude, mochi, agy), execute it
            if self.initial_cmd:
                loop.call_later(0.3, lambda: self.write_input(self.initial_cmd + "\n"))

    def _on_read(self):
        if not self.is_alive or self.master_fd is None:
            return
        try:
            chunk = os.read(self.master_fd, 16384)
            if not chunk:
                self.close()
                return
            self.last_active = time.time()
            self._append_history(chunk)
            
            # Broadcast to all connected clients
            for ws in list(self.websockets):
                asyncio.create_task(self._safe_send(ws, chunk))
        except OSError:
            self.close()

    async def _safe_send(self, ws: WebSocket, data: bytes):
        try:
            await ws.send_bytes(data)
        except Exception:
            self.websockets.discard(ws)

    def _append_history(self, chunk: bytes):
        self.history_buffer.extend(chunk)
        self.total_bytes += len(chunk)
        if len(self.history_buffer) > self.max_buffer_size:
            excess = len(self.history_buffer) - self.max_buffer_size
            self.history_buffer = self.history_buffer[excess:]
            self.history_start_offset += excess

    def get_slice(self, client_offset: int) -> bytes:
        if client_offset <= 0:
            return bytes(self.history_buffer)
        if client_offset >= self.total_bytes:
            return b""
        start_idx = max(0, client_offset - self.history_start_offset)
        return bytes(self.history_buffer[start_idx:])

    def get_recent_snippet(self, max_lines: int = 6) -> str:
        try:
            if not self.history_buffer:
                return ""
            tail = self.history_buffer[-8192:]
            decoded = tail.decode("utf-8", errors="replace")
            cleaned = clean_ansi(decoded)
            lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
            return "\n".join(lines[-max_lines:]) if lines else ""
        except Exception:
            return ""

    def write_input(self, data: str):
        if self.is_alive and self.master_fd is not None:
            try:
                os.write(self.master_fd, data.encode("utf-8"))
                self.last_active = time.time()
            except OSError:
                self.close()

    def resize(self, cols: int, rows: int):
        if self.is_alive and self.master_fd is not None:
            try:
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except OSError:
                pass

    def close(self):
        if not self.is_alive:
            return
        self.is_alive = False

        # Persist session buffer and record to disk
        try:
            save_session_buffer(self.session_id, bytes(self.history_buffer))
            save_session_record(self, is_active=False)
            mark_session_closed(self.session_id)
        except Exception:
            pass

        if self.master_fd is not None:
            if self.loop is not None:
                try:
                    self.loop.remove_reader(self.master_fd)
                except Exception:
                    pass
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

        if self.child_pid is not None:
            try:
                os.kill(self.child_pid, signal.SIGTERM)
                time.sleep(0.05)
                os.waitpid(self.child_pid, os.WNOHANG)
            except Exception:
                pass
            self.child_pid = None

        for ws in list(self.websockets):
            asyncio.create_task(self._notify_close(ws))

    async def _notify_close(self, ws: WebSocket):
        try:
            await ws.send_json({"type": "exit", "sessionId": self.session_id})
        except Exception:
            pass


sessions: Dict[str, TerminalSession] = {}


def get_or_create_session(
    session_id: str,
    title: str = "Shell",
    agent_id: Optional[str] = None,
    initial_cmd: Optional[str] = None,
    cwd: Optional[str] = None
) -> TerminalSession:
    if session_id in sessions and sessions[session_id].is_alive:
        return sessions[session_id]
    
    # Auto-resolve command if agent_id is provided and initial_cmd is missing
    if not initial_cmd and agent_id and agent_id.lower() not in ("shell", "sh", "bash"):
        try:
            from adapters import get_agent_adapter
            adapter = get_agent_adapter(agent_id)
            if adapter:
                initial_cmd = adapter.get("resume_cmd") or adapter.get("launch_cmd") or adapter.get("cmd")
        except Exception:
            pass

    session = TerminalSession(session_id, title, agent_id, initial_cmd, cwd)
    loop = asyncio.get_running_loop()
    session.start(loop)
    sessions[session_id] = session
    try:
        save_session_record(session, is_active=True)
    except Exception:
        pass
    return session


# ---------------------------------------------------------
# Machine Telemetry & Control Plane Metrics
# ---------------------------------------------------------
def get_machine_telemetry():
    cpu_pct = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_count(logical=True) or 4
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot_time = psutil.boot_time()
    uptime_sec = int(time.time() - boot_time)
    
    hours = uptime_sec // 3600
    minutes = (uptime_sec % 3600) // 60
    uptime_str = f"{hours}h {minutes}m"
    
    hostname = socket.gethostname()
    os_info = f"{platform.system()} {platform.machine()}"
    kernel = platform.release()
    
    # GPU detection (Intel UHD or NVIDIA)
    gpu_info = "Intel UHD Graphics (Alder Lake-N)"
    try:
        if shutil.which("nvidia-smi"):
            nv_out = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"], text=True, timeout=1)
            parts = nv_out.strip().split(",")
            if len(parts) >= 3:
                gpu_info = f"{parts[0].strip()} ({parts[1].strip()}/{parts[2].strip()} MB)"
    except Exception:
        pass
    
    lan_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    # Count running agents and total discovered
    running_agents = 0
    total_agents = 0
    try:
        all_agents_list = adapters.get_all_agents()
        total_agents = len(all_agents_list)
        for a in all_agents_list:
            if a["running_count"] > 0:
                running_agents += 1
    except Exception:
        pass

    # Load average
    try:
        load_avg = [round(x, 2) for x in os.getloadavg()]
    except Exception:
        load_avg = [0.0, 0.0, 0.0]

    return {
        "hostname": hostname,
        "os": os_info,
        "kernel": kernel,
        "cpu": cpu_pct,
        "cpu_cores": cpu_cores,
        "load_avg": load_avg,
        "gpu": gpu_info,
        "memory": {
            "percent": mem.percent,
            "used_gb": round(mem.used / (1024**3), 1),
            "total_gb": round(mem.total / (1024**3), 1),
        },
        "disk": {
            "percent": disk.percent,
            "free_gb": round(disk.free / (1024**3), 1),
            "total_gb": round(disk.total / (1024**3), 1),
        },
        "uptime": uptime_str,
        "lan_ip": lan_ip,
        "port": config.PORT,
        "active_sessions": len([s for s in sessions.values() if s.is_alive]),
        "running_agents_count": running_agents,
        "total_agents_count": total_agents,
        "app_name": config.APP_NAME,
        "app_tagline": config.APP_TAGLINE,
        "version": "1.0.0-PRO"
    }


# ---------------------------------------------------------
# Web Routes
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login?next=/", status_code=302)
    
    telemetry = get_machine_telemetry()
    all_agents = adapters.get_all_agents()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "telemetry": telemetry,
        "agents": all_agents,
        "auth_enabled": config.AUTH_ENABLED,
        "app_name": config.APP_NAME,
        "app_tagline": config.APP_TAGLINE,
        "home_dir": str(Path.home())
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error,
        "port": config.PORT,
        "app_name": config.APP_NAME,
        "app_tagline": config.APP_TAGLINE
    })


@app.post("/api/login")
async def login_submit(username: str = Form(...), password: str = Form(...)):
    if username == config.DEFAULT_USERNAME and password == config.DEFAULT_PASSWORD:
        token = create_auth_token(username)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=AUTH_DURATION,
            httponly=True,
            samesite="lax"
        )
        return response
    return RedirectResponse(url="/login?error=Invalid+credentials", status_code=303)


@app.post("/api/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=COOKIE_NAME)
    response.delete_cookie(key="ag_session")
    return response


# ---------------------------------------------------------
# REST APIs for Control Plane
# ---------------------------------------------------------
@app.get("/api/telemetry")
async def api_telemetry(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return get_machine_telemetry()


@app.get("/api/agents")
async def api_agents(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"agents": adapters.get_all_agents()}


@app.post("/api/agents/launch")
async def api_launch_agent(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    agent_id = payload.get("agent_id")
    mode = payload.get("mode", "launch")  # launch, resume, prompt
    prompt = payload.get("prompt", "")
    cwd = payload.get("cwd", config.WORKING_DIRECTORY)

    # Locate agent definition
    agent_info = None
    for a in adapters.get_all_agents():
        if a["id"] == agent_id:
            agent_info = a
            break

    if not agent_info or not agent_info["installed"]:
        raise HTTPException(status_code=404, detail="Agent not installed or found")

    cmd = agent_info["launch_cmd"]
    if mode == "resume" and agent_info.get("resume_cmd"):
        cmd = agent_info["resume_cmd"]
    elif mode == "prompt" and prompt:
        cmd = f"{agent_info['launch_cmd']} {json.dumps(prompt)}"

    # Generate dedicated tab session
    session_id = f"{agent_id}-{int(time.time() % 10000)}"
    title = agent_info["name"]
    session = get_or_create_session(session_id, title=title, agent_id=agent_id, initial_cmd=cmd, cwd=cwd)
    activity.record_activity(agent_id, "agent_launched", f"Launched {title}", details=f"Cmd: {cmd}", path=cwd)

    return {
        "session_id": session_id,
        "title": title,
        "agent_id": agent_id,
        "cmd": cmd
    }


@app.get("/api/processes")
async def api_processes(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"processes": processes.list_agent_processes()}


@app.post("/api/processes/{pid}/kill")
async def api_kill_process(pid: int, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    res = processes.terminate_process(pid, force=True)
    activity.record_activity("system", "process_killed", f"Terminated PID {pid}", details=str(res))
    return res


@app.get("/api/projects")
async def api_projects(request: Request, refresh: bool = False):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"projects": projects.scan_projects(force=refresh)}


@app.post("/api/projects/open")
async def api_open_project(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    proj_path = payload.get("path")
    if not proj_path or not os.path.isdir(proj_path):
        raise HTTPException(status_code=400, detail="Invalid or non-existent project path")
    
    req_agent_id = payload.get("agent_id")
    reuse_existing = payload.get("reuse_existing", True)
    
    # Check if an active session is already targeting this project directory
    if reuse_existing:
        for sid, s in list(sessions.items()):
            if s.is_alive and s.cwd == proj_path:
                if not req_agent_id or s.agent_id == req_agent_id:
                    return {
                        "session_id": sid,
                        "title": s.title,
                        "cwd": s.cwd,
                        "agent_id": s.agent_id,
                        "existing": True
                    }
    
    # Resolve which agent to launch
    agent_id = req_agent_id
    if not agent_id:
        agent_map = projects.get_last_project_agents()
        agent_id = agent_map.get(proj_path, None)
    
    proj_name = os.path.basename(proj_path)
    initial_cmd = None
    title = proj_name
    
    all_agents = {a["id"]: a for a in adapters.get_all_agents()}
    if agent_id and agent_id in all_agents and all_agents[agent_id]["installed"]:
        agent_info = all_agents[agent_id]
        initial_cmd = agent_info["launch_cmd"]
        title = f"{proj_name} · {agent_info['name']}"
        projects.set_last_project_agent(proj_path, agent_id)
    else:
        # Fall back to standard shell in that project directory
        title = f"{proj_name} · Shell"
        agent_id = None
        projects.set_last_project_agent(proj_path, "bash")

    clean_prefix = re.sub(r'[^a-zA-Z0-9]', '', proj_name.lower())[:10] or "proj"
    session_id = f"{clean_prefix}-{int(time.time() % 10000)}"
    
    session = get_or_create_session(
        session_id=session_id,
        title=title,
        agent_id=agent_id,
        initial_cmd=initial_cmd,
        cwd=proj_path
    )
    
    activity.record_activity(agent_id or "shell", "project_opened", f"Opened {proj_name}", details=f"{title} targeting {proj_path}", project=proj_name, path=proj_path)

    return {
        "session_id": session_id,
        "title": title,
        "cwd": proj_path,
        "agent_id": agent_id,
        "existing": False
    }


@app.get("/api/files")
async def api_files(request: Request, path: str = ""):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return files.list_directory(path)


@app.get("/api/files/content")
async def api_files_content(request: Request, path: str = ""):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return files.read_file_content(path)


@app.post("/api/files/save")
async def api_files_save(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    path = payload.get("path", "")
    content = payload.get("content", "")
    return files.save_file_content(path, content)


@app.get("/api/ports")
async def api_ports(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"ports": ports.get_listening_ports()}


@app.get("/api/logs")
async def api_logs(request: Request, source: str = "terminus", lines: int = 100, query: str = ""):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return logs.fetch_logs(source, lines, query)


@app.get("/api/logs/sources")
async def api_logs_sources(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"sources": logs.get_log_sources()}


@app.get("/api/doctor")
async def api_doctor(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return doctor.run_diagnostics()


@app.get("/api/activity")
async def api_activity(request: Request, limit: int = 50):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"activities": activity.get_activities(limit=limit)}


@app.get("/api/mcp")
async def api_mcp(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"servers": mcp_manager.get_mcp_servers()}


@app.get("/api/sessions")
async def list_sessions(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    session_list = []
    for sid, s in list(sessions.items()):
        if s.is_alive:
            try:
                save_session_record(s, is_active=True)
            except Exception:
                pass
            session_list.append({
                "id": sid,
                "title": s.title,
                "agent_id": s.agent_id,
                "cwd": s.cwd,
                "created_at": s.created_at,
                "last_active": s.last_active,
                "clients": len(s.websockets),
                "total_bytes": s.total_bytes,
                "snippet": s.get_recent_snippet(6),
                "is_active": True,
            })
    
    history_records = load_session_history()
    active_ids = {s["id"] for s in session_list}
    past_sessions = [h for h in history_records if h.get("id") not in active_ids]
    
    return {
        "sessions": session_list,
        "history": past_sessions
    }


@app.post("/api/sessions")
@app.post("/api/sessions/create")
async def create_session_api(request: Request, payload: Dict[str, Any] = Body(default={})):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    title = payload.get("title", "Shell")
    agent_id = payload.get("agent_id") or payload.get("agent")
    initial_cmd = payload.get("initial_cmd")
    cwd = payload.get("cwd", config.WORKING_DIRECTORY)

    session_id = payload.get("session_id") or f"term-{int(time.time() % 10000)}-{os.urandom(2).hex()}"
    get_or_create_session(session_id, title=title, agent_id=agent_id, initial_cmd=initial_cmd, cwd=cwd)
    activity.record_activity(agent_id or "shell", "session_created", f"Started session: {title}", details=f"Target: {cwd}", path=cwd)
    return {"session_id": session_id, "title": title, "cwd": cwd, "agent_id": agent_id}


@app.delete("/api/sessions/{session_id}")
@app.post("/api/sessions/{session_id}/close")
async def close_session(session_id: str, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if session_id in sessions:
        session = sessions.pop(session_id)
        session.close()
        return {"status": "closed", "session_id": session_id}
    return {"status": "not_found", "session_id": session_id}


@app.post("/api/sessions/{session_id}/rename")
async def api_rename_session(session_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    new_title = payload.get("title", "").strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Invalid title")
    if session_id in sessions:
        sessions[session_id].title = new_title
        try:
            save_session_record(sessions[session_id], is_active=True)
        except Exception:
            pass
    else:
        history = load_session_history()
        for rec in history:
            if rec.get("id") == session_id:
                rec["title"] = new_title
                with open(SESSION_HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=2)
                break
    return {"status": "renamed", "success": True, "session_id": session_id, "title": new_title}


@app.post("/api/sessions/{session_id}/duplicate")
async def api_duplicate_session(session_id: str, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    src_title = "Shell"
    src_agent = None
    src_cmd = None
    src_cwd = config.WORKING_DIRECTORY
    
    if session_id in sessions:
        src = sessions[session_id]
        src_title = src.title
        src_agent = src.agent_id
        src_cmd = src.initial_cmd
        src_cwd = src.cwd
    else:
        history = load_session_history()
        rec = next((h for h in history if h.get("id") == session_id), None)
        if rec:
            src_title = rec.get("title", "Shell")
            src_agent = rec.get("agent_id")
            src_cwd = rec.get("cwd", config.WORKING_DIRECTORY)
        else:
            raise HTTPException(status_code=404, detail="Session not found")
            
    new_sid = f"term-{int(time.time() % 10000)}-{os.urandom(2).hex()}"
    new_title = f"{src_title} (Copy)"
    get_or_create_session(new_sid, title=new_title, agent_id=src_agent, initial_cmd=src_cmd, cwd=src_cwd)
    activity.record_activity(src_agent or "shell", "session_duplicated", f"Duplicated session: {new_title}", path=src_cwd)
    return {"session_id": new_sid, "title": new_title, "agent_id": src_agent, "cwd": src_cwd}


@app.get("/api/sessions/{session_id}/buffer")
async def api_session_buffer(session_id: str, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if session_id in sessions:
        s = sessions[session_id]
        text = s.history_buffer.decode("utf-8", errors="replace")
        return {
            "session_id": session_id,
            "title": s.title,
            "agent_id": s.agent_id,
            "cwd": s.cwd,
            "buffer": text,
            "total_bytes": s.total_bytes,
            "is_active": True
        }
    
    archived = get_session_buffer(session_id)
    history = load_session_history()
    rec = next((h for h in history if h.get("id") == session_id), {})
    if archived or rec:
        return {
            "session_id": session_id,
            "title": rec.get("title", "Archived Session"),
            "agent_id": rec.get("agent_id"),
            "cwd": rec.get("cwd", config.WORKING_DIRECTORY),
            "buffer": archived,
            "total_bytes": len(archived),
            "is_active": False,
            "created_at": rec.get("created_at"),
            "closed_at": rec.get("closed_at")
        }
        
    raise HTTPException(status_code=404, detail="Session buffer not found")


@app.delete("/api/sessions/{session_id}/history")
async def api_delete_session_history(session_id: str, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        history = load_session_history()
        history = [h for h in history if h.get("id") != session_id]
        with open(SESSION_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        buf_file = BUFFERS_DIR / f"{session_id}.log"
        if buf_file.exists():
            buf_file.unlink()
        return {"status": "deleted", "session_id": session_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/sessions/{session_id}/resume")
async def api_resume_session(session_id: str, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Case 1: Session is active in memory
    if session_id in sessions and sessions[session_id].is_alive:
        s = sessions[session_id]
        if s.agent_id and s.agent_id.lower() not in ("shell", "sh", "bash"):
            from adapters import get_agent_adapter
            adapter = get_agent_adapter(s.agent_id)
            if adapter:
                snippet = s.get_recent_snippet(3).strip()
                if snippet.endswith("$") or snippet.endswith("#") or not snippet:
                    cmd = adapter.get("resume_cmd") or adapter.get("launch_cmd") or adapter.get("cmd")
                    if cmd:
                        s.write_input(cmd + "\n")
        return {
            "session_id": session_id,
            "title": s.title,
            "agent_id": s.agent_id,
            "cwd": s.cwd,
            "status": "resumed_active"
        }
    
    # Case 2: Historical / closed session -> relaunch with agent resume command
    history = load_session_history()
    rec = next((h for h in history if h.get("id") == session_id), None)
    
    new_sid = f"term-{int(time.time() % 10000)}-{os.urandom(2).hex()}"
    new_title = rec.get("title", "Shell") if rec else "Shell"
    agent_id = rec.get("agent_id") if rec else None
    cwd = rec.get("cwd", config.WORKING_DIRECTORY) if rec else config.WORKING_DIRECTORY
    
    initial_cmd = None
    if agent_id and agent_id.lower() not in ("shell", "sh", "bash"):
        from adapters import get_agent_adapter
        adapter = get_agent_adapter(agent_id)
        if adapter:
            initial_cmd = adapter.get("resume_cmd") or adapter.get("launch_cmd") or adapter.get("cmd")
            
    get_or_create_session(new_sid, title=new_title, agent_id=agent_id, initial_cmd=initial_cmd, cwd=cwd)
    activity.record_activity(agent_id or "shell", "session_resumed", f"Resumed conversation: {new_title}", path=cwd)
    return {
        "session_id": new_sid,
        "title": new_title,
        "agent_id": agent_id,
        "cwd": cwd,
        "status": "resumed_new"
    }


@app.post("/api/sessions/{session_id}/relaunch")
async def api_relaunch_session(session_id: str, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    history = load_session_history()
    rec = next((h for h in history if h.get("id") == session_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Historical session not found")
    
    new_sid = f"term-{int(time.time() % 10000)}-{os.urandom(2).hex()}"
    new_title = rec.get("title", "Shell")
    agent_id = rec.get("agent_id")
    cwd = rec.get("cwd", config.WORKING_DIRECTORY)
    
    initial_cmd = None
    if agent_id and agent_id.lower() not in ("shell", "sh", "bash"):
        from adapters import get_agent_adapter
        adapter = get_agent_adapter(agent_id)
        if adapter:
            initial_cmd = adapter.get("resume_cmd") or adapter.get("launch_cmd") or adapter.get("cmd")
            
    get_or_create_session(new_sid, title=new_title, agent_id=agent_id, initial_cmd=initial_cmd, cwd=cwd)
    activity.record_activity(agent_id or "shell", "session_relaunched", f"Relaunched session: {new_title}", path=cwd)
    return {"session_id": new_sid, "title": new_title, "agent_id": agent_id, "cwd": cwd}


# ---------------------------------------------------------
# Universal Skill Tree & Cross-Agent Execution Bridge
# ---------------------------------------------------------
@app.get("/api/skills")
async def api_skills(request: Request, force: bool = False):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if force:
        skills_manager.scan_all_skills(force=True)
    return skills_manager.get_skills_tree()


@app.get("/api/skills/details")
async def api_skill_details(request: Request, id: Optional[str] = None, skill_id: Optional[str] = None):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    sid = id or skill_id
    if not sid:
        raise HTTPException(status_code=400, detail="Missing skill id")
    details = skills_manager.get_skill_details(sid)
    if not details:
        raise HTTPException(status_code=404, detail="Skill not found")
    return details


@app.post("/api/skills/inject")
async def api_skill_inject(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    skill_id = payload.get("skill_id")
    session_id = payload.get("session_id")
    if not skill_id or not session_id or session_id not in sessions:
        raise HTTPException(status_code=400, detail="Invalid skill_id or session_id")
    
    session = sessions[session_id]
    directive = skills_manager.inject_skill_into_prompt(skill_id)
    session.write_input(directive)
    activity.record_activity("terminus", "skill_injected", f"Injected skill {skill_id} into {session.title}", details=f"Target session: {session_id}")
    return {"success": True, "session_id": session_id, "skill_id": skill_id}


@app.post("/api/skills/bridge")
async def api_skill_bridge(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    skill_id = payload.get("skill_id")
    target_agent = payload.get("target_agent", "universal")
    custom_dest = payload.get("custom_dest")
    res = skills_manager.bridge_skill(skill_id, target_agent, custom_dest)
    activity.record_activity("terminus", "skill_bridged", f"Bridged skill {skill_id} to {target_agent}", details=str(res))
    return res


# ---------------------------------------------------------
# Universal Multi-Agent Memory & Context Hub
# ---------------------------------------------------------
@app.get("/api/memory")
async def api_memory(request: Request, query: Optional[str] = None, agent: Optional[str] = None):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"memories": memory_hub.get_all_memories(query=query, agent=agent)}


@app.post("/api/memory")
async def api_add_memory(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    title = payload.get("title", "")
    content = payload.get("content", "")
    agent_origin = payload.get("agent_origin", "User / Shared")
    tags = payload.get("tags", [])
    entry = memory_hub.add_memory(title, content, agent_origin, tags)
    activity.record_activity("terminus", "memory_created", f"Added shared memory: {title}", details=content[:100])
    return entry


@app.delete("/api/memory/{memory_id}")
async def api_delete_memory(memory_id: str, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    success = memory_hub.delete_memory(memory_id)
    return {"success": success, "id": memory_id}


# ---------------------------------------------------------
# Universal Multi-Agent Task & Cron Scheduler
# ---------------------------------------------------------
@app.get("/api/cron")
async def api_cron(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"jobs": cron_manager.get_all_jobs()}


@app.post("/api/cron")
async def api_create_cron(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    name = payload.get("name", "")
    agent_id = payload.get("agent_id", "bash")
    prompt_or_cmd = payload.get("prompt_or_cmd", "")
    schedule = payload.get("schedule", "Hourly")
    cwd = payload.get("cwd", "/home/jewboy420")
    job = cron_manager.create_job(name, agent_id, prompt_or_cmd, schedule, cwd)
    activity.record_activity("cron", "job_created", f"Scheduled task: {name}", details=f"Agent: {agent_id}, Schedule: {schedule}")
    return job


@app.post("/api/cron/{job_id}/toggle")
async def api_toggle_cron(job_id: str, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    status = cron_manager.toggle_job(job_id)
    return {"id": job_id, "enabled": status}


@app.delete("/api/cron/{job_id}")
async def api_delete_cron(job_id: str, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    success = cron_manager.delete_job(job_id)
    return {"success": success, "id": job_id}


@app.post("/api/cron/{job_id}/run")
async def api_run_cron(job_id: str, request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    res = cron_manager.run_job_now(job_id)
    activity.record_activity("cron", "job_executed", f"Executed cron task {job_id}", details=str(res.get('output', ''))[:100])
    return res


# ---------------------------------------------------------
# Universal Terminal WebSocket Handler
# ---------------------------------------------------------
@app.websocket("/ws/terminal/{session_id}")
async def terminal_websocket(websocket: WebSocket, session_id: str):
    cookies = websocket.cookies
    token = cookies.get(COOKIE_NAME) or cookies.get("ag_session")
    if not verify_auth_token(token):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    session = get_or_create_session(session_id)
    
    # Immediately push existing terminal history on connection so user sees the screen with 0ms roundtrip delay!
    initial_buffer = session.get_slice(0)
    if initial_buffer:
        try:
            await websocket.send_bytes(initial_buffer)
        except Exception:
            pass
    try:
        await websocket.send_json({"type": "init", "totalBytes": session.total_bytes})
    except Exception:
        pass

    session.websockets.add(websocket)

    try:
        while True:
            msg = await websocket.receive()
            if "text" in msg and msg["text"]:
                text = msg["text"]
                if text.startswith("{") and text.endswith("}"):
                    try:
                        data = json.loads(text)
                        m_type = data.get("type")
                        if m_type == "input":
                            input_data = data.get("data", "")
                            session.write_input(input_data)
                        elif m_type == "resize":
                            cols = int(data.get("cols", 80))
                            rows = int(data.get("rows", 24))
                            session.resize(cols, rows)
                        elif m_type == "ping":
                            await websocket.send_json({"type": "pong", "totalBytes": session.total_bytes})
                        elif m_type == "sync":
                            client_offset = int(data.get("offset", 0))
                            slice_data = session.get_slice(client_offset)
                            if slice_data:
                                await websocket.send_bytes(slice_data)
                            await websocket.send_json({"type": "sync_ack", "totalBytes": session.total_bytes})
                    except json.JSONDecodeError:
                        session.write_input(text)
                else:
                    session.write_input(text)
            elif "bytes" in msg and msg["bytes"]:
                try:
                    text_data = msg["bytes"].decode("utf-8", errors="replace")
                    session.write_input(text_data)
                except Exception:
                    pass
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        pass
    finally:
        session.websockets.discard(websocket)


# ---------------------------------------------------------
# Remote Access & Cloudflare Quick Tunnel
# ---------------------------------------------------------
@app.get("/api/tunnel/status")
async def api_tunnel_status(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return tunnel_manager.tunnel_instance.get_status()

@app.post("/api/tunnel/start")
async def api_tunnel_start(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    st = tunnel_manager.tunnel_instance.start_tunnel()
    activity.record_activity("tunnel", "remote_access_started", f"Cloudflare tunnel online: {st.get('public_url')}")
    return st

@app.post("/api/tunnel/stop")
async def api_tunnel_stop(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    st = tunnel_manager.tunnel_instance.stop_tunnel()
    activity.record_activity("tunnel", "remote_access_stopped", "Cloudflare tunnel stopped")
    return st


# ---------------------------------------------------------
# Omni-Communicator (Universal Broadcast & Inter-Agent Hub)
# ---------------------------------------------------------
@app.get("/api/communicator/history")
async def api_comm_history(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"history": communicator.load_history()}

@app.get("/api/communicator/presets")
async def api_comm_presets(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"presets": communicator.DEFAULT_PRESETS}

@app.get("/api/communicator/pipelines")
async def api_comm_pipelines(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"pipelines": getattr(communicator, "DEFAULT_PIPELINES", [])}

@app.post("/api/communicator/clear")
async def api_comm_clear(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    communicator.clear_history()
    return {"status": "cleared"}

@app.post("/api/communicator/broadcast")
async def api_comm_broadcast(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    msg = payload.get("message", "").strip()
    target = payload.get("target", "all")
    session_id = payload.get("session_id")
    if not msg:
        raise HTTPException(status_code=400, detail="Empty message")

    targets_dispatched = []
    if target == "all":
        for sid, sess in sessions.items():
            if sess.is_alive:
                sess.write_input(msg + "\n")
                targets_dispatched.append(sess.title)
    elif session_id and session_id in sessions:
        sessions[session_id].write_input(msg + "\n")
        targets_dispatched.append(sessions[session_id].title)
    else:
        matched = False
        for sid, sess in sessions.items():
            if sess.is_alive and (sess.agent_id == target or target in sess.title.lower()):
                sess.write_input(msg + "\n")
                targets_dispatched.append(sess.title)
                matched = True
                break
        if not matched:
            new_sid = f"term-{int(time.time() % 10000)}-{os.urandom(2).hex()}"
            adapter = adapters.get_agent_adapter(target)
            title = adapter.get("name", target.title()) if adapter else target.title()
            launch_cmd = adapter.get("launch_cmd") if adapter else target
            s = get_or_create_session(new_sid, title=title, agent_id=target, initial_cmd=launch_cmd)
            def delayed_write():
                time.sleep(0.5)
                s.write_input(msg + "\n")
            threading.Thread(target=delayed_write, daemon=True).start()
            targets_dispatched.append(title)

    entry = communicator.record_message("User", target, msg)
    activity.record_activity("communicator", "broadcast_sent", f"Broadcast to {target}: {msg[:40]}...", details=f"Dispatched to: {', '.join(targets_dispatched)}")
    return {"status": "ok", "dispatched_to": targets_dispatched, "entry": entry}

@app.post("/api/communicator/hermes_direct")
async def api_comm_hermes_direct(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    prompt = payload.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Empty prompt")
    res = communicator.execute_solo_hermes(prompt)
    entry = communicator.record_message("User", "Solo Hermes", prompt, response=res.get("output"))
    return {"result": res, "entry": entry}


# ---------------------------------------------------------
# Solo Hermes & Model Switcher
# ---------------------------------------------------------
@app.get("/api/hermes/status")
async def api_hermes_status(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return hermes_hub.get_hermes_status()

@app.post("/api/hermes/model")
async def api_hermes_model(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    model_id = payload.get("model_id")
    if not model_id:
        raise HTTPException(status_code=400, detail="Missing model_id")
    res = hermes_hub.set_active_model(model_id)
    activity.record_activity("hermes", "model_switched", f"Switched Hermes model to: {model_id}")
    return res


# ---------------------------------------------------------
# Linked Multi-Terminal Workspace & Parallel Dispatch
# ---------------------------------------------------------
@app.get("/api/workspaces")
async def api_get_workspaces(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"workspaces": workspace_manager.load_workspaces()}

@app.post("/api/workspaces")
async def api_save_workspaces(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    ws_list = payload.get("workspaces", [])
    workspace_manager.save_workspaces(ws_list)
    return {"status": "saved", "count": len(ws_list)}

@app.post("/api/workspaces/parallel_dispatch")
async def api_parallel_dispatch(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    dispatches = payload.get("dispatches", [])
    results = []
    for item in dispatches:
        sid = item.get("session_id")
        prompt = item.get("prompt", "").strip()
        agent = item.get("agent")
        if not prompt:
            continue
        if sid and sid in sessions and sessions[sid].is_alive:
            sessions[sid].write_input(prompt + "\n")
            results.append({"session_id": sid, "title": sessions[sid].title, "status": "sent"})
        elif agent:
            new_sid = f"term-{int(time.time() % 10000)}-{os.urandom(2).hex()}"
            adapter = adapters.get_agent_adapter(agent)
            title = adapter.get("name", agent.title()) if adapter else agent.title()
            launch_cmd = adapter.get("launch_cmd") if adapter else agent
            s = get_or_create_session(new_sid, title=title, agent_id=agent, initial_cmd=launch_cmd)
            def delayed_write(sess=s, p=prompt):
                time.sleep(0.5)
                sess.write_input(p + "\n")
            threading.Thread(target=delayed_write, daemon=True).start()
            results.append({"session_id": new_sid, "title": title, "status": "spawned_and_sent"})

    activity.record_activity("workspace", "parallel_dispatch", f"Parallel dispatched to {len(results)} agents", details=f"Target sessions: {', '.join([r['title'] for r in results])}")
    return {"status": "dispatched", "results": results}

@app.post("/api/workspaces/pipe")
async def api_pipe_terminals(request: Request, payload: Dict[str, Any] = Body(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    src_id = payload.get("source_session_id")
    dst_id = payload.get("target_session_id")
    prefix = payload.get("prompt_prefix", "Analyze output from linked agent session:")
    lines_count = int(payload.get("lines", 40))

    if not src_id or not dst_id:
        raise HTTPException(status_code=400, detail="Missing source or target session ID")

    src_snippet = ""
    src_title = src_id
    if src_id in sessions:
        src_snippet = sessions[src_id].get_recent_snippet(lines_count).strip()
        src_title = sessions[src_id].title

    if not src_snippet:
        raise HTTPException(status_code=400, detail="Source session has no terminal output to pipe")

    pipe_prompt = f"{prefix}\n\n[OUTPUT FROM {src_title.upper()}]:\n{src_snippet}\n"

    if dst_id in sessions and sessions[dst_id].is_alive:
        sessions[dst_id].write_input(pipe_prompt + "\n")
        dst_title = sessions[dst_id].title
    else:
        raise HTTPException(status_code=404, detail="Target session not active")

    activity.record_activity("workspace", "terminals_piped", f"Piped {src_title} -> {dst_title}")
    return {"status": "piped", "source": src_title, "target": dst_title, "bytes_piped": len(src_snippet)}

# ---------------------------------------------------------
# Chat Engine API (ChatGPT-Style Workspace)
# ---------------------------------------------------------
@app.get("/api/chat/providers")
async def api_chat_providers(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    return chat_engine.get_available_providers()


@app.get("/api/chat/threads")
async def api_chat_threads(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    return chat_engine.list_threads()


@app.post("/api/chat/threads")
async def api_create_chat_thread(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    thread = chat_engine.create_thread(
        title=body.get("title", "New Chat"),
        provider_id=body.get("provider_id", "opencode-zen"),
        model_id=body.get("model_id", "opencode/deepseek-v4-flash-free"),
        system_prompt=body.get("system_prompt", ""),
    )
    activity.record_activity("chat", "thread_created", f"Thread: {thread['title']}")
    return thread


@app.get("/api/chat/threads/{thread_id}")
async def api_get_chat_thread(request: Request, thread_id: str):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    thread = chat_engine.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@app.patch("/api/chat/threads/{thread_id}")
async def api_update_chat_thread(request: Request, thread_id: str):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    thread = chat_engine.update_thread(thread_id, body)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@app.delete("/api/chat/threads/{thread_id}")
async def api_delete_chat_thread(request: Request, thread_id: str):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    if not chat_engine.delete_thread(thread_id):
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"status": "deleted"}


@app.get("/api/chat/threads/{thread_id}/messages")
async def api_chat_messages(request: Request, thread_id: str):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    return chat_engine.get_messages(thread_id)


@app.post("/api/chat/threads/{thread_id}/messages")
async def api_add_chat_message(request: Request, thread_id: str):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    msg = chat_engine.add_message(thread_id, body.get("role", "user"), body.get("content", ""))
    return msg


@app.post("/api/chat/stream")
async def api_chat_stream(request: Request):
    """SSE endpoint for streaming chat completions."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    thread_id = body.get("thread_id")
    user_message = body.get("message", "")
    provider_id = body.get("provider_id")
    model_id = body.get("model_id")

    if not thread_id or not user_message:
        raise HTTPException(status_code=400, detail="thread_id and message required")

    thread = chat_engine.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Use thread defaults if not overridden
    provider_id = provider_id or thread.get("provider_id", "opencode-zen")
    model_id = model_id or thread.get("model_id", "opencode/deepseek-v4-flash-free")

    # Save user message
    chat_engine.add_message(thread_id, "user", user_message)

    # Get full conversation history for context
    messages = chat_engine.get_messages(thread_id)

    async def generate():
        full_response = []
        async for chunk in chat_engine.stream_chat_completion(
            provider_id=provider_id,
            model_id=model_id,
            messages=messages,
            temperature=body.get("temperature", 0.7),
            max_tokens=body.get("max_tokens", 4096),
        ):
            # Extract content from SSE chunk for accumulation
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    if data.get("content"):
                        full_response.append(data["content"])
                    if data.get("done"):
                        # Save the complete assistant response
                        complete_text = "".join(full_response)
                        if complete_text:
                            chat_engine.add_message(thread_id, "assistant", complete_text)
                except Exception:
                    pass
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/chat/threads/{thread_id}/retry")
async def api_chat_retry(request: Request, thread_id: str):
    """Remove last assistant message and re-generate."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    messages = chat_engine.get_messages(thread_id)
    # Find and remove last assistant message
    if messages and messages[-1].get("role") == "assistant":
        chat_engine.delete_messages_after(thread_id, messages[-2]["id"] if len(messages) > 1 else messages[-1]["id"])
    return {"status": "ready_for_retry"}


@app.post("/api/chat/threads/{thread_id}/abort")
async def api_chat_abort(request: Request, thread_id: str):
    """Abort signal (for future use with cancellable streams)."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    return {"status": "abort_requested"}


# ---------------------------------------------------------
# Team Leader Harness & GitHub Hub APIs
# ---------------------------------------------------------
@app.post("/api/harness/stream")
async def api_harness_stream(request: Request):
    """Autonomous Team Leader Harness multi-agent execution loop with streaming SSE."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    thread_id = body.get("thread_id")
    message = body.get("message", "")
    provider_id = body.get("provider_id", "opencode-zen")
    model_id = body.get("model_id", "opencode/deepseek-v4-flash-free")
    temperature = body.get("temperature", 0.6)

    if not thread_id or not message:
        raise HTTPException(status_code=400, detail="thread_id and message required")

    return StreamingResponse(
        harness.stream_harness_turn(
            thread_id=thread_id,
            user_message=message,
            provider_id=provider_id,
            model_id=model_id,
            temperature=temperature
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/skills/github/search")
async def api_github_skills_search(request: Request, q: str = "", category: str = "all"):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    return await github_hub.search_github_skills(q, category)


@app.post("/api/skills/github/install")
async def api_github_skills_install(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    skill_id = body.get("skill_id", "")
    target = body.get("target", "all")
    if not skill_id:
        raise HTTPException(status_code=400, detail="skill_id required")
    res = await github_hub.install_github_skill(skill_id, target)
    skills_manager.scan_all_skills(force=True)  # Refresh skills cache
    return res


@app.get("/api/mcp/github/search")
async def api_github_mcp_search(request: Request, q: str = ""):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    return github_hub.search_github_mcps(q)


@app.post("/api/mcp/github/install")
async def api_github_mcp_install(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    body = await request.json()
    mcp_id = body.get("mcp_id", "")
    env = body.get("env", {})
    if not mcp_id:
        raise HTTPException(status_code=400, detail="mcp_id required")
    try:
        res = github_hub.install_github_mcp(mcp_id, env)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------
# Shutdown
# ---------------------------------------------------------
@app.on_event("shutdown")
def shutdown_event():
    tunnel_manager.tunnel_instance.stop_tunnel()
    for session in list(sessions.values()):
        session.close()
    sessions.clear()
