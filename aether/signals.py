import datetime as dt
import os
import re
import subprocess

from .proc import NO_WINDOW

LIBRARY_EXT = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".html", ".htm", ".pdf"}
READ_LOG = "reference/research/files-read.md"
JOURNAL_DATE = re.compile(r"^\s*-\s*(\d{4}-\d{2}-\d{2})(?: (\d{1,2}:\d{2} [AP]M))?:")
WORKSPACE_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv"}
WORKSPACE_MAX = 2000
SLACK = dt.timedelta(milliseconds=10)


def ago(when, now):
    if when is None:
        return "never"
    mins = int((now - when).total_seconds() // 60)
    if mins < 2:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    if mins < 48 * 60:
        return f"{mins // 60} h ago"
    return f"{mins // (24 * 60)} days ago"


def quoted(name, most=60):
    n = " ".join(str(name).replace('"', "'").split())
    return '"' + (n if len(n) <= most else n[:most - 3] + "...") + '"'


def _arrived(path):
    try:
        return dt.datetime.fromtimestamp(max(os.path.getctime(path), os.path.getmtime(path)))
    except OSError:
        return None


def library(lib_dir, mem_root, since=None):
    files = []
    for root, _, names in os.walk(lib_dir or ""):
        for n in names:
            if not n.startswith(".") and n != "README.txt" and os.path.splitext(n)[1].lower() in LIBRARY_EXT:
                p = os.path.join(root, n)
                files.append((os.path.relpath(p, lib_dir).replace("\\", "/"), _arrived(p)))
    try:
        with open(os.path.join(mem_root, *READ_LOG.split("/")), encoding="utf-8") as f:
            read = set(re.findall(r"^- \d{4}-\d{2}-\d{2}: (.+)$", f.read(), re.M))
    except OSError:
        read = set()
    new = sorted((x for x in files if since and x[1] and x[1] > since + SLACK), key=lambda x: x[1], reverse=True)
    return {"total": len(files), "unread": sum(1 for name, _ in files if name not in read), "new": [n for n, _ in new],
            "read": read}


def workspace(ws_dir, since=None):
    newest, count, changed = None, 0, 0
    for root, dirs, names in os.walk(ws_dir or ""):
        dirs[:] = [d for d in dirs if d not in WORKSPACE_SKIP and not d.startswith(".")]
        for n in names:
            if n.startswith("."):
                continue
            count += 1
            p = os.path.join(root, n)
            try:
                t = dt.datetime.fromtimestamp(os.path.getmtime(p))
            except OSError:
                continue
            changed += 1 if since and t > since + SLACK else 0
            if newest is None or t > newest[1]:
                newest = (os.path.relpath(p, ws_dir).replace("\\", "/"), t)
            if count >= WORKSPACE_MAX:
                break
        if count >= WORKSPACE_MAX:
            break
    return {"files": count, "newest": newest, "changed": changed}


def journal_last(body):
    for ln in (body or "").splitlines():
        m = JOURNAL_DATE.match(ln)
        if m:
            day = dt.date.fromisoformat(m.group(1))
            t = dt.datetime.strptime(m.group(2), "%I:%M %p").time() if m.group(2) else dt.time(12, 0)
            return dt.datetime.combine(day, t)
    return None


def notebook_last(mem_root):
    try:
        out = subprocess.run(["git", "-C", mem_root, "log", "-1", "--format=%cI", "--", "reference/research",
                              ":(exclude)" + READ_LOG], capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW).stdout.strip()
        return dt.datetime.fromisoformat(out).replace(tzinfo=None) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


DOORS = (("journal", ("journal",)), ("library", ("research", "save_research", "library", "pdf")),
         ("tasks", ("task",)), ("workspace", ("shell",)), ("pictures", ("make_image", "gallery")),
         ("memory", ("memory_add", "memory_replace", "memory_remove", "memory_create", "memory_delete")))


def pattern(life_log, most=12):
    wakes = [e for e in life_log or [] if str(e.get("what", "")).startswith("woke")][-most:]
    if not wakes:
        return ""
    counts = {name: 0 for name, _ in DOORS}
    quiet = 0
    for e in wakes:
        did = [s.strip() for s in str(e.get("detail", "")).split(";")[0].split(",")]
        hit = False
        for name, kinds in DOORS:
            if any(s in kinds for s in did):
                counts[name] += 1
                hit = True
        quiet += 0 if hit or any(s and s != "nothing" for s in did) else 1
    shown = [f"{name} {n}" for name, n in counts.items() if n] + ([f"nothing at all {quiet}"] if quiet else [])
    return f"Your last {len(wakes)} wake-ups, by what you did in them: " + (", ".join(shown) or "other steps only") + "."
