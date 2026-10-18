import datetime as dt
import json
import os
import re
from .names import USER, fill

REL = "reference/music/ratings.md"
DESC = ("{USER}'s 👍 / 👎 on my tracks, from the code box in our chat. Written by Aether when he clicks (not by my "
        "memory steps); my music skill shows them when I make a track.")
MARK = {"up": "👍", "down": "👎"}
LINE_ID = re.compile(r" · id ([0-9a-f]{8})$")


def track_id(code):
    h = 0x811C9DC5
    for b in code.strip().encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def summary(code):
    first = next((ln.strip().lstrip("/").strip() for ln in code.splitlines() if ln.strip().startswith("//")), "")
    parts = [first[:90] or "(no title)"]
    tempo = re.search(r"setcp[ms]\(\s*([\d.]+)\s*/\s*4\s*\)", code)
    if tempo and str(int(float(tempo.group(1)))) not in first:
        parts.append(f"{int(float(tempo.group(1)))} BPM")
    key = re.search(r"const\s+key\s*=\s*[`\"']([^`\"']+)", code)
    if key and key.group(1).split(":")[0] not in first:
        parts.append(f"key {key.group(1)}")
    prog = re.search(r"const\s+prog\s*=\s*[`\"']([^`\"']+)", code)
    if prog:
        parts.append(f"chords {prog.group(1)}")
    sounds = sorted({s for s in re.findall(r"\.s\(\s*[`\"']([\w-]+)[`\"']", code)})
    if sounds:
        parts.append("sounds " + ", ".join(sounds[:5]))
    return " · ".join(parts)


def rate(memory, code, rating, now=None):
    if rating not in ("up", "down", "none") or not str(code or "").strip():
        raise ValueError("a rating is up, down or none, for a track's code")
    now = now or dt.datetime.now()
    tid = track_id(code)
    path = os.path.join(memory.root, *REL.split("/"))
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.startswith("- ")]
    kept = [ln for ln in lines if not ln.endswith(f" · id {tid}")]
    what = summary(code)
    if rating != "none":
        stamp = now.strftime("%Y-%m-%d %I:%M %p").replace(" 0", " ")
        kept.append(f"- {stamp} · {MARK[rating]} · {what} · id {tid}")
    if kept == lines:
        return {"id": tid, "rating": rating, "message": "Nothing to change."}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(fill(f"---\ndescription: {DESC}\n---\n", memory.cfg) + "\n".join(kept) + ("\n" if kept else ""))
    title = what.split(" · ")[0][:60]
    reason = f"{USER} {'took back his rating of' if rating == 'none' else MARK[rating]} {title}"
    r = memory._finish(REL, "music", reason, reason)
    return {"id": tid, "rating": rating, "message": r["message"]}


FENCED = re.compile(r"```([\w+-]*)[^\n]*\n(.*?)(?:```|$)", re.S)
STRUDEL = re.compile(r"\b(?:setcpm|setcps|stack|arrange|note|sound|chord)\s*\(|\bs\(\s*[\"'`]")
_seen_files = {}


def tracks_in(text):
    return [m.group(2).strip() for m in FENCED.finditer(str(text or ""))
            if re.fullmatch(r"(?:js|javascript|strudel)?", m.group(1), re.I) and STRUDEL.search(m.group(2))]


def her_tracks(conv_dir):
    found = {}
    for name in sorted(os.listdir(conv_dir)) if os.path.isdir(conv_dir) else []:
        path = os.path.join(conv_dir, name)
        if not name.endswith(".jsonl") or not os.path.isfile(path):
            continue
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
        if _seen_files.get(path, (None,))[0] != key:
            mine = []
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    if "```" not in ln:
                        continue
                    try:
                        ev = json.loads(ln)
                    except ValueError:
                        continue
                    if ev.get("kind") in ("reply", "reach_out"):
                        mine += [(code, str(ev.get("ts") or "")) for code in tracks_in(ev.get("text"))]
            _seen_files[path] = (key, mine)
        for code, made in _seen_files[path][1]:
            tid = track_id(code)
            rank = (name == "heartbeat.jsonl", made)
            if tid not in found or rank < (found[tid]["chat"] == "heartbeat", found[tid]["made"]):
                about = summary(code).split(" · ")
                found[tid] = {"id": tid, "title": about[0], "about": " · ".join(about[1:]), "code": code,
                              "chat": name[:-6], "made": made}
    return sorted(found.values(), key=lambda t: t["made"], reverse=True)


def all_ratings(memory):
    path = os.path.join(memory.root, *REL.split("/"))
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for ln in f:
                m = LINE_ID.search(ln.rstrip("\n"))
                if m:
                    out[m.group(1)] = "up" if " · 👍 · " in ln else "down"
    return out
