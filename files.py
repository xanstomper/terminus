import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

ALLOWED_ROOT = Path("/home/jewboy420").resolve()

def resolve_path(relative_path: str = "") -> Path:
    if not relative_path or relative_path == "~":
        return ALLOWED_ROOT
    p = Path(relative_path)
    if not p.is_absolute():
        p = (ALLOWED_ROOT / relative_path).resolve()
    else:
        p = p.resolve()
    if not str(p).startswith(str(ALLOWED_ROOT)):
        return ALLOWED_ROOT
    return p


def list_directory(target_path: str = "", query: str = "") -> Dict[str, Any]:
    resolved = resolve_path(target_path)
    if not resolved.exists():
        return {"error": "Path not found", "path": str(resolved)}
    if not resolved.is_dir():
        return {"error": "Not a directory", "path": str(resolved)}

    entries = []
    q_lower = query.lower().strip() if query else ""

    try:
        for item in resolved.iterdir():
            try:
                if q_lower and q_lower not in item.name.lower():
                    continue

                is_dir = item.is_dir()
                stat = item.stat()
                mtime = stat.st_mtime
                size = stat.st_size if not is_dir else 0
                
                ext = item.suffix.lower().lstrip(".")
                kind = "dir" if is_dir else "file"
                if not is_dir:
                    if ext in ["py", "js", "ts", "jsx", "tsx", "go", "rs", "c", "cpp", "h", "zig", "sh", "bash"]:
                        kind = "code"
                    elif ext in ["json", "yaml", "yml", "toml", "xml", "ini", "env"]:
                        kind = "config"
                    elif ext in ["md", "txt", "rst", "log"]:
                        kind = "doc"
                    elif ext in ["png", "jpg", "jpeg", "gif", "svg", "webp"]:
                        kind = "image"

                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": is_dir,
                    "kind": kind,
                    "size": size,
                    "ext": ext,
                    "mtime": mtime,
                    "modified": time.strftime("%b %d %H:%M", time.localtime(mtime))
                })
            except (PermissionError, FileNotFoundError):
                continue
    except PermissionError:
        return {"error": "Permission denied", "path": str(resolved)}

    # Folders first, then alphabetical
    entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    
    # Breadcrumbs
    rel = resolved.relative_to(ALLOWED_ROOT)
    breadcrumbs = [{"name": "~", "path": str(ALLOWED_ROOT)}]
    curr = ALLOWED_ROOT
    for part in rel.parts:
        curr = curr / part
        breadcrumbs.append({"name": part, "path": str(curr)})

    return {
        "current_path": str(resolved),
        "parent_path": str(resolved.parent) if resolved != ALLOWED_ROOT else None,
        "breadcrumbs": breadcrumbs,
        "total_count": len(entries),
        "entries": entries[:1000]
    }


def read_file_content(target_path: str, max_bytes: int = 1024 * 1024) -> Dict[str, Any]:
    resolved = resolve_path(target_path)
    if not resolved.exists() or not resolved.is_file():
        return {"error": "File not found"}

    try:
        size = resolved.stat().st_size
        if size > max_bytes:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_bytes)
            return {
                "name": resolved.name,
                "path": str(resolved),
                "size": size,
                "truncated": True,
                "content": content
            }
        else:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {
                "name": resolved.name,
                "path": str(resolved),
                "size": size,
                "truncated": False,
                "content": content
            }
    except Exception as e:
        return {"error": str(e)}


def save_file_content(target_path: str, content: str) -> Dict[str, Any]:
    resolved = resolve_path(target_path)
    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "path": str(resolved)}
    except Exception as e:
        return {"success": False, "error": str(e)}
