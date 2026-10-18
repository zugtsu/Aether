import os
import re

FALLBACK = "That's {USER}'s business, not mine to hand out."
STOP = set("""
about above after again against also always another anything around because been before being
below between both could does doing down during each even every from further have having here
hers herself hmm into just know like made make many more most much must myself never only other
ours over really same should since some still such than that their them then there these they
thing things this those through today under until very want what when where which while will
with would your yours yourself yeah okay sure well good great user companion
""".split())
SENT = re.compile(r"(?<=[.!?])\s+|\n+")


def _words(s):
    return {w for w in re.findall(r"[a-z0-9']+", s.lower()) if len(w) >= 4 and w not in STOP and not w.isdigit()}


def _numbers(s):
    return {n for n in re.findall(r"\d[\d:,.\-/]{2,}\d|\d{3,}", s)}


SELF_FILES = ("persona.md", "rules.md", "channels.md")


def private_lines(memory_root, extra_texts=()):
    out = []
    sysdir = os.path.join(memory_root, "system")
    for root, _dirs, files in os.walk(sysdir):
        for f in files:
            if not f.endswith(".md"):
                continue
            try:
                with open(os.path.join(root, f), encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            about_user = not (root == sysdir and f in SELF_FILES)
            out += [(ln, about_user) for ln in _split_private(text)]
    for t in extra_texts:
        out += [(ln, False) for ln in _split_private(t)]
    return [(ln, _words(ln), _numbers(ln), mine) for ln, mine in out if len(_words(ln)) >= 3 or _numbers(ln)]


def _split_private(text):
    out = []
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    for ln in body.splitlines():
        ln = ln.strip().lstrip("-*# ").strip()
        if len(ln) >= 12:
            out += [s for s in SENT.split(ln) if len(s) >= 12]
    return out


def leaks(sentence, private):
    sw, sn = _words(sentence), _numbers(sentence)
    for line, lw, ln, about_user in private:
        shared = sw & lw
        if about_user:
            if len(shared) >= 3 and len(shared) >= 0.5 * len(lw):
                return line
            if ln and (sn & ln) and shared:
                return line
        elif len(shared) >= 8 and len(shared) >= 0.7 * len(lw):
            return line
    return None


def mentions(text, private):
    sw, sn = _words(text), _numbers(text)
    for line, lw, ln, about_user in private:
        if not about_user:
            continue
        shared = sw & lw
        if len(shared) >= 2 or (ln and (sn & ln) and shared):
            return line
    return None


def stranger_reply(text, memory_root, vault=None, extra_texts=()):
    if not text:
        return text, []
    private = private_lines(memory_root, extra_texts)
    kept, dropped = [], []
    for s in [s for s in SENT.split(text.strip()) if s.strip()]:
        if vault and vault.scrub(s) != s:
            dropped.append((s, "a vault secret"))
            continue
        hit = leaks(s, private)
        if hit:
            dropped.append((s, f"repeats: {hit[:80]}"))
            continue
        kept.append(s)
    out = " ".join(kept).strip()
    return (out or FALLBACK), dropped
