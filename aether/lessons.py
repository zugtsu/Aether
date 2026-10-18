import datetime as dt
import difflib
import json
import os
import re

HISTORY = "reference/lessons-history.md"
HISTORY_DESC = ("Lessons that left my rulebook: ones that didn't make the mistake rarer, named a skill I don't have "
                "anymore, or were replaced by a newer lesson on the same mistake. With the numbers. Kept, never deleted.")
MARK = "\n[Lessons you wrote before"
OTHER = "other"
KINDS = [
    (r"^You already (?:took|tried) exactly this step", "repeat"),
    (r"^Not that one:|^Nothing changed: (?:you already did|[^.]{1,40}? aren't open)", "not the one he named"),
    (r"you read outside content in this reply|outside content from earlier in this chat", "changes after outside content"),
    (r"^Read first", "save before reading"),
    (r"came out empty or too short", "empty"),
    (r"reads like an instruction", "instruction-like"),
    (r"\S+ didn't allow|\S+ isn't here on your own time|\S+ already said no", "not allowed"),
    (r"^I couldn't tell", "couldn't read the date"),
    (r"usage: |^Wrong arguments|error: (?:the following arguments|unrecognized arguments|argument )|invalid choice", "wrong arguments"),
    (r"matches \d+ lines|appears \d+ times|lines in \S+ match that", "matches several lines"),
    (r"no line on the board contains|is not in \S+, so nothing changed|No line in \S+ matches|There is no memory file",
     "no such line"),
    (r"^\S+ already exists\. To add to it", "file already exists"),
    (r"^Not run:", "command refused"),
    (r"^exit code", "script failed"),
    (r"^Aether hit an error|^Unknown step", "error"),
    (r"used all your steps", "step limit"),
    (r"^Two steps failed", "two failures"),
    (r"got cut off", "cut off"),
    (r"you just told \S+", "claimed without the step"),
]
KINDS = [(re.compile(p, re.I), name) for p, name in KINDS]
BUILTIN = {"reply", "journal", "save_research", "calendar", "recall", "read_chat", "make_image", "make_video", "gallery",
           "wake_me", "set_mood", "task", "memory", "read_file", "read_skill", "shell"}


def what_of(step):
    kind = str((step or {}).get("step") or "")
    if kind == "skill":
        return str(step.get("skill") or "skill")
    return "memory" if kind.startswith("memory_") else kind


def kind_of(result):
    text = " ".join(str(result or "").split(MARK)[0].split())
    return next((name for pat, name in KINDS if pat.search(text)), OTHER)


def tag(step, result):
    return f"{what_of(step)}: {kind_of(result)}"


def norm(text):
    text = re.sub(r"^\s*-\s*(?:\d{4}-\d{2}-\d{2}\s*:\s*)?", "", str(text))
    return " ".join(re.sub(r"[^\w\s/:-]", " ", text.lower()).split())


def line_date(line):
    m = re.match(r"\s*-\s*(\d{4}-\d{2}-\d{2})", str(line))
    return m.group(1) if m else ""


def guess_what(text):
    m = re.match(r"\s*(?:-\s*)?(?:\d{4}-\d{2}-\d{2}\s*:\s*)?([a-z_/]+?)(?:_skills?|_access|_management)?\s*:", str(text), re.I)
    if not m:
        return None
    first = m.group(1).lower().split("/")[0]
    return first if re.fullmatch(r"[a-z_]{3,30}", first) else None


def skill_label(text):
    m = re.match(r"\s*(?:-\s*)?(?:\d{4}-\d{2}-\d{2}\s*:\s*)?([a-z/]+?)_skills?\s*:", str(text), re.I)
    return m.group(1).lower().split("/")[0] if m else None


def read_audit(path, since=None):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                    when = dt.datetime.fromisoformat(r["ts"])
                except (ValueError, KeyError, TypeError):
                    continue
                if since and when < since:
                    continue
                step = r.get("step") if isinstance(r.get("step"), dict) else {}
                ok = bool(r.get("ok"))
                rows.append((when, what_of(step), ok, None if ok else (r.get("tag") or tag(step, r.get("result")))))
    except OSError:
        pass
    return rows


def worse(rows, since, now, before_days=14, rise=0.10, min_fails=2):
    start = since - dt.timedelta(days=before_days)
    out = {}
    for when, what, ok, t in rows:
        if not start <= when < now:
            continue
        r = out.setdefault(what, {"what": what, "before": [0, 0], "after": [0, 0], "kinds": {}})
        side = r["after"] if when >= since else r["before"]
        side[1] += 1
        if not ok:
            side[0] += 1
            if when >= since:
                k = (t or "").split(": ", 1)[-1] or OTHER
                r["kinds"][k] = r["kinds"].get(k, 0) + 1
    res = []
    for r in out.values():
        r["before"], r["after"] = tuple(r["before"]), tuple(r["after"])
        r["worse"] = r["after"][0] >= min_fails and rate(r["after"]) - rate(r["before"]) > rise
        res.append(r)
    return sorted(res, key=lambda r: (not r["worse"], -(rate(r["after"]) - rate(r["before"])), r["what"]))


def counts(rows, tags, start, end):
    whats = {t.split(": ", 1)[0] for t in tags}
    attempts = mistakes = 0
    for when, what, ok, t in rows:
        if not (start <= when < end) or what not in whats:
            continue
        attempts += 1
        if not ok and any(t == x or (x.endswith(": any") and t.split(": ", 1)[0] == x.split(": ", 1)[0]) for x in tags):
            mistakes += 1
    return mistakes, attempts


def measure(rows, tags, added, now, days):
    start = dt.datetime.combine(dt.date.fromisoformat(added), dt.time())
    before = counts(rows, tags, start - dt.timedelta(days=days), start)
    after_end = min(now, start + dt.timedelta(days=days))
    after = counts(rows, tags, start, after_end)
    return {"before": before, "after": after, "days_after": max(0, (after_end - start).days)}


def rate(pair):
    mistakes, attempts = pair
    return mistakes / attempts if attempts else 0.0


def verdict(m, days, min_after=2):
    if m["days_after"] < days:
        return None
    if m["after"][0] >= min_after and rate(m["after"]) >= rate(m["before"]):
        return "didn't help"
    return None


def describe(m):
    (bn, bt), (an, at) = m["before"], m["after"]
    return f"before: {bn} of {bt} tries; after ({m['days_after']} days): {an} of {at} tries"


def report(lines, meta, installed, rows, now, days):
    out = []
    for ln in lines:
        info = meta.get(norm(ln)) or {}
        tags, guessed = info.get("tags") or [], guess_what(ln)
        measured = bool(tags)
        if not tags and guessed:
            tags = [f"{guessed}: any"]
        added = info.get("added") or line_date(ln)
        row = {"line": ln.strip(), "tags": tags, "measured": measured, "numbers": "", "verdict": None}
        gone = skill_label(ln)
        if gone and gone not in installed:
            row["verdict"] = f"names the {gone} skill, which she no longer has"
        elif tags and added:
            m = measure(rows, tags, added, now, days)
            row["numbers"] = describe(m)
            row["verdict"] = verdict(m, days) if measured else None
        out.append(row)
    return out


def similar(a, b, ratio=0.8):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio() >= ratio


def names(what, step=None):
    if what == "memory":
        rel = str((step or {}).get("file") or (step or {}).get("path") or "")
        base = os.path.basename(rel)
        out = {base, os.path.splitext(base)[0]}
    else:
        out = {what, what.replace("_", " ")}
        if what == "save_research":
            out |= {"research"}
    return {w for w in out if len(w) >= 4}


def _names_in(line, words):
    return any(re.search(rf"\b{re.escape(w)}(?:_skill)?\b", line, re.I) for w in words)


def pick(step, result, lines, meta, installed, most=2):
    t, what = tag(step, result), what_of(step)
    if kind_of(result) == "repeat":
        return []
    words = names(what, step)
    scored, seen = [], []
    for ln in lines:
        info = meta.get(norm(ln)) or {}
        if info.get("retired"):
            continue
        tags = info.get("tags") or []
        guessed = guess_what(ln)
        if guessed and guessed not in installed:
            continue
        if t in tags:
            score = 3
        elif ((any(x.split(": ", 1)[0] == what for x in tags) or guessed == what)
              and (what != "memory" or _names_in(ln, words))):
            score = 2
        elif _names_in(ln, words):
            score = 1
        else:
            continue
        scored.append((score, line_date(ln), ln.strip()))
    out = []
    for _, _, ln in sorted(scored, key=lambda x: (x[0], x[1]), reverse=True):
        if not any(similar(ln, s) for s in seen):
            seen.append(ln)
            out.append(ln)
        if len(out) >= most:
            break
    return out


def hint(found):
    return (MARK + ", from mistakes like this one (your own words, from your rulebook and its archive):\n"
            + "\n".join(f"{x if x.startswith('-') else '- ' + x}" for x in found) + "]") if found else ""
