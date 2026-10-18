import difflib
import re
import subprocess

from .digest import AETHER_DID
from .memory import DATE_PREFIX
from .names import USER, is_user_author
from .proc import NO_WINDOW

SKIP = ("life", "skills", ".obsidian")
RECORDS = ("reference/facts-history.md", "reference/lessons-history.md", "reference/lessons-archive.md")
MOST_ITEMS = 16
MOST_CHARS = 3500
LINE_MAX = 180
STOP = set("""a an and or the of to in on at for from by with about into over than then that this these those it its is
was were be been am are do did does done have has had i me my mine you your yours he him his she her hers we our they
them their what when where which who why how did learn learned learnt know knew remember first time ever back notes
note memory memories said say says tell told user user's companion something thing things""".split())
STOP |= set("""check checking checked look looking looked see seeing find finding found search searching history
histories entry entries record records recorded add added adding change changed changes update updates updated today
today's tonight before after since earlier now file files line lines written wrote write got get own""".split())
ABOUT_MAX = 80
FILE_IN = re.compile(r"[\w/.-]*[\w-]+\.md\b")
SKILL_LINE = ("when you first wrote something down, what one of your files said before, how you've changed lately: "
              "your memory's history (what was SAID in chats is recall). Use your look_back step (read_skill look_back "
              "shows how)")
SKILL_DOC = """# Look back (built into Aether: you use it with your `look_back` step)

Your memory is kept in git: every line you, Aether or {USER} ever added, changed or took out is still there, with its
date. Your look_back step reads that history for you and hands you plain dated lines.

Use it when {USER} asks when you learned something ("when did I first tell you about my bike?"), what your notes said
back then ("what did you think of the game's name before?"), or when you want to see how you've changed.
What was SAID in a chat is your recall or read_chat step; this is what was KEPT in your memory files.

## How: one look_back step
- about: a word or two to look for, not a sentence (a name, a thing: "bike", "Starling"), or one of your memory files
  ("system/me.md") to see its newest changes

As you fill it in:
```
{"step": "look_back", "about": "bike"}
```
```
{"step": "look_back", "about": "system/me.md"}
```

## Then
Each line says the day, who did it (you, {USER}, or Aether's nightly jobs), the file, and what happened: added,
changed (was -> now), took out, or moved. The oldest line is when it first reached your memory. A line that was
taken out isn't true anymore unless something newer says so.
"""


def _git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=30, creationflags=NO_WINDOW).stdout


def _clean(line):
    s = DATE_PREFIX.sub("", re.sub(r"^\s*[-*]\s+", "", line)).strip()
    return s if len(s) <= LINE_MAX else s[:LINE_MAX - 3].rstrip() + "..."


def _who(author, subject):
    if is_user_author(author):
        return USER
    return "Aether" if AETHER_DID.match(subject) else "you"


def _noise(line):
    s = line.strip()
    return not s or s == "---" or s.startswith("#") or re.match(r"^(?:description|read_only|name):", s)


def changes(root, path=None):
    where = [path] if path else ["."] + [f":(exclude){d}" for d in SKIP + RECORDS]
    raw = _git(root, "log", "--reverse", "--date=short", "--format=%x1e%h%x1f%ad%x1f%an%x1f%s", "-p", "--unified=0",
               "--no-color", "--no-renames", "--no-ext-diff", "--", *where)
    out = []
    for block in raw.split("\x1e")[1:]:
        head, _, body = block.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 4:
            continue
        _, date, author, subject = parts[:4]
        who = _who(author, subject)
        per_file, cur = {}, None
        for ln in body.splitlines():
            if ln.startswith("diff --git "):
                m = re.match(r"diff --git a/(.+?) b/(.+)$", ln)
                cur = m.group(2) if m else None
                continue
            if ln.startswith(("---", "+++", "@@", "index ", "new file", "deleted file", "similarity", "\\")):
                continue
            if cur and ln[:1] in "+-" and not _noise(ln[1:]):
                per_file.setdefault(cur, {"+": [], "-": []})[ln[0]].append(ln[1:])
        arrived = {t.strip(): f for f, d in per_file.items() for t in d["+"]}
        for f, d in per_file.items():
            for t in list(d["-"]):
                to = arrived.get(t.strip())
                if to and to != f:
                    out.append({"date": date, "who": who, "file": f"{f} -> {to}", "kind": "moved", "text": _clean(t)})
                    del arrived[t.strip()]
                    d["-"].remove(t)
                    per_file[to]["+"] = [x for x in per_file[to]["+"] if x.strip() != t.strip()]
        for f, d in per_file.items():
            added = list(d["+"])
            for t in d["-"]:
                near = difflib.get_close_matches(t, added, n=1, cutoff=0.5)
                if near:
                    added.remove(near[0])
                    out.append({"date": date, "who": who, "file": f, "kind": "changed", "text": _clean(near[0]),
                                "old": _clean(t)})
                else:
                    out.append({"date": date, "who": who, "file": f, "kind": "took out", "text": _clean(t)})
            out += [{"date": date, "who": who, "file": f, "kind": "added", "text": _clean(t)} for t in added]
    return out


def merged(found):
    out = []
    for c in found:
        if out and all(out[-1].get(k) == c.get(k) for k in ("date", "who", "file", "kind", "text", "old")):
            out[-1]["times"] = out[-1].get("times", 1) + 1
        else:
            out.append(dict(c))
    return out


def show(c):
    old = c.get("old", "")
    old = old if len(old) <= 100 else old[:97].rstrip() + "..."
    what = f"{old} -> now: {c['text']}" if c["kind"] == "changed" else c["text"]
    times = f" (x{c['times']})" if c.get("times", 1) > 1 else ""
    return f"{c['date']} · {c['who']} · {c['file']} · {c['kind']}{times}: {what}"


def words_of(about):
    out = []
    for w in re.findall(r"[\w$'-]+", str(about).lower()):
        w = w.strip("'-")
        if len(w) >= 3 and w not in STOP and w not in out:
            out.append(w)
    return out


def _has(c, words):
    text = c["text"] + " " + c.get("old", "")
    return sum(bool(re.search(rf"(?<![\w$]){re.escape(w)}", text, re.I)) for w in words)


def as_file(memory, about):
    m = FILE_IN.search(str(about).replace("\\", "/"))
    if not m:
        return None
    a = m.group(0).strip("./")
    if a in memory.files:
        return a
    hits = [r for r in memory.files if r.endswith("/" + a)]
    if len(hits) == 1:
        return hits[0]
    return a if _git(memory.root, "log", "-1", "--format=%h", "--", a).strip() else None


class LookBack:
    def __init__(self, app):
        self.app = app

    def option(self):
        return {"type": "object", "properties": {"step": {"const": "look_back"},
                                                 "about": {"type": "string", "maxLength": ABOUT_MAX}},
                "required": ["step", "about"], "additionalProperties": False}

    def run_step(self, step):
        mem = self.app.engine.memory
        about = str(step.get("about") or "").strip()
        path = as_file(mem, about)
        if path:
            found = merged(changes(mem.root, path))
            if not found:
                return True, f"No changes to {path} in your memory's history."
            shown = found[-MOST_ITEMS:]
            head = (f"The last {len(shown)} changes to {path} (of {len(found)} since it began), oldest first, from your "
                    "memory's history:")
            return True, self._fit(head, [show(c) for c in shown])
        words = words_of(about)
        if not words:
            return False, ("Say what to look for: a word or two (a name, a thing), or one of your memory files like "
                           "system/me.md.")
        every = merged(changes(mem.root))
        found = [c for c in every if _has(c, words) == len(words)]
        note = ""
        if not found and len(words) > 1:
            need = (len(words) + 1) // 2
            found = [c for c in every if _has(c, words) >= need]
            note = " (no change had all of those words; these have most of them)"
        if not found:
            return True, (f"Nothing in your memory's history mentions {', '.join(words)}: it never reached your memory "
                          "files. If it was said in a chat, your recall step finds that.")
        lines = [show(c) for c in found]
        if len(lines) > MOST_ITEMS:
            lines = lines[:10] + [f"... ({len(lines) - 16} more changes in between) ..."] + lines[-6:]
        head = (f"Changes to your memory with {', '.join(words)}{note}, oldest first ({len(found)} in all). The first one "
                "is when it reached your memory:")
        return True, self._fit(head, lines)

    @staticmethod
    def _fit(head, lines):
        text = head + "\n" + "\n".join(lines)
        return text if len(text) <= MOST_CHARS else text[:MOST_CHARS - 20].rsplit("\n", 1)[0] + "\n(... more not shown)"
