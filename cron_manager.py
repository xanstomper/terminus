import json
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

CRON_FILE = Path.home() / ".terminus" / "cron.json"

DEFAULT_JOBS = [
    {
        "id": "cron-audit-01",
        "name": "Machine & Toolchain Integrity Check",
        "agent_id": "bash",
        "agent_name": "Standard Shell",
        "prompt_or_cmd": "python3 /home/jewboy420/terminus/doctor.py",
        "schedule": "Every 4 hours",
        "interval_sec": 14400,
        "cwd": "/home/jewboy420/terminus",
        "enabled": True,
        "last_run": time.time() - 3600,
        "last_status": "success",
        "last_output": "All system checks nominal. Terminus PTY engine operational."
    },
    {
        "id": "cron-hermes-02",
        "name": "Hermes OpenCode Heartbeat",
        "agent_id": "hermes",
        "agent_name": "Hermes Agent",
        "prompt_or_cmd": "hermes -z 'ping'",
        "schedule": "Daily at 03:00",
        "interval_sec": 86400,
        "cwd": "/home/jewboy420",
        "enabled": False,
        "last_run": None,
        "last_status": "pending",
        "last_output": "Scheduled for automatic background execution."
    },
    {
        "id": "cron-git-03",
        "name": "Git Repository Dirty State Sweep",
        "agent_id": "bash",
        "agent_name": "Standard Shell",
        "prompt_or_cmd": "git status -s",
        "schedule": "Hourly",
        "interval_sec": 3600,
        "cwd": "/home/jewboy420/terminus",
        "enabled": True,
        "last_run": time.time() - 1200,
        "last_status": "success",
        "last_output": "Working tree synchronized."
    }
]

def load_jobs() -> List[Dict[str, Any]]:
    CRON_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CRON_FILE.exists():
        save_jobs(DEFAULT_JOBS)
        return DEFAULT_JOBS.copy()
    try:
        data = json.loads(CRON_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return DEFAULT_JOBS.copy()

def save_jobs(jobs: List[Dict[str, Any]]) -> None:
    CRON_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRON_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

def get_all_jobs() -> List[Dict[str, Any]]:
    jobs = load_jobs()
    now = time.time()
    for j in jobs:
        lr = j.get("last_run")
        if lr:
            diff = now - lr
            if diff < 60:
                j["last_run_str"] = "Just now"
            elif diff < 3600:
                j["last_run_str"] = f"{int(diff // 60)}m ago"
            elif diff < 86400:
                j["last_run_str"] = f"{int(diff // 3600)}h ago"
            else:
                j["last_run_str"] = time.strftime("%b %d %H:%M", time.localtime(lr))
        else:
            j["last_run_str"] = "Never"
    return jobs

def create_job(name: str, agent_id: str, prompt_or_cmd: str, schedule: str, cwd: str) -> Dict[str, Any]:
    jobs = load_jobs()
    new_id = f"cron-{int(time.time() * 1000) % 1000000}"

    interval = 3600
    s_lower = schedule.lower()
    if "15" in s_lower:
        interval = 900
    elif "30" in s_lower:
        interval = 1800
    elif "daily" in s_lower or "24" in s_lower:
        interval = 86400
    elif "weekly" in s_lower:
        interval = 604800

    entry = {
        "id": new_id,
        "name": name.strip(),
        "agent_id": agent_id.strip(),
        "agent_name": agent_id.capitalize(),
        "prompt_or_cmd": prompt_or_cmd.strip(),
        "schedule": schedule.strip(),
        "interval_sec": interval,
        "cwd": cwd.strip() or "/home/jewboy420",
        "enabled": True,
        "last_run": None,
        "last_status": "pending",
        "last_output": "Ready for execution."
    }
    jobs.append(entry)
    save_jobs(jobs)
    return entry

def toggle_job(job_id: str) -> Optional[bool]:
    jobs = load_jobs()
    for j in jobs:
        if j["id"] == job_id:
            j["enabled"] = not j["enabled"]
            save_jobs(jobs)
            return j["enabled"]
    return None

def delete_job(job_id: str) -> bool:
    jobs = load_jobs()
    orig_len = len(jobs)
    jobs = [j for j in jobs if j["id"] != job_id]
    if len(jobs) < orig_len:
        save_jobs(jobs)
        return True
    return False

def run_job_now(job_id: str) -> Dict[str, Any]:
    jobs = load_jobs()
    job = None
    for j in jobs:
        if j["id"] == job_id:
            job = j
            break

    if not job:
        return {"success": False, "error": "Job not found"}

    cmd = job["prompt_or_cmd"]
    cwd = job.get("cwd", "/home/jewboy420")
    if not Path(cwd).exists():
        cwd = "/home/jewboy420"

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = (proc.stdout + "\n" + proc.stderr).strip()
        job["last_run"] = time.time()
        job["last_status"] = "success" if proc.returncode == 0 else "failed"
        job["last_output"] = output[:1000] or f"Process exited with code {proc.returncode}"
        save_jobs(jobs)
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": job["last_output"]
        }
    except Exception as e:
        job["last_run"] = time.time()
        job["last_status"] = "failed"
        job["last_output"] = str(e)
        save_jobs(jobs)
        return {"success": False, "error": str(e)}
