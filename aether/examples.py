import datetime as dt
import hashlib
import json
import os
import re
import threading

from .config import DATA_DIR
from .history import from_user, said as his_words
from .names import USER

STORE = os.path.join(DATA_DIR, "examples.json")
TOOLS = ("skill", "calendar", "recall", "read_chat", "save_research", "task", "make_image", "wake_me", "gallery")
SHAPE_ONLY = {"calendar": "do", "task": "do", "wake_me": None, "make_image": None, "recall": None, "read_chat": None,
              "gallery": None, "save_research": None}
MATURE = dt.timedelta(days=1)
PER_TOOL, MOST = 15, 300
LONGEST = 300
LOOK_BACK = 60
NOPE = re.compile(r"^\W*(?:no+\b|nope|wrong|not that|that'?s not|that isn'?t|you didn'?t|stop)", re.I)
PREFIX = "search_query: "
NAMED = {"board": r"\bboard\b", "calendar": r"\bcalendar\b", "research|pdf": r"\blibrary\b",
         "make_image": r"\b(?:draw|picture|image|wallpaper)\b"}
NAMED = {tools: re.compile(rx, re.I) for tools, rx in NAMED.items()}


def names_another_tool(words, tool):
    named = [tools.split("|") for tools, rx in NAMED.items() if rx.search(words)]
    return bool(named) and not any(tool in group for group in named)


def tool_of(step):
    return str(step.get("skill") or "skill") if step.get("step") == "skill" else str(step.get("step"))


def shape(step):
    kind = step.get("step")
    if kind == "skill":
        out = {"step": "skill", "skill": step.get("skill")}
        for k in ("script", "command"):
            if step.get(k):
                out[k] = step[k]
        out["args"] = [str(a)[:80] for a in (step.get("args") or [])][:6]
        return out
    field = SHAPE_ONLY.get(kind)
    return {"step": kind, **({field: step[field]} if field and step.get(field) else {})}


def shown(sh):
    if sh.get("step") == "skill":
        bits = [f"command: {sh['command']}"] if sh.get("command") else []
        if sh.get("args"):
            bits.append("args: " + ", ".join(json.dumps(a, ensure_ascii=False) for a in sh["args"]))
        return f"{sh.get('skill')} skill" + (f" ({'; '.join(bits)})" if bits else "")
    return " ".join(str(v) for v in sh.values())


def harvest(events, chat_id, final=False):
    out = []
    for i, e in enumerate(events):
        if e.get("kind") != "user" or not from_user(e):
            continue
        words = his_words(e.get("text"))
        if not words or len(words) > LONGEST:
            continue
        if any(x.get("outside") for x in events[max(0, i - LOOK_BACK):i] if x.get("kind") == "result"):
            continue
        before = next((x for x in reversed(events[:i]) if x.get("kind") in ("reply", "reach_out")), None)
        if before and str(before.get("text") or "").rstrip().endswith("?"):
            continue
        end = next((j for j in range(i + 1, len(events)) if events[j].get("kind") in ("user", "wake")), len(events))
        if end == len(events) and not final:
            continue
        turn = events[i + 1:end]
        if not any(x.get("kind") == "reply" and not x.get("stopped") for x in turn):
            continue
        if end < len(events) and from_user(events[end]) and NOPE.match(his_words(events[end].get("text")) or ""):
            continue
        picked = None
        for j, x in enumerate(turn):
            if x.get("kind") == "result" and x.get("outside"):
                break
            if x.get("kind") != "step" or not isinstance(x.get("step"), dict) or x.get("auto"):
                continue
            step = x["step"]
            if step.get("step") not in TOOLS:
                continue
            res = next((r for r in turn[j + 1:] if r.get("kind") == "result"), {})
            if res.get("ok"):
                picked = step
            break
        if picked and not names_another_tool(words, tool_of(picked)):
            out.append({"said": words, "step": shape(picked), "tool": tool_of(picked), "chat": chat_id, "ts": e["ts"]})
    return out


def doc_hash(skill):
    return hashlib.sha1(str(getattr(skill, "doc", "") or "").encode("utf-8")).hexdigest()[:10]


FITS = ("{USER} said to his AI companion (in his app): \"{said}\"\nHer first step was: {step}.\nWas that the step his "
        "message asked for? yes: it's what he asked her to do or look up. no: he asked for something else, or he wasn't "
        "asking for anything (just talking, joking, or telling her about his day). unclear: you can't tell from his "
        "words alone.")
FITS_SCHEMA = {"type": "object", "properties": {"fits": {"enum": ["yes", "no", "unclear"]}}, "required": ["fits"],
               "additionalProperties": False}


PLAIN = {"recall": "searched her memory of their past chats and her notes", "read_chat": "opened one of their past chats",
         "calendar": "their shared calendar", "task": "her own task list", "make_image": "drew a picture",
         "save_research": "saved a note to her research notebook", "wake_me": "set herself a wake-up",
         "gallery": "looked through the pictures she made"}


def described(sh, skills):
    if sh.get("step") == "skill":
        sk = skills.get(sh.get("skill"))
        what = " ".join(str(getattr(sk, "description", "") or "").split())[:160]
        return shown(sh) + (f": {what}" if what else "")
    return f"{shown(sh)} ({PLAIN.get(sh.get('step'), '')})"


def fits_check(llm):
    def fits(said, step):
        try:
            raw = llm.complete([{"role": "user", "content": FITS.format(USER=USER, said=" ".join(said.split())[:400], step=step)}],
                               FITS_SCHEMA, "examples_check", 0.0, 20)
            return json.loads(raw).get("fits") == "yes"
        except Exception:
            return False
    return fits


def skill_pages_changed(memory):
    out = {}
    root = os.path.join(memory.root, "skills")
    for name in (os.listdir(root) if os.path.isdir(root) else []):
        r = memory._git("log", "-1", "--format=%cI", "--", f"skills/{name}/SKILL.md")
        try:
            out[name] = dt.datetime.fromisoformat((r.stdout or "").strip()).replace(tzinfo=None)
        except ValueError:
            pass
    return out


class Examples:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.lock = threading.Lock()
        self.items, self.pending, self.seen = [], [], set()
        self._load()

    def _load(self):
        self.backfilled = False
        try:
            with open(STORE, encoding="utf-8") as f:
                d = json.load(f)
            self.items, self.pending = d.get("items") or [], d.get("pending") or []
            self.seen = set(d.get("seen") or [])
            self.backfilled = bool(d.get("backfilled"))
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        with open(STORE + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"items": self.items, "pending": self.pending, "seen": sorted(self.seen)[-5000:],
                       "backfilled": self.backfilled}, f)
        os.replace(STORE + ".tmp", STORE)

    @staticmethod
    def key(c):
        return f"{c['chat']}|{c['ts']}"

    def observe(self, events, chat_id, final=False):
        with self.lock:
            for c in harvest(events, chat_id, final):
                if self.key(c) not in self.seen:
                    self.seen.add(self.key(c))
                    self.pending.append(c)
            self.save()

    def backfill(self, conv_dir, list_chats, load_events):
        for cid in list_chats(conv_dir):
            if cid == "heartbeat" or cid.startswith("game-"):
                continue
            try:
                self.observe(load_events(cid), cid, final=True)
            except Exception:
                continue
        self.backfilled = True
        with self.lock:
            self.save()

    def on(self):
        return bool(getattr(self.cfg, "examples_enabled", False)) and getattr(self.app, "recall", None) is not None

    def collecting(self):
        return (self.on() or bool(getattr(self.cfg, "examples_collect", False))) and getattr(self.app, "recall", None) is not None

    def tick(self, now):
        from .history import Conversation, list_conversations
        app = self.app
        if not self.backfilled:
            self.backfill(app.conv_dir, list_conversations, lambda cid: Conversation(app.conv_dir, cid).events)
        if not any(dt.datetime.fromisoformat(c["ts"]) <= now - MATURE for c in self.pending):
            return 0
        kept, dropped = self.mature(now, app.recall.embed, app.engine.skills, fits_check(app.engine.llm),
                                    skill_pages_changed(app.engine.memory), budget=8)
        return kept + dropped

    def note_for(self, text):
        if not self.on():
            return ""
        try:
            return self.note(self.matches(text, self.app.recall.embed, self.app.engine.skills))
        except Exception:
            return ""

    def mature(self, now, embed, skills, fits, changed=None, budget=16):
        with self.lock:
            ready = [c for c in self.pending if dt.datetime.fromisoformat(c["ts"]) <= now - MATURE][:budget]
        if not ready:
            return 0, 0
        keep = []
        for c in ready:
            if c["step"].get("step") == "skill":
                sk = skills.get(c["tool"])
                when = (changed or {}).get(c["tool"])
                if not sk or (when and dt.datetime.fromisoformat(c["ts"]) < when):
                    continue
                c["doc"] = doc_hash(sk)
            if fits(c["said"], described(c["step"], skills)):
                keep.append(c)
        vecs = embed([PREFIX + c["said"] for c in keep]) if keep else []
        with self.lock:
            for c, v in zip(keep, vecs):
                self.items.append(dict(c, vec=[round(x, 5) for x in v]))
            self.pending = [c for c in self.pending if c not in ready]
            self._cap()
            self.save()
        return len(keep), len(ready) - len(keep)

    def _cap(self):
        self.items.sort(key=lambda c: c["ts"], reverse=True)
        kept, per, said = [], {}, set()
        for c in self.items:
            k = (c["tool"], c["said"].lower())
            if k in said or per.get(c["tool"], 0) >= PER_TOOL:
                continue
            said.add(k)
            per[c["tool"]] = per.get(c["tool"], 0) + 1
            kept.append(c)
        self.items = kept[:MOST]

    def matches(self, text, embed, skills, most=2):
        if not self.items or not text or len(text) > LONGEST * 3:
            return []
        q = embed([PREFIX + text])[0]
        scored = []
        with self.lock:
            for c in self.items:
                if c["step"].get("step") == "skill":
                    sk = skills.get(c["tool"])
                    if not sk or c.get("doc") != doc_hash(sk):
                        continue
                scored.append((sum(a * b for a, b in zip(q, c["vec"])), c))
        scored.sort(key=lambda x: -x[0])
        out, tools = [], set()
        for s, c in scored:
            if s < self.cfg.examples_min:
                break
            if c["tool"] in tools:
                continue
            tools.add(c["tool"])
            out.append((s, c))
            if len(out) >= most:
                break
        return out

    def note(self, found):
        if not found:
            return ""
        lines = [f"- he said \"{' '.join(c['said'].split())[:160]}\" -> you used: {shown(c['step'])}" for _, c in found]
        return ("[Steps that worked before, for messages like this one (yours; use one only if this message asks for "
                "the same thing, with what he says now):\n" + "\n".join(lines) + "]")

    def forget(self, i):
        with self.lock:
            c = self.items.pop(i)
            self.save()
        return c
