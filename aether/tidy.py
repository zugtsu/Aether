import datetime as dt
import difflib
import json
import os
import re

from .memory import DATE_PREFIX, _norm
from .names import fill

FACTS = "system/human/facts.md"
HISTORY = "reference/facts-history.md"
MAX_MERGES, MAX_RETIRES = 4, 4
DATED = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(\d{4}-\d{2}-\d{2})(?:\*\*)?\s*[:\-–—]?\s*(.*)$")
TIME_BOUND = re.compile(r"\b(currently|right now|this week|this month|today|tonight|tomorrow|next|due|trying to|"
                        r"plans? to|going to|wants to|about to|soon)\b", re.I)
NUM = re.compile(r"\d+(?:[.,]\d+)?")
WORD = re.compile(r"[a-z][a-z']{3,}")
HEDGED = re.compile(r"\b(?:maybe|might|possibly|probably|perhaps|thinks?|thinking (?:about|of)|considering|plans? to|"
                    r"planning|hop(?:es|ing) to|wants? to|not sure|unsure|undecided|could|if he|whether)\b|"
                    r"\b(?:about|around|roughly|like) \$?\d", re.I)
DESCRIPTION = ("Facts {USER} told me about himself, in his words, dated. I add a line when he tells me something; "
               "when a fact changes or stops being true I fix or remove its line. Old versions are kept in "
               "reference/facts-history.md, and Aether tidies this file every night. After a month a line moves to "
               "reference/about-user.md (my recall finds it there); the lasting core is in system/human/core.md.")
ABOUT = "reference/about-user.md"
CORE = "system/human/core.md"
ASK = ("[Aether: nightly tidy of your facts about {USER}. Below are the fact lines, numbered, oldest first.\n"
       "- merges: lines that say the SAME thing (or one is a newer version of the other). Give their numbers "
       "and ONE line that keeps every detail, number and date from them, in his words, without a date in front. "
       "Never merge different facts just to make things shorter. Keep how sure he was: a line that says he might, "
       "thinks or is considering something still says so (unless a newer line says it's settled).\n"
       "- retire: a line a NEWER line fully replaced (a plan that changed, a date that passed, a show he finished). "
       "If the old line has a detail the new one lacks, merge them instead. Only when you're sure.\n"
       "Empty lists are fine; most nights nothing needs doing.]\n\n")


def nums(text):
    return {n.replace(",", "") for n in NUM.findall(text or "")}


def topic(text):
    return {w for w in WORD.findall((text or "").lower())} - {"user", "that", "with", "this", "from", "have", "wants"}


def parse(text):
    from .memory import split_frontmatter
    meta, fm, body = split_frontmatter(text.replace("\r\n", "\n"))
    pre, facts = [], []
    for ln in body.splitlines():
        m = DATED.match(ln)
        if m and m.group(2).strip():
            facts.append([m.group(1), " ".join(m.group(2).split())])
        elif ln.strip() and ln.strip() not in pre:
            pre.append(ln.strip())
    return meta, pre, facts


def render(meta, pre, facts):
    desc = meta.get("description", "")
    if "Aether tidies" not in desc or "I only ADD" in desc:
        desc = DESCRIPTION
    head = [p for p in pre if p.startswith("#")][:1] or ["# Facts {USER} told me"]
    rest = [p for p in pre if p not in head]
    out = f"---\ndescription: {desc}\n---\n{head[0]}\n\n" + ("\n".join(rest) + "\n\n" if rest else "")
    return out + "\n".join(f"- {d}: {t}" for d, t in facts) + "\n"


def dedupe(facts):
    kept, removed = [], []
    for d, t in facts:
        k = _norm(t)
        twin = next((x for x in kept if _norm(x[1]) == k or
                     (difflib.SequenceMatcher(None, _norm(x[1]), k).ratio() >= 0.92 and nums(x[1]) == nums(t))), None)
        if twin:
            removed.append((d, t))
        else:
            kept.append([d, t])
    return kept, removed


def related(facts):
    out = []
    for i in range(len(facts)):
        for j in range(i + 1, len(facts)):
            a, b = topic(facts[i][1]), topic(facts[j][1])
            if len(a & b) >= 3 or (len(a & b) >= 2 and len(a & b) >= 0.4 * min(len(a), len(b))):
                out.append((i + 1, j + 1))
    return out


def merged_text(m):
    return DATE_PREFIX.sub("", " ".join(str(m.get("text", "")).split()), count=1).strip()


def check_merge(facts, m):
    idx = sorted({int(i) for i in m.get("lines") or []})
    if len(idx) < 2 or any(i < 1 or i > len(facts) for i in idx):
        return "needs two or more real line numbers"
    text = merged_text(m)
    if not 10 <= len(text) <= 400:
        return "the merged line is empty or too long"
    for i in idx:
        others = " ".join(facts[j - 1][1] for j in idx if j != i)
        if len(topic(facts[i - 1][1]) & topic(others)) < 2:
            return f"line {i} isn't about the same thing as the others (separate facts stay separate)"
    olds = " ".join(facts[i - 1][1] for i in idx)
    if nums(text) - nums(olds):
        return "the merged line has a number that wasn't in the originals"
    if nums(olds) - nums(text):
        return "the merged line dropped a number: " + ", ".join(sorted(nums(olds) - nums(text)))
    if len(topic(text) & topic(olds)) < 2:
        return "the merged line isn't about the same thing"
    newest = facts[max(idx, key=lambda i: (facts[i - 1][0], i)) - 1][1]
    if HEDGED.search(newest) and not HEDGED.search(text):
        return "the merged line sounds surer than he was (the newest line says might / thinks / considering)"
    return None


def check_retire(facts, r, today):
    i = int(r.get("line") or 0)
    if not 1 <= i <= len(facts):
        return "no such line"
    d, t = facts[i - 1]
    newer = [x for x in facts if x[0] > d and len(topic(x[1]) & topic(t)) >= 2]
    old = (today - dt.date.fromisoformat(d)).days >= 21
    if TIME_BOUND.search(t) and old:
        return None
    if not newer:
        return "no newer line replaces it, and it isn't an old time-bound fact"
    lost = nums(t) - nums(" ".join(x[1] for x in newer))
    if lost:
        return "the newer line doesn't have its numbers (" + ", ".join(sorted(lost)) + "); merge them instead"
    return None


def tidy_facts(memory, llm=None, today=None, temperature=0.2, dry_run=False, say=None):
    say = say or (lambda s: None)
    today = today or dt.date.today()
    path = os.path.join(memory.root, *FACTS.split("/"))
    if not os.path.exists(path):
        return {"changed": False, "why": "no facts file"}
    with open(path, encoding="utf-8") as f:
        before = f.read()
    meta, pre, facts = parse(before)
    facts.sort(key=lambda x: x[0])
    facts, dups = dedupe(facts)
    history = [f"- duplicate removed: {d}: {t}" for d, t in dups]
    merged = retired = 0
    refused = []
    pairs = related(facts)
    stale = [i for i, (d, t) in enumerate(facts, 1)
             if TIME_BOUND.search(t) and (today - dt.date.fromisoformat(d)).days >= 21]
    if llm is not None and (pairs or stale):
        listing = "\n".join(f"{i}. {d}: {t}" for i, (d, t) in enumerate(facts, 1))
        if pairs:
            listing += ("\n\nLines that look related (they may still be separate facts): " +
                        ", ".join(f"{a} and {b}" for a, b in pairs))
        if stale:
            listing += ("\n\nOld lines about something time-bound (retire only if it's surely over): " +
                        ", ".join(map(str, stale)))
        schema = {"type": "object", "properties": {
            "merges": {"type": "array", "maxItems": MAX_MERGES, "items": {"type": "object", "properties": {
                "lines": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "integer"}},
                "text": {"type": "string"}, "why": {"type": "string"}},
                "required": ["lines", "text", "why"], "additionalProperties": False}},
            "retire": {"type": "array", "maxItems": MAX_RETIRES, "items": {"type": "object", "properties": {
                "line": {"type": "integer"}, "why": {"type": "string"}},
                "required": ["line", "why"], "additionalProperties": False}}},
            "required": ["merges", "retire"], "additionalProperties": False}
        try:
            raw = llm.complete([{"role": "user", "content": ASK + listing}], schema, "tidy", temperature, 1200)
            plan = json.loads(raw)
        except Exception as e:
            plan = {"merges": [], "retire": []}
            refused.append(f"the model's answer was unusable: {e!r}"[:160])
        used, drop, add = set(), set(), []
        for m in plan.get("merges") or []:
            why = check_merge(facts, m)
            idx = sorted({int(i) for i in m.get("lines") or []}) if why is None else []
            if why is None and used & set(idx):
                why = "overlaps another change"
            if why:
                refused.append(f"merge {m.get('lines')}: {why}")
                continue
            used |= set(idx)
            drop |= set(idx)
            text = merged_text(m)
            newest = max(facts[i - 1][0] for i in idx)
            add.append([newest, text])
            history.append(f"- merged ({' '.join(str(m.get('why', '')).split())[:120]}):\n" +
                           "".join(f"  - was: {facts[i - 1][0]}: {facts[i - 1][1]}\n" for i in idx) +
                           f"  - now: {newest}: {text}")
            merged += 1
        for r in plan.get("retire") or []:
            i = int(r.get("line") or 0)
            why = "overlaps another change" if i in used else check_retire(facts, r, today)
            if why:
                refused.append(f"retire {i}: {why}")
                continue
            used.add(i)
            drop.add(i)
            history.append(f"- retired ({' '.join(str(r.get('why', '')).split())[:120]}): {facts[i - 1][0]}: {facts[i - 1][1]}")
            retired += 1
        facts = sorted([f for i, f in enumerate(facts, 1) if i not in drop] + add, key=lambda x: x[0])
    after = fill(render(meta, pre, facts), memory.cfg)
    report = {"changed": after != before, "duplicates": len(dups), "merged": merged, "retired": retired,
              "refused": refused, "history": history}
    for r in refused:
        say("  refused " + r)
    if dry_run or after == before:
        report["preview"] = after
        return report
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(after)
    changed = [FACTS]
    if history:
        hpath = os.path.join(memory.root, *HISTORY.split("/"))
        os.makedirs(os.path.dirname(hpath), exist_ok=True)
        new = not os.path.exists(hpath)
        with open(hpath, "a", encoding="utf-8", newline="\n") as f:
            if new:
                f.write(fill("---\ndescription: Old versions of {USER}'s facts, moved here by Aether's nightly tidy. "
                             "Nothing here is current; it's the record of what changed and why.\n---\n", memory.cfg))
            f.write(f"\n## {today.isoformat()}\n\n" + "\n".join(history) + "\n")
        changed.append(HISTORY)
    parts = [f"{n} {w}" for n, w in ((len(dups), "duplicate(s)"), (merged, "merged"), (retired, "retired")) if n]
    memory._git("add", "--", *changed)
    memory._git("commit", "-q", "-m", "facts tidy: " + (", ".join(parts) or "format and order"), "-m", "via Aether", "--", *changed)
    memory.reload()
    report["commit"] = memory._git("rev-parse", "--short", "HEAD").stdout.strip()
    return report


def roll_facts(memory, today=None, keep_days=30):
    today = today or dt.date.today()
    path = os.path.join(memory.root, *FACTS.split("/"))
    if not os.path.exists(path):
        return {"moved": 0}
    with open(path, encoding="utf-8") as f:
        before = f.read()
    meta, pre, facts = parse(before)
    cutoff = (today - dt.timedelta(days=keep_days)).isoformat()
    keep = [x for x in facts if x[0] >= cutoff]
    move = sorted((x for x in facts if x[0] < cutoff), key=lambda x: x[0])
    if not move:
        return {"moved": 0}
    apath = os.path.join(memory.root, *ABOUT.split("/"))
    os.makedirs(os.path.dirname(apath), exist_ok=True)
    new = not os.path.exists(apath)
    with open(apath, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write(fill("---\ndescription: Older facts {USER} told me about himself, moved here from system/human/facts.md "
                         "after a month by Aether's nightly roll-over. Still true unless a newer line says otherwise; my "
                         "recall finds them.\n---\n# More about {USER}\n\n", memory.cfg))
        f.write("\n".join(f"- {d}: {t}" for d, t in move) + "\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(fill(render(meta, pre, keep), memory.cfg))
    changed = [FACTS, ABOUT]
    memory._git("add", "--", *changed)
    memory._git("commit", "-q", "-m", f"facts roll-over: {len(move)} older line(s) to {ABOUT}", "-m", "via Aether",
                "--", *changed)
    memory.reload()
    return {"moved": len(move), "kept": len(keep), "commit": memory._git("rev-parse", "--short", "HEAD").stdout.strip()}


JOURNAL = "system/journal.md"
JOURNAL_ARCHIVE = "reference/journal/"
ENTRY = re.compile(r"^- (\d{4}-\d{2}-\d{2})\b")


def roll_journal(memory, today=None, keep_days=21, max_chars=30000):
    today = today or dt.date.today()
    path = os.path.join(memory.root, *JOURNAL.split("/"))
    if not os.path.exists(path):
        return {"moved": 0}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\n.*?\n---\n", text, re.S)
    head, body = (m.group(0), text[m.end():]) if m else ("", text)
    lead, entries = [], []
    for line in body.split("\n"):
        mm = ENTRY.match(line)
        if mm:
            entries.append([mm.group(1), [line]])
        elif entries:
            entries[-1][1].append(line)
        else:
            lead.append(line)
    cutoff = (today - dt.timedelta(days=keep_days)).isoformat()
    keep = [e for e in entries if e[0] >= cutoff]
    move = [e for e in entries if e[0] < cutoff]
    size = lambda es: sum(len("\n".join(e[1])) + 1 for e in es)  # noqa: E731
    while keep and size(keep) > max_chars:
        oldest = min(range(len(keep)), key=lambda i: keep[i][0])
        move.append(keep.pop(oldest))
    if not move:
        return {"moved": 0}
    by_month = {}
    for date, lines in sorted(move, key=lambda e: e[0]):
        by_month.setdefault(date[:7], []).append("\n".join(lines).rstrip())
    changed = [JOURNAL]
    for month, items in by_month.items():
        rel = f"{JOURNAL_ARCHIVE}{month}.md"
        apath = os.path.join(memory.root, *rel.split("/"))
        os.makedirs(os.path.dirname(apath), exist_ok=True)
        new = not os.path.exists(apath)
        with open(apath, "a", encoding="utf-8", newline="\n") as f:
            if new:
                label = dt.date(int(month[:4]), int(month[5:]), 1).strftime("%B %Y")
                f.write(f"---\ndescription: My journal from {label}: older entries, moved here from system/journal.md "
                        f"by Aether's nightly roll-over (it keeps my last {keep_days} days in mind). Still mine to read.\n---\n")
            f.write("\n".join(items) + "\n")
        changed.append(rel)
    kept_lines = "\n".join(lead).rstrip("\n")
    kept_lines = (kept_lines + "\n" if kept_lines.strip() else "") + "\n".join("\n".join(e[1]).rstrip() for e in keep)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(head + kept_lines.rstrip("\n") + "\n")
    memory._git("add", "--", *changed)
    months = ", ".join(sorted(by_month))
    memory._git("commit", "-q", "-m", f"journal roll-over: {len(move)} older entries to {JOURNAL_ARCHIVE}{months}",
                "-m", "via Aether", "--", *changed)
    memory.reload()
    return {"moved": len(move), "kept": len(keep), "months": sorted(by_month),
            "commit": memory._git("rev-parse", "--short", "HEAD").stdout.strip()}
