import datetime as dt
import difflib
import os
import re
import subprocess

from .proc import NO_WINDOW
from .names import USER, fill

SKIP_DIRS = {".git", ".obsidian", "skills", "__pycache__", "mods"}
DATE_PREFIX = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?\d{4}-\d{2}-\d{2}(?:\*\*)?\s*[:\-–—]?\s*")
BULLET = re.compile(r"^\s*[-*•]\s+")
TASK_LINE = re.compile(r"^\s*(?:[-*]\s*)?\[t\d+\]")
FACTS_FILE = "system/human/facts.md"
CHAT_EVENT = re.compile(r"^[\w'-]+\s+(?:just\s+)?(?:shared|sent|showed|pasted|forwarded|linked|gave|dropped|uploaded)\b"
                        r"(?:\s+(?:me|you|with me))?.{0,40}?\b(?:resume|cv|document|doc|file|link|url|article|e-?mail|"
                        r"screenshot|picture|photo|image|pic|profile|report|post|video|message|paste|text|pdf|page|"
                        r"website|site)s?\b", re.I)
SECRET = re.compile(r"\b(?:sk|pk|rk|ghp|gho|xox[abp]|AKIA|AIza)[-_A-Za-z0-9]{12,}|\b[A-Fa-f0-9]{32,}\b|"
                    r"\b[A-Za-z0-9_\-]{40,}\b|(?:password|passwd|api[ _-]?key|token|secret)\s*(?:is|=|:)\s*\S+|"
                    r"\b(?:\d[ -]?){13,16}\b|-----BEGIN [A-Z ]*KEY-----", re.I)
SECRET_MSG = ("Not saved: that looks like a password, key, token or card number. Those never go in your memory (it's git: "
              "a line taken out later is still in the history). His keys live in the vault (Settings -> Keys), where a "
              "skill gets them without you ever seeing them. Keep the rest of what he said, without the secret.")
CHAT_EVENT_MSG = ("Not saved: that's something that happened in this chat (he shared or sent you something), not a lasting "
                  "fact about {USER}, and the chat already keeps it. His facts are only what he tells you about himself, in "
                  "his own words; a document he shares is about whoever is in it. Answer him about it instead.")
MOMENT = re.compile(r"\b(?:(?:has|got|had) (?:an? |some |new )?ideas?\b|ideas? for\b|admits?|admitted|agrees?|agreed|jokes?|joked|joking(?:ly)?|confirms?|confirmed|concedes?|"
                    r"corrected me|wants (?:me|lucy) to|told me to|asked me to|prefers that i|"
                    r"currently|right now|at the moment|today|tonight|this (?:morning|afternoon|evening|week|chat|"
                    r"conversation|session)|in (?:our|this) (?:current )?(?:chat|conversation|session)|"
                    r"since (?:yesterday|last night|sunday|monday|tuesday|wednesday|thursday|friday|saturday)|"
                    r"for about (?:a|an|\d+) (?:day|hour|night)s?(?: or two)?)\b", re.I)
MOMENT_MSG = ("Not saved: that's a moment in this chat (how he feels, what he admits or jokes, a correction, how today is "
              "going), not a lasting fact about {USER}; the chat keeps it. If it really is lasting, say it as the plain fact, "
              "without the moment words (no 'currently', 'today', 'admits', 'wants me to').")
IDEA = re.compile(r"\b(?:(?:has|got|had) (?:an? |some |new )?ideas?\b|ideas? for\b)", re.I)
IDEA_MSG = ("Not saved, and nothing was written, so there's nothing to undo: an idea he's talking through isn't a fact "
            "about him. Don't save it in other words. The chat keeps it. If he wants it kept, he'll say so, and it goes on "
            "his board's Later list.")


def moment_msg(text):
    return IDEA_MSG if IDEA.search(str(text or "")) else MOMENT_MSG
HERS_SYSTEM = ("system/journal.md", "system/me.md", "system/working.md", "system/workspace.md")
HERS_UNDER = ("notes/", "reference/")
HIS_UNDER = ("reference/almanac/", "reference/facts-history.md")
BLOCKED = "[BLOCKED: looked like an order, not a memory]"


def hers(rel):
    rel = str(rel or "").replace("\\", "/")
    return rel in HERS_SYSTEM or (rel.startswith(HERS_UNDER) and not rel.startswith(HIS_UNDER))


def suspect(text):
    from .keeper import INJECT
    out, n = [], 0
    for ln in str(text or "").split("\n"):
        if INJECT.search(ln):
            out.append(BLOCKED)
            n += 1
        else:
            out.append(ln)
    return "\n".join(out), n


TASK_DONE = ("That's a line from your task list (system/working.md), which only your task step changes. A task under "
             "\"Finished lately\" is already done or dropped: there's nothing left to remove.")
NEW_FILE = re.compile(r"^(reference|notes)/[a-z0-9][a-z0-9_\-/]*\.md$")
STARTER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "starter-memory")


def seed(root, starter=STARTER):
    import shutil
    root = os.path.abspath(os.path.expanduser(root))
    if os.path.exists(root) or not os.path.isdir(starter):
        return False
    shutil.copytree(starter, root)
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=Aether", "-c", "user.email=starter@local", "commit", "-q", "-m",
                  "starter memory"]):
        subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
    return True


class MemoryError_(Exception):
    pass


def split_frontmatter(text):
    if text.startswith("---\n") or text.startswith("---\r\n"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 4)
            fm = text[: (nl + 1) if nl != -1 else len(text)]
            body = text[len(fm):]
            meta = {}
            for line in fm.splitlines()[1:-1]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip("'\"")
            return meta, fm, body
    return {}, "", text


FACT_OVERLAP = 0.80
FACT_SKIP = {"user", "users", "the", "and", "his", "him", "with", "that", "this", "for", "from", "has", "was", "are",
             "but", "about", "its", "it", "very", "really", "just"}


def _fact_words(normed):
    return {w for w in normed.split() if len(w) >= 3 and w not in FACT_SKIP}


def _norm(line):
    s = DATE_PREFIX.sub("", line)
    s = re.sub(r"[^\w\s]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


class MemoryFile:
    def __init__(self, root, rel):
        self.rel = rel.replace("\\", "/")
        self.path = os.path.join(root, *self.rel.split("/"))
        with open(self.path, encoding="utf-8", newline="") as f:
            self.text = f.read().replace("\r\n", "\n")
        self.meta, self.frontmatter, self.body = split_frontmatter(self.text)

    @property
    def description(self):
        return self.meta.get("description", "")

    @property
    def read_only(self):
        return str(self.meta.get("read_only", "")).lower() == "true"

    @property
    def is_system(self):
        return self.rel.startswith("system/")


class Memory:
    def __init__(self, root, cfg):
        self.root = os.path.abspath(root)
        self.cfg = cfg
        self.files = {}
        self.reload()

    def reload(self):
        self.files = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel_dir = os.path.relpath(dirpath, self.root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            dirnames[:] = sorted(d for d in dirnames if not (rel_dir == "" and d in SKIP_DIRS) and d not in (".git", "__pycache__"))
            for n in sorted(filenames):
                if n.endswith(".md"):
                    rel = f"{rel_dir}/{n}" if rel_dir else n
                    try:
                        self.files[rel] = MemoryFile(self.root, rel)
                    except (OSError, UnicodeDecodeError):
                        pass

    def system_files(self):
        sys_files = [f for f in self.files.values() if f.is_system]
        return sorted(sys_files, key=lambda f: (f.rel != "system/persona.md", f.rel))

    def other_files(self):
        return [f for f in self.files.values() if not f.is_system]

    def protected_by(self, rel):
        for prefix, owner in self.cfg.protected.items():
            if rel == prefix or (prefix.endswith("/") and rel.startswith(prefix)):
                return owner if " " in owner else f"the {owner} skill"
        return None

    def _writable(self):
        return sorted(f.rel for f in self.files.values() if not f.read_only and not self.protected_by(f.rel))

    def addable(self):
        edit_only = getattr(self.cfg, "edit_only", [])
        return [r for r in self._writable() if r not in edit_only]

    def editable(self):
        return [r for r in self._writable() if r not in self.cfg.add_only]

    def deletable(self):
        return [r for r in self.editable() if NEW_FILE.match(r)]

    def readable(self):
        return sorted(f.rel for f in self.other_files())

    def read(self, rel):
        f = self.files.get(rel)
        if not f:
            raise MemoryError_(f"There is no memory file {rel}.")
        if f.is_system:
            return (f"{rel} is already in your prompt under <memory>: answer from what it says there, don't open "
                    "other files looking for it." + (" Your newest journal entry is the first one." if rel == "system/journal.md" else "")
                    + f" What it said before, or when a line got there: your look_back step with \"{rel}\".")
        return suspect(f.text)[0] if hers(rel) else f.text

    def _check_write(self, rel, op):
        f = self.files.get(rel)
        if not f:
            raise MemoryError_(f"There is no memory file {rel}.")
        owner = self.protected_by(rel)
        if owner:
            raise MemoryError_(f"{rel} is written by {owner}, not by memory steps.")
        if f.read_only:
            raise MemoryError_(f"{rel} is read-only. {USER} set it; you can't change it.")
        if op != "add" and rel in self.cfg.add_only:
            raise MemoryError_(f"{rel} is add-only: you can add new lines, never change or remove old ones.")
        if op == "add" and rel in getattr(self.cfg, "edit_only", []):
            raise MemoryError_(f"{rel} is your read of him, kept in sections: change a section with memory_replace. "
                               "Something he told you about himself goes in system/human/facts.md.")
        return f

    def _keep_history(self, f, new_body, op, reason, today=None):
        hist = self.cfg.keep_history.get(f.rel)
        if not hist:
            return None
        after = set(new_body.splitlines())
        gone = [ln.strip() for ln in f.body.splitlines() if ln.strip() and ln not in after]
        if not gone:
            return None
        before = set(f.body.splitlines())
        came = [ln.strip() for ln in new_body.splitlines() if ln.strip() and ln not in before]
        path = os.path.join(self.root, *hist.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.exists(path)
        why = " ".join(str(reason).split())[:150]
        with open(path, "a", encoding="utf-8", newline="\n") as out:
            if new:
                out.write(fill("---\ndescription: Old versions of {USER}'s facts: what changed, when and why. "
                               "Nothing here is current; it's the record.\n---\n", self.cfg))
            out.write(f"\n## {(today or dt.date.today()).isoformat()}: {'changed' if came else 'removed'} by me ({why})\n\n"
                      + "".join(f"- was: {g}\n" for g in gone) + "".join(f"- now: {c}\n" for c in came))
        return hist

    def _save(self, f, body):
        new = fill(f.frontmatter + body, self.cfg)
        with open(f.path, "w", encoding="utf-8", newline="\n") as out:
            out.write(new)

    def _no_secrets(self, text):
        if SECRET.search(str(text)):
            raise MemoryError_(SECRET_MSG)

    def add(self, rel, text, reason, today=None):
        f = self._check_write(rel, "add")
        text = " ".join(str(text).split())
        if not text:
            raise MemoryError_("Nothing to add: the text was empty.")
        self._no_secrets(text)
        if rel == FACTS_FILE and CHAT_EVENT.match(BULLET.sub("", DATE_PREFIX.sub("", text)).strip()):
            raise MemoryError_(CHAT_EVENT_MSG)
        if rel == FACTS_FILE and MOMENT.search(text):
            raise MemoryError_(moment_msg(text))
        dup = self.find_duplicate(f, text)
        if dup:
            return {"ok": True, "changed": False, "file": rel,
                    "message": f"Already in {rel}, nothing saved: {dup.strip()}"}
        day = (today or dt.date.today()).isoformat()
        line = f"- {day}: {BULLET.sub('', DATE_PREFIX.sub('', text)).strip()}"
        body = f.body.rstrip("\n") + "\n" + line + "\n"
        self._save(f, body)
        return self._finish(rel, "add", reason, f"Added to {rel}: {line}")

    THERE_MIN = 20

    def _lives_in(self, old, skip):
        if len(old.strip()) < self.THERE_MIN:
            return ""
        pat = re.compile(r"\s+".join(map(re.escape, old.split())))
        for rel, f in sorted(self.files.items()):
            if rel == skip or not pat.search(f.body):
                continue
            owner = self.protected_by(rel)
            if owner:
                return f"It's in {rel}, which is written by {owner}, not by memory steps."
            if f.read_only:
                return f"It's in {rel}, which is read-only ({USER} set it)."
            return f"It's in {rel}: memory_replace with file {rel}."
        return ""

    def replace(self, rel, old, new, reason):
        f = self._check_write(rel, "replace")
        old = str(old)
        if not old.strip():
            raise MemoryError_("old text was empty.")
        if rel == FACTS_FILE and MOMENT.search(str(new or "")):
            raise MemoryError_(moment_msg(new))
        count = f.body.count(old)
        if count == 0:
            pat = re.compile(r"\s+".join(map(re.escape, old.split())))
            hits = list(pat.finditer(f.body))
            if len(hits) == 1:
                old = hits[0].group(0)
                count = 1
            else:
                there = self._lives_in(old, rel)
                close = difflib.get_close_matches(old.strip(), [ln.strip() for ln in f.body.splitlines() if ln.strip()], n=1, cutoff=0.5)
                hint = f" {there}" if there else f" Closest line: {close[0]}" if close else ""
                raise MemoryError_(f"That old text is not in {rel}, so nothing changed.{hint}")
        if count > 1:
            raise MemoryError_(f"That old text appears {count} times in {rel}; quote more of the line so it is unique.")
        if "\n" not in old.strip():
            new = str(new)
            new = new[:len(new) - len(new.lstrip())] + " ".join(new.split()) + new[len(new.rstrip()):]
        if old.strip() == str(new).strip():
            return {"ok": True, "changed": False, "file": rel,
                    "message": f"Nothing to change in {rel}: that line already says that."}
        self._no_secrets(new)
        body = f.body.replace(old, str(new), 1)
        hist = self._keep_history(f, body, "replace", reason)
        self._save(f, body)
        return self._finish(rel, "replace", reason, f"Changed in {rel}: {old.strip()[:120]} -> {str(new).strip()[:120]}",
                            also=hist)

    def remove(self, rel, line, reason):
        f = self._check_write(rel, "remove")
        want = str(line).strip()
        lines = f.body.split("\n")
        hits = [i for i, ln in enumerate(lines) if ln.strip() == want] or \
               [i for i, ln in enumerate(lines) if want and want in ln]
        if not hits:
            there = (TASK_DONE if TASK_LINE.match(want) else self._lives_in(want, rel))
            raise MemoryError_(f"No line in {rel} matches that, so nothing was removed." + (f" {there}" if there else ""))
        if len(hits) > 1:
            raise MemoryError_(f"{len(hits)} lines in {rel} match that; quote the whole line.")
        gone = lines.pop(hits[0])
        hist = self._keep_history(f, "\n".join(lines), "remove", reason)
        self._save(f, "\n".join(lines))
        return self._finish(rel, "remove", reason, f"Removed from {rel}: {gone.strip()}", also=hist)

    def create(self, rel, description, text, reason):
        rel = str(rel).replace("\\", "/").strip("/")
        if not NEW_FILE.match(rel):
            raise MemoryError_("New files go under reference/ or notes/, lowercase, ending in .md.")
        if rel in self.files:
            raise MemoryError_(f"{rel} already exists. To add to it: memory_add with file {rel}. To change a line in "
                               "it: memory_replace.")
        if self.protected_by(rel):
            raise MemoryError_(f"{rel} belongs to {self.protected_by(rel)}.")
        self._no_secrets(text)
        desc = " ".join(str(description).split()) or "Notes."
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as out:
            out.write(f"---\ndescription: {desc}\n---\n{str(text).strip()}\n")
        return self._finish(rel, "create", reason, f"Created {rel}")

    def delete(self, rel, reason):
        rel = str(rel).replace("\\", "/").strip("/")
        self._check_write(rel, "delete")
        if not NEW_FILE.match(rel):
            raise MemoryError_(f"{rel} isn't one of your notes: only files under notes/ or reference/ can be deleted. "
                               "To take a line out, use memory_remove.")
        os.remove(self.files[rel].path)
        return self._finish(rel, "delete", reason, f"Deleted {rel} (it stays in your memory's history; {USER} can "
                                                   "bring it back)")

    def find_duplicate(self, f, text):
        want = _norm(text)
        if not want:
            return None
        words = _fact_words(want) if f.rel == FACTS_FILE else set()
        for line in f.body.splitlines():
            have = _norm(line)
            if not have:
                continue
            if have == want or difflib.SequenceMatcher(None, have, want).ratio() >= self.cfg.dedupe_similarity:
                return line
            if words and len(words) >= 6:
                had = _fact_words(have)
                if len(had) >= 6 and len(words & had) / min(len(words), len(had)) >= FACT_OVERLAP:
                    return line
        return None

    def _git(self, *args):
        name = " ".join(str(getattr(self.cfg, "display_name", "") or "").split()) or "Companion"
        author = ["-c", f"user.name={name}", "-c", f"user.email={self.cfg.agent_id or 'companion'}@aether.local"]
        return subprocess.run(["git", *author, "-C", self.root, *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30, creationflags=NO_WINDOW)

    def _finish(self, rel, op, reason, message, also=None):
        reason = " ".join(str(reason).split())[:200] or op
        paths = [rel] + ([also] if also else [])
        self._git("add", "--", *paths)
        c = self._git("commit", "-q", "-m", f"{op} {rel}: {reason}", "-m", "via Aether", "--", *paths)
        commit = ""
        if c.returncode == 0:
            commit = self._git("rev-parse", "--short", "HEAD").stdout.strip()
        self.reload()
        return {"ok": True, "changed": True, "file": rel, "commit": commit,
                "message": message + (f" (commit {commit})" if commit else " (saved, but the git commit failed)")}

    def history(self, n=20):
        out = self._git("log", f"-{n}", "--pretty=%h%x09%an%x09%ar%x09%s").stdout
        return [ln.split("\t", 3) for ln in out.splitlines() if ln.count("\t") >= 3]
