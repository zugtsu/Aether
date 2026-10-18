import datetime as dt
import re

from .keeper import THREADS
from .names import USER

NUDGE_PLACE = "a thread you're keeping"
NUDGE_AFTER = dt.timedelta(hours=2)
EVENING = dt.time(19, 0)
TOO_LATE = dt.timedelta(hours=24)
DUE = re.compile(r"\bdue (\d{4}-\d{2}-\d{2})(?: (\d{2}:\d{2}))?")
ASK = ("[A thread you've been keeping about {USER}'s life: \"{what}\" ({when}). That's past now. Do you want to check on "
       "him about it? If you do, message him in your own words: short and natural, like a friend who remembered, not "
       "a reminder app. If it doesn't feel right (it's small, or you'd be nagging), let it go.]")


def nudge_at(line):
    if " · nudged " in line:
        return None
    m = DUE.search(line)
    if not m:
        return None
    day = dt.date.fromisoformat(m.group(1))
    if m.group(2):
        return dt.datetime.combine(day, dt.time.fromisoformat(m.group(2))) + NUDGE_AFTER
    return dt.datetime.combine(day, EVENING)


class Nudge:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg

    def due(self, now):
        out = []
        for line in self.app.keeper._lines(THREADS):
            at = nudge_at(line)
            if at and at <= now:
                out.append((line, at))
        return sorted(out, key=lambda x: x[1])

    def mark(self, line, now, how="nudged"):
        k = self.app.keeper
        lines = k._lines(THREADS)
        if line not in lines:
            return
        head, what = line.rsplit(" · ", 1)
        lines[lines.index(line)] = f"{head} · nudged {now:%Y-%m-%d %H:%M} · {what}"
        k._write(THREADS, lines, f"Aether: {how} ({what[:40]})")

    def calendar_has(self, line):
        from .life import topic_words
        cal = getattr(self.app, "calendar", None)
        m = DUE.search(line)
        if cal is None or not m or not getattr(self.cfg, "calendar_enabled", False):
            return ""
        day = dt.date.fromisoformat(m.group(1))
        words = topic_words(line.rsplit(" · ", 1)[-1])
        for e in cal.entries():
            if not (topic_words(e["what"]) & words):
                continue
            d, rep = dt.date.fromisoformat(e["day"]), e.get("repeat") or ""
            if (d == day or (rep == "month" and d.day == day.day) or (rep == "year" and (d.month, d.day) == (day.month, day.day))
                    or (rep in ("week", "2 weeks") and d.weekday() == day.weekday())):
                return e["what"]
        return ""

    def wait_reason(self, now):
        life = self.app.life
        why = life.heartbeat_gate(now) or life.message_gate(now)
        if why:
            return why
        return None

    def tick(self, now=None):
        if not getattr(self.cfg, "nudge_enabled", False):
            return False
        now = now or dt.datetime.now()
        due = self.due(now)
        if not due:
            return False
        line, at = due[0]
        if now - at > TOO_LATE:
            self.mark(line, now, "nudge skipped, too late")
            self.app.life.log_event("check-in skipped", line.rsplit(" · ", 1)[-1][:120])
            return False
        covered = self.calendar_has(line)
        if covered:
            self.mark(line, now, "nudge skipped, the calendar has it")
            self.app.life.log_event("check-in skipped", f"the calendar has it ({covered}): {line.rsplit(' · ', 1)[-1][:100]}")
            return False
        if self.wait_reason(now) or not self.app.gpu.acquire(blocking=False):
            return False
        from .life import topic_words
        life = self.app.life
        life._own_begin()
        try:
            self.mark(line, now)
            head = life._head()
            what = line.rsplit(" · ", 1)[-1]
            m = DUE.search(line)
            when = f"it was {dt.datetime.strptime(m.group(1), '%Y-%m-%d'):%A %b %d}".replace(" 0", " ") + \
                (f" at {dt.datetime.strptime(m.group(2), '%H:%M'):%I:%M %p}".replace(" 0", " ") if m.group(2) else "")
            text = ASK.format(USER=USER, what=what, when=when) + "\n\n" + "\n".join(life._own_facts(now))
            life._private_turn(text, NUDGE_PLACE, "thought about a thread", head, now=now, about=topic_words(what))
            return True
        finally:
            life._own_end()
            self.app.gpu.release()
            self.app.broadcast({"type": "done", "chat": "heartbeat", "text": ""})
