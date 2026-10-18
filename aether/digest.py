import datetime as dt
import os
import re

from .history import Conversation, from_user, list_conversations

SINCE = ["since he was last here", "today", "the last 3 days"]
AETHER_DID = re.compile(r"(?:Aether: |reflection: |lessons: |journal roll-over|facts tidy|dream: |life: |"
                        r"calendar: next time for|calendar: reminder )")
BY_USER_RE = re.compile(r"\(by (?:user|jordan)\)\s*$", re.I)
GAP = dt.timedelta(hours=1)
MOST = 3500
SKILL_LINE = ("what you did on your own time (your wake-ups, notes, tasks, files, pictures, proposals), from your "
              "records, when {USER} asks what you got up to. Use your my_time step (read_skill my_time shows how)")
SKILL_DOC = """# My time (built into Aether: you use it with your `my_time` step)

When {USER} asks what you got up to ("what did you do while I slept?", "what have you been up to?", "anything new?"),
take your my_time step. Aether hands you your records since then: each wake-up and what you did in it, what you saved
or changed (research notes, your task list), files in your workspace, pictures, messages you sent him, your proposals
and his answers.

## How: one my_time step
- since: "since he was last here" (back to the end of his last visit; the usual one), "today", or "the last 3 days"

As you fill it in:
```
{"step": "my_time", "since": "since he was last here"}
```

## Then
Tell him in your own words: what you actually did, what you found, what's waiting for his yes. Only what the records
show. If nothing's new, say so; that's fine.
"""


def last_visit_end(conv_dir, now, look_back=dt.timedelta(days=7)):
    stamps = []
    cut = now - look_back
    for cid in list_conversations(conv_dir):
        if cid == "heartbeat":
            continue
        try:
            if dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(conv_dir, cid + ".jsonl"))) < cut:
                break
        except OSError:
            continue
        for e in Conversation(conv_dir, cid).events:
            if from_user(e):
                try:
                    t = dt.datetime.fromisoformat(e["ts"])
                except (KeyError, ValueError):
                    continue
                if cut <= t <= now:
                    stamps.append(t)
    stamps.sort()
    for a, b in zip(reversed(stamps[:-1]), reversed(stamps[1:])):
        if b - a >= GAP:
            return a
    return None


class Digest:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg

    def option(self):
        return {"type": "object", "properties": {"step": {"const": "my_time"}, "since": {"enum": SINCE}},
                "required": ["step", "since"], "additionalProperties": False}

    def since(self, which, now):
        if which == "today":
            return dt.datetime.combine(now.date(), dt.time())
        if which == "the last 3 days":
            return now - dt.timedelta(days=3)
        return last_visit_end(self.app.conv_dir, now) or now - dt.timedelta(hours=24)

    def records(self, start, now):
        app, life = self.app, self.app.life
        mem = app.engine.memory
        out = []
        log = [e for e in (life.state.get("life_log") or []) if e.get("when", "") >= start.isoformat(timespec="seconds")]
        woke = [e for e in log if e["what"].startswith(("woke", "thought about a thread"))]
        other = [e for e in log if e not in woke and not e["what"].startswith(("heartbeat skipped", "reminder"))]
        if woke:
            out.append(f"Your wake-ups ({len(woke)}):\n" + "\n".join(
                f"- {e['when'][5:16].replace('T', ' ')} {e['what']}: {e['detail']}" for e in woke[-12:]))
        if other:
            out.append("Other things in your log:\n" + "\n".join(
                f"- {e['when'][5:16].replace('T', ' ')} {e['what']}: {e['detail'][:120]}" for e in other[-8:]))
        r = mem._git("log", f"--since={start.isoformat(timespec='seconds')}", "--author=@aether\\.local>", "--format=%ad %s",
                     "--date=format:%m-%d %H:%M")
        commits = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
        mine = [c for c in commits if not (AETHER_DID.match(c[12:]) or BY_USER_RE.search(c))]
        auto = [c for c in commits if AETHER_DID.match(c[12:])]
        if mine:
            out.append(f"What YOU saved or changed in your memory ({len(mine)}):\n"
                       + "\n".join(f"- {c[:150]}" for c in mine[:15]) + (" ..." if len(mine) > 15 else ""))
        if auto:
            out.append(f"Done by Aether on its own, not by you ({len(auto)}): "
                       + "; ".join(c[12:70] for c in auto[:4]) + (" ..." if len(auto) > 4 else ""))
        ws = []
        for root, dirs, names in os.walk(self.cfg.workspace_dir or ""):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
            for n in names:
                p = os.path.join(root, n)
                try:
                    if dt.datetime.fromtimestamp(os.path.getmtime(p)) >= start:
                        ws.append(os.path.relpath(p, self.cfg.workspace_dir).replace("\\", "/"))
                except OSError:
                    pass
            if len(ws) > 20:
                break
        if ws:
            out.append("Files you changed in your workspace: " + ", ".join(f"\"{w}\"" for w in ws[:10]))
        imagine = getattr(app, "imagine", None)
        pics = [g for g in (imagine.gallery() if imagine else []) if g.get("made", "") >= start.isoformat(timespec="seconds")]
        if pics:
            out.append("Pictures you made: " + "; ".join(f"\"{g.get('title') or g.get('caption', '')}\"" for g in pics[:6]))
        sent = [e for e in log if "messaged you" in e.get("detail", "")]
        if sent:
            out.append(f"Messages you sent him on your own: {len(sent)}")
        tasks = app.tasks.lines(now) if getattr(app, "tasks", None) else []
        if tasks:
            out.append("Your task list now:\n" + "\n".join(tasks))
        props = app.proposals.lines(start) if getattr(app, "proposals", None) else []
        if props:
            out.append("Your proposals:\n" + "\n".join(props))
        return out

    def run_step(self, step):
        now = dt.datetime.now()
        which = step.get("since") if step.get("since") in SINCE else SINCE[0]
        start = self.since(which, now)
        lines = self.records(start, now)
        head = (f"Your own time {which} (from {start.strftime('%a %b %d %I:%M %p').replace(' 0', ' ')}), from your "
                "records, not your memory. Tell him from these, in your own words; what isn't here didn't happen.")
        if not lines:
            return True, head + "\nNothing in your records since then: nothing new to tell him."
        text = head + "\n\n" + "\n\n".join(lines)
        return True, text if len(text) <= MOST else text[:MOST - 20] + "\n(... more not shown)"
