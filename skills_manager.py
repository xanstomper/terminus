import os
import re
import time
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

_SKILLS_CACHE: Optional[List[Dict[str, Any]]] = None
_CACHE_TIME: float = 0
_CACHE_TTL: float = 30.0  # 30 seconds

CATEGORY_MAP = {
    "software-development": "Software Engineering",
    "systems": "Systems & Low-Level",
    "cpu-emulator-construction": "Systems & Low-Level",
    "gamedev": "Game Development",
    "autonomous-ai-agents": "Autonomous Agents",
    "computer-use": "Autonomous Agents",
    "browser-automation-bridge": "Web & Browser Automation",
    "data-science": "AI & Data Science",
    "mlops": "AI & Data Science",
    "mochi": "Autonomous Agents",
    "mochi-development": "Autonomous Agents",
    "osint": "Security & Intelligence",
    "linux": "Systems & Low-Level",
    "apple": "Mobile & Cross-Platform",
    "smart-home": "IoT & Hardware",
    "iot": "IoT & Hardware",
    "creative": "Creative & Generative",
    "media": "Creative & Generative",
    "social-media": "Communication & Social",
    "email": "Communication & Social",
    "productivity": "Productivity & Workflow",
    "note-taking": "Productivity & Workflow",
    "research": "Research & Analysis",
    "github": "Developer Tools",
    "agy-customizations": "Antigravity & DeepMind",
    "antigravity_guide": "Antigravity & DeepMind",
    "generative_ui": "Antigravity & DeepMind",
    "migrate-workflows": "Antigravity & DeepMind",
    "permissioned-github": "Antigravity & DeepMind",
    "tui-development": "UI & Terminal Design",
    "xbox-dev-mode-sideloading": "Game Development",
    "papaya": "Game Development"
}

def clean_value(val: str) -> str:
    return val.strip().strip('"\'')

def parse_skill_md(skill_md: Path, origin: str) -> Dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    skill_name = skill_md.parent.name
    desc = ""
    category = "General"
    tags: List[str] = []
    version = "1.0.0"
    author = f"{origin} Agent"
    platforms = ["linux"]
    related: List[str] = []

    # Parse YAML frontmatter if available
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            in_desc_block = False
            desc_lines = []

            for line in fm_text.splitlines():
                stripped = line.strip()
                if stripped.startswith("name:"):
                    in_desc_block = False
                    skill_name = clean_value(stripped.split(":", 1)[1])
                elif stripped.startswith("version:"):
                    in_desc_block = False
                    version = clean_value(stripped.split(":", 1)[1])
                elif stripped.startswith("author:"):
                    in_desc_block = False
                    author = clean_value(stripped.split(":", 1)[1])
                elif stripped.startswith("tags:"):
                    in_desc_block = False
                    raw_tags = clean_value(stripped.split(":", 1)[1]).strip("[]")
                    tags = [clean_value(t) for t in raw_tags.split(",") if t.strip()]
                elif stripped.startswith("platforms:"):
                    in_desc_block = False
                    raw_p = clean_value(stripped.split(":", 1)[1]).strip("[]")
                    platforms = [clean_value(p) for p in raw_p.split(",") if p.strip()]
                elif stripped.startswith("related_skills:"):
                    in_desc_block = False
                    raw_r = clean_value(stripped.split(":", 1)[1]).strip("[]")
                    related = [clean_value(r) for r in raw_r.split(",") if r.strip()]
                elif stripped.startswith("description:"):
                    val = stripped.split(":", 1)[1].strip()
                    if val in [">", ">-", "|", "|-"]:
                        in_desc_block = True
                    else:
                        in_desc_block = False
                        desc = clean_value(val)
                elif in_desc_block:
                    if line.startswith("  ") or line.startswith("\t"):
                        desc_lines.append(stripped)
                    else:
                        in_desc_block = False

            if desc_lines and not desc:
                desc = " ".join(desc_lines)

    # Fallback to first non-empty markdown paragraph if description was not in frontmatter
    if not desc:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                desc = line[:240]
                break

    # Determine intelligent category
    parent_cat_name = skill_md.parent.parent.name.lower()
    folder_name = skill_md.parent.name.lower()

    if folder_name in CATEGORY_MAP:
        category = CATEGORY_MAP[folder_name]
    elif parent_cat_name in CATEGORY_MAP:
        category = CATEGORY_MAP[parent_cat_name]
    elif parent_cat_name not in ["skills", "builtin", "plugins", ".gemini", ".hermes"]:
        category = parent_cat_name.replace("-", " ").title()
    else:
        category = "Core Capabilities"

    # Identify scripts and references
    scripts = []
    scripts_dir = skill_md.parent / "scripts"
    if scripts_dir.exists() and scripts_dir.is_dir():
        for s in sorted(scripts_dir.iterdir()):
            if s.is_file() and not s.name.startswith("."):
                scripts.append({
                    "name": s.name,
                    "path": str(s),
                    "size": s.stat().st_size,
                    "is_executable": os.access(s, os.X_OK) or s.suffix in [".sh", ".py"]
                })

    references = []
    ref_dir = skill_md.parent / "references"
    if ref_dir.exists() and ref_dir.is_dir():
        for r in sorted(ref_dir.iterdir()):
            if r.is_file() and not r.name.startswith("."):
                references.append({
                    "name": r.name,
                    "path": str(r),
                    "size": r.stat().st_size
                })

    skill_id = f"{origin.lower()}:{skill_name}"

    return {
        "id": skill_id,
        "name": skill_name,
        "title": skill_name.replace("-", " ").replace("_", " ").title(),
        "category": category,
        "origin": origin,
        "description": desc or "Universal AI developer workflow and capability module.",
        "version": version,
        "author": author,
        "tags": tags,
        "platforms": platforms,
        "related_skills": related,
        "path": str(skill_md),
        "dir_path": str(skill_md.parent),
        "scripts": scripts,
        "references": references,
        "has_scripts": len(scripts) > 0,
        "has_references": len(references) > 0
    }


def scan_all_skills(force: bool = False) -> List[Dict[str, Any]]:
    global _SKILLS_CACHE, _CACHE_TIME
    now = time.time()
    if not force and _SKILLS_CACHE is not None and (now - _CACHE_TIME) < _CACHE_TTL:
        return _SKILLS_CACHE

    skills_list: List[Dict[str, Any]] = []
    seen_ids = set()

    search_roots = [
        (Path.home() / ".hermes" / "skills", "Hermes"),
        (Path.home() / ".gemini" / "antigravity-cli" / "builtin" / "skills", "Antigravity"),
        (Path.home() / ".gemini" / "antigravity-cli" / "skills", "Antigravity"),
        (Path.home() / ".gemini" / "skills", "Antigravity"),
        (Path.home() / ".claude" / "plugins", "Claude Code"),
        (Path.home() / ".claude" / "skills", "Claude Code"),
    ]

    for root_dir, origin in search_roots:
        if not root_dir.exists():
            continue
        try:
            for skill_file in root_dir.glob("**/SKILL.md"):
                # Avoid backup / archive tarballs
                if ".curator_backups" in str(skill_file) or ".archive" in str(skill_file):
                    continue
                try:
                    meta = parse_skill_md(skill_file, origin)
                    if meta["id"] not in seen_ids:
                        seen_ids.add(meta["id"])
                        skills_list.append(meta)
                except Exception:
                    pass
        except Exception:
            pass

    # Sort alphabetically by category and then by title
    skills_list.sort(key=lambda s: (s["category"], s["title"]))
    _SKILLS_CACHE = skills_list
    _CACHE_TIME = now
    return skills_list


def get_skills_tree() -> Dict[str, Any]:
    skills = scan_all_skills()
    tree: Dict[str, List[Dict[str, Any]]] = {}
    origins: Dict[str, int] = {}

    for s in skills:
        cat = s["category"]
        if cat not in tree:
            tree[cat] = []
        tree[cat].append(s)

        orig = s["origin"]
        origins[orig] = origins.get(orig, 0) + 1

    return {
        "total_skills": len(skills),
        "total_categories": len(tree),
        "origins": origins,
        "tree": tree,
        "skills": skills
    }


def get_skill_details(skill_id: str) -> Optional[Dict[str, Any]]:
    skills = scan_all_skills()
    target = None
    for s in skills:
        if s["id"] == skill_id:
            target = dict(s)
            break

    if not target:
        return None

    # Read markdown content
    path = Path(target["path"])
    if path.exists():
        target["content"] = path.read_text(encoding="utf-8", errors="ignore")
    else:
        target["content"] = "(Skill file not found on filesystem)"

    return target


def inject_skill_into_prompt(skill_id: str) -> str:
    details = get_skill_details(skill_id)
    if not details:
        raise ValueError("Skill not found")

    content = details.get("content", "")
    injection = (
        f"\n\n# === [TERMINUS UNIVERSAL SKILL ACTIVATION: {details['title']} ({details['origin']})] ===\n"
        f"You are equipped with the following specialized workflow instructions. Follow them precisely:\n\n"
        f"{content}\n"
        f"# === [END OF SKILL SPECIFICATION] ===\n\n"
    )
    return injection


def bridge_skill(skill_id: str, target_agent: str, custom_dest: Optional[str] = None) -> Dict[str, Any]:
    details = get_skill_details(skill_id)
    if not details:
        return {"success": False, "error": "Skill not found"}

    src_dir = Path(details["dir_path"])
    skill_name = details["name"]

    if custom_dest:
        dest_dir = Path(custom_dest) / skill_name
    elif target_agent.lower() in ["antigravity", "agy"]:
        dest_dir = Path.home() / ".gemini" / "antigravity-cli" / "skills" / skill_name
    elif target_agent.lower() in ["hermes"]:
        dest_dir = Path.home() / ".hermes" / "skills" / skill_name
    elif target_agent.lower() in ["claude"]:
        dest_dir = Path.home() / ".claude" / "skills" / skill_name
    else:
        dest_dir = Path.home() / ".terminus" / "shared_skills" / skill_name

    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)

    shutil.copytree(src_dir, dest_dir)
    scan_all_skills(force=True)

    return {
        "success": True,
        "message": f"Successfully bridged {details['title']} to {target_agent.capitalize()}",
        "destination": str(dest_dir),
        "target_agent": target_agent
    }
