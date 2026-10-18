import datetime as dt
import difflib
import json
import os
import sys
import re

from .config import DATA_DIR
from .names import fill

STORE = os.path.join(DATA_DIR, "proposals.json")
KINDS = ["build", "change", "do", "opinion", "review"]
ANSWERS = ("yes", "no", "later")
MAX_OPEN = 3
BRIEF_SECTIONS = ["Goal", "Success looks like", "Constraints", "Known unknowns", "Research first", "Tasks",
                  "Technical spec", "Risks", "First step"]
SKILL_LINE = ("send {USER} an idea that needs his yes as a card with Yes / No / Later. Most cards are kind \"do\" (something "
              "to try or do, brief \"none\"); \"change\" is a change to something of his, \"opinion\" asks what he thinks; "
              "\"build\" only once its finished architect plan exists (its name in brief): an idea for a new skill with no "
              "plan yet is a \"do\" card too. Use your propose step (read_skill propose "
              "shows how)")
SKILL_DOC = """# Propose (built into Aether: you use it with your `propose` step, not the skill step)

For an idea of yours that needs {USER}'s yes before it goes further. It arrives in his chat as a card with Yes / No /
Later buttons; his answer comes back to you there, in your wake-up and in your digest.

## Kinds
- build: a new skill or something to build (maybe with Claude), only once its architect plan exists with every section
  filled (the plan's name in "brief"). No finished plan yet: send the idea as a "do" card with brief "none". A plan
  gets written when he asks for one, or on your own time (architect skill, in your Workspace); a build card is for an
  idea whose plan is finished.
- change: a change to something of his (a board line, a calendar date, his notes): say exactly what would change.
- do: something you'd do that needs his OK first, a change to how you work (your heartbeat, your habits) included.
- opinion: you want his take before you go further.

## How: one propose step
- kind: build, change, do or opinion
- title: a few words he'll know it by
- why: why it's worth doing, in a sentence or two
- plan: what you'd do, short: the steps, or exactly what changes
- brief: for build, the plan's name (from the architect skill's list); otherwise "none"

As you fill it in:
```
{"step": "propose", "kind": "opinion", "title": "A rainy-day playlist", "why": "He keeps saying rain kills his mood.", "plan": "Ask what he'd want on it, then make it with him.", "brief": "none"}
```

## Limits
At most 3 waiting at once (one he answered "later" still counts). One card per idea. On your own time it waits for a
moment you could message him, and counts as one of your messages. Nothing happens by itself on his yes: you see his
answer and do the next step.
"""


def brief_complete(path):
    try:
        with open(path, encoding="utf-8") as f:
            md = f.read()
    except OSError:
        return False, ["(no such brief)"]
    empty = []
    for title in BRIEF_SECTIONS:
        m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", md, flags=re.S | re.M)
        body = m.group(1).strip() if m else ""
        if not body or body.startswith("(empty)"):
            empty.append(title)
    return not empty, empty


def clean(text, most):
    text = " ".join(str(text or "").split())
    return text if len(text) <= most else text[:most - 1].rstrip() + "…"


class Proposals:
    def __init__(self, app, clock=None):
        self.app = app
        self.cfg = app.cfg
        self.clock = clock or dt.datetime.now
        self.items = []
        try:
            with open(STORE, encoding="utf-8") as f:
                self.items = json.load(f).get("items") or []
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        with open(STORE + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"items": self.items}, f, indent=1)
        os.replace(STORE + ".tmp", STORE)

    def open(self):
        return [p for p in self.items if p["status"] in ("open", "later")]

    def get(self, pid):
        return next((p for p in self.items if p["id"] == pid), None)

    def option(self):
        return {"type": "object", "properties": {
            "step": {"const": "propose"}, "kind": {"enum": KINDS},
            "title": {"type": "string", "maxLength": 80}, "why": {"type": "string", "maxLength": 300},
            "plan": {"type": "string", "maxLength": 400}, "brief": {"type": "string", "maxLength": 60}},
            "required": ["step", "kind", "title", "why", "plan", "brief"], "additionalProperties": False}

    def _brief_path(self, slug):
        slug = re.sub(r"[^a-z0-9]+", "-", str(slug or "").lower().removesuffix(".md")).strip("-")
        lib = os.environ.get("AETHER_LIBRARY") or self.cfg.library_dir
        ws = self.cfg.workspace_dir
        for folder in (os.path.join(ws, "plans"), os.path.join(ws, "briefs"), os.path.join(lib, "projects")):
            p = os.path.join(folder, slug + ".md")
            if slug and os.path.isfile(p):
                return p
        return None

    def run_step(self, step):
        eng, life, now = self.app.engine, self.app.life, self.clock()
        kind = step.get("kind") if step.get("kind") in KINDS else "do"
        title, why, plan = clean(step.get("title"), 80), clean(step.get("why"), 300), clean(step.get("plan"), 400)
        brief = clean(step.get("brief"), 60)
        if len(title) < 4 or len(why) < 10 or len(plan) < 10:
            return False, "A proposal needs a title, why it's worth it, and your plan (a sentence or two each)."
        same = [p for p in self.open() if difflib.SequenceMatcher(None, p["title"].lower(), title.lower()).ratio() >= 0.8]
        if same:
            return False, f"That's already waiting for his answer: \"{same[0]['title']}\". One card per idea."
        if len(self.open()) >= MAX_OPEN:
            return False, ("You have 3 proposals waiting for his answer: " + "; ".join(f"\"{p['title']}\"" for p in self.open())
                           + ". Wait for one of them first.")
        if kind == "build":
            path = self._brief_path(brief) if brief.lower() != "none" else None
            if not path:
                if eng._kind == "user":
                    return False, ("Not sent: a build card needs its finished architect plan, and this idea has none "
                                   "yet. Send it as a \"do\" card: the propose step again with the same title, why and "
                                   "plan, kind \"do\" and brief \"none\".")
                return False, ("A build proposal needs its architect plan: write it with the architect skill (every "
                               "section), then propose with the plan's name in \"brief\". That's for a new skill or "
                               "something to build. A smaller idea (a change to how you work, something to try) is a "
                               "\"do\" card: take the propose step again with kind \"do\" and brief \"none\".")
            ok, empty = brief_complete(path)
            if not ok:
                return False, (f"The plan isn't finished: {', '.join(empty)} still empty. Fill them with the architect "
                               "skill (set), then propose it.")
        outside = list(dict.fromkeys((eng._outside or []) + (eng._stale_outside or [])))
        p = {"id": f"p{1 + max([int(x['id'][1:]) for x in self.items] + [0])}", "kind": kind, "title": title, "why": why,
             "plan": plan, "brief": brief if kind == "build" else "", "status": "open", "made": now.isoformat(timespec="seconds"),
             "own_time": eng._kind != "user", "after_outside": outside, "delivered": "", "answered": ""}
        self.items.append(p)
        self.save()
        if eng._kind == "user":
            self.deliver(p, eng.conv, counts=False)
            where = "in this chat, as a card with Yes / No / Later"
        elif life.message_gate(now) is None:
            self.deliver(p, counts=True)
            where = "to him now, as a card with Yes / No / Later (one of today's messages)"
        else:
            where = "waiting for a moment you could message him; then it goes out as a card"
        life.log_event("proposed", f"{kind}: {title}")
        return True, f"Proposal {p['id']} made: \"{title}\". It went {where}. His answer comes back to you."

    def card_text(self, p):
        return (f"{p['kind']}: {p['title']}. {p['why']} Plan: {p['plan']}"
                + (f" (brief: {p['brief']})" if p.get("brief") else ""))

    def deliver(self, p, conv=None, counts=True):
        life, app = self.app.life, self.app
        dm = None
        if conv is None:
            conv, dm = life.reach_target()
        if counts:
            life.count_reach_out()
        app.wake_chat(conv.id)
        conv.add("proposal", pid=p["id"], type=p["kind"], title=p["title"], why=p["why"], plan=p["plan"],
                 brief=p.get("brief", ""), after_outside=p.get("after_outside") or [])
        p["delivered"] = conv.id
        self.save()
        app.meta.setdefault(conv.id, {})["unread"] = True
        app._save_meta()
        app.broadcast({"type": "proposal", "chat": conv.id, "pid": p["id"], "title": p["title"]})
        dc = getattr(app, "discord", None)
        if dc and self.cfg.discord_enabled:
            text = (f"💡 {self.cfg.display_name} proposes ({self.card_text(p)}). Yes / No / Later: answer in the app.")
            try:
                dc.send(dm, text) if dm else dc.dm_owner(text)
            except Exception:
                pass

    def review(self, data, conv=None):
        name = str(data.get("name") or "").strip()
        if not name:
            return None
        for p in self.items:
            if p["kind"] == "review" and p["title"] == name and p["status"] in ("open", "later"):
                return p
        done_like = str(data.get("done_looks_like") or "").strip() or "(the plan's 'Done looks like' is still empty)"
        files = list(data.get("step_files") or [])
        where = f"Plan: {data.get('plan_file') or ''}" + (f" · steps: {', '.join(files)}" if files else "")
        eng = self.app.engine
        p = {"id": f"p{1 + max([int(x['id'][1:]) for x in self.items] + [0])}", "kind": "review", "title": name,
             "why": "Done looks like:\n" + done_like, "plan": where, "brief": "", "status": "open",
             "made": self.clock().isoformat(timespec="seconds"), "own_time": getattr(eng, "_kind", "") != "user",
             "after_outside": [], "delivered": "", "answered": ""}
        self.items.append(p)
        self.save()
        if getattr(eng, "_kind", "") == "user" and conv is None:
            conv = eng.conv
        self.deliver(p, conv, counts=False)
        self.app.life.log_event("review card", name)
        return p

    def _board(self, *args):
        import json as _json
        import subprocess
        script = os.path.join(self.app.engine.memory.root, "skills", "board", "scripts", "board.py")
        env = {**os.environ, "MEMORY_DIR": self.app.engine.memory.root,
               "AETHER_WORKSPACE": os.path.expanduser(self.cfg.workspace_dir or "")}
        try:
            r = subprocess.run([sys.executable, script, *args], capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
            first = r.stdout.splitlines()[0] if r.stdout.strip() else "{}"
            return r.returncode == 0, _json.loads(first)
        except Exception as e:
            return False, {"error": repr(e)}

    def _send_back(self, name, note):
        ok, d = self._board("show", name)
        slug = d.get("plan") if ok else ""
        if slug:
            path = os.path.join(os.path.expanduser(self.cfg.workspace_dir or ""), "plans", slug + ".md")
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                line = fill("- [ ] {USER} sent it back: ", self.cfg) + " ".join(str(note).split())[:200]
                if "## Steps" in text:
                    head, body = text.split("## Steps", 1)
                    text = head + "## Steps" + body.rstrip("\n") + "\n" + line + "\n"
                else:
                    text = text.rstrip("\n") + "\n\n## Steps\n" + line + "\n"
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            except OSError:
                pass
        return self._board("next", name)

    def answer(self, pid, answer, note=""):
        if answer not in ANSWERS:
            raise ValueError("answer yes, no or later")
        p = self.get(pid)
        if p is None:
            raise ValueError("no such proposal")
        if p["status"] in ("yes", "no"):
            raise ValueError(f"already answered: {p['status']}")
        p["status"], p["answered"] = answer, self.clock().isoformat(timespec="seconds")
        if note:
            p["note"] = str(note)[:400]
        self.save()
        if p["kind"] == "review":
            if answer == "yes":
                self._board("done", p["title"], fill("{USER}: done", self.cfg))
            elif answer == "no":
                self._send_back(p["title"], note or "not done yet")
            else:
                self._board("wait", p["title"], "your look")
            try:
                self.app.engine.memory.reload()
                self.app.engine.refresh()
            except Exception:
                pass
        if p.get("delivered"):
            try:
                conv = self.app.conv(p["delivered"])
                conv.add("proposal_answer", pid=pid, title=p["title"], answer=answer)
            except ValueError:
                pass
        self.app.life.log_event("proposal answered", f"{answer}: {p['title']}")
        self.app.broadcast({"type": "proposal_answer", "chat": p.get("delivered"), "pid": pid, "answer": answer})
        return p

    def tick(self, now):
        life = self.app.life
        waiting = [p for p in self.items if p["status"] == "open" and not p.get("delivered")]
        if not waiting or life.heartbeat_gate(now) or life.message_gate(now):
            return False
        self.deliver(waiting[0], counts=True)
        return True

    def lines(self, since=None):
        out = []
        for p in self.items:
            if p["status"] == "open":
                out.append(f"- \"{p['title']}\" ({p['kind']}): waiting for his answer"
                           + ("" if p.get("delivered") else ", not sent yet"))
            elif p["status"] == "later":
                out.append(f"- \"{p['title']}\" ({p['kind']}): he said later")
            elif since is None or (p.get("answered") and dt.datetime.fromisoformat(p["answered"]) >= since):
                out.append(f"- \"{p['title']}\" ({p['kind']}): he said {p['status']}")
        return out

    def said_no(self, since):
        return [p for p in self.items if p["status"] == "no" and p.get("answered")
                and dt.datetime.fromisoformat(p["answered"]) >= since]
