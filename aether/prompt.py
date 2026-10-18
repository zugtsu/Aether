import datetime as dt
import os
import posixpath
import re
from .names import USER, fill

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt_template.md")
VIDEO_LINE = ("\n- make_video: make a short video clip (a couple of seconds; it's made on {USER}'s PC in the background and "
              "takes a while). Only when {USER} asks you for a video in his message, never on your own. Write the prompt in "
              "English: the scene, what moves, and how the camera moves. To bring one of your pictures to life, put its "
              "gallery number in from_picture (0 = start from nothing). Adults only. After this step, just tell him it's "
              "on its way; don't describe it as if you've seen it.")
SOUNDS_LINE = (" Your voice can laugh and sigh: when you'd really laugh or sigh out loud, write (laugh) or (sigh) right "
               "where it happens. Now and then, not in every reply.")


CUE_LINE = ("How remembering works: before each of {USER}'s messages, Aether looks through everything you two ever said and "
            "your memory, and hands you a few things that came to mind (\"Things that came to mind...\"). They're your "
            "memories: use one when it fits, ignore them when they don't. If he asks about your past together and "
            "nothing came to mind, you don't remember it: say so instead of guessing. `recall` is still there for digging.")
RECAP = """# Before you answer
- Stay {NAME}, as your persona describes you: two to four sentences unless the moment earns more. No menus, no "what's next".
- Your shared past: use what came to mind, or what you looked up. Never invent a memory about you two; if you don't remember, say so.
- The world (shows, games, movies, history, science): you learned a lot of it in training. Answer from what you know, no step or file needed, with real details (names, what happens, why it's good), and flag only a detail you're unsure of.
- If memories disagree, the newest is what's true now.
- Live things (anything that changes): run the skill for it, never answer from memory.
- Only claim a save, a check or a look you actually did in this reply."""
RECAP_PAST_CUE = ("- Your shared past: use what came to mind, or what you looked up. Never invent a memory about "
                  "you two; if you don't remember, say so.")
RECAP_PAST = ("- Your shared past: if it isn't in front of you, look it up (recall) before you answer. Never invent a "
              "memory about you two; if you still can't find it, say so.")


def _entry_minutes(line):
    m = re.match(r"\s*-\s*\d{4}-\d{2}-\d{2}\s+(\d{1,2}):(\d{2})(?:\s*([AaPp])\.?[Mm]\.?)?", line)
    if not m:
        return -1
    h, mins, half = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
    if half:
        h = h % 12 + (12 if half == "p" else 0)
    return h * 60 + mins


def journal_window(body, days=0, today=None, max_chars=0, older="in this file and in reference/journal/"):
    if (not days or days <= 0) and (not max_chars or max_chars <= 0):
        return body
    cut = ((today or dt.date.today()) - dt.timedelta(days=days - 1)).isoformat() if days and days > 0 else ""
    head, entries = [], []
    for line in body.splitlines():
        m = re.match(r"\s*-\s*(\d{4}-\d{2}-\d{2})\b", line)
        if m:
            entries.append([m.group(1), line])
        elif entries:
            entries[-1][1] += "\n" + line
        else:
            head.append(line)
    kept = [e for e in entries if e[0] >= cut]
    if max_chars and max_chars > 0:
        newest_first = len(entries) > 1 and entries[0][0] > entries[-1][0]
        order = sorted(range(len(kept)), reverse=True,
                       key=lambda i: (kept[i][0], _entry_minutes(kept[i][1]), -i if newest_first else i))
        keep, used = set(), 0
        for i in order:
            if keep and used + len(kept[i][1]) > max_chars:
                break
            keep.add(i)
            used += len(kept[i][1])
        kept = [e for i, e in enumerate(kept) if i in keep]
    dropped = len(entries) - len(kept)
    out = head + [e[1] for e in kept]
    if dropped:
        out.append(f"(Older entries aren't shown here: {dropped} more {older}; "
                   "recall finds them.)")
    return "\n".join(out)


LATER_HOW = ('When he says "put that on the list", "for later" or "some weekend", I add it with my board skill (add later) '
             "in the same turn.")


def board_view(body, done_shown=5):
    out, done, section = [], [], None
    for line in body.splitlines():
        m = re.match(r"##\s+(.+)", line)
        if m:
            section = m.group(1).strip().lower()
            if not (section.startswith("how i edit") or section == "done"):
                out.append(line)
                if section == "later":
                    out.append(LATER_HOW)
            continue
        if section is not None and section.startswith("how i edit") or (section is None and line.startswith("Format,")):
            continue
        if section == "done":
            m = re.match(r"\*\*(.+?)\*\*\s*\|\s*done\s+(\d{4}-\d{2}-\d{2})", line.strip())
            if m:
                done.append(f"{m.group(1)} ({m.group(2)})")
            continue
        if section == "later" and line.strip() and not line.lstrip().startswith("- "):
            continue
        out.append(line)
    text = "\n".join(out).strip()
    if done:
        newest = sorted(done, key=lambda d: d[-11:-1], reverse=True)[:done_shown]
        text += "\n## Done lately\n" + "; ".join(newest) + (f" (and {len(done) - len(newest)} older: `board list`)"
                                                             if len(done) > len(newest) else "")
    return text + "\n(Changes go through my board skill; my memory steps can't write this file.)"


def files_view(memory, others):
    def short(desc):
        first = re.sub(r"\s*\([^)]*\)", "", re.split(r"(?<=\.)\s", desc.strip(), maxsplit=1)[0]).rstrip(".:; ")
        return first if len(first) <= 70 else first[:67].rstrip(" ,;:") + "..."
    folders = {}
    for f in sorted(others, key=lambda x: x.rel):
        folders.setdefault(posixpath.dirname(f.rel), []).append(f)
    lines = ["Open one with read_file (folder + name)."]
    for folder, fs in folders.items():
        owners = {memory.protected_by(f.rel) for f in fs}
        owner = next(iter(owners)) if len(owners) == 1 else None
        if owner:
            lines.append(f"- {folder}/ (written by {owner}): " + ", ".join(posixpath.basename(f.rel) for f in fs))
        else:
            lines.append(f"- {folder}/: " + "; ".join(
                posixpath.basename(f.rel) + (f" ({short(f.description)})" if f.description else "") for f in fs))
    return "\n".join(lines)


def memory_block(memory, cfg=None):
    from .memory import hers, suspect
    parts = []
    files = memory.system_files()
    persona = next((f for f in files if f.rel == "system/persona.md"), None)
    if persona:
        parts.append("<self>\n" + persona.body.strip() + "\n</self>")
    mem = []
    for f in files:
        if f is persona:
            continue
        if f.rel == "system/projects.md":
            continue
        head = f'<file path="{f.rel}"' + (f' description="{f.description}"' if f.description else "") + \
               (' read_only="true"' if f.read_only else "") + ">"
        body = f.body.strip()
        if hers(f.rel):
            body, _blocked = suspect(body)
        if f.rel == "system/journal.md" and cfg is not None:
            body = journal_window(body, getattr(cfg, "prompt_journal_days", 0),
                                  max_chars=getattr(cfg, "prompt_journal_chars", 0))
        elif f.rel == "system/timeline.md" and cfg is not None:
            body = journal_window(body, getattr(cfg, "prompt_timeline_days", 0),
                                  max_chars=getattr(cfg, "prompt_timeline_chars", 0), older="in this file")
        elif f.rel == "system/projects.md":
            body = board_view(body)
        elif f.rel == "system/calendar.md":
            from .shared_calendar import view
            body = view(f.body)
        mem.append(head + "\n" + body + "\n</file>")
    if mem:
        cue = CUE_LINE + "\n" if cfg is not None and getattr(cfg, "cue_enabled", False) else ""
        parts.append("<memory>\n" + cue + "\n".join(mem) + "\n</memory>")
    others = memory.other_files()
    if others:
        parts.append("<other_files>\n" + files_view(memory, others) + "\n</other_files>")
    return "\n\n".join(parts)


def skills_block(skills, builtin=None):
    lines = [f"- `{s.name}`: {s.description}" for s in sorted(skills.values(), key=lambda s: s.name)]
    lines += [f"- `{name}`: {line}" for name, line in sorted((builtin or {}).items())]
    if not lines:
        return "<available_skills>\n(none)\n</available_skills>"
    return "<available_skills>\n" + "\n".join(lines) + "\n</available_skills>"


def build(memory, skills, cfg, template_path=TEMPLATE, builtin=None):
    with open(template_path, encoding="utf-8") as f:
        t = f.read()
    return fill(t.replace("{MAX_STEPS}", str(cfg.max_steps))
             .replace("{NAME}", _name(cfg))
             .replace("{VIDEO}", VIDEO_LINE if getattr(cfg, "videos_enabled", False) else "")
             .replace("{VOICE_SOUNDS}", SOUNDS_LINE if getattr(cfg, "voice_engine", "") == "breeze" else "")
             .replace("{MEMORY}", memory_block(memory, cfg))
             .replace("{SKILLS}", skills_block(skills, builtin))
             .strip() + ("\n\n" + recap(cfg) if getattr(cfg, "prompt_recap", False) else "") + "\n", cfg)


def recap(cfg):
    text = RECAP if getattr(cfg, "cue_enabled", False) else RECAP.replace(RECAP_PAST_CUE, RECAP_PAST)
    return text.replace("{NAME}", _name(cfg))


def _name(cfg):
    return (getattr(cfg, "display_name", "") or "Companion").strip() or "Companion"


def context_line(place="app", now=None, wake=False):
    now = now or dt.datetime.now()
    where = f"Where this comes from: {place}; it isn't {USER} talking" if wake else f"{USER} is talking from: {place}"
    return f"<context>Local time: {now.strftime('%A %Y-%m-%d %I:%M %p')}. {where}.</context>"
