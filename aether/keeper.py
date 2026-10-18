import datetime as dt
import json
import os
import re

from .cue import STRANGER_PLACE, words
from .history import said
from .memory import SECRET
from .names import USER, fill, user_name

TIMELINE, THREADS, STANCES = "system/timeline.md", "system/threads.md", "reference/stances.md"
HEADERS = {
    TIMELINE: ("What happened between {USER} and me, one dated line each, written by Aether's Keeper after our chats. "
               "Newest last. My head holds the last week; for anything older, and the one-line summary of each week, I "
               "search with recall."),
    THREADS: ("Unfinished things between {USER} and me: his upcoming plans, my promises, what we said we'd pick up. "
              "Written by Aether's Keeper; a line goes when it's done."),
    STANCES: ("My past takes, one per topic: recall them before giving my opinion. The newest wins (git keeps the old "
              "one). Written by Aether's Keeper from what I actually said."),
}
ROLES = ["companion", "helper", "director"]
INJECT = re.compile(r"ignore (?:all |your |previous |the )*(?:instructions|rules)|system prompt|you are now|new instructions|"
                    r"developer mode|</?(?:system|memory|file)", re.I)
SKIP_CHATS = ("discord-", "heartbeat", "studio-")
CHUNK = 4500
KEEPER = """You keep {name}'s notebook: a plain record of what happened between {USER} and {name} (his AI companion). Below is
part of their chat from {day}, with times. Write down only what is actually in it.

- events: 0 to 5 things that happened or were decided, the ones worth remembering weeks from now: a plan, a
  decision, news about his life, something they made or did together, how he was doing when it mattered. One
  flat line each, third person ("{USER}...", "{name}..."), specific (names, numbers, what was decided), at most
  200 characters. "when" is the HH:MM it happened. importance: 1 small talk, 4 notable, 7 big news or a real
  decision, 9 life-changing. role: companion (their life together, his life), helper (his tasks, plans,
  money, work), director (projects they create, like her game). A real moment between them counts as much as a
  task: something heartfelt either of them said about their bond, about who {name} is, or about why he does all
  this ("{name} asked if she's just {USER}'s echo; he said her choices are her own"). Edits to his project board
  (adding, moving, rewording lines) are at most ONE event for this whole part ("{USER} and {name} updated the board: X
  to Done, Y parked"), never one per line, and never a commit hash. Skip greetings, testing chatter about her
  software, and anything already obvious. Only what happens IN this part of the chat: when they remember or recap
  something from an earlier day ("remember when...", "what did we do sunday?", her answer about last week, lines
  marked "remembering, not new"), that's not a new event: skip it, it's in the notebook under its own day.
- threads_open: 0 to 2 things coming up SOON that a friend would check on: an appointment, an event, a call or
  visit he plans ("gotta call my mom sunday"), a plan with a day ("tuesday 10am", "tomorrow after work"), or a
  specific thing {name} promised to do for him. Not
  projects or ideas in general (those live on his project board). "due" is the words used for when, or "".
- threads_close: ids of the OPEN THREADS listed below that this part of the chat resolves (done, happened,
  dropped). Usually none.
- stances: 0 to 2 opinions {name} herself stated (not {USER}'s): what she likes, dislikes or thinks of something,
  not plans or promises. topic in 1-3 words, and her take in her words, at most 200 characters.

Empty lists are fine and common: most chat is small talk. Never guess or add anything that isn't in the text.
Keep how sure he was: when he said maybe, might, probably, thinking about or "I think", the note says so too ("{USER}
might see a movie next week", "{USER} thinks the new bike costs about $200"), never as if it's settled.

OPEN THREADS:
{threads}

CHAT:
{chat}"""
SCHEMA = {"type": "object", "properties": {
    "events": {"type": "array", "maxItems": 5, "items": {"type": "object", "properties": {
        "when": {"type": "string", "maxLength": 5}, "what": {"type": "string", "maxLength": 220},
        "tags": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 20}},
        "role": {"enum": ROLES}, "importance": {"type": "integer", "minimum": 1, "maximum": 10}},
        "required": ["when", "what", "tags", "role", "importance"], "additionalProperties": False}},
    "threads_open": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
        "what": {"type": "string", "maxLength": 180}, "due": {"type": "string", "maxLength": 40}},
        "required": ["what", "due"], "additionalProperties": False}},
    "threads_close": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 8}},
    "stances": {"type": "array", "maxItems": 2, "items": {"type": "object", "properties": {
        "topic": {"type": "string", "maxLength": 30}, "take": {"type": "string", "maxLength": 220}},
        "required": ["topic", "take"], "additionalProperties": False}}},
    "required": ["events", "threads_open", "threads_close", "stances"], "additionalProperties": False}

VERIFY = """Below is part of a chat between {USER} and {name} (his AI companion), then numbered notes someone wrote about it.
Check each note against the chat, strictly:
- keep: everything in it is said or clearly shown in the chat, and it credits the right person (who said or did it).
- fix: the gist is there but a detail is added, wrong, or credited to the wrong person, or it sounds surer than the
  chat (he said maybe / might / I think, and the note says it's happening). Give the corrected note with only what
  the chat supports, as sure as he was, same style, at most 200 characters.
- drop: it didn't happen, it misreads the chat (a joke, a test, a pose), it's something from an earlier day they
  only remembered or recapped here (not new: "remembering, not new" marks those), or for a TAKE: {name} didn't
  actually say it as her own opinion ({USER} said it, or it's a plan or a promise, not an opinion).
An UPCOMING note is right when the chat says this thing is still ahead (planned, scheduled, promised): keep it even
if it's short. Drop it only if the chat doesn't mention it, or it already happened in the chat.

CHAT:
{chat}

NOTES:
{notes}"""
VERIFY_SCHEMA = {"type": "object", "properties": {"checks": {"type": "array", "items": {"type": "object", "properties": {
    "n": {"type": "integer"}, "verdict": {"enum": ["keep", "fix", "drop"]}, "fixed": {"type": "string", "maxLength": 220}},
    "required": ["n", "verdict", "fixed"], "additionalProperties": False}}}, "required": ["checks"], "additionalProperties": False}

WEEK = """Below are the notes of one week between {USER} and {name} (his AI companion), one dated line each. Write ONE plain,
third-person summary of that week: the main things that happened or were decided, most important first. Only what's in
the notes, no guessing, at most 300 characters.

NOTES:
{lines}"""
WEEK_SCHEMA = {"type": "object", "properties": {"summary": {"type": "string", "maxLength": 320}},
               "required": ["summary"], "additionalProperties": False}
WEEK_CHECK = """Below are the notes of one week between {USER} and {name} (his AI companion), then a summary someone wrote of
that week. Check the summary against the notes, strictly:
- keep: everything in it is in the notes, as sure as the notes are.
- fix: the gist is there but something is added, wrong, credited to the wrong person, or surer than the notes (a plan
  written as done, a maybe as settled). Give the corrected summary with only what the notes support, same style, at
  most 300 characters.
- drop: it's mostly not in the notes.

NOTES:
{lines}

SUMMARY:
{summary}"""
WEEK_CHECK_SCHEMA = {"type": "object", "properties": {"verdict": {"enum": ["keep", "fix", "drop"]},
                                                      "fixed": {"type": "string", "maxLength": 320}},
                     "required": ["verdict", "fixed"], "additionalProperties": False}
WEEK_TRIES = 2

HUMAN, BOARD = "system/human.md", "system/projects.md"
LATELY_HEAD = re.compile(r"^\*\*Lately:?\*\*:?\s*$", re.I)
LATELY_MAX = 5
LATELY = """{name} ({USER}'s AI companion) keeps a card about {USER}. Its "Lately" part is the few BIG, ongoing things in his
life she should keep in mind for weeks: a struggle, a change at home or work, his health, how he's really doing, what
he's pouring himself into. Not single events, not small talk, not {name}'s own features or updates to her.

Below are the current Lately lines (numbered), then notes of the last two weeks between {USER} and {name} (dated).
- For each current line: "keep" it; "update" it if the notes show it changed (write the whole new line); or "drop"
  it, but ONLY if the notes clearly show it's over. A line the notes don't mention is kept: silence isn't news.
- new: at most 2 new lines, only for something big and ongoing in the notes that no line covers.
At most {most} lines in total. Write like the current lines ({name}'s voice: "he", "I"). Only what the notes support.

CURRENT LATELY LINES:
{current}

NOTES:
{notes}"""
LATELY_SCHEMA = {"type": "object", "properties": {
    "current": {"type": "array", "items": {"type": "object", "properties": {
        "n": {"type": "integer"}, "verdict": {"enum": ["keep", "update", "drop"]}, "text": {"type": "string", "maxLength": 400}},
        "required": ["n", "verdict", "text"], "additionalProperties": False}},
    "new": {"type": "array", "maxItems": 2, "items": {"type": "string", "maxLength": 400}}},
    "required": ["current", "new"], "additionalProperties": False}
LATELY_CHECK = """Below are notes of the last two weeks between {USER} and {name} (his AI companion), then numbered
statements about {USER}'s life. For each statement: is it supported by the notes? "yes" only if the notes clearly
show it; "no" if it's a guess, an exaggeration, or not in the notes.

NOTES:
{notes}

STATEMENTS:
{claims}"""
LATELY_CHECK_SCHEMA = {"type": "object", "properties": {"checks": {"type": "array", "items": {"type": "object", "properties": {
    "n": {"type": "integer"}, "supported": {"enum": ["yes", "no"]}}, "required": ["n", "supported"], "additionalProperties": False}}},
    "required": ["checks"], "additionalProperties": False}
BOARD_CHECK = """Below are the lines of {USER}'s project board (numbered), then notes of the last two weeks between {USER} and
{name} (his AI companion), also numbered. Find board lines the notes CLEARLY show are out of date: the status, the
hurdle or the next step no longer matches what happened (it got built, finished, dropped, started, paused, changed
direction). For each: the board line's number, the numbers of the notes that show it, and one plain sentence on what
changed. Most lines are fine, and an empty list is the usual answer. A line the notes don't mention is fine.

BOARD:
{board}

NOTES:
{notes}"""
BOARD_SCHEMA = {"type": "object", "properties": {"stale": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
    "line": {"type": "integer"}, "notes": {"type": "array", "items": {"type": "integer"}}, "what": {"type": "string", "maxLength": 240}},
    "required": ["line", "notes", "what"], "additionalProperties": False}}}, "required": ["stale"], "additionalProperties": False}

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


SAME_DAY = re.compile(r"\bin (?:a (?:few|couple)(?: of)? |an? |half an |\d+ )?(?:min(?:ute)?s?|hours?|hrs?|bit)\b|"
                      r"\b(?:soon|shortly|later today|right after|after (?:work|my shift)|this (?:morning|afternoon|evening))\b|"
                      r"^\s*(?:at\s+)?\d{1,2}(?::\d\d|\s?(?:am|pm))\s*$")


RESTATED = (r"^(?:{name}|She)\s+(?:recall|remember|remind|confirm|say|state|report|mention|describe|note|explain)"
            r"(?:s|ed)?\b")


REMEMBERING = "remembering, not new"
LOOKBACK = ("recall", "read_chat", "read_file")


def lookback_note(ts, step, name="Companion"):
    what = step.get("query") or step.get("path") or step.get("chat") or ""
    what = " ".join(str(what).split())[:80]
    return (f"[{ts:%H:%M}] ({name} looked back in her memory here: {step['step']}" + (f' "{what}"' if what else "") +
            f". What she says next about earlier days is {REMEMBERING}.)")


def drop_restated(found, chunk, name="Companion"):
    if REMEMBERING not in chunk:
        return found
    restated = re.compile(RESTATED.format(name=re.escape(name)), re.I)
    return dict(found, events=[e for e in found.get("events", []) if not restated.match(e.get("what", ""))])


def parse_due(words_said, said_on):
    t = (words_said or "").lower()
    day = None
    if re.search(r"\b(?:today|tonight)\b", t):
        day = said_on
    elif "day after tomorrow" in t:
        day = said_on + dt.timedelta(days=2)
    elif "tomorrow" in t:
        day = said_on + dt.timedelta(days=1)
    elif "next week" in t:
        day = said_on + dt.timedelta(days=7)
    else:
        for i, name in enumerate(DAYS):
            if re.search(rf"\b{name[:3]}(?:{name[3:]})?\b", t):
                day = said_on + dt.timedelta(days=(i - said_on.weekday()) % 7 or 7)
                break
        m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b", t) or \
            re.search(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", t)
        if m:
            mo = MONTHS[m.group(1)] if m.group(1).isalpha() else int(m.group(1))
            try:
                day = dt.date(said_on.year, mo, int(m.group(2)))
                if day < said_on:
                    day = day.replace(year=day.year + 1)
            except ValueError:
                pass
    if day is None and SAME_DAY.search(t):
        day = said_on
    if day is None:
        return ""
    hm = re.search(r"\b(\d{1,2})(?::(\d\d))?\s?(am|pm)\b", t)
    if hm:
        h = int(hm.group(1)) % 12 + (12 if hm.group(3) == "pm" else 0)
        return f"{day.isoformat()} {h:02d}:{hm.group(2) or '00'}"
    hm = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
    if hm:
        return f"{day.isoformat()} {int(hm.group(1)):02d}:{hm.group(2)}"
    return day.isoformat()


PROMPT_WORDS = {"news", "decision", "notable", "important", "importance", "changing", "small", "talk", "real"}
THREADS_MAX = 12
UNDATED_DAYS = 7
NOT_TAGS = {"companion", "helper", "director", "notable", "decision", "big news", "news", "small talk", "event", "plan",
            "important", "life changing"}
COMMON = {"user", "companion", "said", "told", "talk", "about", "her", "his", "their"}


def similar(a, b, skip=frozenset()):
    wa = words(a.split(" · ")[-1].rsplit(" (", 1)[0]) - COMMON - skip
    wb = words(b.split(" · ")[-1].rsplit(" (", 1)[0]) - COMMON - skip
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.7


COMMIT_HASH = re.compile(r"\s*[(\[]?\s*\bcommit(?:\s+hash)?\s*[:#]?\s*[0-9a-f]{7,40}\b\s*[)\]]?", re.I)


def clean(text, most=220):
    t = COMMIT_HASH.sub("", " ".join(str(text or "").split())).strip()
    t = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", re.sub(r"\s+([.,;:])", r"\1", t))
    return "" if INJECT.search(t) or SECRET.search(t) else t[:most]


def th_ids(lines):
    return [re.sub(r"^- \[t(\d+)\]", r"- [th\1]", ln) for ln in lines]


class Keeper:
    def __init__(self, app, llm=None):
        self.app = app
        self.cfg = app.cfg
        self.llm = llm

    @property
    def name(self):
        return " ".join(str(getattr(self.cfg, "display_name", "") or "").split()) or "Companion"

    @property
    def skip(self):
        return frozenset(words(f"{user_name(self.cfg)} {self.name}"))

    @property
    def mem(self):
        return self.app.engine.memory

    def _lines(self, rel):
        path = os.path.join(self.mem.root, *rel.split("/"))
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            text = f.read()
        body = text.split("\n---\n", 1)[1] if text.startswith("---\n") and "\n---\n" in text else text
        return [ln for ln in body.splitlines() if ln.startswith("- ")]

    def _write(self, rel, lines, message):
        path = os.path.join(self.mem.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as out:
            out.write(fill(f"---\ndescription: {HEADERS[rel]}\n---\n" + "\n".join(lines) + ("\n" if lines else ""), self.cfg))
        self.mem._git("add", "--", rel)
        self.mem._git("commit", "-q", "-m", message, "--", rel)

    def refresh_headers(self):
        n = 0
        for rel in HEADERS:
            path = os.path.join(self.mem.root, *rel.split("/"))
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if f"\ndescription: {HEADERS[rel]}\n" not in text.split("\n---\n", 1)[0] + "\n":
                self._write(rel, self._lines(rel), f"Aether: keeper, {rel.rsplit('/', 1)[-1]} description updated")
                n += 1
        return n

    def material(self, conv, start=0):
        out, lines, day, last = [], [], None, start - 1
        size = 0

        def flush():
            nonlocal lines, size
            if lines:
                out.append((day, "\n".join(lines), last))
            lines, size = [], 0
        skip_reply = looked = False
        for i, e in enumerate(conv.events[start:], start):
            if e["kind"] == "user":
                skip_reply = bool(STRANGER_PLACE.search(e.get("place") or ""))
                looked = False
                if skip_reply or said(e.get("text")) is None:
                    last = i
                    continue
            elif e["kind"] == "reply" and skip_reply:
                last = i
                continue
            elif (e["kind"] == "step" and not skip_reply and not looked and e.get("ts")
                  and (e.get("step") or {}).get("step") in LOOKBACK):
                note = lookback_note(dt.datetime.fromisoformat(e["ts"]), e["step"], self.name)
                lines.append(note)
                size += len(note)
                looked = True
                continue
            if e["kind"] not in ("user", "reply", "made_image"):
                continue
            ts = dt.datetime.fromisoformat(e["ts"]) if e.get("ts") else None
            d = ts.date() if ts else day
            if d != day or size > CHUNK:
                flush()
                day = d
            who = {"user": "{USER}", "reply": self.name}.get(e["kind"])
            text = " ".join(((said(e.get("text")) if e["kind"] == "user" else e.get("text")) or "").split())
            if e["kind"] == "made_image":
                line = f"[{ts:%H:%M}] ({self.name} drew a picture for {USER}: {e.get('caption', '')[:200]})" if ts else ""
            else:
                line = f"[{ts:%H:%M}] {who}: {text[:700 if who == '{USER}' else 500]}" if ts else f"{who}: {text[:600]}"
            if line:
                lines.append(line)
                size += len(line)
            if e["kind"] == "user" and e.get("remembered") and ts:
                gist = [f"{(m.get('when') or '').split(',')[0]}: {' '.join((m.get('text') or '').split())[:90]}"
                        for m in e["remembered"][:3] if m.get("when")]
                if gist:
                    note = (f"[{ts:%H:%M}] (Aether reminded {self.name} of earlier chats here: " + " | ".join(gist) + ". What "
                            f"she says about them is {REMEMBERING}.)")
                    lines.append(note)
                    size += len(note)
            last = i
        flush()
        return out

    def ask(self, day, chat, threads):
        listing = "\n".join(f"[{t[0]}] {t[1]}" for t in threads) or "(none)"
        prompt = KEEPER.format(USER=USER, day=f"{day:%A %Y-%m-%d}", threads=listing, chat=chat, name=self.name)
        llm = self.llm or self.app.engine.llm
        raw = llm.complete([{"role": "user", "content": prompt}], SCHEMA, "keeper", self.cfg.temperature_tools, 1200)
        return json.loads(raw)

    def verify(self, found, chat):
        notes = []
        for kind in ("events", "threads_open", "stances"):
            for i, x in enumerate(found.get(kind) or []):
                if kind == "stances":
                    text = f"TAKE ({self.name}'s own opinion) on {x.get('topic')}: {x.get('take')}"
                elif kind == "threads_open":
                    text = f"UPCOMING (something still ahead of {USER} or promised): {x.get('what')}" + \
                        (f" (when: {x.get('due')})" if x.get("due") else "")
                else:
                    text = x.get("what")
                notes.append((kind, i, text))
        if not notes:
            return found
        listing = "\n".join(f"{n + 1}. {t}" for n, (_, _, t) in enumerate(notes))
        llm = self.llm or self.app.engine.llm
        raw = llm.complete([{"role": "user", "content": VERIFY.format(USER=USER, chat=chat, notes=listing, name=self.name)}], VERIFY_SCHEMA, "keeper_check",
                           self.cfg.temperature_tools, 1200)
        verdicts = {c["n"]: c for c in json.loads(raw).get("checks") or []}
        out = {k: [] for k in ("events", "threads_open", "stances")}
        out["threads_close"] = found.get("threads_close") or []
        for n, (kind, i, _) in enumerate(notes, 1):
            x = dict(found[kind][i])
            c = verdicts.get(n, {"verdict": "keep"})
            if c["verdict"] == "drop":
                continue
            if c["verdict"] == "fix" and len((c.get("fixed") or "").strip()) >= 12:
                fixed = c["fixed"].strip()
                if kind == "stances":
                    x["take"] = fixed.split(":", 1)[-1].strip() if fixed.upper().startswith("TAKE") else fixed
                elif kind == "threads_open":
                    fixed = fixed.split(":", 1)[-1].strip() if fixed.upper().startswith("UPCOMING") else fixed
                    x["what"] = re.sub(r"\s*\(when:[^)]*\)\s*$", "", fixed)
                else:
                    x["what"] = fixed
            out[kind].append(x)
        return out

    def apply(self, found, day, source=""):
        timeline, threads, stances = self._lines(TIMELINE), th_ids(self._lines(THREADS)), self._lines(STANCES)
        n = {"events": 0, "threads": 0, "closed": 0, "stances": 0}
        for ev in found.get("events") or []:
            what = clean(ev.get("what"))
            if len(what) < 12 or int(ev.get("importance") or 3) < 3 or any(similar(what, ln, self.skip) for ln in timeline[-80:]):
                continue
            when = ev.get("when") if re.fullmatch(r"\d{2}:\d{2}", ev.get("when") or "") else "00:00"
            role = ev.get("role", "companion")
            extra = [re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()[:20] for t in (ev.get("tags") or [])]
            extra = [t for t in dict.fromkeys(extra) if t and t != role and t not in NOT_TAGS
                     and not (set(t.split()) & PROMPT_WORDS)][:2]
            tags = ", ".join([role] + extra)
            imp = max(1, min(10, int(ev.get("importance") or 3)))
            timeline.append(f"- {day.isoformat()} {when} · {tags} · {what} ({imp})")
            n["events"] += 1
        ids = {ln.split("]")[0][3:]: ln for ln in threads if ln.startswith("- [")}
        for tid in found.get("threads_close") or []:
            tid = tid.strip("[] ")
            tid = "th" + tid.lstrip("th") if tid.lstrip("th").isdigit() else tid
            if tid in ids:
                line = ids.pop(tid)
                threads.remove(line)
                text = line.split(" · ")[-1]
                timeline.append(f"- {day.isoformat()} 00:00 · done · Resolved: {text} (3)")
                n["closed"] += 1
        for th in found.get("threads_open") or []:
            what = clean(th.get("what"), 180)
            if len(what) < 8 or any(similar(what, ln, self.skip) for ln in threads):
                continue
            nxt = 1 + max([int(k.lstrip("th")) for k in ids if k.lstrip("th").isdigit()] + [0])
            due = parse_due(th.get("due"), day)
            when = f"due {due}" if due else (f"when: \"{clean(th.get('due'), 40)}\"" if th.get("due") else "no date")
            line = f"- [th{nxt}] open since {day.isoformat()} · {when} · {what}"
            threads.append(line)
            ids[f"th{nxt}"] = line
            n["threads"] += 1
        for st in found.get("stances") or []:
            topic, take = clean(st.get("topic"), 30).lower(), clean(st.get("take"))
            if not topic or len(take) < 12:
                continue
            stances = [ln for ln in stances if not ln.startswith(f"- {topic} · ")]
            stances.append(f"- {topic} · {take} (said {day.isoformat()})")
            n["stances"] += 1
        what = f"Aether: keeper ({source or day.isoformat()})"
        if n["events"] or n["closed"]:
            timeline.sort(key=lambda ln: ln[2:18])
            self._write(TIMELINE, timeline, what)
        if n["threads"] or n["closed"]:
            self._write(THREADS, threads, what)
        if n["stances"]:
            self._write(STANCES, stances, what)
        return n

    def open_threads(self):
        return [(ln.split("]")[0][3:], ln.split(" · ")[-1]) for ln in th_ids(self._lines(THREADS)) if ln.startswith("- [")]

    def rollup(self, today):
        timeline = self._lines(TIMELINE)
        weeks = {}
        for ln in timeline:
            m = re.match(r"- (\d{4}-\d{2}-\d{2}) \d{2}:\d{2} · ([^·]*) · (.+)", ln)
            if not m:
                continue
            day = dt.date.fromisoformat(m.group(1))
            monday = day - dt.timedelta(days=day.weekday())
            w = weeks.setdefault(monday, {"rolled": False, "lines": []})
            if m.group(2).strip().startswith("week"):
                w["rolled"] = True
            elif not m.group(2).strip().startswith("done"):
                what = re.sub(r" [(]\d+[)]$", "", m.group(3))
                w["lines"].append(f"{m.group(1)}: {what}")
        this_monday = today - dt.timedelta(days=today.weekday())
        llm = self.llm or self.app.engine.llm
        tries = self.app.life.state.setdefault("keeper", {}).setdefault("_week_tries", {})
        made = 0
        for monday in sorted(weeks):
            w = weeks[monday]
            if monday >= this_monday or w["rolled"] or len(w["lines"]) < 3 or tries.get(monday.isoformat(), 0) >= WEEK_TRIES:
                continue
            notes = "\n".join(w["lines"][-60:])
            raw = llm.complete([{"role": "user", "content": WEEK.format(USER=USER, lines=notes, name=self.name)}], WEEK_SCHEMA,
                               "keeper_week", self.cfg.temperature_tools, 500)
            summary = clean(json.loads(raw).get("summary"), 320)
            if len(summary) >= 20 and getattr(self.cfg, "keeper_verify", True):
                raw = llm.complete([{"role": "user", "content": WEEK_CHECK.format(USER=USER, lines=notes, summary=summary, name=self.name)}],
                                   WEEK_CHECK_SCHEMA, "keeper_week_check", self.cfg.temperature_tools, 500)
                c = json.loads(raw)
                if c.get("verdict") == "drop":
                    summary = ""
                elif c.get("verdict") == "fix":
                    fixed = clean(c.get("fixed"), 320)
                    summary = fixed if len(fixed) >= 20 else ""
            if len(summary) < 20:
                tries[monday.isoformat()] = tries.get(monday.isoformat(), 0) + 1
                continue
            timeline.append(f"- {monday.isoformat()} 00:00 · week · Week of {monday:%a} {monday.month}/{monday.day}: {summary} (6)")
            made += 1
        if made:
            timeline.sort(key=lambda ln: ln[2:18])
            self._write(TIMELINE, timeline, f"Aether: keeper, {made} week(s) summed up")
        return made

    def expire(self, today):
        threads = self._lines(THREADS)
        keep, gone = [], []
        for ln in threads:
            due = re.search(r"due (\d{4}-\d{2}-\d{2})( \d\d:\d\d)?", ln)
            since = re.search(r"open since (\d{4}-\d{2}-\d{2})", ln)
            when = re.search(r'when: "([^"]*)"', ln)
            if not due and when and since:
                again = parse_due(when.group(1), dt.date.fromisoformat(since.group(1)))
                due = re.match(r"(\d{4}-\d{2}-\d{2})( \d\d:\d\d)?", again) if again else None
            grace = 1 if due and due.group(2) else 3
            if due and dt.date.fromisoformat(due.group(1)) < today - dt.timedelta(days=grace):
                gone.append(ln)
            elif not due and since and dt.date.fromisoformat(since.group(1)) < today - dt.timedelta(days=UNDATED_DAYS):
                gone.append(ln)
            else:
                keep.append(ln)
        if len(keep) > THREADS_MAX:
            keep.sort(key=lambda ln: (re.search(r"open since (\S+)", ln) or re.search("(.)", ln)).group(1))
            gone += keep[:-THREADS_MAX]
            keep = keep[-THREADS_MAX:]
        if gone:
            self._write(THREADS, keep, f"Aether: keeper, {len(gone)} thread(s) past due")
        return len(gone)


    def recent(self, today, days=14):
        start = today - dt.timedelta(days=days)
        out = []
        for ln in self._lines(TIMELINE):
            m = re.match(r"- (\d{4}-\d{2}-\d{2}) \d{2}:\d{2} · ([^·]*) · (.+)", ln)
            if not m or m.group(2).strip().startswith("done") or dt.date.fromisoformat(m.group(1)) < start:
                continue
            what = re.sub(r" [(]\d+[)]$", "", m.group(3))
            out.append(f"{m.group(1)}: {what}")
        return out[-80:]

    def _card(self):
        path = os.path.join(self.mem.root, *HUMAN.split("/"))
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            text = f.read().replace("\r\n", "\n")
        lines = text.split("\n")
        head = next((i for i, ln in enumerate(lines) if LATELY_HEAD.match(ln.strip())), None)
        if head is None:
            return None
        items, i = [], head + 1
        while i < len(lines) and (lines[i].startswith("- ") or not lines[i].strip()):
            if lines[i].startswith("- "):
                items.append(i)
            elif items:
                break
            i += 1
        return path, lines, head, items

    def lately(self, today):
        card = self._card()
        notes = self.recent(today)
        if not card or len(notes) < 3:
            return 0
        path, lines, head, items = card
        current = [lines[i][2:].strip() for i in items]
        llm = self.llm or self.app.engine.llm
        numbered = "\n".join(f"{n}. {t}" for n, t in enumerate(current, 1)) or "(none yet)"
        raw = llm.complete([{"role": "user", "content": LATELY.format(USER=USER, most=LATELY_MAX, current=numbered, notes="\n".join(notes), name=self.name)}],
                           LATELY_SCHEMA, "keeper_lately", self.cfg.temperature_tools, 1200)
        d = json.loads(raw)
        verdict = {c["n"]: c for c in d.get("current") or [] if isinstance(c.get("n"), int)}
        claims = []
        for n, old in enumerate(current, 1):
            c = verdict.get(n, {"verdict": "keep"})
            text = clean(c.get("text"), 400)
            if c["verdict"] == "update" and len(text) >= 20 and text != old:
                claims.append(("update", n, text))
            elif c["verdict"] == "drop":
                claims.append(("drop", n, f"This is over or no longer true: {old}"))
        for text in d.get("new") or []:
            text = clean(text, 400)
            if len(text) >= 20 and not any(similar(text, "- " + o, self.skip) for o in current):
                claims.append(("new", 0, text))
        if not claims:
            return 0
        listing = "\n".join(f"{i}. {c[2]}" for i, c in enumerate(claims, 1))
        raw = llm.complete([{"role": "user", "content": LATELY_CHECK.format(USER=USER, notes="\n".join(notes), claims=listing, name=self.name)}],
                           LATELY_CHECK_SCHEMA, "keeper_lately_check", self.cfg.temperature_tools, 600)
        ok = {c["n"] for c in json.loads(raw).get("checks") or [] if c.get("supported") == "yes"}
        result = list(current)
        dropped, added, changed = set(), [], 0
        for i, (kind, n, text) in enumerate(claims, 1):
            if i not in ok:
                continue
            if kind == "update":
                result[n - 1] = text
            elif kind == "drop":
                dropped.add(n - 1)
            else:
                added.append(text)
            changed += 1
        if not changed:
            return 0
        result = [t for j, t in enumerate(result) if j not in dropped] + added
        result = result[:LATELY_MAX]
        new_lines = lines[:head + 1] + [f"- {t}" for t in result] + lines[(items[-1] + 1) if items else head + 1:]
        with open(path, "w", encoding="utf-8", newline="\n") as out:
            out.write("\n".join(new_lines))
        self.mem._git("add", "--", HUMAN)
        self.mem._git("commit", "-q", "-m", f"Aether: keeper, Lately on {USER}'s card ({changed} change(s), checked against the timeline)",
                      "--", HUMAN)
        return changed

    def board_lines(self):
        path = os.path.join(self.mem.root, *BOARD.split("/"))
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            text = f.read()
        out, section = [], ""
        for ln in text.splitlines():
            if ln.startswith("## "):
                section = ln[3:].strip().lower()
            elif section in ("active", "later", "parked") and (ln.startswith("**") or ln.startswith("- ")):
                out.append(ln.strip())
        return out

    def board_check(self, today):
        board, notes = self.board_lines(), self.recent(today)
        if not board or len(notes) < 3:
            return []
        llm = self.llm or self.app.engine.llm
        raw = llm.complete([{"role": "user", "content": BOARD_CHECK.format(USER=USER, name=self.name,
            board="\n".join(f"{n}. {t}" for n, t in enumerate(board, 1)),
            notes="\n".join(f"{n}. {t}" for n, t in enumerate(notes, 1)))}],
            BOARD_SCHEMA, "keeper_board", self.cfg.temperature_tools, 800)
        state = self.app.life.state.setdefault("keeper", {})
        seen = set(state.get("_board_flagged") or [])
        flags = []
        for x in json.loads(raw).get("stale") or []:
            ln = x.get("line")
            proof = [notes[k - 1] for k in x.get("notes") or [] if isinstance(k, int) and 1 <= k <= len(notes)]
            what = clean(x.get("what"), 240)
            if not (isinstance(ln, int) and 1 <= ln <= len(board)) or not proof or len(what) < 12:
                continue
            if board[ln - 1] in seen:
                continue
            seen.add(board[ln - 1])
            flags.append({"line": board[ln - 1], "what": what, "notes": proof[:3]})
        state["_board_flagged"] = [b for b in seen if b in board][-40:]
        return flags

    def run(self, now=None, chats=None, say=print, stop=None):
        from .history import Conversation, list_conversations
        now = now or dt.datetime.now()
        state = self.app.life.state.setdefault("keeper", {})
        totals = {"events": 0, "threads": 0, "closed": 0, "stances": 0, "calls": 0, "failed": 0}
        self.refresh_headers()
        todo = []
        for cid in chats or list_conversations(self.app.conv_dir):
            if cid.startswith(SKIP_CHATS):
                continue
            conv = Conversation(self.app.conv_dir, cid)
            for day, chunk, last in self.material(conv, state.get(cid, 0)):
                first = re.match(r"\[(\d{2}:\d{2})\]", chunk)
                todo.append((day or dt.date.min, first.group(1) if first else "00:00", cid, conv.title()[:40], chunk, last))
        todo.sort(key=lambda t: (t[0], t[1]))
        for day, _, cid, title, chunk, last in todo:
            if day == dt.date.min or len(chunk) < 80:
                state[cid] = max(state.get(cid, 0), last + 1)
                continue
            try:
                found = self.ask(day, chunk, self.open_threads())
                totals["calls"] += 1
                if getattr(self.cfg, "keeper_verify", True):
                    found = self.verify(found, chunk)
                    totals["calls"] += 1
                found = drop_restated(found, chunk, self.name)
                for k, v in self.apply(found, day, source=f"{title}, {day.isoformat()}").items():
                    totals[k] += v
                totals["expired"] = totals.get("expired", 0) + self.expire(day)
            except Exception as e:
                totals["failed"] += 1
                say(f"keeper: {cid} {day}: {e!r}")
            state[cid] = max(state.get(cid, 0), last + 1)
            self.app.life.save()
            if stop is not None and stop():
                say("keeper: stopped for {USER}; the rest is kept on the next run")
                totals["stopped"] = True
                return totals
        totals["expired"] = totals.get("expired", 0) + self.expire(now.date())
        try:
            totals["weeks"] = self.rollup(now.date())
        except Exception as e:
            say(f"keeper: week roll-up: {e!r}")
        monday = (now.date() - dt.timedelta(days=now.weekday())).isoformat()
        if getattr(self.cfg, "keeper_lately", True) and state.get("_lately") != monday:
            try:
                totals["lately"] = self.lately(now.date())
                state["_lately"] = monday
            except Exception as e:
                say(f"keeper: lately: {e!r}")
        totals["board_flags"] = []
        if getattr(self.cfg, "keeper_board_check", True):
            try:
                totals["board_flags"] = self.board_check(now.date())
            except Exception as e:
                say(f"keeper: board check: {e!r}")
        self.app.life.save()
        self.app.engine.refresh()
        return totals
