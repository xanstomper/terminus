import os
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

IGNORED_SUBSTRINGS = [
    '/.wine', '/.steam', '/.cache', '/node_modules', '/.jcode/scratch',
    '/.codex/.tmp', '/.themes', '/.local/share', '/.mimocode',
    '/citron-sxs/build', '/.cargo', '/.rustup', '/venv', '/.venv', '/.venvs'
]

_projects_cache: List[Dict[str, Any]] = []
_cache_time: float = 0
PROJECT_AGENTS_CACHE_FILE = Path("/home/jewboy420/terminus/project_agents.json")


def get_last_project_agents() -> Dict[str, str]:
    if PROJECT_AGENTS_CACHE_FILE.exists():
        try:
            import json
            return json.loads(PROJECT_AGENTS_CACHE_FILE.read_text())
        except Exception:
            return {}
    return {}


def set_last_project_agent(proj_path: str, agent_id: str):
    data = get_last_project_agents()
    data[proj_path] = agent_id
    try:
        import json
        PROJECT_AGENTS_CACHE_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def scan_projects(root_dir: str = "/home/jewboy420", force: bool = False) -> List[Dict[str, Any]]:
    global _projects_cache, _cache_time
    if not force and time.time() - _cache_time < 45 and _projects_cache:
        return _projects_cache

    projects = []
    agent_map = get_last_project_agents()

    try:
        cmd = ['find', root_dir, '-maxdepth', '5', '-name', '.git', '-type', 'd']
        out = subprocess.check_output(cmd, text=True, timeout=8)
        
        for line in out.splitlines():
            line = line.strip()
            if not line or any(ig in line for ig in IGNORED_SUBSTRINGS):
                continue
            
            proj_path = os.path.dirname(line)
            if proj_path == root_dir or proj_path == os.path.join(root_dir, ".git"):
                continue

            info = _inspect_project(Path(proj_path), root_dir, agent_map)
            if info:
                projects.append(info)
    except Exception:
        pass

    # Sort by most recently modified by default
    projects.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    _projects_cache = projects
    _cache_time = time.time()
    return _projects_cache


def _inspect_project(path: Path, root_dir: str, agent_map: Dict[str, str]) -> Optional[Dict[str, Any]]:
    try:
        mtime = path.stat().st_mtime
        branch = "main"
        dirty = False
        modified_count = 0
        
        # Git branch & status
        try:
            head_file = path / ".git" / "HEAD"
            if head_file.exists():
                head_content = head_file.read_text().strip()
                if head_content.startswith("ref: refs/heads/"):
                    branch = head_content.replace("ref: refs/heads/", "")
                else:
                    branch = head_content[:7]
        except Exception:
            pass

        try:
            status_out = subprocess.run(
                ["git", "-C", str(path), "status", "--porcelain"],
                capture_output=True, text=True, timeout=1
            )
            if status_out.returncode == 0 and status_out.stdout.strip():
                dirty = True
                modified_count = len(status_out.stdout.strip().splitlines())
        except Exception:
            pass

        # Detect primary language / framework
        lang = "General"
        if (path / "package.json").exists():
            lang = "TypeScript/Node"
        elif (path / "go.mod").exists():
            lang = "Go"
        elif (path / "Cargo.toml").exists():
            lang = "Rust"
        elif (path / "pyproject.toml").exists() or (path / "requirements.txt").exists() or any(path.glob("*.py")):
            lang = "Python"
        elif (path / "project.godot").exists():
            lang = "Godot"
        elif (path / "build.zig").exists():
            lang = "Zig"
        elif (path / "CMakeLists.txt").exists() or any(path.glob("*.cpp")) or any(path.glob("*.c")):
            lang = "C/C++"

        str_path = str(path)
        rel_path = str_path.replace(root_dir + "/", "")
        last_agent = agent_map.get(str_path, None)

        # Pretty time format
        diff_sec = time.time() - mtime
        if diff_sec < 3600:
            time_str = f"{int(diff_sec // 60)}m ago"
        elif diff_sec < 86400:
            time_str = f"{int(diff_sec // 3600)}h ago"
        elif diff_sec < 86400 * 7:
            time_str = f"{int(diff_sec // 86400)}d ago"
        else:
            time_str = time.strftime("%b %d", time.localtime(mtime))

        return {
            "name": path.name,
            "path": str_path,
            "rel_path": rel_path,
            "branch": branch,
            "dirty": dirty,
            "modified_count": modified_count,
            "lang": lang,
            "mtime": mtime,
            "last_modified": time_str,
            "last_agent": last_agent
        }
    except Exception:
        return None
