import re

from . import tool_table

ASKS = [(name, what, how, trigger, done) for name, what, how, trigger, done, _ in tool_table.asks()]
_TRIGGERS = [(name, what, how, re.compile(trigger, re.I), done) for name, what, how, trigger, done in ASKS]
NEEDS = {name: tool for name, _, _, _, _, tool in tool_table.asks()}
ASKED_ABOUT = re.compile(r"\b(?:did|have|do|were|was) (?:you|we)\s+$", re.I)
TOLD_NOT = re.compile(r"\b(?:don['’]?t|do not|never|stop|no need to|quit)\b(?!\s+(?:forget|mind)\b)[^.,;!?\n]*$", re.I)


LONG = 500
OPENING = 200


def asks_in(message, have=None):
    text = str(message or "")
    if len(text) > LONG:
        text = text[:OPENING].split("\n\n")[0]
    found = []
    for name, what, how, rx, done in _TRIGGERS:
        if have is not None and NEEDS[name] not in have:
            continue
        m = next((m for m in rx.finditer(text) if not ASKED_ABOUT.search(text[max(0, m.start() - 14):m.start()])
                  and not TOLD_NOT.search(text[max(0, m.start() - 30):m.start()])), None)
        if m:
            found.append((m.start(), name, what, how, done))
    return [(name, what, how, done) for _, name, what, how, done in sorted(found, key=lambda x: x[0])]


def route_note(asks):
    if not asks:
        return ""
    if len(asks) == 1:
        _, what, how, _ = asks[0]
        return f"[Aether: his message asks for {what}: {how}. Do it, then your reply.]"
    return ("[Aether: his message asks for " + str(len(asks)) + " things; each is its own step, then your reply: "
            + "; ".join(f"({i}) {what}: {how}" for i, (_, what, how, _) in enumerate(asks, 1)) + "]")


def ask_for(name):
    return next(((n, w, h, d) for n, w, h, _rx, d in _TRIGGERS if n == name), None)


def missing(asks, done):
    return [a for a in asks if not any(ok and a[3](s) for s, ok in done)]


def ask_recall(conv_dir, since=""):
    import json
    import os
    out = {}
    for name in sorted(os.listdir(conv_dir)) if os.path.isdir(conv_dir) else []:
        if not name.endswith(".jsonl") or name == "heartbeat.jsonl" or name.startswith("letta-"):
            continue
        evs = []
        with open(os.path.join(conv_dir, name), encoding="utf-8") as f:
            for ln in f:
                try:
                    evs.append(json.loads(ln))
                except ValueError:
                    pass
        for i, ev in enumerate(evs):
            if ev.get("kind") != "user" or str(ev.get("ts") or "") < since:
                continue
            asks = asks_in(ev.get("text"))
            if not asks:
                continue
            done, j = [], i + 1
            while j < len(evs) and evs[j].get("kind") not in ("user", "wake", "reply"):
                if evs[j].get("kind") == "step":
                    res = next((r for r in evs[j + 1:] if r.get("kind") == "result"), {})
                    done.append((evs[j].get("step") or {}, bool(res.get("ok"))))
                j += 1
            left = {a[0] for a in missing(asks, done)}
            for a in asks:
                row = out.setdefault(a[0], [0, 0])
                row[0] += 1
                row[1] += a[0] not in left
    return out


def reflect_note(left):
    items = "; ".join(f"{what}: {how}" for _, what, how, _ in left)
    return (f"[Aether, before you reply: his message also asked for {items}. That isn't done yet. Do it now, one step "
            "each; if you can't, or he didn't mean that, reply and tell him plainly.]")
