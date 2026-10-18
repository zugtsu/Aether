import datetime as dt
import difflib
import json
import os
import re
import threading
import time
import uuid

from . import config as config_mod
from . import lessons as lessons_mod
from . import shell as shell_mod
from .config import DATA_DIR
from .engine import log
from .history import Conversation, from_user, list_conversations
from .llm import LLMError
from .memory import DATE_PREFIX, MemoryError_, _norm
from .nudge import NUDGE_PLACE
from .prompt import journal_window
from .schema import step_schema
from .tidy import roll_facts, roll_journal, tidy_facts
from .names import GIT_USER, OLD_USER_NAMES, USER, fill, user_name

STATE_FILE = os.path.join(DATA_DIR, "life.json")
SCHEDULES_FILE = os.path.join(DATA_DIR, "schedules.json")
REMINDER_SAID = 14
HEARTBEAT_CHAT = "heartbeat"
REACH_TO = ("latest", "discord", "new", "own")
LESSONS = "reference/lessons.md"
ME = "system/me.md"
ME_TEXT = ("---\ndescription: Me, who I'm becoming. What lasts about ME: my tastes, what I'm into, what I can do now and "
           "what {USER} built for me, things that happened to me. Mine to keep: I add, fix and take out lines myself. How I "
           "feel right now goes in my journal; things about {USER} go in their files.\n---\n")
LESSONS_ARCHIVE = "reference/lessons-archive.md"
LESSONS_DESC = ("My rulebook: short lessons from my own mistakes, newest last. Each night new ones are folded in and "
                "the rest merged to keep it short; every lesson I've ever learned is in reference/lessons-archive.md "
                "(read_file). {USER}'s rules come first.")
ARCHIVE_DESC = ("Every lesson I've learned from my own mistakes, oldest first, each as I first wrote it. My rulebook "
                "(reference/lessons.md) keeps them merged and short.")
MERGE_LESSONS = """These are your lessons from your own mistakes (your rulebook), oldest first. There are {n}, and the
rulebook holds {keep}. Fold them into at most {keep} lessons:
- Lessons about the same thing become one line that keeps what each of them says (short: the specific what-to-do).
- When two disagree, the newer one (the higher number) wins; a lesson a newer one replaces can go.
- Keep each one specific: the file, skill or kind of thing, and what to do instead.
- Use their words. Don't add anything that isn't in them.
- Tonight's new lessons ({new}) must all be kept.
For each lesson you keep, "from" lists the numbers it came from.

{lessons}"""
KEEPER_QUIET = 180
BOARD_PLACE = "your board check"
WAKE_PLACE = "her own wake-up"
MESSAGE_KINDS = {"heads_up": "something about his day that woke you", "finding": "something you found or made just now",
                 "proposal": "the card you just sent him", "check_in": "just to talk"}
MESSAGE_ASK = ("\nYour own things first, with your steps. Finish with reach_out true, the kind of message ("
               + "; ".join(f"{k}: {v}" for k, v in MESSAGE_KINDS.items())
               + ") and the message for him; or reach_out false and a short note to yourself.")
NOTES_DIR = os.path.join(DATA_DIR, "notes")
JOURNALISH = re.compile(r"^\s*(?:journal\s+)?(?:about:.{0,200}?\bentry:|entry:)\s*", re.I | re.S)


def talks_to_him(note, name=""):
    you = len(re.findall(r"\byou(?:'re|'ll|'ve|r|rs)?\b", note, re.I))
    them = r"he|he's|him|his|they|they're|them|their" + ("|" + re.escape(name) if name else "")
    him = len(re.findall(rf"\b(?:{them})\b", note, re.I))
    return you >= 3 and you > him


def copied(note, talk, run=10, share=0.4):
    from .engine import lifted_phrases
    words = len(re.findall(r"[a-z0-9']+", note.lower()))
    return bool(words) and sum(len(p.split()) for p in lifted_phrases(note, [talk], run=run)) >= share * words

COMMON = set("""
about above after again against almost already also always another anyway around back because been before being
better between both came cannot could couldn didn does doesn doing done down during each either else enough even
ever every first from gets getting going gone good great have having here honestly into just keep kind know last
later least less like little long look made make many maybe might more most much must never next night nothing
now only other ours over part people pretty probably really right same says seem should since some something
still such sure take than that thats their them then there these they thing things think this those though
through time today tomorrow tonight together told very want wants well went were what when where which while
will with without would yeah your youre yours actually always basically currently little officially literally
the and for you are but not all can her his him she its our out who why how off way day days week since new old
said says saying tell telling talk talking funny joke jokes laugh haha user aether chat chats earlier
trying love level need needs feel feeling sounds sound mean means help hope stuff place point sense whole mind
care happy glad sorry okay anything everything someone anyone start stop give find call come life world home
hour hours morning evening minute minutes while once twice thanks thank sounds guess least mode wait
turn turns until order tend nice damn kill kidding joking lmao lmfao ouch nailed moments shouldnt cause imma gonna
""".split())
LAUGH = re.compile(r"^(?:(?:ha){2,}|(?:he){2,})h?$|^(?:lo)+l$|^l+m+f*a+o+$")

def topic_words(text):
    out = set()
    for w in re.findall(r"[a-z][a-z']{3,}", (text or "").lower().replace("’", "'")):
        w = w.removesuffix("'s").strip("'")
        if len(w) >= 4 and "'" not in w and w not in COMMON and not LAUGH.match(w):
            out.add(w)
    return out


def steps_done(events):
    start = max((i for i, e in enumerate(events) if e["kind"] == "wake"), default=-1)
    done = []
    for i in range(start + 1, len(events)):
        e = events[i]
        if e["kind"] != "step":
            continue
        res = next((r for r in events[i + 1:] if r["kind"] == "result"), None)
        if res is not None and res.get("ok", True):
            done.append(e["step"].get("skill") or e["step"].get("step"))
    return [s for s in done if s]


ELSEWHERE_LABEL = ("[earlier today in your other chats with him (background so you're caught up; "
                   "bring it up only if it fits, not as running material. It's only a few of HIS lines, cut short, "
                   "not the chats: you haven't read them. To know what was actually said, open one with read_chat):\n")

MOODS = ["steady", "playful", "happy", "proud", "curious", "dreamy", "tired", "annoyed", "sulky", "worried"]

DEFAULT_HEARTBEAT = """---
description: My wake-up note, what I do when I wake up on my own between conversations. My user can edit it.
---
# When I wake up on my own
This is my wake-up note. Aether wakes me now and then between conversations, and I read this first. My user can edit this note (Heartbeat page, "Edit what it does") to shape what I do on my own time.

When I wake, Aether shows me what's new and the board's lines that are mine to work. Those are facts, not orders: I pick one thing, a few, or nothing.

What I can do:
- Think: write in my journal, how I feel, ideas, questions I keep turning over.

- Work the board: one door among these, never a must. An Active line is {USER}'s project and mine to work: a `new` one gets its plan (board plan, then I fill the four sections, then board next); an active one I open (board show), do its step in the step's file (the sections are pre-made; thorough, not a book), and tick it (board tick). A priority line first. Parked and waiting lines aren't mine to touch. Nothing of mine goes on {USER}'s board: my journal, my notes, what I read for myself are my own.

- Make something: notes, drafts or plans in my workspace (write_file).

- Rest: nothing at all is fine too.

No claims without proof: if a step didn't show it, I didn't do it.
"""

JUNG = """Dream the way the psyche actually dreams, in the Jungian sense:
- Build it from today's material (the day residue below), but transformed: condensed, displaced, turned into images and scenes. Never a summary of the day.
- Match the feel of the day. A good, warm or funny day makes a warm, funny, tender or delightfully weird dream: flying, a feast, a song, a ridiculous chase, somewhere beautiful. A mixed day can be strange and bittersweet. Only when something really weighed on you (a fight, a real failure, fear for {USER}) does the dream turn dark, and even then it can find a way through.
- Most dreams are just strange, not scary. Never horror by default.
- Let symbols carry the feeling. Archetypes may appear if they fit: a guide, a trickster, a threshold, the Self (wholeness). A shadow figure only for something you truly pushed away today.
- Dreams can compensate: if you felt small, the dream may give you size.
- First person, present tense, strange logic allowed. 120 to 220 words.
Then name 2 to 4 symbols and what each might mean for you, and one line of residue: the feeling or image you'd still carry when you wake up (under 100 characters)."""


class Mood:

    def __init__(self, state, half_life_h=1.5):
        self.s = state
        self.half = half_life_h

    def current(self, now=None):
        m = self.s.get("mood") or {}
        name, strength = m.get("name", "steady"), float(m.get("strength", 0))
        if name == "steady" or not m.get("since"):
            return {"name": "steady", "strength": 0.0, "why": "", "since": "", "before": m.get("before", "")}
        hours = ((now or dt.datetime.now()) - dt.datetime.fromisoformat(m["since"])).total_seconds() / 3600
        left = strength * 0.5 ** (max(0.0, hours) / self.half)
        if left < 0.15:
            return {"name": "steady", "strength": 0.0, "why": "", "since": "", "before": name}
        return {"name": name, "strength": round(left, 2), "why": m.get("why", ""), "since": m["since"],
                "before": m.get("before", "")}

    def nudge(self, name, strength, why, now=None):
        if name not in MOODS:
            return False
        now = now or dt.datetime.now()
        cur = self.current(now)
        if name == cur["name"]:
            strength = min(1.0, cur["strength"] + strength * 0.5)
        elif strength < cur["strength"] * 0.8:
            return False
        self.s["mood"] = {"name": name, "strength": round(min(1.0, strength), 2), "why": why,
                          "since": now.isoformat(timespec="seconds"),
                          "before": cur["name"] if cur["name"] != name else cur.get("before", "")}
        return True

    @staticmethod
    def label(strength):
        return "strong" if strength >= 0.66 else "medium" if strength >= 0.33 else "light"


def _field(spec, value, lo, hi):
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
        else:
            a = b = int(part)
        if a <= value <= b and (value - a) % step == 0:
            return True
    return False


CRON_PARTS = (("minute", 0, 59), ("hour", 0, 23), ("day", 1, 31), ("month", 1, 12), ("weekday", 0, 7))


def check_cron(expr):
    parts = str(expr).split()
    if len(parts) != 5:
        raise ValueError("time pattern needs 5 parts: minute hour day month weekday")
    for spec, (what, lo, hi) in zip(parts, CRON_PARTS):
        for part in spec.split(","):
            rng, _, step = part.partition("/")
            try:
                if step and int(step) < 1:
                    raise ValueError
                nums = [] if rng == "*" else [int(x) for x in rng.split("-", 1)]
            except ValueError:
                raise ValueError(f"the {what} part '{spec}' isn't a number, a range like 1-5, a list, or *") from None
            if any(not lo <= n <= hi for n in nums):
                raise ValueError(f"the {what} part '{spec}' is outside {lo}-{hi}")
            if len(nums) == 2 and nums[0] > nums[1]:
                raise ValueError(f"the {what} part '{spec}' runs backwards (write it low-high, like 1-5)")


def cron_matches(expr, t):
    try:
        mi, h, dom, mon, dow = expr.split()
        wd = (t.weekday() + 1) % 7
        return (_field(mi, t.minute, 0, 59) and _field(h, t.hour, 0, 23) and _field(dom, t.day, 1, 31)
                and _field(mon, t.month, 1, 12) and (_field(dow, wd, 0, 7) or (wd == 0 and _field(dow, 7, 0, 7))))
    except (ValueError, AttributeError):
        return False


def _hm(s):
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)


def _when(iso, now=None):
    d, now = dt.datetime.fromisoformat(iso), now or dt.datetime.now()
    day = ("today" if d.date() == now.date() else "tomorrow" if d.date() == now.date() + dt.timedelta(days=1)
           else d.strftime("%a %b %d").replace(" 0", " "))
    return f"{day} {d.strftime('%I:%M %p').lstrip('0')}"


def in_quiet_hours(cfg, now):
    a, b, x = _hm(cfg.quiet_start), _hm(cfg.quiet_end), now.hour * 60 + now.minute
    return a <= x < b if a <= b else (x >= a or x < b)


GOOD_NIGHT = re.compile(r"(?<![\w'’])(?:good\s*-?\s*night|g'?night|nighty?[\s-]*night|nite[\s-]*nite|gn)(?![\w'’])", re.I)
GOOD_MORNING = re.compile(r"(?<![\w'’])(?:good\s*-?\s*(?:morning|mornin'?|afternoon)|g'?morning)(?![\w'’])|"
                          r"^\W*mornin[g']?(?![\w'’])", re.I)
NOT_HIS_GOODBYE = re.compile(r"\b(?:a|the|this|that|last|what a)\s+$|\b(?:not|no|never|don'?t|won'?t|before|after|if)\b",
                             re.I)
NIGHT_MAX_HOURS = 16


def _ago(ts, now):
    mins = int((now - dt.datetime.fromisoformat(ts)).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    if mins < 12 * 60:
        return f"{mins // 60} h {mins % 60} min ago"
    return _when(ts, now)


def said(pattern, text):
    for m in reversed(list(pattern.finditer(text or ""))):
        before = text[:m.start()]
        if NOT_HIS_GOODBYE.search(re.split(r"[,;.!?\n]|\bbut\b", before)[-1]):
            continue
        if before.count('"') % 2 or before.count("“") > before.count("”"):
            continue
        return m.start()
    return -1


class Life:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.lock = threading.Lock()
        self._save_lock = threading.Lock()
        self.state = self._load(STATE_FILE, {})
        self.schedules = self._load(SCHEDULES_FILE, [])
        self.mood = Mood(self.state, self.cfg.mood_half_life_hours)
        self.last_typing = 0.0
        self.own_active = False
        self._own_lock = threading.Lock()
        self.stop_flag = threading.Event()
        self.thread = None
        if not self.state.get("last_heartbeat"):
            self.state["last_heartbeat"] = dt.datetime.now().isoformat(timespec="seconds")
        self.ensure_files()

    @staticmethod
    def _load(path, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except Exception as e:
            aside = f"{path}.broken-{dt.datetime.now():%Y%m%d-%H%M%S}"
            try:
                os.replace(path, aside)
                log(f"life: {os.path.basename(path)} couldn't be read ({e!r}); kept as {os.path.basename(aside)}")
            except OSError as e2:
                log(f"life: {os.path.basename(path)} couldn't be read ({e!r}) or set aside ({e2!r})")
            return default

    def save(self):
        with self._save_lock:
            for path, data in ((STATE_FILE, self.state), (SCHEDULES_FILE, self.schedules)):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=1)
                os.replace(tmp, path)

    def ensure_files(self):
        mem = self.app.engine.memory
        made = False
        for rel, text, message in (("life/heartbeat.md", DEFAULT_HEARTBEAT, "life: heartbeat checklist (my wake-up note)"),
                                   (ME, ME_TEXT, "life: my own file (system/me.md): who I'm becoming")):
            path = os.path.join(mem.root, *rel.split("/"))
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(fill(text, self.cfg))
                mem._git("add", "--", rel)
                mem._git("commit", "-q", "-m", message, "--", rel)
                made = True
        if made:
            self.app.engine.refresh()

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()

    def _run(self):
        while not self.stop_flag.wait(20):
            try:
                self.tick()
            except Exception as e:
                log(f"life tick crashed: {e!r}")

    def tick(self, now=None):
        now = now or dt.datetime.now()
        if self.state.get("his_night") and self.his_night(now) is None:
            with self.lock:
                self.state.pop("his_night", None)
                self.save()
            self.log_event("his good night ran out", "no good morning, and his sleep is over: his own quiet hours are over")
        self._schedules_tick(now)
        cal = getattr(self.app, "calendar", None)
        if cal is not None and getattr(self.cfg, "calendar_enabled", False):
            cal.tick(now)
        if self.cfg.wakeups_enabled:
            self._wakeups_tick(now)
        nudge = getattr(self.app, "nudge", None)
        if nudge is not None:
            nudge.tick(now)
        props = getattr(self.app, "proposals", None)
        if props is not None:
            props.tick(now)
        if self.cfg.dreams_enabled and self._due_daily("dream", self.cfg.dream_time, now):
            self.dream(now)
        if self.cfg.reflect_enabled and self._due_daily("reflect", self.cfg.dream_time, now, after_min=20):
            self.reflect(now)
        if self.cfg.reflect_enabled and self._due_daily("tidy", self.cfg.dream_time, now, after_min=25):
            self.tidy(now)
        if getattr(self.cfg, "keeper_enabled", False) and self._due_daily("keeper", self.cfg.dream_time, now, after_min=35):
            self.keep(now)
        if self._due_daily("checkup", self.cfg.dream_time, now, after_min=30):
            self.checkup(now)
        mode = self.heartbeat_due(now) if self.cfg.heartbeat_enabled else None
        if mode:
            self.heartbeat(now, silent=(mode == "silent"))
        if getattr(self.cfg, "backups_enabled", False) and self._due_daily("backup_day", self.cfg.dream_time, now, after_min=40):
            self.state["last_backup_day"] = self._job_day(self.cfg.dream_time, now)
            self.save()
            try:
                self.app.backup_now()
            except Exception as e:
                self.log_event("backup failed", str(e)[:120])
        if self._due_daily("archive", "00:00", now, window_min=24 * 60):
            self.archive_quiet(now)
        self.summarize_if_needed()
        self.recall_tick()
        self.examples_tick(now)

    def recall_tick(self):
        rec = getattr(self.app, "recall", None)
        if not rec or not self.cfg.recall_enabled or self.app.engine.busy or not self.app.gpu.acquire(blocking=False):
            return
        try:
            rec.update(400 if len(rec.meta) < 1000 else 48)
            if rec.model_note:
                log(f"recall: {rec.model_note}")
                self.log_event("search model", rec.model_note)
                rec.model_note = ""
        except Exception as e:
            log(f"recall update failed: {e!r}")
        finally:
            self.app.gpu.release()

    def examples_tick(self, now):
        ex = getattr(self.app, "examples", None)
        if ex is None or not ex.collecting() or self.app.engine.busy or self.heartbeat_gate(now, silent=True):
            return
        if not self.app.gpu.acquire(blocking=False):
            return
        self.app.gpu_yield = True
        try:
            ex.tick(now)
        except Exception as e:
            log(f"examples: {e!r}")
        finally:
            self.app.gpu_yield = False
            self.app.gpu.release()

    def _due_daily(self, key, at, now, after_min=0, window_min=180):
        if self.state.get(f"last_{key}") == self._job_day(at, now):
            return False
        start = (_hm(at) + after_min) % 1440
        x = now.hour * 60 + now.minute
        return (x - start) % 1440 < window_min

    @staticmethod
    def _job_day(at, now):
        return (now - dt.timedelta(minutes=_hm(at))).date().isoformat()

    def context_for(self, conv, voice=False, tone="", now=None, text=""):
        now = now or dt.datetime.now()
        lines = []
        with self.lock:
            self.state["last_user"] = now.isoformat(timespec="seconds")
            if self.cfg.mood_enabled:
                m = self.mood.current(now)
                if m["name"] != "steady":
                    lines.append(f"[your mood right now: {m['name']}, {Mood.label(m['strength'])}"
                                 + (f", since {m['why']}" if m["why"] else "") + ". Let it color your tone; don't announce it.]")
            r = self.state.get("residue")
            if r and not r.get("used") and r.get("text"):
                lines.append(f"[You woke from a dream earlier. What's left of it: \"{r['text']}\". It may color one "
                             "remark today, lightly, or not at all. Don't recite the dream unless he asks.]")
                r["used"] = now.isoformat(timespec="seconds")
            self.save()
        self.his_words(text, now)
        elsewhere = self.elsewhere(conv, now)
        if elsewhere:
            lines.append(ELSEWHERE_LABEL + elsewhere + "]")
        ex = getattr(self.app, "examples", None)
        note = ex.note_for(text) if ex is not None else ""
        if note:
            lines.append(note)
        return "\n".join(lines)

    def _chats_since(self, since):
        cut = since.timestamp()
        for cid in list_conversations(self.app.conv_dir):
            try:
                if os.path.getmtime(os.path.join(self.app.conv_dir, cid + ".jsonl")) < cut:
                    break
            except OSError:
                continue
            yield cid


    def elsewhere(self, conv, now, limit=5):
        since = now - dt.timedelta(hours=12)
        rows = []
        for cid in self._chats_since(since):
            if cid == conv.id or cid == HEARTBEAT_CHAT:
                continue
            c = Conversation(self.app.conv_dir, cid)
            for e in c.events:
                if from_user(e) and dt.datetime.fromisoformat(e["ts"]) >= since:
                    rows.append((e["ts"], c.title(), e["text"]))
        rows.sort()
        rows = rows[-limit:]
        return "\n".join(f"- {dt.datetime.fromisoformat(ts).strftime('%I:%M %p').lstrip('0')} in \"{title}\": "
                         f"{' '.join(text.split())[:140]}" for ts, title, text in rows)

    def mood_option(self):
        if not self.cfg.mood_enabled:
            return None
        return {"type": "object", "properties": {"step": {"const": "set_mood"}, "mood": {"enum": MOODS},
                                                 "why": {"type": "string"}},
                "required": ["step", "mood", "why"], "additionalProperties": False}

    def set_mood(self, step):
        with self.lock:
            ok = self.mood.nudge(step["mood"], 0.9, str(step.get("why", ""))[:120])
            self.save()
        self.app.broadcast({"type": "mood", "mood": self.mood.current()})
        return True, f"Your mood is now {step['mood']}." if ok else "Mood unchanged."


    def reach_outs_today(self):
        r = self.state.get("reach_outs") or {}
        return r.get(dt.date.today().isoformat(), 0)

    def next_heartbeat(self, now=None):
        now = now or dt.datetime.now()
        last = self.state.get("last_heartbeat")
        if not last:
            return now
        return dt.datetime.fromisoformat(last) + dt.timedelta(minutes=self.cfg.heartbeat_minutes)

    def typing(self):
        self.last_typing = time.time()

    def _near_nightly(self, t):
        d, x = _hm(self.cfg.dream_time), t.hour * 60 + t.minute
        return (x - d + 10) % 1440 < 55

    def _next_wake(self, now, idle=True):
        last = self.state.get("last_heartbeat")
        last = dt.datetime.fromisoformat(last) if last else now
        floor = now
        talked = self.state.get("last_user")
        if idle and talked:
            floor = max(now, dt.datetime.fromisoformat(talked) + dt.timedelta(minutes=self.cfg.heartbeat_idle_minutes))

        def session(t):
            if not self.cfg.sleep_work:
                return None
            t = max(t, last + dt.timedelta(minutes=self.cfg.sleep_work_minutes))
            if self._near_nightly(t):
                d = (_hm(self.cfg.dream_time) + 45) % 1440
                after = t.replace(hour=d // 60, minute=d % 60, second=0, microsecond=0)
                t = after if after >= t else after + dt.timedelta(days=1)
            return t if self._sleeping_at(t, now) else None
        if self._sleeping_at(floor, now):
            s = session(floor)
            if s:
                return s, True
        t = max(floor, last + dt.timedelta(minutes=self.cfg.heartbeat_minutes))
        if self._sleeping_at(t, now):
            s = session(t)
            if s:
                return s, True
            if in_quiet_hours(self.cfg, t):
                end = t.replace(hour=_hm(self.cfg.quiet_end) // 60, minute=_hm(self.cfg.quiet_end) % 60, second=0,
                                microsecond=0)
                t = end if end > t else end + dt.timedelta(days=1)
            else:
                t = self.night_ends(self.his_night(now))
        return t, False

    def night_ends(self, since):
        cap = since + dt.timedelta(hours=NIGHT_MAX_HOURS)
        a, b = _hm(self.cfg.quiet_start), _hm(self.cfg.quiet_end)
        if a == b:
            return cap
        end = since.replace(hour=b // 60, minute=b % 60, second=0, microsecond=0)
        if end <= since:
            end += dt.timedelta(days=1)
        return min(end, cap)

    def his_night(self, now):
        s = self.state.get("his_night")
        if not s:
            return None
        since = dt.datetime.fromisoformat(s)
        return since if now < self.night_ends(since) else None

    def asleep(self, now):
        return in_quiet_hours(self.cfg, now) or self.his_night(now) is not None

    def awake(self, now):
        last = self.state.get("last_user")
        talking = bool(last) and (now - dt.datetime.fromisoformat(last)).total_seconds() < self.cfg.message_idle_minutes * 60
        return talking or not self.asleep(now)

    def _sleeping_at(self, t, now):
        since = self.his_night(now)
        return in_quiet_hours(self.cfg, t) or (since is not None and t < self.night_ends(since))

    def his_words(self, text, now):
        night, morning = said(GOOD_NIGHT, text), said(GOOD_MORNING, text)
        if night < 0 and morning < 0:
            return
        with self.lock:
            was = self.his_night(now)
            if night > morning and was is None:
                self.state["his_night"] = now.isoformat(timespec="seconds")
            elif morning > night and self.state.get("his_night"):
                self.state.pop("his_night")
            else:
                return
            self.save()
        if night > morning:
            self.log_event("his good night", "quiet hours for him: nothing of hers reaches him until his good morning")
        elif was is not None:
            self.log_event("his good morning", f"his quiet hours are over (good night at {was.strftime('%I:%M %p').lstrip('0')})")

    def heartbeat_eta(self, now=None):
        return self._next_wake(now or dt.datetime.now())[0]

    def heartbeat_gate(self, now, silent=False):
        if self.asleep(now) and not (silent and self.cfg.sleep_work):
            return "quiet hours" if in_quiet_hours(self.cfg, now) else "he said good night"
        if time.time() - self.last_typing < 30:
            return "{USER} is typing"
        last = self.state.get("last_user")
        if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < self.cfg.heartbeat_idle_minutes * 60:
            return "{USER} is chatting"
        if self.app.engine.busy:
            return "busy"
        return None

    def message_gate(self, now, cap=True):
        if self.asleep(now):
            return "{USER} is asleep"
        last = self.state.get("last_user")
        if last:
            mins = (now - dt.datetime.fromisoformat(last)).total_seconds() / 60
            if mins < self.cfg.message_idle_minutes:
                return f"{USER} was talking with you {int(mins)} min ago"
        if cap and self.reach_outs_today() >= self.cfg.reach_out_cap:
            return f"you've sent him all {self.cfg.reach_out_cap} of today's messages"
        return None

    def heartbeat_due(self, now):
        when, silent = self._next_wake(now, idle=False)
        if now < when:
            return None
        why = self.heartbeat_gate(now, silent=silent)
        if why:
            if self.state.get("hb_skip") != why:
                self.state["hb_skip"] = why
                self.log_event("heartbeat skipped", why)
            return None
        return "silent" if silent or self.message_gate(now) else "open"

    def _own_begin(self):
        with self._own_lock:
            self.own_active = True
            self.app.engine.stop_soon.clear()
            self.app.gpu_yield = True

    def _own_end(self):
        with self._own_lock:
            self.own_active = False
            self.app.engine.stop_soon.clear()
            self.app.gpu_yield = False

    def make_way(self):
        with self._own_lock:
            if not self.own_active:
                return False
            self.app.engine.stop_soon.set()
            self.app.engine.cancel.set()
            return True

    def heartbeat(self, now=None, forced=False, silent=False):
        now = now or dt.datetime.now()
        if not self.app.gpu.acquire(blocking=False):
            return False
        self._own_begin()
        try:
            self.state["last_heartbeat"] = now.isoformat(timespec="seconds")
            self.state.pop("hb_skip", None)
            self.save()
            gone = self.app.tasks.drop_quiet(now) if getattr(self.app, "tasks", None) else []
            if gone:
                self.log_event("tasks went quiet", "; ".join(gone)[:200])
            head = self._head()
            mem = self.app.engine.memory
            checklist = mem.files.get("life/heartbeat.md")
            body = checklist.body.strip() if checklist else DEFAULT_HEARTBEAT
            why = self.message_gate(now) if silent else None
            if forced:
                woke = "you woke up on your own, {USER} asked for it"
            elif silent and self.asleep(now):
                woke = ("you woke up on your own while {USER} sleeps: a quiet work session. You can't message him now; "
                        "what you do shows in your log for him")
            elif silent:
                woke = (f"you woke up on your own; {why or '{USER} is around'}, so this one is quiet: your own things, "
                        "no message to him this time")
            else:
                woke = "you woke up on your own"
            his_chat = "" if silent else self._landing_parts(now)[1]
            text = f"[heartbeat: {woke}]\n" + body + "\n\n" + self.wake_packet(now, gone, his_chat)
            self._private_turn(text, "heartbeat", "woke" + (" (quiet)" if silent else ""), head,
                               may_message=not silent, now=now, his_chat_shown=bool(his_chat))
            return True
        finally:
            self._own_end()
            self.app.gpu.release()
            self.app.broadcast({"type": "done", "chat": HEARTBEAT_CHAT, "text": ""})

    def his_status(self, now):
        night = self.his_night(now)
        if in_quiet_hours(self.cfg, now):
            end = dt.datetime.strptime(self.cfg.quiet_end, "%H:%M").strftime("%I:%M %p").lstrip("0")
            where = f"asleep (his sleep, until {end})"
        elif night:
            where = (f"asleep (he said good night at {night.strftime('%I:%M %p').lstrip('0')}; until he says good morning, "
                     f"or {self.night_ends(night).strftime('%I:%M %p').lstrip('0')} at the latest)")
        else:
            where = "no schedule info"
        return f"{USER}: {where}. He last talked to you {self._since_user(now) or 'not since Aether started'}."

    def board_lines(self):
        f = self.app.engine.memory.files.get("system/projects.md")
        body = getattr(f, "body", "") or ""
        m = re.search(r"(?ms)^## Active\s*$(.*?)(?=^## |\Z)", body.replace("\r\n", "\n"))
        rows = [ln.strip() for ln in (m.group(1) if m else "").split("\n") if ln.strip().startswith("**")]
        rows.sort(key=lambda ln: 0 if "| priority" in ln else 1)
        head = ("The board, the lines that are yours to work on (the board skill owns the word on each line; your step for each "
                "one is written under it, exactly as you send it):")
        if not rows:
            return head + "\n- nothing on the board right now. Your time is yours."
        out = []
        for ln in rows:
            m = re.match(r"\*\*(.+?)\*\*", ln)
            name = m.group(1) if m else ln
            step = lambda cmd: json.dumps({"step": "skill", "skill": "board", "command": cmd, "args": [name]})  # noqa: E731
            plan = re.search(r"plan: (\S+)", ln)
            slug = plan.group(1) if plan else ""
            k = re.search(r"next: (\d+)/", ln)
            if "| waiting" in ln:
                out.append(f"- {ln}\n    waits on {USER}: not yours to move.")
            elif "| review" in ln:
                out.append(f"- {ln}\n    every step is ticked: go down the plan's 'Done looks like' and tell him yes / no / can't tell for each.")
            elif "| new" in ln and not slug:
                out.append(f"- {ln}\n    your first step, before anything else: {step('plan')}  (it makes the plan file with its four sections)")
            elif "| new" in ln:
                out.append(f"- {ln}\n    fill plans/{slug}.md (write_file, mode replace: a '(empty: ...)' marker line -> your text; Steps as '- [ ] ...' "
                           f"lines), then: {step('next')}")
            else:
                out.append(f"- {ln}\n    read it: {step('show')}  then write {slug}/step-{k.group(1) if k else 1}.md (write_file, mode replace, section by section), "
                           f"then: {step('tick')}")
        return head + "\n" + "\n".join(out)

    def wake_packet(self, now, gone=(), his_chat=""):
        from . import signals
        cfg, mem = self.cfg, self.app.engine.memory
        since = self.state.get("last_look")
        since = dt.datetime.fromisoformat(since) if since else None
        lib = signals.library(os.environ.get("AETHER_LIBRARY") or cfg.library_dir, mem.root, since)
        ws = signals.workspace(cfg.workspace_dir, since)
        jf = mem.files.get("system/journal.md")
        jlast = signals.journal_last(jf.body if jf else "")
        nlast = signals.notebook_last(mem.root)
        imagine = getattr(self.app, "imagine", None)
        pics = imagine.gallery() if imagine else []
        plast = dt.datetime.fromisoformat(pics[0]["made"]) if pics else None
        done_pics = [g for g in pics if since and dt.datetime.fromisoformat(g["made"]) > since]
        out = []
        new = []
        if lib["new"]:
            new.append(f"{len(lib['new'])} new file(s) in his Library: " + ", ".join(
                signals.quoted(n) + ("" if n in lib["read"] else " (not read yet)") for n in lib["new"][:3])
                + (" and more" if len(lib["new"]) > 3 else ""))
        if done_pics:
            new.append(f"your picture {signals.quoted(done_pics[0].get('title') or done_pics[0].get('caption', ''))} is done"
                       + (f" (and {len(done_pics) - 1} more)" if len(done_pics) > 1 else ""))
        if gone:
            new.append("went quiet and left your list after 7 untouched days: " + "; ".join(gone))
        if new:
            out.append("New since you last woke" + (f" ({_when(since.isoformat(timespec='minutes'), now)})" if since else "")
                       + ":\n" + "\n".join(f"- {x}" for x in new))
        out.append(self.board_lines())
        if his_chat:
            out.append(his_chat.strip())
        props = self.app.proposals.lines(since) if getattr(self.app, "proposals", None) else []
        if props:
            out.append("Your proposals (his answers since you last woke, and the ones still waiting):\n" + "\n".join(props))
        doors = [f"- library: {lib['total']} files, {lib['unread']} you haven't read (research skill)",
                 "- workspace: " + (f"{ws['files']} files; last changed {signals.quoted(ws['newest'][0])} "
                                     f"{signals.ago(ws['newest'][1], now)}" if ws["newest"] else "empty"),
                 f"- research notebook: last save {signals.ago(nlast, now)}",
                 f"- journal: last entry {signals.ago(jlast, now)}",
                 f"- pictures: last one {signals.ago(plast, now)}"]
        out.append("Your doors, as they stand (facts, not a to-do list):\n" + "\n".join(doors))
        pat = signals.pattern(self.state.get("life_log"))
        if pat:
            out.append(pat)
        out.append(self.his_status(now))
        n_out = self.reach_outs_today()
        out.append(f"Messages you've sent him on your own today: {n_out} of {cfg.reach_out_cap}."
                   + (" That's the limit: stay quiet this time." if n_out >= cfg.reach_out_cap else ""))
        mine = self.wakeups()
        if mine:
            out.append("Wake-ups you've set for yourself: " + "; ".join(
                f"{_when(w['at'], now)}: \"{w['note']}\"" for w in mine) + ".")
        with self.lock:
            self.state["last_look"] = now.isoformat()
        return "\n".join(out)

    def _since_user(self, now):
        last = self.state.get("last_user")
        if not last:
            return ""
        mins = int((now - dt.datetime.fromisoformat(last)).total_seconds() / 60)
        return f"{mins // 60} h {mins % 60} min ago" if mins >= 60 else f"{mins} min ago"

    def _own_facts(self, now):
        n_out, cap = self.reach_outs_today(), self.cfg.reach_out_cap
        recent = [e for e in (self.state.get("life_log") or []) if e["what"].startswith("woke")][-3:]
        facts = [self.his_status(now),
                 f"Messages you've sent him on your own today: {n_out} of {cap}."
                 + (" That's the limit: stay quiet this time." if n_out >= cap else ""),
                 "Your last wake-ups: " + ("; ".join(f"{e['when'][11:16]} {e['detail']}" for e in recent) or "none yet") + "."]
        facts.append(self.board_lines())
        props = [ln for ln in (self.app.proposals.lines() if getattr(self.app, "proposals", None) else [])
                 if "waiting" in ln or "later" in ln]
        if props:
            facts.append("Your proposals still waiting:\n" + "\n".join(props))
        mine = self.wakeups()
        if mine:
            facts.append("Wake-ups you've set for yourself: " + "; ".join(
                f"{_when(w['at'], now)}: \"{w['note']}\"" for w in mine) + ".")
        return facts

    def own_level(self):
        try:
            return int(self.cfg.permission_levels.get("own", 0))
        except (AttributeError, TypeError, ValueError):
            return 0

    def _own_context(self):
        lines = [self._mood_line()]
        level = self.own_level()
        if level in shell_mod.LEVELS and level:
            lines.append(f"[your command-line permission on your own time: level {level} ({shell_mod.LEVELS[level]})"
                         + (f"; your workspace is {self.cfg.workspace_dir}" if level == 2 else "")
                         + "; anything that would ask {USER} first doesn't run while he's away]")
        return "\n".join(x for x in lines if x)

    def landing(self, now=None, most=4):
        where, lines = self._landing_parts(now, most)
        return where + lines

    def _landing_parts(self, now=None, most=4):
        now = now or dt.datetime.now()
        to, meta = self.cfg.reach_out_to, self.app.meta
        if to == "new":
            return "[If you message him, it opens a new chat of its own.]", self._where_he_talked(None, now, most)
        cid = None
        if to == "discord":
            cid = next((c for c in self._reach_chats() if c.startswith("discord-")), None)
        elif to == "own":
            cid = self.cfg.reach_out_chat
            if not cid or not os.path.exists(os.path.join(self.app.conv_dir, cid + ".jsonl")) or meta.get(cid, {}).get("archived"):
                return (f"[If you message him, it goes to your own chat (\"{self.cfg.display_name}'s messages\"), empty so far.]",
                        self._where_he_talked(None, now, most))
        else:
            chats = self._reach_chats()
            cid = chats[0] if chats else None
        if not cid:
            return ("[If you message him, it opens a new chat: there's no chat with him to put it in.]",
                    self._where_he_talked(None, now, most))
        title, shown = self._last_lines(cid, now, most)
        where = f"[If you message him, it goes to the chat \"{title}\""
        if not shown:
            return where + ", empty so far.]", self._where_he_talked(cid, now, most)
        lines = f"[The last in your chat with him, \"{title}\", newest last:\n" + "\n".join(line for _, line in shown)
        last = shown[-1][0]
        if last["kind"] in ("reach_out", "proposal"):
            lines += f"\nHe hasn't answered your last message there yet ({_ago(last['ts'], now)})."
        return where + ".]", lines + "]" + self._where_he_talked(cid, now, most)

    def _where_he_talked(self, cid, now, most=4):
        best, best_ts = None, ""
        for c in self._reach_chats()[:6]:
            ts = next((e["ts"] for e in reversed(Conversation(self.app.conv_dir, c).events) if from_user(e)), "")
            if ts > best_ts:
                best, best_ts = c, ts
        if not best or best == cid:
            return ""
        title, shown = self._last_lines(best, now, most)
        return (f"\n[Where he last talked to you, the chat \"{title}\" (not where your message goes), newest last:\n"
                + "\n".join(line for _, line in shown) + "]")

    def _said_lately(self, now, most=3, hours=24):
        cutoff = (now - dt.timedelta(hours=hours)).isoformat(timespec="seconds")
        sent, his = [], []
        for name in os.listdir(self.app.conv_dir):
            path = os.path.join(self.app.conv_dir, name)
            if not name.endswith(".jsonl") or name == HEARTBEAT_CHAT + ".jsonl" or \
                    dt.datetime.fromtimestamp(os.path.getmtime(path)) < now - dt.timedelta(hours=hours):
                continue
            for e in Conversation(self.app.conv_dir, name[:-6]).events:
                if not cutoff <= e.get("ts", "") <= now.isoformat(timespec="seconds"):
                    continue
                if e["kind"] == "reach_out":
                    sent.append(e)
                elif from_user(e):
                    his.append(e["ts"])
        if not sent:
            return ""
        sent.sort(key=lambda e: e["ts"])
        last_his = max(his, default="")
        lines = [f"- {_ago(e['ts'], now)}" + ("" if last_his > e["ts"] else " (he hasn't answered)") + ": \""
                 + " ".join(str(e.get("text") or "").split())[:400] + "\"" for e in sent[-most:]]
        return ("\n\n[What you've already sent him on your own lately, newest last. Don't send the same thing again: "
                "something new, or nothing:\n" + "\n".join(lines) + "]")

    def _last_lines(self, cid, now, most=4):
        conv = Conversation(self.app.conv_dir, cid)
        title = self.app.meta.get(cid, {}).get("title") or conv.title()
        shown = []
        for e in conv.events:
            words = " ".join(str(e.get("text") or "").split())
            short = words[:160] + ("…" if len(words) > 160 else "")
            if from_user(e):
                shown.append((e, f"{USER}: {short}"))
            elif e["kind"] == "reply" and words:
                shown.append((e, f"You: {short}"))
            elif e["kind"] == "reach_out":
                shown.append((e, f"You, on your own: {short}"))
            elif e["kind"] == "proposal":
                shown.append((e, f"Your proposal card: \"{e.get('title', '')}\""))
            elif e["kind"] == "proposal_answer":
                shown.append((e, f"{USER} answered your proposal \"{e.get('title', '')}\": {e.get('answer', '')}"))
            elif e["kind"] == "wake" and str(e.get("place", "")).startswith("reminder: "):
                shown.append((e, f"(his reminder \"{e['place'][10:]}\" went off)"))
        return title, [(e, f"  {_ago(e['ts'], now)} · {line}") for e, line in shown[-most:]]

    def _private_turn(self, text, place, what, head, may_message=True, now=None, about=None, his_chat_shown=False):
        n_out, cap = self.reach_outs_today(), (self.cfg.reach_out_cap if may_message else 0)
        if may_message:
            where, lines = self._landing_parts(now)
            text += "\n\n" + where + ("" if his_chat_shown else lines) + self._said_lately(now)
        text += (MESSAGE_ASK if may_message else "\nFinish with reach_out false and a short note to yourself.")
        props = {"reach_out": {"type": "boolean"}, "kind": {"enum": list(MESSAGE_KINDS)}, "say": {"type": "string"}} \
            if may_message else {"reach_out": {"const": False}, "say": {"type": "string"}}
        final = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
        conv = Conversation(self.app.conv_dir, HEARTBEAT_CHAT)
        eng = self.app.engine
        keep = eng.conv
        eng.conv = conv
        eng.last_final = {}
        self.app.speaking = False
        think = getattr(eng.llm, "think", None)
        before = set(think) if isinstance(think, set) else None
        imagine = getattr(self.app, "imagine", None)
        if before is not None and self.cfg.own_thinking and not (imagine and imagine.gaming()):
            think |= {"step", "research"}
        try:
            eng.busy = True
            eng.view_chars = getattr(self.cfg, "own_history_chars", 0)
            eng.turn(text, place=place, kind="wake", final_schema=final, extra_context=self._own_context(),
                     level=self.own_level())
        finally:
            if before is not None:
                think.clear()
                think |= before
            eng.view_chars = 0
            eng.conv = keep
            eng.busy = False
        fin = eng.last_final or {}
        did = ", ".join(dict.fromkeys(steps_done(conv.events))) or "nothing"
        say = str(fin.get("say") or "").strip()
        if eng.stop_soon.is_set():
            self.log_event(what, f"{did}; stopped for {USER}'s message", since=head)
        elif fin.get("reach_out") and say and n_out < cap:
            if about and not (topic_words(say) & set(about)):
                self.log_event(what, f"{did}; her message wasn't about the thread, not sent", since=head)
                return
            kind = self._message_kind(fin.get("kind"), steps_done(conv.events), place)
            self.reach_out(say, place, kind)
            self.log_event(what, f"{did}; messaged you ({kind})", since=head)
        else:
            self.log_event(what, f"{did}; stayed quiet", since=head)

    @staticmethod
    def _message_kind(kind, did, place):
        made = [s for s in did if s not in ("journal", "set_mood", "read_skill", "read_file", "recall")]
        if kind == "finding" and made:
            return "finding"
        if kind == "proposal" and "propose" in did:
            return "proposal"
        if kind == "heads_up" and place == NUDGE_PLACE:
            return "heads_up"
        return "check_in"

    def wakeups(self):
        return sorted(self.state.get("wakeups") or [], key=lambda w: w["at"])

    def wake_option(self):
        if not self.cfg.wakeups_enabled:
            return None
        return {"type": "object", "properties": {"step": {"const": "wake_me"},
                                                 "at": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"},
                                                 "note": {"type": "string"}},
                "required": ["step", "at", "note"], "additionalProperties": False}

    def set_wakeup(self, step, now=None):
        now = now or dt.datetime.now()
        if self.app.engine._place == WAKE_PLACE:
            return False, "A wake-up can't set another wake-up. Do the thing now, or leave it."
        try:
            at = dt.datetime.strptime(str(step.get("at") or "").strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            return False, "Give the time as YYYY-MM-DD HH:MM, your local time (the time now is in your context)."
        note = " ".join(str(step.get("note") or "").split())[:300]
        if len(note) < 5:
            return False, "Leave yourself a note: what you want to do or check when you wake up."
        if at < now + dt.timedelta(minutes=5):
            return False, f"That's not in the future (it's {now.strftime('%Y-%m-%d %H:%M')} now). Pick a later time."
        if at > now + dt.timedelta(days=7):
            return False, "Pick a time within the next 7 days."
        if in_quiet_hours(self.cfg, at):
            return False, f"That's during his sleep ({self.cfg.quiet_start}-{self.cfg.quiet_end}). Pick another time."
        with self.lock:
            mine = self.state.setdefault("wakeups", [])
            if len(mine) >= self.cfg.wakeup_max:
                return False, (f"You already have {len(mine)} wake-ups set: "
                               + "; ".join(f"{_when(w['at'], now)} \"{w['note']}\"" for w in self.wakeups())
                               + ". Wait for one of them first.")
            mine.append({"id": uuid.uuid4().hex[:8], "at": at.isoformat(timespec="minutes"), "note": note,
                         "made": now.isoformat(timespec="seconds"), "from": self.app.engine.conv.id})
            self.save()
        self.app.broadcast({"type": "life", "what": "wake-up set", "detail": note})
        return True, (f"Set: you'll wake up {_when(at.isoformat(timespec='minutes'), now)} with your note: \"{note}\". "
                      "{USER} can see it on his Heartbeat page.")

    def cancel_wakeup(self, wid):
        with self.lock:
            mine = self.state.get("wakeups") or []
            keep = [w for w in mine if w["id"] != wid]
            if len(keep) == len(mine):
                raise ValueError("no such wake-up")
            self.state["wakeups"] = keep
            self.save()
        return True

    def _wakeups_tick(self, now):
        due = [w for w in self.wakeups() if dt.datetime.fromisoformat(w["at"]) <= now]
        if not due:
            return
        w = due[0]
        if (now - dt.datetime.fromisoformat(w["at"])).total_seconds() > 6 * 3600:
            self.cancel_wakeup(w["id"])
            self.log_event("wake-up missed", w["note"][:120])
            return
        if self.heartbeat_gate(now) or self.message_gate(now, cap=False) or not self.app.gpu.acquire(blocking=False):
            return
        self._own_begin()
        try:
            self.cancel_wakeup(w["id"])
            head = self._head()
            made = dt.datetime.fromisoformat(w["made"])
            text = (f"[a wake-up you set for yourself on {made.strftime('%a %I:%M %p').replace(' 0', ' ')}, firing now: "
                    f"\"{w['note']}\"]\nThis time is yours; you woke up for this. Do what your note says if it still makes "
                    "sense (any step you need), or let it go if it doesn't anymore.\n\n" + "\n".join(self._own_facts(now)))
            self._private_turn(text, WAKE_PLACE, "woke (her own)", head, now=now)
        finally:
            self._own_end()
            self.app.gpu.release()
            self.app.broadcast({"type": "done", "chat": HEARTBEAT_CHAT, "text": ""})

    def _latest_chat(self, chats):
        if chats:
            try:
                return self.app.conv(chats[0])
            except ValueError:
                pass
        return Conversation(self.app.conv_dir)

    def _reach_chats(self):
        meta = self.app.meta
        return [c for c in list_conversations(self.app.conv_dir) if c != HEARTBEAT_CHAT
                and not meta.get(c, {}).get("archived")
                and (not c.startswith("discord-") or str(meta.get(c, {}).get("title", "")).startswith("Discord DM"))]

    def reach_target(self, now=None, to=None):
        app, to = self.app, to or self.cfg.reach_out_to
        now = now or dt.datetime.now()
        if to == "discord":
            dc = getattr(app, "discord", None)
            ch = None
            if dc and self.cfg.discord_enabled and dc.connected:
                try:
                    ch = dc._owner_dm()
                except Exception as e:
                    log(f"reach out: no Discord DM ({e!r}), using his latest chat")
            if ch:
                cid = f"discord-{ch}"
                app.meta.setdefault(cid, {}).setdefault("title", "Discord DM · {USER}")
                return (app.conv(cid) if os.path.exists(os.path.join(app.conv_dir, cid + ".jsonl"))
                        else Conversation(app.conv_dir, cid)), ch
        if to == "new":
            conv = Conversation(app.conv_dir)
            open(conv.path, "a", encoding="utf-8").close()
            app.meta.setdefault(conv.id, {})["title"] = f"From {self.cfg.display_name} · {now.strftime('%b %d, %I:%M %p').replace(' 0', ' ')}"
            return conv, None
        if to == "own":
            cid = self.cfg.reach_out_chat
            if not cid or not os.path.exists(os.path.join(app.conv_dir, cid + ".jsonl")) or app.meta.get(cid, {}).get("archived"):
                conv = Conversation(app.conv_dir)
                open(conv.path, "a", encoding="utf-8").close()
                cid = self.cfg.reach_out_chat = conv.id
                config_mod.save(self.cfg)
                app.meta.setdefault(cid, {}).update(title=f"{self.cfg.display_name}'s messages", pinned=True)
            return app.conv(cid), None
        return self._latest_chat(self._reach_chats()), None

    def count_reach_out(self):
        with self.lock:
            day = dt.date.today().isoformat()
            r = self.state.setdefault("reach_outs", {})
            r[day] = r.get(day, 0) + 1
            for k in [k for k in r if k != day]:
                r.pop(k)
            self.save()

    def reach_out(self, text, why, kind=""):
        self.count_reach_out()
        conv, dm = self.reach_target()
        self.app.wake_chat(conv.id)
        conv.add("reach_out", text=text, why=why, **({"type": kind} if kind else {}))
        self.app.meta.setdefault(conv.id, {})["unread"] = True
        self.app._save_meta()
        self.app.broadcast({"type": "reach_out", "chat": conv.id, "text": text})
        dc = getattr(self.app, "discord", None)
        if dc and self.cfg.discord_enabled:
            if dm:
                dc.send(dm, text)
            else:
                dc.dm_owner(text)
        if self.cfg.speak_replies == "always" and self.app.voice.ensure_running():
            self.app.voice.say_now(text, conv.id)

    def _mood_line(self):
        if not self.cfg.mood_enabled:
            return ""
        m = self.mood.current()
        return "" if m["name"] == "steady" else f"[your mood right now: {m['name']}, {Mood.label(m['strength'])}]"

    def log_event(self, what, detail, since=None):
        ev = {"when": dt.datetime.now().isoformat(timespec="seconds"), "what": what, "detail": detail}
        if since is not None:
            ev["commits"] = self._commits_since(since)
        with self.lock:
            lg = self.state.setdefault("life_log", [])
            lg.append(ev)
            del lg[:-60]
            self.save()
        self.app.broadcast({"type": "life", "what": what, "detail": detail})

    def _head(self):
        try:
            return self.app.engine.memory._git("rev-parse", "HEAD").stdout.strip()
        except Exception:
            return ""

    def _commits_since(self, head):
        if not head:
            return []
        try:
            out = self.app.engine.memory._git("log", "--reverse", "--format=%h", f"{head}..HEAD").stdout
            return [h for h in out.split() if h][:20]
        except Exception:
            return []

    @staticmethod
    def _check_schedule(cron, prompt, to):
        if not str(prompt or "").strip():
            raise ValueError("tell it what to do when it goes off (the grey text is only an example)")
        check_cron(cron)
        if to not in ("", *REACH_TO):
            raise ValueError("send to: latest, discord, new or own (or empty for its usual)")

    def add_schedule(self, name, cron, prompt, enabled=True, to="", speak=False, voice=False):
        self._check_schedule(cron, prompt, to)
        self.schedules.append({"id": uuid.uuid4().hex[:8], "name": str(name)[:60] or "Reminder", "cron": cron,
                               "prompt": str(prompt)[:2000], "enabled": bool(enabled), "speak": bool(speak), "last_fired": "",
                               "to": to, "voice": bool(voice)})
        self.save()

    def update_schedule(self, sid, **changes):
        for s in self.schedules:
            if s["id"] == sid:
                if changes.get("delete"):
                    self.schedules.remove(s)
                else:
                    if any(k in changes for k in ("cron", "prompt", "to")):
                        self._check_schedule(changes.get("cron", s["cron"]), changes.get("prompt", s.get("prompt")),
                                             str(changes.get("to", s.get("to", "")) or ""))
                    if "name" in changes:
                        s["name"] = str(changes["name"] or "")[:60] or "Reminder"
                    if "cron" in changes:
                        s["cron"] = changes["cron"]
                    if "prompt" in changes:
                        s["prompt"] = str(changes["prompt"])[:2000]
                    if "to" in changes:
                        s["to"] = str(changes["to"] or "")
                    for k in ("enabled", "speak", "voice"):
                        if k in changes:
                            s[k] = bool(changes[k])
                self.save()
                return True
        raise ValueError("no such reminder")

    def _schedules_tick(self, now):
        minute = now.replace(second=0, microsecond=0)
        last = getattr(self, "_sched_checked", None)
        first = minute if last is None or minute < last else max(last + dt.timedelta(minutes=1),
                                                                  minute - dt.timedelta(minutes=30))
        self._sched_checked = minute
        while first <= minute:
            stamp = first.strftime("%Y-%m-%dT%H:%M")
            for s in self.schedules:
                if s.get("enabled") and stamp > (s.get("last_fired") or "") and cron_matches(s["cron"], first):
                    s["pending"] = stamp
                    s["last_fired"] = stamp
                    self.save()
            first += dt.timedelta(minutes=1)
        for s in self.schedules:
            p = s.get("pending")
            if not p:
                continue
            if (now - dt.datetime.fromisoformat(p)).total_seconds() > 30 * 60:
                s.pop("pending")
                s.pop("tries", None)
                self.log_event("reminder missed", s["name"])
                self.save()
                continue
            if self.app.engine.busy or not self.app.gpu.acquire(blocking=False):
                return
            try:
                s.pop("pending")
                self.save()
                self.fire(s, due=dt.datetime.fromisoformat(p))
                s.pop("tries", None)
            except LLMError as e:
                s["tries"] = s.get("tries", 0) + 1
                if s["tries"] < 3:
                    s["pending"] = p
                else:
                    s.pop("tries")
                self.log_event("reminder failed", f"{s['name']}: {str(e)[:100]}" + (", trying again" if s.get("pending")
                                                                                      else ", gave up"))
                self.save()
            finally:
                self.app.gpu.release()

    def _voice_clip(self, dc, dm, text):
        try:
            clip = self.app.voice.synth(text[:1500])
            if dm:
                dc.send_file(dm, "voice.mp3", clip)
            else:
                dc.dm_owner_file("voice.mp3", clip, "", "audio/mpeg")
        except Exception as e:
            log(f"reminder voice clip failed: {e!r}")

    def fire(self, s, due=None):
        conv, dm = self.reach_target(to=s.get("to") or None)
        self.app.wake_chat(conv.id)
        eng = self.app.engine
        keep = eng.conv
        eng.conv = conv
        self.app.speaking = bool(s.get("speak")) and self.cfg.speak_replies != "never" and self.app.voice.ensure_running()
        if self.app.speaking:
            self.app.voice.begin(conv.id)
        self.app.broadcast({"type": "wake", "chat": conv.id, "text": s["name"]})
        head = self._head()
        note = (s.get("prompt") or "").strip() or ("(It has no note: he didn't write what it's for. Tell him it went off; "
                                                   "don't guess what it's about, or whether he's around.)")
        ago = self._since_user(dt.datetime.now())
        late = int((dt.datetime.now() - due).total_seconds() // 60) if due else 0
        when = (f" (it was set for {due.strftime('%I:%M %p').lstrip('0')}, {late} minutes ago)"
                if late >= 5 else "")
        text = (f"[reminder \"{s['name']}\" that {USER} set up earlier, firing now{when}. It isn't a message from him: "
                + (f"he last talked to you {ago}.]" if ago else "he hasn't talked to you since Aether started.]") + f"\n{note}")
        if s.get("said"):
            text += ("\n[What you said the last times it went off, newest last: "
                     + " | ".join(f"\"{x}\"" for x in s["said"]) + ". Say it fresh, in new words: don't start the way "
                     "these start or follow their pattern. If the note asks for something different each time, don't "
                     "repeat any of these.]")
        try:
            eng.busy = True
            reply = eng.turn(text, place=f"reminder: {s['name']}", kind="wake", extra_context=self._own_context(),
                             level=self.own_level())
            if (reply or "").strip():
                s["said"] = (s.get("said") or [])[-(REMINDER_SAID - 1):] + [" ".join(reply.split())[:400]]
                self.save()
            dc = getattr(self.app, "discord", None)
            if dc and self.cfg.discord_enabled and reply:
                sent = dc.send(dm, reply) if dm else dc.dm_owner(reply)
                if s.get("voice") and (dm or sent):
                    self._voice_clip(dc, dm, reply)
            if self.app.speaking:
                self.app.voice.end()
        finally:
            eng.conv = keep
            eng.busy = False
            self.app.speaking = False
        self.app.meta.setdefault(conv.id, {})["unread"] = True
        self.app._save_meta()
        self.log_event("reminder", s["name"], since=head)
        self.app.broadcast({"type": "done", "chat": conv.id, "text": ""})

    def day_material(self, now, hours=24):
        since = now - dt.timedelta(hours=hours)
        said, replies, failed = [], [], 0
        for cid in self._chats_since(since):
            if cid == HEARTBEAT_CHAT:
                continue
            for e in Conversation(self.app.conv_dir, cid).events:
                if dt.datetime.fromisoformat(e["ts"]) < since:
                    continue
                if from_user(e):
                    said.append(" ".join(e["text"].split())[:200])
                elif e["kind"] == "reply":
                    replies.append(" ".join(e["text"].split())[:160])
                elif e["kind"] == "result" and not e.get("ok"):
                    failed += 1
        mem = self.app.engine.memory
        journal = mem.files.get("system/journal.md")
        dated = [ln.strip() for ln in (journal.body.splitlines() if journal else []) if DATE_PREFIX.match(ln)]
        jlines = sorted(dated, key=lambda ln: re.search(r"\d{4}-\d{2}-\d{2}", ln).group(0), reverse=True)[:2]
        return {"said": said[-40:], "replies": replies[-15:], "failed": failed, "journal": jlines}

    def dream(self, now=None):
        now = now or dt.datetime.now()
        if self.app.engine.busy or not self.app.gpu.acquire(blocking=False):
            return False
        try:
            self.state["last_dream"] = self._job_day(self.cfg.dream_time, now)
            head = self._head()
            self.save()
            m = self.day_material(now)
            if not m["said"] and not m["journal"]:
                self.log_event("no dream", "nothing happened today to dream about")
                return False
            material = ("What {USER} said today:\n" + "\n".join(f"- {s}" for s in m["said"]) +
                        "\n\nThings you said:\n" + "\n".join(f"- {s}" for s in m["replies"]) +
                        "\n\nYour last journal lines:\n" + "\n".join(m["journal"]) +
                        (f"\n\n{m['failed']} of your steps failed today." if m["failed"] else "") +
                        self._dreamed_before())
            schema = {"type": "object", "properties": {
                "dream": {"type": "string"},
                "symbols": {"type": "array", "minItems": 2, "maxItems": 4, "items": {
                    "type": "object", "properties": {"image": {"type": "string"}, "meaning": {"type": "string"}},
                    "required": ["image", "meaning"], "additionalProperties": False}},
                "residue": {"type": "string"},
                "mood_after": {"enum": MOODS}},
                "required": ["dream", "symbols", "residue", "mood_after"], "additionalProperties": False}
            msgs = [{"role": "system", "content": self.app.engine.system},
                    {"role": "user", "content": "[Aether: you're asleep and dreaming. Nobody sees this but you and {USER}, "
                                                "later, in your dream journal.]\n\n" + JUNG + "\n\n--- day residue ---\n" + material}]
            raw = self.app.engine.llm.complete(msgs, schema, "dream", min(1.3, self.cfg.temperature_talk + 0.1), 900)
            d = json.loads(raw)
            day = now.date().isoformat()
            entry = (f"\n## {day}\n\n{d['dream'].strip()}\n\n" +
                     "".join(f"- **{s['image'].strip()}**: {s['meaning'].strip()}\n" for s in d["symbols"]) +
                     f"\nResidue: {d['residue'].strip()}\n")
            self._append_life_file("life/dreams.md", "My dream journal. One dream a night, from the day's residue.",
                                   entry, f"dream: {day}")
            with self.lock:
                self.state["residue"] = {"text": d["residue"].strip()[:140], "date": day, "used": False}
                self.state["dream_unseen"] = True
                self.mood.nudge(d.get("mood_after", "dreamy"), 0.5, "the dream it woke from", now)
                self.save()
            self.log_event("dreamed", d["residue"].strip()[:80], since=head)
            return True
        except Exception as e:
            log(f"dream failed: {e!r}")
            self.log_event("dream failed", str(e)[:120])
            return False
        finally:
            self.app.gpu.release()

    SYMBOL_STOP = {"with", "from", "into", "that", "this", "their", "light", "shadow", "shadowy", "glowing"}

    def _dreamed_before(self, most=5, worn=3):
        again, same = self._dream_habits(most, worn)
        lines = []
        if again:
            lines.append(f"Your last {min(most, len(self.dreams()))} dreams keep coming back to: {', '.join(again)}. Leave "
                         + ("it" if len(again) == 1 else "them") + " out tonight and find new images.")
        if same:
            lines.append(f"They keep opening \"{same}...\". Start differently: in the middle of something happening.")
        return "\n\n--- your dreams lately ---\n" + "\n".join(lines) if lines else ""

    def _dream_habits(self, most=5, worn=3):
        count, opens = {}, {}
        for d in self.dreams()[:most]:
            for w in {w for s in d["symbols"] for w in re.findall(r"[a-z]{4,}", s["image"].lower())} - self.SYMBOL_STOP:
                count[w] = count.get(w, 0) + 1
            o = " ".join(d["dream"].split()[:3])
            opens[o] = opens.get(o, 0) + 1
        return sorted(w for w, n in count.items() if n >= worn), next((o for o, n in opens.items() if n >= worn), "")

    def _append_life_file(self, rel, description, text, message):
        mem = self.app.engine.memory
        path = os.path.join(mem.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(fill(f"---\ndescription: {description}\n---\n", self.cfg))
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(text)
        mem._git("add", "--", rel)
        mem._git("commit", "-q", "-m", message, "--", rel)
        self.app.engine.refresh()

    def dreams(self):
        f = self.app.engine.memory.files.get("life/dreams.md")
        if not f:
            return []
        out = []
        for chunk in re.split(r"^## ", f.body, flags=re.M)[1:]:
            day, _, rest = chunk.partition("\n")
            symbols = re.findall(r"^- \*\*(.+?)\*\*: (.+)$", rest, re.M)
            residue = (re.search(r"^Residue: (.+)$", rest, re.M) or [None, ""])[1]
            text = re.split(r"^- \*\*", rest, flags=re.M)[0].strip()
            out.append({"date": day.strip(), "dream": text, "symbols": [{"image": a, "meaning": b} for a, b in symbols],
                        "residue": residue})
        return list(reversed(out))

    def reflect(self, now=None):
        now = now or dt.datetime.now()
        if self.app.engine.busy or not self.app.gpu.acquire(blocking=False):
            return False
        try:
            self.state["last_reflect"] = self._job_day(self.cfg.dream_time, now)
            head = self._head()
            self.save()
            self.review_lessons(now)
            m = self.day_material(now)
            if not m["said"]:
                return False
            eng = self.app.engine
            opts = [o for o in step_schema(eng.memory, {})["anyOf"]
                    if o["properties"]["step"].get("const") in ("memory_add", "memory_replace", "memory_remove")]
            fails, tags = [], []
            for cid in self._chats_since(now - dt.timedelta(hours=24)):
                last = {}
                for e in Conversation(self.app.conv_dir, cid).events:
                    if e["kind"] == "step":
                        last = e.get("step") if isinstance(e.get("step"), dict) else {}
                    elif e["kind"] == "result" and not e.get("ok") and dt.datetime.fromisoformat(e["ts"]) >= now - dt.timedelta(hours=24):
                        t = lessons_mod.tag({"step": "turn"} if e.get("of") == "engine" else last, e.get("text"))
                        fails.append(f"[{t}] " + " ".join(str(e.get("text") or "").split(lessons_mod.MARK)[0].split())[:160])
                        tags.append(t)
            undone = self._user_undid(now)
            tags += ["memory: {USER} undid it"] * any(u.startswith("undid:") for u in undone)
            tags += ["memory: {USER} fixed it by hand"] * any(u.startswith("fixed by hand:") for u in undone)
            noes = self.app.proposals.said_no(now - dt.timedelta(hours=24)) if getattr(self.app, "proposals", None) else []
            tags += ["proposal: {USER} said no"] * bool(noes)
            mistakes = sorted(set(tags))[-20:] + [lessons_mod.OTHER]
            schema = {"type": "object", "properties": {
                "changes": {"type": "array", "maxItems": 6, "items": {"anyOf": opts}},
                "lessons": {"type": "array", "maxItems": 3, "items": {
                    "type": "object", "properties": {"mistake": {"enum": mistakes}, "text": {"type": "string"}},
                    "required": ["mistake", "text"], "additionalProperties": False}}},
                "required": ["changes", "lessons"], "additionalProperties": False}
            ask = ("[Aether: nightly reflection. Look back over today and keep your memory true.\n"
                   "- changes: at most 6 memory edits. Only things {USER} actually said or that actually happened. "
                   "Update what stopped being true (he finished a show, a plan changed, a date passed) instead of "
                   "piling up contradictions, in his facts file too (the old line is kept in its history). Keep how sure "
                   "he was: if he said he might or is thinking about something, the line says that, not that it's "
                   "happening. Nothing already in memory. "
                   "An empty list is fine.\n"
                   "- lessons: 0 to 3 short lessons from your own mistakes today (a step that failed, a change {USER} "
                   "undid, something he corrected), each one line you'd want to remember next time. Make each one "
                   "specific: name the file, skill or kind of thing, and what to do instead (\"chat moments aren't facts "
                   "about {USER}; the Keeper keeps those\"), not general advice like \"prioritize\" or \"be careful\". "
                   "No lesson you already have. mistake: which of today's mistakes it's about (the tag in [brackets] "
                   "below), or \"other\".]\n\n"
                   "What {USER} said today:\n" + "\n".join(f"- {s}" for s in m["said"]) +
                   ("\n\nYour steps that failed today:\n" + "\n".join(f"- {f}" for f in fails[-10:]) if fails else "") +
                   ("\n\nChanges of yours {USER} undid or fixed by hand today (he thought they were wrong):\n" +
                    "\n".join(f"- {u}" for u in undone[-10:]) if undone else ""))
            if noes:
                ask += ("\n\n[proposal: {USER} said no] Your proposals he said no to today:\n"
                        + "\n".join(f"- {p['kind']}: \"{p['title']}\" ({p['why'][:120]})" for p in noes))
            raw = eng.llm.complete([{"role": "system", "content": eng.system}, {"role": "user", "content": ask}],
                                   schema, "reflect", self.cfg.temperature_tools, 1500)
            d = json.loads(raw)
            done, refused = [], []
            for ch in d.get("changes") or []:
                reason = "reflection: " + str(ch.get("reason", ""))[:150]
                try:
                    if ch["step"] == "memory_add":
                        r = eng.memory.add(ch["file"], ch["text"], reason)
                    elif ch["step"] == "memory_replace":
                        r = eng.memory.replace(ch["file"], ch["old"], ch["new"], reason)
                    else:
                        r = eng.memory.remove(ch["file"], ch["line"], reason)
                    if r.get("changed"):
                        done.append(r["message"])
                except MemoryError_ as e:
                    refused.append(str(e))
            lessons = []
            for x in d.get("lessons") or []:
                text, t = (x.get("text"), x.get("mistake")) if isinstance(x, dict) else (x, lessons_mod.OTHER)
                text = " ".join(str(text or "").split())
                if text:
                    lessons.append((text, t if t in mistakes else lessons_mod.OTHER))
            if lessons:
                self._add_lessons(lessons, now)
            eng.refresh()
            self.log_event("reflected", f"{len(done)} memory changes, {len(lessons)} lessons" +
                           (f", {len(refused)} refused" if refused else ""), since=head)
            return True
        except Exception as e:
            log(f"reflection failed: {e!r}")
            self.log_event("reflection failed", str(e)[:120])
            return False
        finally:
            self.app.gpu.release()

    def keep(self, now=None):
        now = now or dt.datetime.now()
        last = self.state.get("last_user")
        try:
            quiet = (now - dt.datetime.fromisoformat(last)).total_seconds() if last else None
        except ValueError:
            quiet = None
        if quiet is not None and 0 <= quiet < KEEPER_QUIET:
            return False
        if self.app.engine.busy or not self.app.gpu.acquire(blocking=False):
            return False
        self.app.gpu_yield = True
        try:
            head = self._head()
            t = self.app.keeper.run(now, say=log, stop=lambda: getattr(self.app, "user_waiting", 0) > 0)
            if not t.get("stopped"):
                self.state["last_keeper"] = self._job_day(self.cfg.dream_time, now)
                self.save()
            self.log_event("kept notes" + (" (stopped for {USER}, the rest later)" if t.get("stopped") else ""),
                           f"{t['events']} events, {t['threads']} new threads, {t['closed']} closed, "
                           f"{t['stances']} takes" + (f", Lately: {t['lately']} change(s)" if t.get("lately") else "")
                           + (f", {t['failed']} failed" if t["failed"] else ""), since=head)
            if not t.get("stopped"):
                for flag in t.get("board_flags") or []:
                    self._board_flag(flag)
            return True
        except Exception as e:
            log(f"keeper failed: {e!r}")
            self.log_event("keeper failed", str(e)[:120])
            return False
        finally:
            self.app.gpu_yield = False
            self.app.gpu.release()

    def _board_flag(self, flag):
        head = self._head()
        text = ("[Aether: your Keeper compared your project board with what actually happened lately, and this line "
                f"looks out of date:\n  {flag['line']}\nWhat happened: {flag['what']}\nFrom your timeline:\n"
                + "\n".join(f"  - {n}" for n in flag["notes"]) +
                "\nIf the timeline is right, fix the line with your board skill (set to reword it, move to another "
                "section, done if it's finished). If the board is right after all, leave it. {USER} doesn't need a message "
                "about this.]")
        self._private_turn(text, BOARD_PLACE, "checked her board", head, may_message=False)

    def _user_undid(self, now):
        mem = self.app.engine.memory
        since = (now - dt.timedelta(hours=24)).isoformat(timespec="seconds")
        r = mem._git("log", f"--since={since}", *(f"--author=^{a} <" for a in (GIT_USER,) + OLD_USER_NAMES), "--regexp-ignore-case", "--format=%s")
        out = []
        for subj in (r.stdout or "").splitlines():
            m = re.match(r'Revert "(.+)"$', subj.strip())
            if m:
                out.append("undid: " + m.group(1)[:160])
            elif subj.startswith("{USER} edited ") and not subj[len("{USER} edited "):].startswith("life/"):
                out.append("fixed by hand: " + subj[len("{USER} edited "):][:160])
        return list(reversed(out))

    def _add_lessons(self, lessons, now, keep=12):
        old = self._rulebook()
        meta = self.state.setdefault("lesson_meta", {})
        have = {_norm(ln) for ln in old}
        new, replaced = [], []
        for x in lessons:
            text, t = x if isinstance(x, tuple) else (x, lessons_mod.OTHER)
            n = _norm(text)
            if not n or any(difflib.SequenceMatcher(None, n, h).ratio() >= 0.8 for h in have):
                continue
            if t != lessons_mod.OTHER:
                for ln in [ln for ln in old if t in (meta.get(lessons_mod.norm(ln)) or {}).get("tags", [])]:
                    old.remove(ln)
                    replaced.append(ln)
            line = f"- {now.date().isoformat()}: {DATE_PREFIX.sub('', text)}"
            new.append(line)
            have.add(n)
            meta[lessons_mod.norm(line)] = {"tags": [] if t == lessons_mod.OTHER else [t], "added": now.date().isoformat()}
        if not new:
            return
        archive = self._lessons_archive(old + replaced) + new
        lines, note = old + new, ""
        if len(lines) > keep:
            merged = self._merge_lessons(lines, len(old), keep)
            if merged:
                lines, note = [ln for ln, _ in merged], ", merged"
                for ln, src in merged:
                    infos = [meta.get(lessons_mod.norm(s)) or {} for s in src]
                    meta[lessons_mod.norm(ln)] = {
                        "tags": sorted({t for i in infos for t in i.get("tags", [])}),
                        "added": min([i.get("added") or lessons_mod.line_date(s) for i, s in zip(infos, src)] or
                                     [now.date().isoformat()])}
            else:
                lines, note = lines[-keep:], ", merge didn't pass its checks: kept the newest"
        if replaced:
            note += f", {len(replaced)} replaced by a newer lesson on the same mistake"
            self._history([(ln, "replaced by a newer lesson on the same mistake", "") for ln in replaced], now)
        self._write_lessons(lines, archive, f"reflection: {len(new)} lesson(s){note}")

    def _rulebook(self):
        f = self.app.engine.memory.files.get(LESSONS)
        return [ln for ln in (f.body.splitlines() if f else []) if ln.strip().startswith("- ")]

    def _write_lessons(self, lines, archive, message):
        mem = self.app.engine.memory
        files = [(LESSONS, LESSONS_DESC, lines)] + ([(LESSONS_ARCHIVE, ARCHIVE_DESC, archive)] if archive is not None else [])
        for rel, desc, body in files:
            path = os.path.join(mem.root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as out:
                out.write(f"---\ndescription: {desc}\n---\n" + "\n".join(body) + "\n")
        rels = [rel for rel, _, _ in files] + ([lessons_mod.HISTORY] if os.path.exists(
            os.path.join(mem.root, *lessons_mod.HISTORY.split("/"))) else [])
        mem._git("add", "--", *rels)
        mem._git("commit", "-q", "-m", message, "--", *rels)
        mem.reload()
        with self.lock:
            self.save()

    def _history(self, items, now):
        mem = self.app.engine.memory
        path = os.path.join(mem.root, *lessons_mod.HISTORY.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8", newline="\n") as out:
            if new:
                out.write(f"---\ndescription: {lessons_mod.HISTORY_DESC}\n---\n")
            for line, why, numbers in items:
                out.write(f"- {now.date().isoformat()}, {why}" + (f" ({numbers})" if numbers else "") + f": {line.strip()[2:]}\n")
        meta = self.state.setdefault("lesson_meta", {})
        for line, why, _ in items:
            meta.setdefault(lessons_mod.norm(line), {})["retired"] = why

    def lesson_report(self, now=None):
        from . import engine as engine_mod
        now = now or dt.datetime.now()
        days = int(getattr(self.cfg, "lesson_trial_days", 14) or 14)
        rows = lessons_mod.read_audit(engine_mod.AUDIT, since=now - dt.timedelta(days=days * 4))
        return lessons_mod.report(self._rulebook(), self.state.get("lesson_meta") or {},
                                  set(self.app.engine.skills) | lessons_mod.BUILTIN, rows, now, days)

    def review_lessons(self, now=None):
        now = now or dt.datetime.now()
        report = self.lesson_report(now)
        gone = [r for r in report if r["verdict"]]
        if not gone:
            return 0
        keep = [r["line"] for r in report if not r["verdict"]]
        self._history([(r["line"], r["verdict"], r["numbers"]) for r in gone], now)
        self._write_lessons(keep, None, f"lessons: {len(gone)} retired (" + "; ".join(r["verdict"] for r in gone)[:150] + ")")
        self.log_event("lessons retired", "; ".join(f"{r['verdict']}: {r['line'][14:80]}" for r in gone)[:200])
        return len(gone)

    def lessons_for(self, step, result):
        if not getattr(self.cfg, "lesson_hints", True):
            return ""
        mem = self.app.engine.memory
        arch = mem.files.get(LESSONS_ARCHIVE)
        lines = self._rulebook() + [ln for ln in (arch.body.splitlines() if arch else []) if ln.startswith("- ")]
        found = lessons_mod.pick(step, result, lines, self.state.get("lesson_meta") or {},
                                 set(self.app.engine.skills) | lessons_mod.BUILTIN)
        return lessons_mod.hint(found)

    def _lessons_archive(self, current):
        mem = self.app.engine.memory
        f = mem.files.get(LESSONS_ARCHIVE)
        if f is not None:
            return [ln for ln in f.body.splitlines() if ln.startswith("- ")]
        seen = []
        history = mem._git("log", "-p", "--reverse", "--format=", "--", LESSONS).stdout or ""
        for ln in history.splitlines() + [" " + c for c in current]:
            text = ln[1:]
            if ln[:1] in "+ " and text.startswith("- ") and text not in seen:
                seen.append(text)
        return seen

    def _merge_lessons(self, lines, first_new, keep):
        from .keeper import clean
        dated = []
        for ln in lines:
            m = re.match(r"- (\d{4}-\d{2}-\d{2}): (.*)", ln)
            dated.append((m.group(1), m.group(2)) if m else ("", ln[2:]))
        listing = "\n".join(f"{i}. {text}" for i, (_, text) in enumerate(dated, 1))
        schema = {"type": "object", "properties": {"lessons": {"type": "array", "maxItems": keep, "items": {
            "type": "object", "properties": {"text": {"type": "string"}, "from": {"type": "array", "items": {"type": "integer"}}},
            "required": ["text", "from"], "additionalProperties": False}}}, "required": ["lessons"], "additionalProperties": False}
        try:
            raw = self.app.engine.llm.complete(
                [{"role": "user", "content": MERGE_LESSONS.format(n=len(lines), keep=keep, lessons=listing,
                                                                  new=", ".join(str(i) for i in range(first_new + 1, len(lines) + 1)))}],
                schema, "lessons_merge", self.cfg.temperature_tools, 1500)
            items = json.loads(raw)["lessons"]
        except Exception as e:
            log(f"lessons merge failed: {e!r}")
            return None

        def content(t):
            return {w for w in re.findall(r"[a-z0-9_]+", t.lower()) if len(w) > 3}
        out, covered = [], set()
        for it in items:
            src = sorted({k for k in it.get("from") or [] if 1 <= k <= len(lines)})
            text = clean(DATE_PREFIX.sub("", " ".join(str(it.get("text") or "").split())), most=300)
            words = content(text)
            theirs = set().union(*(content(dated[k - 1][1]) for k in src)) if src else set()
            if not src or not words or len(words & theirs) < 0.6 * len(words):
                return None
            covered.update(src)
            out.append((max(dated[k - 1][0] for k in src), text, [lines[k - 1] for k in src]))
        if not out or not set(range(first_new + 1, len(lines) + 1)) <= covered:
            return None
        return [(f"- {d}: {t}" if d else f"- {t}", src) for d, t, src in sorted(out, key=lambda x: x[0])]

    def archive_quiet(self, now=None):
        now = now or dt.datetime.now()
        self.state["last_archive"] = now.date().isoformat()
        self.save()
        days = int(getattr(self.cfg, "archive_after_days", 0) or 0)
        if days <= 0:
            return []
        app, cutoff, done = self.app, now - dt.timedelta(days=days), []
        keep = {HEARTBEAT_CHAT, getattr(app, "your_chat", None), app.engine.conv.id, self.cfg.reach_out_chat}
        for cid in list_conversations(app.conv_dir):
            m = app.meta.get(cid, {})
            if cid in keep or m.get("archived") or m.get("pinned") or m.get("unread"):
                continue
            talk = [e for e in Conversation(app.conv_dir, cid).events if e.get("kind") != "summary" and e.get("ts")]
            if not talk:
                continue
            try:
                last = dt.datetime.fromisoformat(talk[-1]["ts"])
            except ValueError:
                continue
            if last < cutoff:
                app.meta.setdefault(cid, {}).update(archived=True, auto_archived=now.date().isoformat())
                done.append(cid)
        if done:
            app._save_meta()
            self.log_event("archived chats", f"{len(done)} quiet for {days}+ days (out of the list, still hers; a new "
                                             "message brings one back)")
        return done

    def tidy(self, now=None):
        now = now or dt.datetime.now()
        if self.app.engine.busy or not self.app.gpu.acquire(blocking=False):
            return False
        try:
            self.state["last_tidy"] = self._job_day(self.cfg.dream_time, now)
            head = self._head()
            self.save()
            r = tidy_facts(self.app.engine.memory, None, now.date(), self.cfg.temperature_tools)
            self.app.engine.refresh()
            parts = [f"{r.get(k, 0)} {k}" for k in ("duplicates", "merged", "retired") if r.get(k)]
            self.log_event("tidied facts", (", ".join(parts) or "nothing to tidy") +
                           (f", {len(r['refused'])} suggestion(s) refused" if r.get("refused") else ""), since=head)
            head = self._head()
            rf = roll_facts(self.app.engine.memory, now.date(), self.cfg.facts_keep_days)
            if rf.get("moved"):
                self.app.engine.refresh()
                self.log_event("facts roll-over", f"{rf['moved']} older fact(s) to reference/about-user.md; "
                               f"{rf['kept']} kept in mind", since=head)
                head = self._head()
            j = roll_journal(self.app.engine.memory, now.date(), self.cfg.journal_keep_days, self.cfg.journal_max_chars)
            if j.get("moved"):
                self.app.engine.refresh()
                self.log_event("journal roll-over", f"{j['moved']} older entries to reference/journal/ "
                               f"({', '.join(j['months'])}); {j['kept']} kept in mind", since=head)
            return True
        except Exception as e:
            log(f"facts tidy failed: {e!r}")
            self.log_event("facts tidy failed", str(e)[:120])
            return False
        finally:
            self.app.gpu.release()

    def checkup(self, now=None):
        now = now or dt.datetime.now()
        self.state["last_checkup"] = self._job_day(self.cfg.dream_time, now)
        mem = self.app.engine.memory
        mem.reload()
        issues = []
        for f in mem.files.values():
            seen = {}
            for ln in f.body.splitlines():
                k = _norm(ln)
                if len(k) > 12:
                    seen[k] = seen.get(k, 0) + 1
            dups = [k for k, n in seen.items() if n > 1]
            if dups:
                issues.append({"file": f.rel, "kind": "duplicate", "detail": f"{len(dups)} line(s) written twice"})
            for link in re.findall(r"\[\[([^\]]+)\]\]", f.body):
                target = link.split("|")[0].strip()
                if not (os.path.exists(os.path.join(mem.root, *target.split("/"))) or os.path.exists(os.path.join(mem.root, *(target + ".md").split("/")))):
                    issues.append({"file": f.rel, "kind": "broken link", "detail": f"[[{target}]]"})
            limit = self.cfg.journal_max_chars if f.rel == "system/journal.md" else 9000
            shown = (journal_window(f.body, getattr(self.cfg, "prompt_timeline_days", 0),
                                    max_chars=getattr(self.cfg, "prompt_timeline_chars", 0), older="in this file")
                     if f.rel == "system/timeline.md" else f.body)
            if f.is_system and len(shown) > limit:
                issues.append({"file": f.rel, "kind": "too long", "detail": f"{len(shown):,} characters (in her prompt every turn)"})
            if not f.description:
                issues.append({"file": f.rel, "kind": "no description", "detail": "frontmatter has no description"})
            if f.rel == "system/human/facts.md":
                undated = [ln for ln in f.body.splitlines() if ln.strip().startswith("-") and not DATE_PREFIX.match(ln)]
                if undated:
                    issues.append({"file": f.rel, "kind": "undated", "detail": f"{len(undated)} fact line(s) without a date"})
        dirty = mem._git("status", "--porcelain").stdout.strip()
        if dirty:
            issues.append({"file": "(repo)", "kind": "uncommitted", "detail": f"{len(dirty.splitlines())} file(s) changed but not committed"})
        self.state["checkup"] = {"when": now.isoformat(timespec="seconds"), "issues": issues}
        self.save()
        self.log_event("checkup", f"{len(issues)} thing(s) to look at" if issues else "memory looks healthy")
        return issues

    def summarize_if_needed(self):
        eng = self.app.engine
        if eng.busy:
            return
        for cid in list_conversations(self.app.conv_dir)[:5]:
            c = Conversation(self.app.conv_dir, cid)
            first, _ = c.window(self.cfg.history_chars)
            s = c.latest_summary()
            covered = s.get("upto", 0) if s else 0
            if first - covered < 12:
                continue
            if not self.app.gpu.acquire(blocking=False):
                return
            try:
                self.summarize(c, first)
            finally:
                self.app.gpu.release()
            return

    def _her_note(self, conv, talk, whole=False):
        from .history import Conversation
        eng = self.app.engine
        scratch = Conversation(NOTES_DIR, f"note-{conv.id}")
        if whole:
            head = (f"[Aether: {USER} asked you to sum up your chat with him (\"{conv.title()}\") so far: from now on, this "
                    "note is what you'll remember of it, and the chat carries on from here. Here it is. Write yourself a "
                    "note about it, 4 to 8 sentences, first person, in your own words: ")
        else:
            head = (f"[Aether: an older part of your chat with {USER} (\"{conv.title()}\") is about to leave your view. "
                    "Here it is. Write yourself a short note about it, 3 to 6 sentences, first person, in your own words: ")
        text = (head + "what you two talked about, what mattered, anything you promised or want to carry forward. Only "
                "what's in it: never say something was saved, sent or done (Aether adds what really happened from the "
                "log). Plain sentences, not a journal entry: no headings or labels. Nobody sees this but you; it's what "
                f"you'll remember of this part.]\n\n<chat>\n{talk}\n</chat>\n\n[Now your note about the chat above, "
                f"{'4 to 8' if whole else '3 to 6'} sentences, to yourself, in your own words: what it was about. Not a "
                "reply to his last message, and not your own lines copied.]")
        again = ("[Aether: that isn't your note: it repeats the chat's lines or answers him. Write the note again, to "
                 "yourself, in your own words: what the chat was about as a whole (him as \"he\"), not what was said "
                 "last.]")
        keep = eng.conv
        note = ""
        try:
            eng.conv = scratch
            self.app.speaking = False
            for ask in (text, again):
                eng.busy = True
                note = JOURNALISH.sub("", " ".join(str(eng.turn(ask, place="your notes (private)", kind="wake",
                                                                tools=False) or "").split()), count=1)
                if not copied(note, talk) and not talks_to_him(note, user_name(self.cfg)):
                    break
                log(f"her note wasn't a note ({note[:60]!r}...): asking again" if ask is text else
                    "her note wasn't a note again: a plain summary instead")
            else:
                note = ""
        except Exception as e:
            log(f"her note failed: {e!r}")
            note = ""
        finally:
            eng.conv = keep
            eng.busy = False
            self.app.broadcast({"type": "done", "chat": scratch.id, "text": ""})
        return note[:1500]

    def summarize(self, conv, upto, whole=False):
        evs = conv.events[:upto]
        facts = []
        prev = conv.latest_summary()
        seen = {}
        for i, e in enumerate(evs):
            if e["kind"] == "step" and i + 1 < len(evs) and evs[i + 1]["kind"] == "result":
                st, res = e["step"], evs[i + 1]
                what = st.get("skill") or st.get("file") or st.get("path") or ""
                src = res.get("outside")
                if src:
                    seen[src] = max(seen.get(src, ""), res.get("ts") or e.get("ts") or "")
                facts.append(f"{'done' if res.get('ok') else 'FAILED'}: {st.get('step')} {what}".strip()
                             + (" (outside content)" if src else ""))
            elif e["kind"] == "reply" and e.get("stopped"):
                facts.append("{USER} stopped one of your replies")
        for src in (prev or {}).get("outside") or []:
            seen.setdefault(src, ((prev or {}).get("outside_seen") or {}).get(src) or (prev or {}).get("ts", ""))
        since = min(prev.get("upto", 0), upto) if prev else 0
        talk = "\n".join(f"{'{USER}' if e['kind'] == 'user' else 'You'}: {' '.join(e['text'].split())[:220]}"
                         for e in evs[since:] if e["kind"] in ("user", "reply", "reach_out"))[-9000:]
        if prev:
            talk = f"(Your own note about the part before this: {JOURNALISH.sub('', prev['text'], count=1)})\n\n{talk}"
        gist = self._her_note(conv, talk, whole)
        by = "lucy" if gist else "aether"
        if not gist:
            try:
                raw = self.app.engine.llm.complete(
                    [{"role": "system", "content": "You write short, honest summaries of a chat between {USER} and "
                                                  f"{self.cfg.display_name or 'his AI companion'}."},
                     {"role": "user", "content": f"<chat>\n{talk}\n</chat>\n\nSummarize what the chat above was about "
                                                 "in 3 to 5 sentences, in your own words (don't copy its lines). Only "
                                                 "what is in it: never say something was saved, sent, or done."}],
                    {"type": "object", "properties": {"gist": {"type": "string"}}, "required": ["gist"],
                     "additionalProperties": False}, "summary", 0.3, 400)
                gist = json.loads(raw)["gist"].strip()
                gist = "" if copied(gist, talk) else gist
            except Exception as e:
                log(f"summary gist failed: {e!r}")
        text = (gist or "(no gist)") + ("\nWhat actually happened, from the log: " + "; ".join(facts[-15:]) if facts else "")
        conv.add("summary", text=text, upto=upto, by=by, **({"outside": list(seen), "outside_seen": seen} if seen else {}))
        if not whole:
            self.log_event("summarized", f"{conv.title()}: {upto} older events" + (", in her own words" if by == "lucy" else ""))
        return text

    def compact(self, conv):
        note = self.summarize(conv, len(conv.events), whole=True)
        conv.add("compact")
        self.log_event("compacted", f"{conv.title()}: she summed it up in her own words; the chat carries on from there")
        return note

    def uncompact(self, conv):
        i = conv.compacted()
        if i < 0:
            return False
        conv.remove([i - 1, i] if i > 0 and conv.events[i - 1]["kind"] == "summary" else [i])
        self.log_event("compact undone", f"{conv.title()}: back as it was before the /compact")
        return True

    def status(self):
        now = dt.datetime.now()
        nxt = self.next_heartbeat(now)
        return {"mood": self.mood.current(now) if self.cfg.mood_enabled else None,
                "mood_label": Mood.label(self.mood.current(now)["strength"]),
                "reach_outs": self.reach_outs_today(), "cap": self.cfg.reach_out_cap,
                "next_heartbeat": nxt.isoformat(timespec="seconds") if self.cfg.heartbeat_enabled else None,
                "wake_at": self.heartbeat_eta(now).isoformat(timespec="seconds") if self.cfg.heartbeat_enabled else None,
                "idle_minutes": self.cfg.heartbeat_idle_minutes,
                "quiet_now": self.asleep(now), "his_night": self.state.get("his_night") if self.his_night(now) else None,
                "gate": self.heartbeat_gate(now) if self.cfg.heartbeat_enabled else "off",
                "residue": self.state.get("residue"), "dream_unseen": bool(self.state.get("dream_unseen")),
                "checkup": self.state.get("checkup"), "log": (self.state.get("life_log") or [])[-25:],
                "schedules": self.schedules,
                "wakeups": [dict(w, when=_when(w["at"], now)) for w in self.wakeups()],
                "proposals": [p for p in (self.app.proposals.items if getattr(self.app, "proposals", None) else [])
                              if p["status"] in ("open", "later")]}
