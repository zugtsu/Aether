#!/usr/bin/env python3
import datetime as dt
import json
import os
import re
import subprocess
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MEMORY_DIR = os.environ.get("MEMORY_DIR") or os.path.join(os.environ.get("AETHER_HOME") or os.path.join(os.path.expanduser("~"), ".aether"), "memory")
BOARD = os.path.join(MEMORY_DIR, "system", "projects.md")
BOARD_REL = "system/projects.md"
SECTIONS = ["active", "todo", "later", "parked", "done"]
HEADINGS = {"active": "## Active", "todo": "## To-do", "later": "## Later", "parked": "## Parked", "done": "## Done"}
SECTION_WORDS = {"to-do": "todo", "to do": "todo", "todos": "todo", "to-dos": "todo"}
AUTHOR = ["-c", "user.name=Companion", "-c", "user.email=companion@aether.local"]
TRAILER_CHANGE = "[When you answer him: say what changed and the commit hash exactly as printed, then one line of you.]"
TRAILER_LIST = ("[When you answer him: if he asked about one section (his to-dos, Later, Parked, Done), answer about that "
                "section first and plainly, 'nothing on the to-do list' when it's empty, and only then the rest if he'd "
                "want it. Otherwise tell him what's on the board in your own words, a few sentences like a friend would: "
                "what's active and where it stands, his open to-dos, what's on Later, anything parked. No raw lines, "
                "pipes, stars or dates. Then one line of you.]")
TRAILER_FAIL = "[When you answer him: nothing changed and there is no hash. Tell him exactly what the script said.]"
STATUS_WORD = re.compile(r"^(active|parked|done|later|todo|to-do|new|waiting|review|priority)\b", re.I)

WORKSPACE = os.environ.get("AETHER_WORKSPACE") or os.path.join(os.path.expanduser("~"), "AetherWorkspace")
PLANS = os.path.join(WORKSPACE, "plans")
PLAN_SECTIONS = [
    ("Goal", "what it is, for whom, and why; a real paragraph"),
    ("Done looks like", "what EXISTS when it's done, one line each: 'a write-up that answers X, Y and Z', 'a two-page brief "
                        "with the options and my pick'. Never tests: nothing here runs or builds"),
    ("What I know, what I need to find out", "what I already know about this, and each thing I don't, with how I'd find "
                                             "it out (a Library file, our old chats, or my own knowledge: say which). "
                                             "Nothing to read = 'working from my own knowledge', and I go"),
    ("Steps", "the work in order, one line each, as '- [ ] the step'. The first one small. New work found mid-way is a "
              "new step here, never a new file or a new project"),
]
STEP_SECTIONS = [
    ("What I did", "the actions, plainly: what I read, what I compared, what I wrote"),
    ("Findings", "the real numbers and names, one line each; enough that the user could decide from this section alone"),
    ("Why this over the alternatives", "the one I'd pick and the one I wouldn't, with the reason that decided it"),
    ("Still unknown", "what I couldn't confirm, and what would confirm it"),
    ("Sources", "the Library file and page, or 'my own knowledge, not verified'"),
]
STEP_LINE = re.compile(r"^- \[( |x|X)\] (.+?)\s*$")
OLD_TASK_LINE = re.compile(r"^(?:- |\d+[.)] )(.+?)\s*$")


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:48] or "project"


def plan_path(slug):
    return os.path.join(PLANS, slug + ".md")


def step_dir(slug):
    return os.path.join(WORKSPACE, slug)


def read_text(p):
    with open(p, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def write_text(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def plan_text_for(name):
    lines = [f"# {name}", f"_Plan started {today()}. A section still marked (empty: ...) needs my work: write_file, mode "
                          f"replace, the marker line -> my text. Steps are '- [ ] ...' lines; `board tick \"{name}\"` ticks "
                          "the current one and opens the next step's file._", ""]
    for title, hint in PLAN_SECTIONS:
        lines += [f"## {title}", f"_{hint}_", f"(empty: {title})", ""]
    return "\n".join(lines)


def section_body(text, title):
    m = re.search(r"(?ms)^## " + re.escape(title) + r"\s*$\n?(.*?)(?=^## |\Z)", text)
    return m.group(1) if m else None


def steps_of(text):
    body = section_body(text, "Steps")
    if body is not None:
        found = [(m.group(1).lower() == "x", m.group(2)) for ln in body.split("\n") if (m := STEP_LINE.match(ln.strip()))]
        if found:
            return found
    for old in ("Tasks", "Ordered tasks"):
        body = section_body(text, old)
        if body:
            pieces = [p for ln in body.split("\n") for p in re.split(r";\s*(?=\d+[.)]\s)", ln.strip())]
            found = [(False, m.group(1)) for p in pieces if (m := OLD_TASK_LINE.match(p)) and not p.startswith("(empty)")]
            if found:
                return found
    return []


def tick_current(text):
    body = section_body(text, "Steps")
    if body is None or not any(STEP_LINE.match(ln.strip()) for ln in body.split("\n")):
        steps = steps_of(text)
        if not steps:
            return None
        text = text.rstrip("\n") + "\n\n## Steps\n" + "\n".join(f"- [{'x' if t else ' '}] {s}" for t, s in steps) + "\n"
    out, k, n, done, hit = [], 0, 0, None, False
    in_steps = False
    for ln in text.split("\n"):
        if ln.startswith("## "):
            in_steps = ln.strip() == "## Steps"
        m = STEP_LINE.match(ln.strip()) if in_steps else None
        if m:
            n += 1
            if m.group(1).lower() != "x":
                if not hit:
                    hit, k, done = True, n, m.group(2)
                    ln = "- [x] " + m.group(2)
        out.append(ln)
    if not hit:
        return None
    return "\n".join(out), k, n, done


def step_file_text(name, slug, k, n, step):
    lines = [f"# Step {k} of {n}: {step}", f"_Part of {name} (plans/{slug}.md). Fill each section: write_file, mode replace, "
                                           "the '(empty: ...)' marker line -> my text. A section still marked (empty: ...) is "
                                           "visible to the user too._", ""]
    for title, hint in STEP_SECTIONS:
        lines += [f"## {title}", f"_{hint}_", f"(empty: {title})", ""]
    return "\n".join(lines)


def untouched(path):
    if not os.path.isfile(path):
        return -1
    text = read_text(path)
    marked = len(re.findall(r"(?m)^\(empty: ", text))
    return marked if marked >= len(STEP_SECTIONS) else 0


def ensure_step_file(name, slug, k, n, step):
    p = os.path.join(step_dir(slug), f"step-{k}.md")
    if not os.path.exists(p):
        write_text(p, step_file_text(name, slug, k, n, step))
    return p


def plan_state(name, slug):
    if not slug or not os.path.isfile(plan_path(slug)):
        return "new", "", 0, 0, ""
    steps = steps_of(read_text(plan_path(slug)))
    if not steps:
        return "new", "", 0, 0, ""
    n = len(steps)
    k = next((i for i, (t, _) in enumerate(steps, 1) if not t), None)
    if k is None:
        return "review", "", n, n, ""
    step = steps[k - 1][1]
    return "active", f"next: {k}/{n} {step}", k, n, step


def out(data, text, trailer=TRAILER_CHANGE):
    print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    print(text)
    print()
    print(trailer)


def fail(msg, **extra):
    data = {"ok": False, "error": msg}
    data.update(extra)
    text = msg
    if extra.get("candidates"):
        text += "\n" + "\n".join("  " + c for c in extra["candidates"])
    out(data, text, TRAILER_FAIL)
    sys.exit(1)


def today():
    return dt.date.today().isoformat()


def find_heads(lines):
    heads = {}
    for i, line in enumerate(lines):
        for key, h in HEADINGS.items():
            if line.strip() == h:
                heads[key] = i
    return heads


def read_board():
    if not os.path.isfile(BOARD):
        fail("board not found: " + BOARD)
    lines = open(BOARD, encoding="utf-8").read().split("\n")
    heads = find_heads(lines)
    if "todo" not in heads and "active" in heads and "later" in heads:
        at = heads["later"]
        lines[at:at] = [HEADINGS["todo"], ""]
        heads = find_heads(lines)
    missing = [k for k in SECTIONS if k not in heads]
    if missing:
        fail("board is missing sections: " + ", ".join(missing))
    if [k for k, _ in sorted(heads.items(), key=lambda kv: kv[1])] != SECTIONS:
        fail("board sections are out of order; expected Active, To-do, Later, Parked, Done")
    return lines, heads


def section_range(lines, heads, key):
    start = heads[key] + 1
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return start, end


def is_item(line):
    return line.startswith("- ") or line.startswith("**")


def items(lines, heads):
    found = []
    for key in SECTIONS:
        s, e = section_range(lines, heads, key)
        for i in range(s, e):
            if is_item(lines[i]):
                found.append((i, key, lines[i]))
    return found


def norm(text):
    text = text.replace("**", "")
    if text.startswith("- "):
        text = text[2:]
    return re.sub(r"\s+", " ", text).strip().lower()


def words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def find_one(lines, heads, match):
    m = norm(match)
    toks = words(match)
    if not toks:
        fail("give me a piece of the line to match")
    everything = items(lines, heads)
    phrase = [(i, k, l) for i, k, l in everything if m in norm(l)]
    if len(phrase) == 1:
        return phrase[0]
    hits = [(i, k, l) for i, k, l in everything if all(t in words(l) for t in toks)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        fail("no line on the board contains '" + match + "'", candidates=[l for _, _, l in everything])
    fail("'" + match + "' matches " + str(len(hits)) + " lines; be more specific", candidates=[l for _, _, l in hits])


def split_fields(text):
    return [f.strip() for f in text.split("|") if f.strip()]


def parse_line(line):
    body = line.strip()
    if body.startswith("- "):
        body = body[2:].strip()
    m = re.match(r"\*\*(.+?)\*\*\s*(.*)$", body)
    if m:
        name = m.group(1).strip()
        rest = split_fields(m.group(2))
    else:
        parts = split_fields(body)
        name = parts[0] if parts else body
        rest = parts[1:]
        if ": " in name:
            head, tail = name.split(": ", 1)
            if 0 < len(head) <= 60:
                name, rest = head.strip(), [tail.strip()] + rest
    brief = None
    kept = []
    for f in rest:
        if f.lower().startswith(("brief:", "plan:")):
            val = f.split(":", 1)[1].strip()
            brief = None if val.lower() in ("", "none") else val
        else:
            kept.append(f)
    return name, kept, brief


def line_info(line):
    name, rest, brief = parse_line(line)
    state = next((f for f in rest if STATUS_WORD.match(f)), "")
    priority = any(f.strip().lower() == "priority" for f in rest)
    free = [f for f in rest if f and not STATUS_WORD.match(f) and not re.match(r"next:", f, re.I)]
    return name, free, brief, state, priority


def render(section, name, rest, brief, note=None, state=None, nxt=None, priority=False):
    rest = [f for f in rest if f and not STATUS_WORD.match(f) and not re.match(r"next:", f, re.I)]
    if section in ("later", "todo"):
        line = "- " + name
        if note:
            rest = rest + [note.strip()]
        if len(rest) == 1 and not re.match(r"(next|last hurdle|brief|plan)\b", rest[0], re.I):
            line += ": " + rest[0]
        elif rest:
            line += " | " + " | ".join(rest)
    else:
        if section == "done":
            head = "done " + today()
        elif section == "parked":
            head = "parked " + today()
        else:
            head = state or "new"
        fields = [head] + (["priority"] if priority and section != "done" else []) + list(rest)
        if note:
            fields.append(note.strip())
        if nxt and section != "done":
            fields.append(nxt)
        line = "**" + name + "** | " + " | ".join(fields)
    if brief:
        line += " | plan: " + brief
    return line


def synced(section, line, note=None, state=None, keep_wait=True):
    name, free, brief, old_state, priority = line_info(line)
    st, nxt, k, n, step = plan_state(name, brief)
    if state is not None:
        st = state
    elif keep_wait and old_state.lower().startswith("waiting"):
        st = old_state
    if section == "active" and st == "active" and brief:
        ensure_step_file(name, brief, k, n, step)
    return render(section, name, free, brief, note, state=st, nxt=nxt, priority=priority), st, k, n, step


def new_line_for(section, text):
    text = text.strip()
    if not text:
        fail("the new line is empty")
    name, free, brief, state, priority = line_info(text)
    if not name:
        fail("the new line has no name")
    if section == "active":
        st, nxt, k, n, step = plan_state(name, brief)
        if state.lower().startswith("waiting"):
            st = state
        if st == "active" and brief:
            ensure_step_file(name, brief, k, n, step)
        return render(section, name, free, brief, state=st, nxt=nxt, priority=priority)
    return render(section, name, free, brief, priority=priority)


def insert_at_section_end(lines, heads, key, line):
    s, e = section_range(lines, heads, key)
    last_item = None
    for i in range(s, e):
        if is_item(lines[i]):
            last_item = i
    if last_item is not None:
        pos = last_item + 1
    else:
        pos = e
        while pos > s and lines[pos - 1].strip() == "":
            pos -= 1
    lines.insert(pos, line)
    return pos


def write_board(lines, header_before):
    heads = find_heads(lines)
    if any(k not in heads for k in SECTIONS):
        fail("internal check failed: a heading would go missing; nothing written")
    if lines[: heads["active"]] != header_before:
        fail("internal check failed: the header would change; nothing written")
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    with open(BOARD, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def git(*args):
    return subprocess.run(["git", "-C", MEMORY_DIR] + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def commit(message):
    r = git("add", "--", BOARD_REL)
    if r.returncode != 0:
        git("checkout", "--", BOARD_REL)
        fail("git add failed; board restored: " + (r.stderr or r.stdout).strip()[:300])
    r = git(*(AUTHOR + ["commit", "-q", "-m", message]))
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()
        if "nothing to commit" in msg or "no changes added" in msg:
            return None
        git("reset", "-q", "--", BOARD_REL)
        git("checkout", "--", BOARD_REL)
        fail("commit refused; board restored to the last commit: " + msg[:300])
    return git("rev-parse", "--short", "HEAD").stdout.strip()


def section_arg(s):
    s = (s or "").strip().lower().rstrip(":")
    s = SECTION_WORDS.get(s, s)
    if s not in SECTIONS:
        fail("unknown section '" + s + "'; use one of: active, todo, later, parked, done")
    return s


DONE_SHOWN = 5


def cmd_list(a):
    lines, heads = read_board()
    board = {k: [l for _, key, l in items(lines, heads) if key == k] for k in SECTIONS}
    done_total = len(board["done"])
    board["done"] = board["done"][-DONE_SHOWN:]
    text = []
    for k in SECTIONS:
        head = HEADINGS[k][3:] + " (" + str(done_total if k == "done" else len(board[k])) + ")"
        if k == "done" and done_total > DONE_SHOWN:
            head += ", the newest " + str(DONE_SHOWN) + " (the rest are in the file)"
        text.append(head + ("" if board[k] else ": nothing on it"))
        for l in board[k]:
            text.append("  " + l)
    out({"ok": True, "board": board, "done_total": done_total}, "\n".join(text), TRAILER_LIST)


def cmd_add(a):
    probe = (a.section or "").strip().lower().rstrip(":")
    if SECTION_WORDS.get(probe, probe) not in SECTIONS:
        a.text = [a.section + (" | " + " ".join(a.text) if a.text else "")]
        a.section = "active"
    section = section_arg(a.section)
    lines, heads = read_board()
    header = lines[: heads["active"]]
    line = new_line_for(section, " ".join(a.text))
    name = parse_line(line)[0].strip().lower()
    for _, k, l in items(lines, heads):
        if norm(l) == norm(line):
            fail("that line is already on the board", line=l)
        if parse_line(l)[0].strip().lower() == name:
            fail("that's already on the board, under " + HEADINGS[k][3:] + " (move it if it belongs elsewhere)", line=l)
    insert_at_section_end(lines, heads, section, line)
    write_board(lines, header)
    h = commit("board: add to " + section + ": " + parse_line(line)[0])
    out({"ok": True, "action": "add", "section": section, "line": line, "commit": h},
        "Added to " + HEADINGS[section][3:] + ": " + line + "\nCommit " + str(h) + ".")


def cmd_move(a):
    def is_section(x):
        x = (x or "").strip().lower().rstrip(":")
        return SECTION_WORDS.get(x, x) in SECTIONS
    if is_section(a.match) and not is_section(a.section):
        a.match, a.section = a.section, a.match
    target = section_arg(a.section)
    lines, heads = read_board()
    header = lines[: heads["active"]]
    i, src, old = find_one(lines, heads, a.match)
    if src == target:
        fail("that line is already under " + HEADINGS[target][3:], line=old)
    name, free, brief, state, priority = line_info(old)
    if target == "active":
        new, _, _, _, _ = synced("active", old, a.note, keep_wait=False)
    else:
        new = render(target, name, free, brief, a.note, priority=priority)
    del lines[i]
    heads = find_heads(lines)
    insert_at_section_end(lines, heads, target, new)
    write_board(lines, header)
    h = commit("board: move to " + target + ": " + name)
    out({"ok": True, "action": "move", "from": src, "to": target, "was": old, "line": new, "commit": h},
        "Moved from " + HEADINGS[src][3:] + " to " + HEADINGS[target][3:] + ": " + new + "\nCommit " + str(h) + ".")


def cmd_done(a):
    a.section = "done"
    cmd_move(a)


def cmd_set(a):
    if not " ".join(a.text).strip():
        fail("set needs the new text. To take a line off the board use: board.py remove \"<words from the line>\"")
    lines, heads = read_board()
    header = lines[: heads["active"]]
    i, src, old = find_one(lines, heads, a.match)
    new = new_line_for(src, " ".join(a.text))
    if new == old:
        fail("that line already reads exactly like that", line=old)
    lines[i] = new
    write_board(lines, header)
    h = commit("board: reword: " + parse_line(new)[0])
    out({"ok": True, "action": "set", "section": src, "was": old, "line": new, "commit": h},
        "Reworded under " + HEADINGS[src][3:] + ":\n  was: " + old + "\n  now: " + new + "\nCommit " + str(h) + ".")


def cmd_remove(a):
    lines, heads = read_board()
    header = lines[: heads["active"]]
    found = [find_one(lines, heads, m) for m in a.match]
    if len({i for i, _, _ in found}) < len(found):
        fail("two of those match the same line; give each line its own words")
    for i, _, _ in sorted(found, reverse=True):
        del lines[i]
    write_board(lines, header)
    h = commit("board: remove " + "; ".join(parse_line(old)[0] for _, _, old in found))
    first = {"section": found[0][1], "was": found[0][2]} if len(found) == 1 else {}
    out({"ok": True, "action": "remove", "removed": [{"section": s, "was": o} for _, s, o in found], "commit": h, **first},
        "\n".join("Removed from " + HEADINGS[s][3:] + ": " + o for _, s, o in found)
        + "\nCommit " + str(h) + ". (Git still has it.)")


def _project_line(match):
    lines, heads = read_board()
    header = lines[: heads["active"]]
    i, src, old = find_one(lines, heads, match)
    if src in ("later", "todo", "done"):
        fail("that line is under " + HEADINGS[src][3:] + "; a plan and steps are for a project under Active (move it "
             "there first)", line=old)
    return lines, heads, header, i, src, old


def _replace_line(lines, header, i, new, message):
    lines[i] = new
    write_board(lines, header)
    return commit(message)


def cmd_plan(a):
    lines, heads, header, i, src, old = _project_line(a.match)
    name, free, brief, state, priority = line_info(old)
    slug = brief or slugify(name)
    rel = os.path.join("plans", slug + ".md").replace("\\", "/")
    if os.path.isfile(plan_path(slug)):
        fail("that project already has a plan: " + rel + " (board show \"" + name + "\" reads it; fill or change it with "
             "write_file, then board next)", plan=rel)
    write_text(plan_path(slug), plan_text_for(name))
    new = render(src, name, free, slug, state="new" if src == "active" else None, priority=priority)
    h = _replace_line(lines, header, i, new, "board: plan for " + name)
    out({"ok": True, "action": "plan", "name": name, "plan": slug, "file": rel, "sections": [t for t, _ in PLAN_SECTIONS],
         "line": new, "commit": h},
        "Plan file made in your Workspace: " + rel + " (" + ", ".join(t for t, _ in PLAN_SECTIONS) + "). Fill each "
        "section with write_file (mode replace: the '(empty) ...' line -> your text; Steps as '- [ ] ...' lines). When "
        "the steps are in: board next \"" + name + "\".\nCommit " + str(h) + ".",
        "[When you answer him: the plan file is made and you're filling it; say what the first section says once it's in.]")


def cmd_next(a):
    lines, heads, header, i, src, old = _project_line(a.match)
    name, free, brief, state, priority = line_info(old)
    if not brief or not os.path.isfile(plan_path(brief)):
        fail("that project has no plan yet: board plan \"" + name + "\" makes the file", line=old)
    new, st, k, n, step = synced(src, old, keep_wait=False)
    if new == old:
        fail("nothing changed: the plan says the same (" + st + ")" + (" and it has no steps yet: add '- [ ] ...' lines "
             "under ## Steps" if st == "new" else ""), line=old)
    h = _replace_line(lines, header, i, new, "board: " + name + " -> " + st)
    step_file = os.path.relpath(os.path.join(step_dir(brief), f"step-{k}.md"), WORKSPACE).replace("\\", "/") if st == "active" else ""
    out({"ok": True, "action": "next", "name": name, "state": st, "step": k, "of": n, "step_text": step, "step_file": step_file,
         "line": new, "commit": h},
        ("Now: " + new + "\n" + (f"Step {k} of {n}: {step}. Its file: {step_file} (fill its sections; board tick \"{name}\" "
                                 "when it's done)." if st == "active" else "")).rstrip() + "\nCommit " + str(h) + ".")


def cmd_tick(a):
    lines, heads, header, i, src, old = _project_line(a.match)
    name, free, brief, state, priority = line_info(old)
    if not brief or not os.path.isfile(plan_path(brief)):
        fail("that project has no plan yet: board plan \"" + name + "\" makes the file", line=old)
    text = read_text(plan_path(brief))
    r = tick_current(text)
    if r is None:
        fail("nothing to tick: the plan has no unticked steps" + (" (it's in review)" if steps_of(text) else
             " (no '- [ ] ...' lines under ## Steps yet)"), line=old)
    text2, k, n, ticked = r
    cur = os.path.join(step_dir(brief), f"step-{k}.md")
    rel_cur = os.path.relpath(cur, WORKSPACE).replace("\\", "/")
    left = untouched(cur)
    if left:
        if left < 0:
            ensure_step_file(name, brief, k, n, ticked)
        fail(f"not ticked: step {k} of {n} ({ticked}) has nothing written in it yet ({rel_cur}" + (": every section still "
             "marked (empty: ...)" if left > 0 else " was missing; it's made now") + "). Do the step there first, then tick.",
             line=old, step_file=rel_cur)
    write_text(plan_path(brief), text2)
    new, st, nk, nn, step = synced(src, old, keep_wait=False)
    h = _replace_line(lines, header, i, new, f"board: {name} step {k}/{n} ticked")
    data = {"ok": True, "action": "tick", "name": name, "ticked": k, "of": n, "ticked_text": ticked, "state": st, "line": new,
            "commit": h}
    if st == "review":
        done_like = (section_body(text2, "Done looks like") or "").strip()
        files = [os.path.relpath(os.path.join(step_dir(brief), f), WORKSPACE).replace("\\", "/")
                 for f in sorted(os.listdir(step_dir(brief)))] if os.path.isdir(step_dir(brief)) else []
        data.update(review=True, done_looks_like=done_like, step_files=files, plan_file=f"plans/{brief}.md")
        msg = (f"Step {k} of {n} ticked: {ticked}. That was the last one: {name} is in review. Go down 'Done looks like' "
               f"({len(done_like.splitlines())} line(s)) and say yes / no / can't tell for each, with why; Aether puts a review "
               "card in {USER}'s chat with your answers.")
    else:
        step_file = os.path.relpath(os.path.join(step_dir(brief), f"step-{nk}.md"), WORKSPACE).replace("\\", "/")
        data.update(step_file=step_file, step_text=step)
        msg = (f"Step {k} of {n} ticked: {ticked}.\nNext: step {nk} of {nn}: {step}. Its file: {step_file} (its sections are "
               "pre-made; fill them, then board tick again).")
    out(data, msg + "\nCommit " + str(h) + ".")


def cmd_wait(a):
    lines, heads, header, i, src, old = _project_line(a.match)
    name, free, brief, state, priority = line_info(old)
    what = " ".join(a.what).strip()
    if len(what) < 4:
        fail("say what it waits on {USER} for")
    new, st, k, n, step = synced(src, old, state="waiting: " + what)
    h = _replace_line(lines, header, i, new, "board: " + name + " waits: " + what[:60])
    out({"ok": True, "action": "wait", "name": name, "what": what, "line": new, "commit": h},
        "Now: " + new + "\nIt waits on {USER}; tell him what you need, and pick something else meanwhile.\nCommit " + str(h) + ".")


def cmd_priority(a):
    lines, heads, header, i, src, old = _project_line(a.match)
    name, free, brief, state, priority = line_info(old)
    st = state if state and not re.match(r"(active|parked|done)\s+\d{4}", state) else None
    new = render(src, name, free, brief, state=st if src == "active" else None, priority=not priority,
                 nxt=plan_state(name, brief)[1] if src == "active" else None)
    h = _replace_line(lines, header, i, new, "board: " + name + (" is a priority" if not priority else " is no longer a priority"))
    out({"ok": True, "action": "priority", "name": name, "priority": not priority, "line": new, "commit": h},
        "Now: " + new + "\nCommit " + str(h) + ".")


def cmd_show(a):
    lines, heads = read_board()
    i, src, old = find_one(lines, heads, a.match)
    name, free, brief, state, priority = line_info(old)
    if not brief or not os.path.isfile(plan_path(brief)):
        fail("that project has no plan file" + (" yet: board plan \"" + name + "\" makes it" if src == "active" else ""), line=old)
    text = read_text(plan_path(brief))
    st, nxt, k, n, step = plan_state(name, brief)
    parts = [old, "", "=== plans/" + brief + ".md ===", text.rstrip()]
    sf = os.path.join(step_dir(brief), f"step-{k}.md")
    if st == "active" and os.path.isfile(sf):
        parts += ["", f"=== {brief}/step-{k}.md (the current step) ===", read_text(sf).rstrip()]
    out({"ok": True, "action": "show", "name": name, "plan": brief, "state": st, "step": k, "of": n},
        "\n".join(parts), "[Read it; if he asked, tell him where it stands in your own words.]")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Edit the project board.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("plan"); p.add_argument("match"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("next"); p.add_argument("match"); p.set_defaults(fn=cmd_next)
    p = sub.add_parser("tick"); p.add_argument("match"); p.set_defaults(fn=cmd_tick)
    p = sub.add_parser("wait"); p.add_argument("match"); p.add_argument("what", nargs="+"); p.set_defaults(fn=cmd_wait)
    p = sub.add_parser("priority"); p.add_argument("match"); p.set_defaults(fn=cmd_priority)
    p = sub.add_parser("show"); p.add_argument("match"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("add"); p.add_argument("section"); p.add_argument("text", nargs="+"); p.set_defaults(fn=cmd_add)
    p = sub.add_parser("move"); p.add_argument("match"); p.add_argument("section"); p.add_argument("note", nargs="?"); p.set_defaults(fn=cmd_move)
    p = sub.add_parser("done"); p.add_argument("match"); p.add_argument("note", nargs="?"); p.set_defaults(fn=cmd_done)
    p = sub.add_parser("set"); p.add_argument("match"); p.add_argument("text", nargs="*"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("remove"); p.add_argument("match", nargs="+"); p.set_defaults(fn=cmd_remove)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
