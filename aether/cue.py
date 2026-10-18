import datetime as dt
import json
import math
import os
import re
import sqlite3
import threading

from .config import DATA_DIR
from .recall import HER, speakers
from .names import USER

FORGOTTEN = os.path.join(DATA_DIR, "forgotten.json")

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DIMS = 768

LIVE = re.compile(r"\b(?:price of|how much is .* (?:at|in) (?:the store|the market))\b", re.I)
PAST_Q = re.compile(r"\b(?:remember|recall|did we|did i (?:tell|say|mention|show)|i (?:told|showed|said to) you|"
                    r"what did (?:you|we|i)|last time|that time|back when|the other day|"
                    r"what was (?:that|the|my)|whats? (?:that|the name of)|how did (?:i|we|you)|when did (?:i|we))\b"
                    r"|\bagain\?", re.I)

INTRO = ("[Things that came to mind from your past with {USER} (memories, not new messages from him). Use one only if it "
         "fits naturally; don't recite them. \"{USER} said\" is him, \"You said\" is you. If two memories disagree, "
         "the newer one is what's true now. Memories are the past: for anything live, use your skill.]")
GENERIC = {"remember", "recall", "tell", "told", "think", "thought", "again", "time", "thing", "stuff", "said", "talk",
           "chat", "doing", "made", "gonna", "wanna", "kinda", "sorta", "yeah", "okay", "haha", "lmao"}
UNKNOWN = ("[Nothing you and {USER} ever said mentions \"{w}\". If that's what he's asking about, you don't remember it: "
           "say so plainly, and don't fill the gap with some other memory.]")
DAY_INTRO = "[What happened on {day}, from your timeline (Aether's dated notes of your days together):]"
NOT_IT = ("[If none of these is actually about what he's asking, you don't remember it: say so plainly instead of "
          "guessing.]")
NOTHING = ("[Nothing from your time with {USER} came to mind about this. If he means something you two did or said and "
           "you don't remember it, say so plainly instead of guessing. General knowledge is yours to answer as always.]")


STRANGER_PLACE = re.compile(r"\bdiscord\b.*(?:,|\bfrom\b)", re.I)


def stranger_turns(conv_dir, chat, _cache={}):
    path = os.path.join(conv_dir, chat + ".jsonl")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return set()
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    found = set()
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if '"place"' in line and STRANGER_PLACE.search(json.loads(line).get("place") or ""):
                found.add(i)
    _cache[path] = (mtime, found)
    return found


def _fingerprint(text):
    return " ".join((text or "").lower().split())[:200]


def forgotten(_cache={}):
    try:
        mtime = os.path.getmtime(FORGOTTEN)
    except OSError:
        return set(), set()
    if _cache.get("mtime") != mtime:
        with open(FORGOTTEN, encoding="utf-8") as f:
            rows = json.load(f)
        _cache.update(mtime=mtime, keys={r["key"] for r in rows if r.get("key")},
                      prints={r["print"] for r in rows if r.get("print")})
    return _cache["keys"], _cache["prints"]


def remember_forgotten(key, text):
    rows = []
    try:
        with open(FORGOTTEN, encoding="utf-8") as f:
            rows = json.load(f)
    except (OSError, ValueError):
        pass
    rows.append({"key": key or "", "print": _fingerprint(text), "when": dt.datetime.now().isoformat(timespec="seconds")})
    tmp = FORGOTTEN + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    os.replace(tmp, FORGOTTEN)


def allowed(m, conv_id="", conv_dir=""):
    where = m.get("where") or ""
    keys, prints = forgotten()
    if keys or prints:
        fp = _fingerprint(m.get("text"))
        if m.get("key") in keys or any(fp.startswith(p[:120]) or p.startswith(fp[:120]) for p in prints if p and fp):
            return False
    if m["kind"] == "source":
        return True
    if m["kind"] == "memory":
        return not (where.startswith("system/journal") or where.startswith("reference/journal")
                    or where.startswith("life/"))
    chat = m.get("chat") or ""
    if chat.startswith("discord-") or chat == "heartbeat" or chat == conv_id:
        return False
    if conv_dir:
        parts = (m.get("key") or "").split(":")
        if len(parts) >= 3 and parts[2].isdigit() and int(parts[2]) in stranger_turns(conv_dir, chat):
            return False
    head = m["text"].split("\n" + HER)[0]
    return not LIVE.search(head)


def date_window(text, now):
    t = text.lower()
    out = set()

    def add(y, mo, d):
        try:
            day = dt.date(y, mo, d)
        except ValueError:
            return
        out.add((day if day <= now.date() else day.replace(year=y - 1)).isoformat())
    for mo, day in re.findall(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", t):
        add(now.year, MONTHS[mo], int(day))
    for mo, day in re.findall(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", t):
        add(now.year, int(mo), int(day))
    for day in re.findall(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", t):
        d = int(day)
        if d <= now.day:
            add(now.year, now.month, d)
        else:
            prev = (now.replace(day=1) - dt.timedelta(days=1))
            add(prev.year, prev.month, d)
    if "yesterday" in t:
        out.add((now.date() - dt.timedelta(days=1)).isoformat())
    if re.search(r"\blast week\b", t):
        out.update((now.date() - dt.timedelta(days=k)).isoformat() for k in range(7, 14))
    if not out:
        for i, name in enumerate(DAYS):
            if re.search(rf"\b{name}\b", t):
                back = (now.weekday() - i) % 7 or 7
                out.add((now.date() - dt.timedelta(days=back)).isoformat())
    return out


def hours_named(text):
    out = set()
    for h, ampm in re.findall(r"\b(\d{1,2})\s?(am|pm)\b", text.lower()):
        h = int(h) % 12 + (12 if ampm == "pm" else 0)
        out.add(h)
    return out


def when_label(ts, now):
    if not ts:
        return ""
    try:
        d = dt.datetime.fromisoformat(ts)
    except ValueError:
        return ""
    days = (now.date() - d.date()).days
    ago = "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"
    return f"{d.strftime('%a')} {d.month}/{d.day}, {ago}"


def clip_hers(text, keep=320):
    if "\n" + HER not in text:
        return text
    his, hers = text.split("\n" + HER, 1)
    return his + "\n" + HER + (hers[:keep].rsplit(" ", 1)[0] + "…" if len(hers) > keep else hers)


class Keyword:
    STOP = set("a an and are as at be but by did do does for from had has have he her his i if in is it its me my "
               "of on or our she so that the their them then there they this to was we were what when where which "
               "who why will with you your yours lol lmao hey yo ok okay u ur im dont again remember tell told "
               "said know think".split())

    def __init__(self):
        self.db, self.n = None, -1

    def build(self, meta):
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.execute("create virtual table p using fts5(text, tokenize='porter unicode61')")
        db.executemany("insert into p(rowid, text) values (?, ?)", [(i, m["text"]) for i, m in enumerate(meta)])
        self.db, self.n = db, len(meta)

    def search(self, meta, q, k=20, only=None, rec=None):
        words = [w for w in re.findall(r"[a-z0-9']+", q.lower()) if w not in self.STOP and len(w) > 2
                 and (only is None or stem(w.replace("'", "")) in only)]
        if not words:
            return []
        expr = " OR ".join('"' + w.replace('"', "") + '"' for w in words)
        if rec is not None and rec.fts_ready(meta):
            pos = {m["key"]: i for i, m in enumerate(meta)}
            return [pos[key] for key in rec.keyword(expr, k) if key in pos]
        if self.n != len(meta):
            self.build(meta)
        try:
            return [r[0] for r in self.db.execute("select rowid from p where p match ? order by rank limit ?", (expr, k))]
        except sqlite3.Error:
            return []


def stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


SMALL_TALK = set("""hello hiya heya howdy goodnight goodmorning gn gm night nights morning mornings afternoon afternoons
evening evenings noon brb gtg ttyl thanks thank thx ty nice awesome cool dope sweet wild damn dang ugh ughh haha hahaha
hehe lmfao rofl omg tired tiring bored boring woke waking sleepy hows wassup sup ouch kidding kiddin joking""".split())
TYPED = set("""havent didnt cant wont isnt wasnt arent doesnt hasnt hadnt wouldnt couldnt shouldnt aint werent theyre
theyve theyll weve youve youll hes shes lets theres heres whos wheres whens hows yall ill id itll thatll gotta kinda
sorta yeah yea yup nope nah idk tho cuz cause ima imma lemme gimme dunno prolly""".split())
WORD_STOP = Keyword.STOP | SMALL_TALK | TYPED | set("just like really got gonna going get want wanna know think thing things "
                                                    "some any would could should about into youre ive thats whats been "
                                                    "being also more most much very".split())
STRETCH = re.compile(r"([a-z])\1{2,}")


DATEISH = re.compile(r"^(?:\d{1,2}(?:st|nd|rd|th|am|pm)|\d{1,2}(?::\d\d)?|monday|tuesday|wednesday|thursday|friday|"
                     r"saturday|sunday|jan\w*|feb\w*|mar|march|apr\w*|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec|"
                     r"december|yesterday|today|tonight|week)$")


LAUGH = re.compile(r"^(?:(?:ha){2,}|(?:he){2,})h?$|^(?:lo)+l$|^l+m+f*a+o+$")


def words(text):
    found = re.findall(r"[a-z0-9+']+", STRETCH.sub(r"\1", text.lower().replace("'", "")))
    return {stem(w) for w in found if len(w) > 2 and w not in WORD_STOP and not LAUGH.match(w)}


class Cue:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.kw = Keyword()
        self.lock = threading.Lock()
        self._docs, self._df, self._n = [], {}, -1

    def _vocab(self, meta):
        if self._n != len(meta):
            docs = [words(m["text"]) for m in meta]
            df = {}
            for d in docs:
                for w in d:
                    df[w] = df.get(w, 0) + 1
            self._docs, self._df, self._n = docs, df, len(meta)
        return self._docs, self._df

    def search(self, text, conv_id="", now=None, k=None, explain=None):
        rec = getattr(self.app, "recall", None)
        if rec is None or not rec.meta:
            return []
        now = now or dt.datetime.now()
        k = k or self.cfg.cue_max
        with rec.lock:
            meta, vecs = list(rec.meta), rec.vecs
        qv = rec.embed(["search_query: " + text])[0]
        if not getattr(rec, "model_ok", True) or len(qv) != DIMS:
            return []
        cos = {}
        for i, m in enumerate(meta):
            if allowed(m, conv_id, self.app.conv_dir):
                cos[i] = sum(a * b for a, b in zip(qv, vecs[i * DIMS:(i + 1) * DIMS]))
        by_meaning = sorted(cos, key=lambda i: -cos[i])
        docs, df = self._vocab(meta)
        most = max(3, int(self.cfg.cue_rare * len(meta)))
        mine = {w for w in words(text) if 0 < df.get(w, 0) <= most and not DATEISH.match(w)}
        with self.lock:
            by_words = [i for i in self.kw.search(meta, text, k=40, only=mine, rec=rec) if i in cos] if mine else []
        days, hours = date_window(text, now), hours_named(text)

        def at_hour(i):
            ts = meta[i].get("ts") or ""
            return bool(hours) and len(ts) >= 13 and any(abs(int(ts[11:13]) - h) <= 2 for h in hours)
        weight = {w: math.log(len(meta) / df[w]) for w in mine}
        by_overlap = sorted((i for i in cos if mine & docs[i]), key=lambda i: -sum(weight[w] for w in mine & docs[i]))[:40]
        lists = [by_meaning[:40], by_words, by_overlap]
        dated = []
        if days:
            on_day = [i for i in by_meaning if (meta[i].get("ts") or "")[:10] in days]
            dated = sorted(on_day, key=lambda i: not at_hour(i))[:20]
            lists.append(dated)
        best_dated = set(dated[:5]) if len(days) <= 2 else set()

        def comes_to_mind(i):
            shared = sum(weight[w] for w in mine & docs[i])
            word_min = getattr(self.cfg, "cue_word_min", 0.0)
            return ((shared >= self.cfg.cue_weight and cos[i] >= word_min)
                    or (i in best_dated and (cos[i] >= self.cfg.cue_min or at_hour(i))))
        pool = [i for i in dict.fromkeys(x for ranked in lists for x in ranked) if comes_to_mind(i)]
        lists.append(sorted(pool, key=lambda i: meta[i].get("ts") or "9999", reverse=True))
        score = {}
        for ranked in lists:
            for r, i in enumerate(ranked):
                score[i] = score.get(i, 0) + 1 / (60 + r)
        picked, seen = [], set()
        for i in sorted(pool, key=lambda i: -score[i]):
            m = meta[i]
            same = ":".join(m.get("key", "").split(":")[:3]) if m["kind"] == "chat" else \
                re.sub(r"^(?:was|now): ", "", " ".join(m["text"].lower().split()))[:60]
            if same in seen:
                continue
            seen.add(same)
            picked.append(i)
            if len(picked) >= k:
                break
        if explain is not None:
            chosen = set(picked)
            explain.extend({"key": meta[i].get("key", ""), "text": meta[i]["text"][:300], "cos": round(cos[i], 3),
                            "shared": {w: round(weight[w], 2) for w in mine & docs[i]}, "dated": i in best_dated,
                            "score": round(score[i], 4), "picked": i in chosen} for i in pool)
        return [dict(meta[i], score=round(score[i], 4), cos=round(cos[i], 3)) for i in reversed(picked)]

    def unknown_words(self, text):
        rec = getattr(self.app, "recall", None)
        if rec is None or not rec.meta:
            return []
        with rec.lock:
            meta = list(rec.meta)
        _, df = self._vocab(meta)
        out = []
        for tok in re.findall(r"[a-z0-9+']+", text.lower().replace("'", "")):
            w = stem(tok)
            if len(tok) > 3 and not ({w, tok} & (WORD_STOP | GENERIC)) and not DATEISH.match(w) and not tok.isdigit() \
                    and df.get(w, 0) == 0 and tok not in out:
                out.append(tok)
        return sorted(out, key=len, reverse=True)[:2]

    def day_lines(self, text, now):
        days = sorted(date_window(text, now))
        f = self.app.engine.memory.files.get("system/timeline.md")
        if not days or len(days) > 2 or f is None:
            return "", []
        hours = hours_named(text)
        rows = []
        for ln in f.body.splitlines():
            m = re.match(r"- (\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) · [^·]* · (.+?)(?: \(\d+\))?$", ln)
            if m and m.group(1) in days:
                near = min((abs(int(m.group(2)) - h) for h in hours), default=0)
                rows.append((near > 3, m.group(1), f"{m.group(2)}:{m.group(3)}", m.group(4)))
        if hours:
            rows.sort(key=lambda r: r[0])
        rows = sorted(rows[:8], key=lambda r: (r[1], r[2]))
        d = dt.date.fromisoformat(days[-1])
        return f"{d:%a} {d.month}/{d.day}", [f"- {r[2]}: {r[3]}" for r in rows]

    def for_turn(self, conv, text, now=None):
        if not self.cfg.cue_enabled or not (text or "").strip() or LIVE.search(text):
            return "", []
        now = now or dt.datetime.now()
        try:
            hits = self.search(text, conv.id, now)
        except Exception:
            return "", []
        past = PAST_Q.search(text)
        day, day_rows = self.day_lines(text, now)
        tail = ""
        if day_rows:
            tail += "\n" + DAY_INTRO.format(day=day) + "\n" + "\n".join(day_rows)
        unknown = self.unknown_words(text) if past else []
        if unknown:
            tail += "\n" + UNKNOWN.format(USER=USER, w=unknown[0])
        if not hits and not day_rows:
            if unknown:
                return UNKNOWN.format(USER=USER, w=unknown[0]), []
            return (NOTHING, []) if past else ("", [])
        lines, items = [], []
        for h in hits:
            when = when_label(h.get("ts"), now)
            if h["kind"] == "chat":
                where = f"{when}, chat \"{h.get('where', '')}\"" if when else f"chat \"{h.get('where', '')}\""
                body = speakers(clip_hers(h["text"]))
            else:
                where = f"from {h.get('where', '')}" if h["kind"] == "source" else f"your memory, {h.get('where', '')}"
                body = h["text"]
            lines.append(f"- {where}: {body}")
            items.append({"where": h.get("where", ""), "when": when, "kind": h["kind"], "text": h["text"][:400],
                          "cos": h["cos"], "key": h.get("key", "")})
        for row in day_rows:
            items.append({"where": "system/timeline.md", "when": day, "kind": "memory", "text": row[2:], "cos": 0, "key": ""})
        head = INTRO + "\n" + "\n".join(lines) if lines else ""
        return (head + tail + ("\n" + NOT_IT if past and lines else "")).strip(), items
