import datetime as dt
import json
import math
import os
import re
from collections import Counter, defaultdict

REGIONS = {
    "self":      ("{name} itself",   "#f5c86b", (0.55, 0.25, 0.00)),
    "journal":   ("Journal & notes", "#b58cff", (0.62, -0.05, 0.45)),
    "user":      ("About {USER}",      "#ff7a9c", (-0.55, 0.25, 0.00)),
    "projects":  ("Projects",        "#ffa24c", (-0.45, 0.35, -0.45)),
    "reference": ("Reference",       "#4fd6ff", (-0.62, -0.10, 0.45)),
    "skills":    ("Skills",          "#46f09a", (0.00, -0.62, 0.05)),
    "notebook":  ("Notebook",        "#c2f25a", (-0.08, 0.66, 0.22)),
    "chats":     ("Our chats",       "#8ea2ff", (0.05, -0.30, -0.62)),
}
TIMELINE, THREADS, STANCES = "system/timeline.md", "system/threads.md", "reference/stances.md"
STRANGER = re.compile(r"^Discord (?:DM from .+|#[^,]*, .+)$|^Discord, .+")
STOP = set("""the a an and or but if then than that this these those with without from into onto over under
about above below after before again while when where which who whom whose what why how all any both each few
more most other some such only own same so too very can will just don dont should now not no nor is are was were
be been being have has had having do does did doing i me my myself we our ours you your yours he him his she her
hers it its they them their theirs to of in on at by for as up down out off here there once also get got use used
using one two new like make made via per etc user companion skill skills script scripts file files memory system md py
json line lines run runs when want wants never always every today tomorrow""".split())


def region_of(rel):
    if rel in (TIMELINE, THREADS):
        return "notebook"
    if rel == STANCES:
        return "self"
    if rel.startswith("skills/"):
        return "skills"
    if rel.startswith("reference/projects") or rel == "system/projects.md":
        return "projects"
    if rel in ("system/journal.md", "system/research-notes.md") or rel.startswith(("life/", "reference/research/")):
        return "journal"
    if rel.startswith(("reference/", "notes/")):
        return "reference"
    if rel.startswith("system/human"):
        return "user"
    return "self"


def split_memories(body):
    bullets = [m.group(1).strip() for m in re.finditer(r"(?m)^\s*(?:[-*]|\d+\.)\s+(.+)$", body)]
    bullets = [b for b in bullets if len(b) >= 18]
    if len(bullets) >= 3:
        return bullets
    paras = []
    for p in re.split(r"\n\s*\n", body):
        p = re.sub(r"(?m)^#+\s.*$", "", p).strip()
        if len(p) >= 40 and not p.startswith("```"):
            paras.append(re.sub(r"\s+", " ", p))
    return bullets + paras


def clean(s, n):
    s = re.sub(r"[*_`]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def our_chats(conv_dir, meta=None):
    if meta is None:
        try:
            with open(os.path.join(conv_dir, "_meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = {}
    out = []
    if not os.path.isdir(conv_dir):
        return out
    for name in os.listdir(conv_dir):
        cid = name[:-6]
        if not name.endswith(".jsonl") or cid == "heartbeat":
            continue
        start = end = first = ""
        msgs = his = 0
        try:
            with open(os.path.join(conv_dir, name), encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("kind") not in ("user", "reply"):
                        continue
                    msgs += 1
                    start, end = start or e.get("ts", ""), e.get("ts", "") or end
                    if e["kind"] == "user" and not STRANGER.match(str(e.get("place") or "")):
                        his += 1
                        first = first or " ".join(str(e.get("text") or "").split())
        except OSError:
            continue
        if his:
            m = meta.get(cid) or {}
            out.append({"id": cid, "title": m.get("title") or (first[:40] + ("..." if len(first) > 40 else "")),
                        "start": start, "end": end, "messages": msgs, "archived": bool(m.get("archived"))})
    out.sort(key=lambda c: c["start"])
    return out


def _day(ts):
    try:
        return dt.datetime.fromisoformat(ts[:19]).strftime("%a %b %d %Y").replace(" 0", " ")
    except ValueError:
        return ""


def build(root, chats=None, name="Companion"):
    regions = {r: (v[0].replace("{name}", name or "Companion"),) + v[1:] for r, v in REGIONS.items()}
    files = []
    for dirpath, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for f in fs:
            if f.startswith(".") or f.endswith((".png", ".jpg", ".pyc", ".ico")):
                continue
            p = os.path.join(dirpath, f)
            files.append((os.path.relpath(p, root).replace("\\", "/"), p))
    files.sort()

    nodes, links, idx = [], [], {}

    def add(node):
        node["i"] = len(nodes)
        nodes.append(node)
        return node["i"]

    core = add({"k": "core", "label": "SOUL", "region": "core", "size": 9})
    for r, (label, _c, _p) in regions.items():
        idx["region:" + r] = add({"k": "region", "label": label, "region": r, "size": 5})
        links.append((core, idx["region:" + r], "spine"))

    mem_items, texts = [], {}
    for rel, p in files:
        reg = region_of(rel)
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        texts[rel] = text
        desc, body = "", text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) == 3:
                m = re.search(r"(?m)^description:\s*(.+)$", parts[1])
                desc = m.group(1).strip().strip("'\"") if m else ""
                body = parts[2]
        is_md = rel.endswith(".md")
        if rel == "system/persona.md":
            fi = core
            nodes[core].update({"file": rel, "text": clean(desc or body, 260)})
        else:
            fi = add({"k": "file", "label": rel, "file": rel, "region": reg, "size": 3.2 if is_md else 1.8,
                      "text": clean(desc or (body if is_md else ""), 220)})
            links.append((idx["region:" + reg], fi, "tree"))
        idx["file:" + rel] = fi
        if is_md and rel == TIMELINE:
            weeks = {}
            for m in split_memories(body):
                d = re.match(r"\d{4}-\d{2}-\d{2}", m)
                hub = fi
                if d:
                    day = dt.date.fromisoformat(d.group(0))
                    monday = day - dt.timedelta(days=day.weekday())
                    if monday not in weeks:
                        name = f"week of {monday:%b} {monday.day}"
                        weeks[monday] = [add({"k": "file", "group": True, "label": f"{TIMELINE}#{monday}", "file": TIMELINE,
                                              "short": name[8:], "region": "notebook", "size": 2.4, "week": name}), 0]
                        links.append((fi, weeks[monday][0], "tree"))
                    weeks[monday][1] += 1
                    hub = weeks[monday][0]
                mi = add({"k": "mem", "label": clean(m, 90), "region": "notebook", "size": 0.6, "text": clean(m, 320),
                          "file": rel, "at": nodes[hub]["label"], "find": m[:60]})
                links.append((hub, mi, "leaf"))
            for hi, n in weeks.values():
                nodes[hi]["text"] = f"His timeline, the {nodes[hi].pop('week')}: {n} moment{'s' * (n != 1)}"
        elif is_md:
            for m in split_memories(body)[: (4 if reg == "skills" else 60)]:
                mi = add({"k": "mem", "label": clean(m, 90), "region": reg, "size": 1.0, "text": clean(m, 320),
                          "file": rel, "find": m[:60]})
                links.append((fi, mi, "leaf"))
                mem_items.append((mi, rel, m))

    for rel, _p in files:
        if rel.startswith("skills/") and not rel.endswith("SKILL.md"):
            sk = "/".join(rel.split("/")[:2]) + "/SKILL.md"
            if "file:" + sk in idx:
                links.append((idx["file:" + sk], idx["file:" + rel], "tree"))

    names = {rel: os.path.splitext(os.path.basename(rel))[0] for rel, _ in files}
    for rel, text in texts.items():
        wikis = {w.strip().lower() for w in re.findall(r"\[\[([^\]]+)\]\]", text)}
        for other, name in names.items():
            if other == rel or "file:" + other not in idx:
                continue
            if other in text or name.lower() in wikis or (len(name) > 4 and name != "SKILL"
                                                           and re.search(r"\b" + re.escape(name) + r"\b", text)):
                links.append((idx["file:" + rel], idx["file:" + other], "mention"))

    words, df = {}, Counter()
    for mi, rel, m in mem_items:
        ws = {w for w in re.findall(r"[a-z][a-z0-9']{3,}", m.lower()) if w not in STOP}
        words[mi] = (rel, ws)
        df.update(ws)
    by_word = defaultdict(list)
    for mi, (rel, ws) in words.items():
        for w in ws:
            if 2 <= df[w] <= 5:
                by_word[w].append((mi, rel))
    seen = set()
    for lst in by_word.values():
        for a in range(len(lst)):
            for b in range(a + 1, len(lst)):
                (x, rx), (y, ry) = lst[a], lst[b]
                if rx != ry and (x, y) not in seen:
                    seen.add((x, y))
                    links.append((x, y, "echo"))
    echo = [lk for lk in links if lk[2] == "echo"]
    if len(echo) > 260:
        keep = set(sorted(echo, key=lambda lk: (lk[0] * 7919 + lk[1]) % 1000)[:260])
        links = [lk for lk in links if lk[2] != "echo" or lk in keep]

    prev = idx["region:chats"]
    for c in chats or []:
        a, b = _day(c["start"]), _day(c["end"])
        when = a if not b or a == b else f"{a} to {b}"
        ci = add({"k": "chat", "label": clean(c["title"] or "a chat", 70), "chat": c["id"], "region": "chats",
                  "size": round(0.9 + min(1.3, math.log1p(c["messages"]) * 0.28), 2), "old": c["archived"],
                  "text": f"{when} · {c['messages']} messages" + (" · archived" if c["archived"] else "")})
        links.append((prev, ci, "tree" if prev == idx["region:chats"] else "leaf"))
        prev = ci

    last_thought = ""
    entries = re.findall(r"(?m)^\s*-\s+(.+)$", texts.get("system/journal.md", ""))
    if entries:
        dated = [((m.group(0) if (m := re.search(r"\d{4}-\d{2}-\d{2}", e)) else ""), i, e) for i, e in enumerate(entries)]
        last_thought = clean(max(dated)[2], 140)

    counts = Counter("group" if n.get("group") else n["k"] for n in nodes)
    return {"nodes": nodes, "links": [[a, b, t] for a, b, t in links],
            "meta": {"files": counts["file"], "memories": counts["mem"], "chats": counts["chat"], "links": len(links),
                     "last_thought": last_thought,
                     "regions": {r: {"label": v[0], "color": v[1], "center": v[2]} for r, v in regions.items()}}}
