import datetime as dt
import os
import re

from .names import fill

CAL = "system/calendar.md"
BY_USER = "user"
OLD_USER = {"jordan"}
HEADER = ("The calendar {USER} and I share: dates that matter, one line each. I add, change or cancel with my calendar "
          "step; {USER} edits it on the Calendar page. My head holds the next two weeks; the rest is in this file.")
AHEAD_DAYS = 14
MAX_OPEN = 60
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_WORDS = [r"\b(?:" + "|".join([d[:k] for k in range(len(d), 2, -1)] + {"thursday": ["thurs"], "wednesday": ["weds"]}
                                 .get(d, [])) + r")\b" for d in DAYS]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], 1)}
PARTS = {"morning": "09:00", "noon": "12:00", "afternoon": "14:00", "evening": "18:00", "night": "21:00",
         "tonight": "21:00", "midnight": "23:59"}
LINE = re.compile(r"^- \[(c\d+)\] (\d{4}-\d{2}-\d{2})(?: (\d{2}:\d{2}))? · (.+?)(?: · every (week|2 weeks|month|year))?"
                  r"(?: · remind ([^·]+?))?(?: · by ([^·]+?))?$")
REPEATS = ("week", "2 weeks", "month", "year")
ASKS_WHATS_ON = re.compile(r"^\W*(?:(?:and|so|ok(?:ay)?|also|just|hey|yo|lucy|um+|uh+)\W+)*"
                           r"(?:do|does|did|is|are|am|any|anything|what|whats|what's|when|whens|when's|how|have|has|"
                           r"got|tell me|show me|list|check|where)\b", re.I)
ADD_ASK = re.compile(r"\b(?:add(?:ing)?|put(?:ting)?|remind(?:ing)?|schedul(?:e|ing)|book(?:ing)?|set(?:ting)?|"
                     r"sav(?:e|ing)|not(?:e|ing)|mark(?:ing)?|pencil|write (?:it |that )?down|"
                     r"keep track|don'?t let me forget|remember)\b", re.I)
ASKING_REDIRECT = ("Nothing added: he's asking what's coming up, not adding anything, and that's already in your "
                   "calendar (the next two weeks are in your head). Answer from it.")

SKILL_LINE = ("the calendar you and {USER} share, for DATES only (a day, a time, a birthday, a payment due): add, move or "
              "cancel them, repeats, reminders. When he ASKS what's coming up (payments, plans, his week), answer from the "
              "calendar in your head (its next two weeks are there): no step. Use your calendar step only to add, move "
              "or cancel (read_skill calendar shows how). Not his project "
              "board: \"put X on the board / the Later list\" is the board skill")
SKILL_DOC = """# Calendar (built into Aether: you use it with your `calendar` step, not the skill step)

The calendar you and {USER} share. It's the file system/calendar.md; your head always holds the next two weeks of it
("Coming up"). {USER} sees and edits the same calendar on his Calendar page.

## When
When he asks: "put this on the calendar", "add this to the calendar", "remember this date, I have X on friday",
"remind me...", "move my ... to ...", "cancel the ...". Dates live on the calendar, not in his facts.
NOT for his project board: "put X on the board", "add X to the Later list / Active / Parked", "mark X done" is the
board skill, even when the project has a day attached. The calendar holds only things that happen on a date.

## How: one calendar step
- do: "add", "change" or "cancel"
- what: a few words for it ("Haircut appointment", "Mom's birthday")
- when: HIS words for the day and time, as he said them: "tuesday at 10am", "oct 12", "the 19th around 3",
  "tomorrow 8pm", "in 2 hours". Never work out the date yourself: Aether does, and tells you what it made of it.
- remind: "" = just noted; "yes" = a week before and 4 hours before (no time: the evening before); or his words
  ("the day before", "2 hours before", "a couple days before", "the day of", "at the time", "3 days before and the
  day of"). A reminder is only for BEFORE the thing (or right at its time), never the new day of a move.
- id: for change or cancel, the [c..] id from your Coming up list or the file ("c2"). For add, leave it empty.

As you fill it in:
```
{"step": "calendar", "do": "add", "id": "", "what": "Haircut appointment", "when": "friday at 2pm", "remind": "yes"}
{"step": "calendar", "do": "change", "id": "c2", "what": "", "when": "monday at 3pm", "remind": ""}
{"step": "calendar", "do": "cancel", "id": "c2", "what": "", "when": "", "remind": ""}
```

## Repeats
Say it in "when": "oct 12 every year", "the 1st of every month", "every tuesday at 7pm", "every other friday". It comes
back by itself. Something every day is not a calendar thing: that's a reminder {USER} sets on his Reminders page.

## Examples
- "remind me to water the plants at 8 tonight" -> do add, what "Water the plants", when "8 tonight", remind "yes"
- "put my mom's birthday on the calendar, it's march 3rd, every year" -> do add, what "Mom's birthday",
  when "mar 3 every year", remind "yes"
- "move the camping trip to saturday, same time" -> do change, id (the trip's), when "saturday"
- "cancel the plumber call" -> do cancel, id (the plumber call's)

## After
Aether answers with the real day and time ("On the calendar [c3]: Tue Oct 6, 10:00 AM..."). Tell {USER} exactly that
day and time, so he can fix it if it's wrong."""
INJECT = re.compile(r"ignore (?:all |your |previous |the )*(?:instructions|rules)|system prompt|you are now|"
                    r"</?(?:system|memory|file)", re.I)
NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "a couple of": 2, "a few": 3,
       "a couple": 2, "couple of": 2, "couple": 2, "few": 3, "several": 3}


class WhenError(ValueError):
    pass


def _next_weekday(today, i):
    return today + dt.timedelta(days=(i - today.weekday()) % 7 or 7)


def _day_of_month(today, d):
    y, m = today.year, today.month
    for _ in range(3):
        try:
            day = dt.date(y, m, d)
            if day >= today:
                return day
        except ValueError:
            pass
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return None


def _time(t):
    m = re.search(r"\b(\d{1,2})(?::(\d\d))?\s?(a\.?m\.?|p\.?m\.?)(?![a-z])", t)
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(3).startswith("p") else 0)
        return f"{h:02d}:{m.group(2) or '00'}", False
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
    if m:
        h = int(m.group(1))
        return f"{h:02d}:{m.group(2)}", 1 <= h <= 12 and not m.group(1).startswith("0")
    m = re.search(r"\b(?:at|around|by|@)\s+(?:around\s+|about\s+)?(\d{1,2})\b(?!\s*(?:st|nd|rd|th|/|\d))", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(1)):02d}:00", True
    for word, hm in PARTS.items():
        if re.search(rf"\b{word}\b", t):
            return hm, False
    return "", False


def parse_repeat(words):
    t = " ".join(str(words or "").lower().split())
    if re.search(r"\bevery (?:single )?(?:day|night|morning|evening|weekday)\b|\bdaily\b|\bnightly\b", t):
        raise WhenError("The calendar repeats every week, every 2 weeks, every month or every year. Something every day "
                        "is a reminder {USER} sets on his Reminders page (Heartbeat & schedules): tell him so.")
    if re.search(r"\bevery (?:other|2|two) (?:weeks?|mon|tue|wed|thu|fri|sat|sun)|\bbi-?weekly\b|\bfortnightly\b", t):
        return "2 weeks"
    if re.search(r"\b(?:every|each) (?:year|birthday)\b|\byearly\b|\bannual(?:ly)?\b|\bonce a year\b", t):
        return "year"
    if re.search(r"\b(?:every|each) month\b|\bmonthly\b|\bof the month\b|\bonce a month\b", t):
        return "month"
    if re.search(r"\b(?:every|each) (?:week|mon|tue|wed|thu|fri|sat|sun)|\bweekly\b|\bonce a week\b", t):
        return "week"
    return ""


def next_after(day, repeat):
    if repeat in ("week", "2 weeks"):
        return day + dt.timedelta(days=7 if repeat == "week" else 14)
    if repeat == "month":
        y, m = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    else:
        y, m = day.year + 1, day.month
    for d in (day.day, 30, 29, 28):
        try:
            return dt.date(y, m, min(d, day.day))
        except ValueError:
            continue
    return dt.date(y, m, 28)


def parse_when(words, now):
    t = " ".join(str(words or "").lower().replace("’", "'").split())
    today = now.date()
    if re.search(r"\byesterday\b|\blast (?:week|night|month|mon|tue|wed|thu|fri|sat|sun)", t) or re.search(r"\bago\b", t):
        raise WhenError(f"'{words}' is in the past: the calendar is for what's coming up. Ask him when he means.")
    day = None
    m = re.search(r"\bin (\d+|an?|one|two|three|four|five|six|a couple of|a few) (minute|min|hour|hr|day|week)s?\b", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUM[m.group(1)]
        unit = m.group(2)
        if unit in ("minute", "min", "hour", "hr"):
            at = now + (dt.timedelta(minutes=n) if unit.startswith("m") else dt.timedelta(hours=n))
            return at.date(), at.strftime("%H:%M")
        day = today + dt.timedelta(days=n * (7 if unit == "week" else 1))
    if day is None:
        if "day after tomorrow" in t:
            day = today + dt.timedelta(days=2)
        elif re.search(r"\btomorrow\b|\btmrw\b|\btmr\b", t):
            day = today + dt.timedelta(days=1)
        elif re.search(r"\b(?:today|tonight)\b|\bthis (?:morning|afternoon|evening)\b", t):
            day = today
        elif re.search(r"\bnext week\b", t):
            day = today + dt.timedelta(days=7)
        elif re.search(r"\bweekend\b", t):
            day = _next_weekday(today, 5) if today.weekday() != 5 else today
    if day is None:
        m = (re.search(r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
                       r"sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", t)
             or re.search(r"(?<![\d/:])(\d{1,2})/(\d{1,2})(?![\d/])", t))
        if m:
            mo = MONTHS[m.group(1)[:3]] if m.group(1).isalpha() else int(m.group(1))
            try:
                day = dt.date(today.year, mo, int(m.group(2)))
            except ValueError:
                raise WhenError(f"'{words}' isn't a real date: ask him which day he means.")
            if day < today:
                day = day.replace(year=day.year + 1)
    if day is None:
        m = re.search(r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b", t)
        if m:
            day = _day_of_month(today, int(m.group(1)))
    if day is None:
        for i, name in enumerate(DAYS):
            if re.search(DAY_WORDS[i], t):
                day = today if i == today.weekday() and re.search(r"\bthis\b", t) else _next_weekday(today, i)
                break
    hm, bare = _time(t)
    if bare:
        h, mins = int(hm[:2]), int(hm[3:])
        if day is None or day == today:
            for cand in (h % 12, h % 12 + 12):
                if (now.hour, now.minute) < (cand, mins):
                    hm = f"{cand:02d}:{mins:02d}"
                    break
            else:
                hm = f"{h % 12:02d}:{mins:02d}"
                day = (day or today) + dt.timedelta(days=1)
        else:
            hm = f"{(h + 12 if 1 <= h <= 7 else h):02d}:{mins:02d}"
    if day is None:
        if not hm:
            raise WhenError(f"I couldn't tell a day from '{words}': ask him which day (and the time, if it has one).")
        day = today if hm > now.strftime("%H:%M") else today + dt.timedelta(days=1)
    if day < today or (day == today and hm and hm <= now.strftime("%H:%M")):
        raise WhenError(f"'{words}' is already past (it's {now:%a %b %d, %I:%M %p} now): ask him when he means.")
    return day, hm


def _earlier_than_sleep(cfg, at):
    from .life import in_quiet_hours
    if not in_quiet_hours(cfg, at):
        return at
    h, m = (int(x) for x in cfg.quiet_start.split(":"))
    before = at.replace(hour=h, minute=m) - dt.timedelta(minutes=30)
    return before if before <= at else before - dt.timedelta(days=1)


def event_time(day, hm):
    return dt.datetime.combine(day, dt.time.fromisoformat(hm)) if hm else dt.datetime.combine(day, dt.time(0, 0))


def default_reminders(cfg, day, hm, now, repeat=""):
    if hm:
        at = event_time(day, hm)
        times = [at - dt.timedelta(days=7), at - dt.timedelta(hours=4)]
    else:
        eve = dt.datetime.combine(day, dt.time(20, 0))
        times = [eve - dt.timedelta(days=7), eve - dt.timedelta(days=1)]
    out = []
    for i, t in enumerate(times):
        t = _earlier_than_sleep(cfg, t)
        if i == 0 and (t < now + dt.timedelta(days=2) or repeat == "week"):
            continue
        if t > now + dt.timedelta(minutes=2) and t not in out:
            out.append(t)
    return out


def parse_remind(cfg, words, day, hm, now, repeat=""):
    t = " ".join(str(words or "").lower().split())
    if t in ("", "no", "none", "false", "noted", "no reminder"):
        return []
    if t in ("yes", "true", "default", "remind", "remind me", "yes please"):
        return default_reminders(cfg, day, hm, now, repeat)
    at = event_time(day, hm) if hm else dt.datetime.combine(day, dt.time(20, 0))
    out = []
    for part in re.split(r"\s*(?:,|\band\b|\bplus\b|&)\s*", t):
        if not part:
            continue
        m = re.search(r"(\d+|a couple of|a couple|couple of|couple|a few|few|several|an?|one|two|three|four|five|six)\s+"
                      r"(minute|min|hour|hr|day|week)s?\s+(?:before|ahead|early|earlier|prior)", part)
        if m:
            n = int(m.group(1)) if m.group(1).isdigit() else NUM[m.group(1)]
            unit = m.group(2)
            delta = {"minute": dt.timedelta(minutes=n), "min": dt.timedelta(minutes=n), "hour": dt.timedelta(hours=n),
                     "hr": dt.timedelta(hours=n), "day": dt.timedelta(days=n), "week": dt.timedelta(weeks=n)}[unit]
            out.append(at - delta)
        elif re.search(r"\b(?:the )?(?:day|night|evening) before\b", part):
            out.append(dt.datetime.combine(day - dt.timedelta(days=1), dt.time(20, 0)))
        elif re.search(r"\bweek before\b", part):
            out.append(at - dt.timedelta(days=7))
        elif re.search(r"\bmorning of\b|\bthat morning\b", part):
            out.append(dt.datetime.combine(day, dt.time(9, 0)))
        elif re.search(r"^(?:on )?(?:the )?day of(?: it)?$|^on the day$|^that day$|^same day$", part):
            nine = dt.datetime.combine(day, dt.time(9, 0))
            out.append(min(nine, event_time(day, hm) - dt.timedelta(hours=1)) if hm else nine)
        elif re.search(r"\b(?:at|on) the time\b|\bwhen it(?:'s| is)? (?:due|starts?|happens)\b|\bright when\b|"
                       r"\bat the same time\b|\bwhen it starts\b", part):
            out.append(event_time(day, hm) if hm else dt.datetime.combine(day, dt.time(9, 0)))
        else:
            try:
                d2, hm2 = parse_when(part, now)
            except WhenError:
                raise WhenError(f"I couldn't tell when to remind him from '{part}': ask him.")
            out.append(event_time(d2, hm2 or "20:00"))
    out = sorted({_earlier_than_sleep(cfg, x) for x in out})
    end = event_time(day, hm) if hm else dt.datetime.combine(day, dt.time(23, 59))
    late = next((x for x in out if x > end), None)
    if late is not None:
        raise WhenError(f"A reminder at {say_at(late, now)} would come after {say_when(day, hm, now)} itself. To move the "
                        "date, put the new day in \"when\" and leave \"remind\" empty; a reminder is only for before it.")
    return [x for x in out if x > now + dt.timedelta(minutes=2)]


def say_when(day, hm, now=None):
    now = now or dt.datetime.now()
    if day == now.date():
        d = "today"
    elif day == now.date() + dt.timedelta(days=1):
        d = "tomorrow"
    else:
        d = f"{day:%a %b} {day.day}" + (f", {day.year}" if day.year != now.year else "")
    if not hm:
        return d
    return f"{d}, {dt.datetime.strptime(hm, '%H:%M'):%I:%M %p}".replace(", 0", ", ")


def say_at(x, now=None):
    return say_when(x.date(), x.strftime("%H:%M"), now)


class Calendar:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg

    @property
    def her_name(self):
        return " ".join(str(getattr(self.cfg, "display_name", "") or "").split()) or "Companion"

    @property
    def mem(self):
        return self.app.engine.memory

    def entries(self):
        path = os.path.join(self.mem.root, *CAL.split("/"))
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return parse(f.read())

    @staticmethod
    def line(e):
        rem = ", ".join(r["at"] + (" ✓" if r["done"] else "") for r in e["reminders"])
        return (f"- [{e['id']}] {e['day']}" + (f" {e['time']}" if e["time"] else "") + f" · {e['what']}"
                + (f" · every {e['repeat']}" if e.get("repeat") else "")
                + (f" · remind {rem}" if rem else "") + (f" · by {e['by']}" if e["by"] else ""))

    def _write(self, entries, message):
        path = os.path.join(self.mem.root, *CAL.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        entries = sorted(entries, key=lambda e: (e["day"], e["time"] or "00:00"))
        with open(path, "w", encoding="utf-8", newline="\n") as out:
            out.write(f"---\ndescription: {fill(HEADER, self.cfg)}\n---\n" + "".join(self.line(e) + "\n" for e in entries))
        self.mem._git("add", "--", CAL)
        self.mem._git("commit", "-q", "-m", message, "--", CAL)
        self.app.engine.refresh()

    def _new_id(self, entries):
        return "c" + str(1 + max([int(e["id"][1:]) for e in entries] + [0]))

    def add(self, what, day, hm, reminders, by, now=None, repeat=""):
        now = now or dt.datetime.now()
        what = clean(what)
        if len(what) < 3:
            raise ValueError("Say what it is (a few words: 'haircut appointment', 'Mom's birthday').")
        entries = self.entries()
        ahead = [e for e in entries if e["day"] >= now.date().isoformat()]
        if len(ahead) >= MAX_OPEN:
            raise ValueError(f"The calendar already has {len(ahead)} dates coming up; cancel some first.")
        same = next((e for e in entries if e["day"] == day.isoformat() and e["time"] == hm
                     and e["what"].lower() == what.lower()), None)
        if same:
            return same, False
        e = {"id": self._new_id(entries), "day": day.isoformat(), "time": hm, "what": what, "repeat": repeat,
             "reminders": [{"at": x.strftime("%Y-%m-%d %H:%M"), "done": False} for x in reminders], "by": by}
        self._write(entries + [e], f"calendar: {what[:50]} on {day.isoformat()}" + (f" {hm}" if hm else "")
                    + (f", every {repeat}" if repeat else "") + f" (by {by})")
        return e, True

    def change(self, cid, by, what=None, day=None, hm=None, reminders=None, repeat=None):
        entries = self.entries()
        e = next((x for x in entries if x["id"] == cid), None)
        if e is None:
            raise ValueError(f"There's no {cid} on the calendar. The ids are in your calendar file ([c1], [c2]...).")
        if what is not None:
            what = clean(what)
            if len(what) < 3:
                raise ValueError("Say what it is.")
            e["what"] = what
        if day is not None:
            e["day"], e["time"] = day.isoformat(), hm or ""
        if reminders is not None:
            e["reminders"] = [{"at": x.strftime("%Y-%m-%d %H:%M"), "done": False} for x in reminders]
        if repeat is not None:
            e["repeat"] = repeat
        self._write(entries, f"calendar: changed {cid} ({e['what'][:40]}) (by {by})")
        return e

    def not_named(self, cid, his):
        entries = self.entries()
        said = words_of(his)
        hits = {e["id"]: len(said & words_of(e["what"])) for e in entries}
        best = max(entries, key=lambda e: hits[e["id"]], default=None)
        if best is None or hits.get(cid, 0) or not hits[best["id"]] or re.search(rf"\b{re.escape(cid)}\b", his, re.I):
            return ""
        chosen = next((e for e in entries if e["id"] == cid), None)
        return (f"{NOT_NAMED}: [{cid}] is \"{chosen['what'] if chosen else '?'}\", and his message doesn't name it. "
                f"[{best['id']}] \"{best['what']}\" matches his words. Nothing changed: take the step again with the id "
                f"of the line he means.")

    def cancel(self, cid, by):
        entries = self.entries()
        e = next((x for x in entries if x["id"] == cid), None)
        if e is None:
            raise ValueError(f"There's no {cid} on the calendar.")
        self._write([x for x in entries if x["id"] != cid], f"calendar: cancelled {cid} ({e['what'][:40]}) (by {by})")
        return e

    def option(self):
        ids = [""] + [e["id"] for e in self.entries()]
        return {"type": "object", "properties": {
            "step": {"const": "calendar"}, "do": {"enum": ["add", "change", "cancel"]},
            "id": {"enum": ids}, "what": {"type": "string", "maxLength": 160},
            "when": {"type": "string", "maxLength": 80}, "remind": {"type": "string", "maxLength": 80}},
            "required": ["step", "do", "id", "what", "when", "remind"], "additionalProperties": False}

    def run_step(self, step, now=None, his=""):
        now = now or dt.datetime.now()
        do = step.get("do")
        cid = str(step.get("id") or "").strip().strip("[]")
        if do == "add" and ASKS_WHATS_ON.search(his or "") and not ADD_ASK.search(his):
            return False, ASKING_REDIRECT
        if do in ("change", "cancel") and his:
            wrong = self.not_named(cid, his)
            if wrong:
                return False, wrong
        try:
            if do == "cancel":
                e = self.cancel(cid, self.her_name)
                return True, f"Cancelled [{e['id']}]: {e['what']} ({say_when(dt.date.fromisoformat(e['day']), e['time'], now)})."
            when = str(step.get("when") or "").strip()
            if do == "change":
                old = next((x for x in self.entries() if x["id"] == cid), None)
                if old is None:
                    raise ValueError(f"There's no {cid or 'id'} on the calendar: use the [c..] id from your calendar file.")
                day, hm = parse_when(when, now) if when else (dt.date.fromisoformat(old["day"]), old["time"])
                if when and not hm and old["time"] and not re.search(r"all day|no time", when, re.I):
                    hm = old["time"]
                rem = str(step.get("remind") or "").strip()
                reminders = parse_remind(self.cfg, rem, day, hm, now) if rem else (
                    default_reminders(self.cfg, day, hm, now) if when and old["reminders"] else None)
                e = self.change(cid, self.her_name, what=(step.get("what") or None), day=day if when else None, hm=hm,
                                reminders=reminders, repeat=(parse_repeat(when) or None) if when else None)
                return True, self._said(e, now, "Changed")
            repeat = parse_repeat(when)
            day, hm = parse_when(when, now)
            reminders = parse_remind(self.cfg, step.get("remind"), day, hm, now, repeat)
            e, new = self.add(step.get("what"), day, hm, reminders, self.her_name, now, repeat=repeat)
            return True, self._said(e, now, "On the calendar" if new else "Already on the calendar")
        except WhenError as ex:
            return False, str(ex)
        except ValueError as ex:
            return False, str(ex)

    def _said(self, e, now, head):
        day = dt.date.fromisoformat(e["day"])
        rem = [say_at(dt.datetime.strptime(r["at"], "%Y-%m-%d %H:%M"), now) for r in e["reminders"] if not r["done"]]
        return (f"{head} [{e['id']}]: {say_when(day, e['time'], now)} · {e['what']}. "
                + (f"Repeats every {e['repeat']}. " if e.get("repeat") else "")
                + (f"Reminders: {'; '.join(rem)}." if rem else "No reminder (just noted).")
                + " Tell {USER} the day and time exactly as written here, so he can correct it if it's wrong.")

    def roll(self, now=None):
        now = now or dt.datetime.now()
        entries, moved = self.entries(), []
        for e in entries:
            if e.get("repeat") not in REPEATS:
                continue
            day = dt.date.fromisoformat(e["day"])
            start = event_time(day, e["time"]) if e["time"] else dt.datetime.combine(day, dt.time(0, 0))
            end = start if e["time"] else dt.datetime.combine(day, dt.time(23, 59))
            if end >= now:
                continue
            new = day
            while (event_time(new, e["time"]) if e["time"] else dt.datetime.combine(new, dt.time(23, 59))) < now:
                new = next_after(new, e["repeat"])
            new_start = event_time(new, e["time"]) if e["time"] else dt.datetime.combine(new, dt.time(0, 0))
            rem = []
            for r in e["reminders"]:
                at = _earlier_than_sleep(self.cfg, new_start - (start - dt.datetime.strptime(r["at"], "%Y-%m-%d %H:%M")))
                if at > now and at.strftime("%Y-%m-%d %H:%M") not in rem:
                    rem.append(at.strftime("%Y-%m-%d %H:%M"))
            e["day"], e["reminders"] = new.isoformat(), [{"at": a, "done": False} for a in sorted(rem)]
            moved.append(e)
        if moved:
            self._write(entries, "calendar: next time for " + ", ".join(f"{e['what'][:30]} ({e['day']})" for e in moved))
        return len(moved)

    def due(self, now):
        out = []
        for e in self.entries():
            for r in e["reminders"]:
                if not r["done"] and dt.datetime.strptime(r["at"], "%Y-%m-%d %H:%M") <= now:
                    out.append((e, r))
        return sorted(out, key=lambda x: x[1]["at"])

    def mark(self, cid, at):
        entries = self.entries()
        for e in entries:
            if e["id"] == cid:
                for r in e["reminders"]:
                    if r["at"] == at:
                        r["done"] = True
        self._write(entries, f"calendar: reminder {cid} {at} done")

    def tick(self, now=None):
        now = now or dt.datetime.now()
        self.roll(now)
        due = self.due(now)
        if not due:
            return False
        e, r = due[0]
        day = dt.date.fromisoformat(e["day"])
        start = event_time(day, e["time"]) if e["time"] else dt.datetime.combine(day, dt.time(23, 59))
        life = self.app.life
        if start <= now:
            self.mark(e["id"], r["at"])
            life.log_event("calendar reminder missed", f"{e['what'][:100]} ({e['day']})")
            return False
        if self.app.engine.busy or not self.app.gpu.acquire(blocking=False):
            return False
        try:
            self.mark(e["id"], r["at"])
            late = (now - dt.datetime.strptime(r["at"], "%Y-%m-%d %H:%M")) > dt.timedelta(minutes=20)
            when = say_when(day, e["time"], now)
            note = (f"Calendar reminder: {e['what']}, {when}" + (f" (in {_until(now, start)})" if e["time"] else "")
                    + ". Tell him in your own words, short, like a friend who remembered."
                    + (f" It's late: it was meant for {say_at(dt.datetime.strptime(r['at'], '%Y-%m-%d %H:%M'), now)}, "
                       "and Aether was closed then; you can say so." if late else ""))
            life.fire({"name": f"calendar: {e['what'][:40]}", "prompt": note, "to": "",
                       "speak": self.cfg.speak_replies == "always", "voice": False})
            return True
        finally:
            self.app.gpu.release()


def parse(text):
    body = text.split("\n---\n", 1)[1] if text.startswith("---\n") and "\n---\n" in text else text
    out = []
    for ln in body.splitlines():
        m = LINE.match(ln.strip())
        if not m:
            continue
        rem = []
        for r in (m.group(6) or "").split(","):
            mm = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})( ✓)?$", r.strip())
            if mm:
                rem.append({"at": mm.group(1), "done": bool(mm.group(2))})
        out.append({"id": m.group(1), "day": m.group(2), "time": m.group(3) or "", "what": m.group(4).strip(),
                    "repeat": m.group(5) or "", "reminders": rem, "by": by_of(m.group(7))})
    return sorted(out, key=lambda e: (e["day"], e["time"] or "00:00"))


def by_of(word):
    word = " ".join(str(word or "").split())
    return BY_USER if word.lower() in OLD_USER | {BY_USER} else word


def view(text, today=None):
    today = today or dt.date.today()
    end = (today + dt.timedelta(days=AHEAD_DAYS)).isoformat()
    now = dt.datetime.combine(today, dt.time(0, 0))
    es = parse(text)
    rows = []
    for e in (x for x in es if today.isoformat() <= x["day"] <= end):
        rem = [say_at(dt.datetime.strptime(r["at"], "%Y-%m-%d %H:%M"), now) for r in e["reminders"] if not r["done"]]
        rows.append(f"- [{e['id']}] {say_when(dt.date.fromisoformat(e['day']), e['time'], now)} · {e['what']}"
                    + (f" (every {e['repeat']})" if e.get("repeat") else "")
                    + (f" (reminders: {'; '.join(rem)})" if rem else ""))
    later = [e for e in es if e["day"] > end]
    if not rows and later:
        e = later[0]
        rows = [f"- nothing in the next two weeks; next after that: [{e['id']}] "
                f"{say_when(dt.date.fromisoformat(e['day']), e['time'], now)} · {e['what']}"]
        later = later[1:]
    return "\n".join([f"Coming up (today is {today:%a %b} {today.day}):"] + (rows or ["- nothing in the next two weeks"])
                     + ([f"({len(later)} more later in this file)"] if later else []))


def _until(now, at):
    mins = int((at - now).total_seconds() // 60)
    if mins < 60:
        return f"{mins} minutes"
    hours = mins // 60
    if hours < 48:
        return f"about {hours} hour{'s' if hours != 1 else ''}"
    return f"{hours // 24} days"


NOT_NAMED = "Not that one"
CAL_STOP = set("""calendar reminder reminders remind cancel remove delete change move moved take taken thing things that
this these those there their they them what when with from have just called sorted myself please thanks love today
tonight tomorrow later earlier yesterday week month morning evening night anymore already about into your mine it's
off the and for can you got due set get put one ones need needs don't dont should would could also thats that's
whats what's gonna wanna""".split())


def words_of(text):
    return {w[:5] for w in re.findall(r"[a-z0-9']{4,}", str(text or "").lower()) if w not in CAL_STOP}


def clean(text):
    t = " ".join(str(text or "").replace("·", "-").replace("[", "(").replace("]", ")").split())[:160]
    return "" if INJECT.search(t) else t
