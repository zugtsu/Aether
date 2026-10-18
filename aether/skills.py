import os
import re
import subprocess
import threading

from .memory import split_frontmatter
from .proc import NO_WINDOW, python_exe


class Skill:
    def __init__(self, name, folder):
        self.name = name
        self.folder = folder
        self.description = ""
        self.doc = ""
        self.scripts = {}
        self.commands = []
        self.problems = []
        self.mcp = False
        self.reads = []
        self.ask_first = []

    @property
    def ok(self):
        return not self.problems


STEP_LINE = '"step": "skill"'


def check_skill(folder):
    name = os.path.basename(folder)
    s = Skill(name, folder)
    md = os.path.join(folder, "SKILL.md")
    if not os.path.isfile(md):
        s.problems.append("no SKILL.md")
        return s
    with open(md, encoding="utf-8", errors="replace") as f:
        text = f.read().replace("\r\n", "\n")
    meta, _, body = split_frontmatter(text)
    s.doc = body.strip()
    if not meta:
        s.problems.append("SKILL.md has no frontmatter (--- name/description ---)")
    s.name = meta.get("name") or name
    s.description = meta.get("description", "")
    s.mcp = meta.get("mcp", "").lower() == "true"
    if s.mcp:
        s.reads = [w.strip() for w in meta.get("reads", "").split(",") if w.strip()]
        s.ask_first = [w.strip() for w in meta.get("ask_first", "").split(",") if w.strip()]
    if meta and not s.description:
        s.problems.append("frontmatter has no description")
    sd = os.path.join(folder, "scripts")
    if os.path.isdir(sd):
        for n in sorted(os.listdir(sd)):
            if n.endswith(".py"):
                p = os.path.join(sd, n)
                try:
                    with open(p, encoding="utf-8", errors="replace") as f:
                        compile(f.read(), p, "exec")
                    s.scripts[n] = p
                except SyntaxError as e:
                    s.problems.append(f"scripts/{n} does not compile (line {e.lineno})")
    s.commands = find_commands(text, s.scripts)
    if s.mcp and s.commands:
        s.ask_first = sorted(set(s.ask_first) | (set(s.commands) - set(s.reads)))
    if not s.scripts and not any("compile" in p for p in s.problems):
        s.problems.append("no scripts/*.py to run")
    elif s.scripts and not any(n in text for n in s.scripts) and STEP_LINE not in text:
        s.problems.append("SKILL.md never shows how to call it (its step, or its script)")
    return s


def find_commands(doc, scripts):
    shown = set(re.findall(r'"command":\s*"([a-z][a-z0-9_-]*)"', doc))
    shown |= set(re.findall(r'[\w-]+\.py"?[ \t]+([a-z][a-z0-9_-]*)\b', doc))
    src = ""
    for p in scripts.values():
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                src += f.read()
        except OSError:
            pass
    real = sorted(c for c in shown if re.search(r"""['"]%s['"]""" % re.escape(c), src))
    return real if len(real) >= 2 else []


def discover(memory_root):
    live, rejected = {}, {}
    root = os.path.join(memory_root, "skills")
    if not os.path.isdir(root):
        return live, rejected
    for n in sorted(os.listdir(root)):
        folder = os.path.join(root, n)
        if not os.path.isdir(folder) or n.startswith((".", "_")) or n == "__pycache__":
            continue
        s = check_skill(folder)
        (live if s.ok else rejected)[s.name] = s
    return live, rejected


class Cancelled(Exception):
    pass


def _kill_tree(proc):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
        else:
            proc.kill()
        proc.wait(5)
    except Exception:
        pass
    try:
        proc.stdout.close()
    except Exception:
        pass


def clean_args(skill, args):
    out = [str(a) for a in (args or [])]
    while out and (out[0].lower() in ("python", "python3", "py") or out[0].lower().endswith(".py")
                   or "$MEMORY_DIR" in out[0]):
        out.pop(0)
    return [a[1:-1] if len(a) > 1 and a[0] == a[-1] and a[0] in "'\"" else a for a in out]


def run(skill, script, args, memory_root, timeout=90, max_chars=6000, cancel=None, extra_env=None):
    if script not in skill.scripts:
        if len(skill.scripts) == 1:
            script = next(iter(skill.scripts))
        else:
            return 2, f"{skill.name} has several scripts ({', '.join(skill.scripts)}); pick one."
    env = dict(os.environ)
    env["MEMORY_DIR"] = memory_root
    env["PYTHONIOENCODING"] = "utf-8"
    env["AETHER"] = "1"
    env.update(extra_env or {})
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000
    proc = subprocess.Popen([python_exe(), skill.scripts[script], *args], cwd=memory_root, env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    chunks = []

    def pump():
        for b in iter(lambda: proc.stdout.read(4096), b""):
            chunks.append(b)

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    waited = 0.0
    while True:
        try:
            proc.wait(timeout=0.2)
            break
        except subprocess.TimeoutExpired:
            waited += 0.2
            if cancel is not None and cancel.is_set():
                _kill_tree(proc)
                raise Cancelled()
            if waited >= timeout:
                _kill_tree(proc)
                t.join(1)
                return 124, f"{skill.name} took longer than {timeout}s and was stopped."
    t.join(2)
    try:
        proc.stdout.close()
    except Exception:
        pass
    out = b"".join(chunks).decode("utf-8", errors="replace").strip()
    if len(out) > max_chars:
        out = out[:max_chars] + f"\n... ({len(out) - max_chars} more characters cut)"
    return proc.returncode, out or "(no output)"


def bad_args(code, out):
    if code != 2 or not re.search(r"^usage: ", out or "", re.M):
        return ""
    m = re.search(r": (error: .+)$", out, re.M)
    return m.group(1).strip() if m else "error: those arguments don't fit"


def usage_lines(skill):
    lines = [ln.strip() for ln in skill.doc.splitlines() if STEP_LINE in ln]
    if not lines:
        lines = [ln.strip() for ln in re.findall(r"^\s*python .*$", skill.doc, re.M)]
    return "\n".join(lines[:8])
