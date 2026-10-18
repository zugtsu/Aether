import argparse
import os
import sys
import threading

from . import config as config_mod
from .config import DATA_DIR
from .engine import Engine, Hooks
from .history import Conversation, list_conversations
from .llm import LLMError, LMStudio
from .memory import Memory, seed
from .skills import discover
from .names import user_name

CONV_DIR = os.path.join(DATA_DIR, "conversations")
DIM, PINK, CYAN, GOLD, RED, OFF = "\033[2m", "\033[95m", "\033[96m", "\033[93m", "\033[91m", "\033[0m"


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if os.name == "nt":
        os.system("")


def cmd_check(cfg, _args):
    print(f"Settings file: {config_mod.CONFIG_FILE}")
    try:
        loaded = [m["id"] for m in LMStudio(cfg).models() if m.get("state") == "loaded"]
        have = cfg.model.split("/")[-1] in [m.split("/")[-1] for m in loaded]
        print(f"LM Studio: reachable. Loaded: {', '.join(loaded) or 'nothing'}"
              + ("" if have else f"  {GOLD}(Aether's model {cfg.model} isn't loaded){OFF}"))
    except Exception as e:
        print(f"LM Studio: {RED}not reachable{OFF} ({e})")
    mode = cfg.memory_mode()
    print(f"Memory: {cfg.memory_path}  " + (f"{RED}a protected folder{OFF}" if mode == "REAL memory" else f"({mode})"))
    if not os.path.isdir(cfg.memory_path):
        print(f"  {GOLD}missing: run  python -m aether new-memory{OFF}")
        return 1
    mem = Memory(cfg.memory_path, cfg)
    print(f"  {len(mem.system_files())} files always in her prompt, {len(mem.other_files())} other files")
    print(f"  add can pick {len(mem.addable())} files; replace/remove {len(mem.editable())}")
    live, rejected = discover(cfg.memory_path)
    print(f"Skills live ({len(live)}): {', '.join(sorted(live))}")
    for n, s in sorted(rejected.items()):
        print(f"  {GOLD}left out: {n}{OFF}: {'; '.join(s.problems)}")
    from . import prompt as p
    from .schema import step_schema
    sysp = p.build(mem, live, cfg)
    print(f"Her instructions: {len(sysp):,} characters (~{len(sysp) // 4:,} tokens).")
    print(f"Step shapes she can pick from: {len(step_schema(mem, live)['anyOf'])}")
    return 0


def cmd_new_memory(cfg):
    dst = cfg.memory_path
    if os.path.exists(dst):
        print(f"Her memory folder is already there: {dst} (nothing changed)")
        return 1
    if not seed(dst):
        print("starter-memory/ isn't in the project folder; nothing made")
        return 1
    print(f"Made her memory from starter-memory/: {dst}")
    return 0


class TerminalHooks(Hooks):
    def __init__(self, name="Companion"):
        self.paused = threading.Event()
        self.speaking = False
        self.name = name

    def on_say(self, text):
        if not self.speaking:
            sys.stdout.write(f"{PINK}{self.name}:{OFF} ")
            self.speaking = True
        sys.stdout.write(text)
        sys.stdout.flush()

    def on_step(self, step):
        k = step["step"]
        what = step.get("skill") or step.get("file") or step.get("path") or ""
        extra = " " + " ".join(step.get("args") or []) if k == "skill" else ""
        print(f"{DIM}  -> {k} {what}{extra}{OFF}")

    def on_result(self, step, ok, text):
        first = text.strip().splitlines()[0] if text.strip() else ""
        mark = f"{CYAN}ok{OFF}" if ok else f"{RED}failed{OFF}"
        print(f"{DIM}     {mark}{DIM}: {first[:150]}{OFF}")

    def on_stop(self):
        print(f"\n{RED}  [stopped]{OFF}")

    def ask(self, question):
        self.paused.set()
        try:
            ans = input(f"\n{GOLD}{question}. Allow? (y/n) {OFF}").strip().lower()
            return ans in ("y", "yes")
        finally:
            self.paused.clear()


def _esc_watcher(engine, hooks, done):
    try:
        import msvcrt
    except ImportError:
        return
    while not done.is_set():
        if not hooks.paused.is_set() and msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch == "\x1b":
                engine.stop()
        done.wait(0.05)


def cmd_chat(cfg, args):
    if not os.path.isdir(cfg.memory_path):
        print("No memory folder yet. Run: python -m aether new-memory")
        return 1
    if args.open:
        cid = args.open
    elif args.new:
        cid = None
    else:
        convs = list_conversations(CONV_DIR)
        cid = convs[0] if convs else None
    conv = Conversation(CONV_DIR, cid)
    hooks = TerminalHooks(cfg.display_name or "Companion")
    engine = Engine(cfg, LMStudio(cfg), conv, hooks)
    where = {"home": "her home", "test copy": "TEST COPY"}.get(cfg.memory_mode(), "a protected folder")
    print(f"{DIM}Aether - chat {conv.id} ({len(conv.events)} events) - memory: {where}")
    print(f"Esc stops her. /help for commands.{OFF}")
    while True:
        try:
            text = input(f"{CYAN}{user_name(cfg)}:{OFF} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text.startswith("/"):
            if _command(text, engine, conv) == "quit":
                return 0
            conv = engine.conv
            continue
        done = threading.Event()
        threading.Thread(target=_esc_watcher, args=(engine, hooks, done), daemon=True).start()
        hooks.speaking = False
        try:
            engine.turn(text, place="Aether terminal")
        except LLMError as e:
            print(f"{RED}{e}{OFF}")
        finally:
            done.set()
        print()


def _command(text, engine, conv):
    cmd = text.split()[0].lower()
    if cmd in ("/quit", "/exit"):
        return "quit"
    if cmd == "/help":
        print("/new  start a new chat      /chats  list chats      /open ID  open one\n"
              "/skills  live + left-out skills   /commits  her latest memory commits   /quit")
    elif cmd == "/new":
        engine.conv = Conversation(CONV_DIR)
        print(f"{DIM}new chat {engine.conv.id}{OFF}")
    elif cmd == "/chats":
        for cid in list_conversations(CONV_DIR)[:15]:
            print(f"  {cid}  {Conversation(CONV_DIR, cid).title()}")
    elif cmd == "/open":
        parts = text.split()
        if len(parts) > 1:
            engine.conv = Conversation(CONV_DIR, parts[1])
            print(f"{DIM}opened {engine.conv.id} ({len(engine.conv.events)} events){OFF}")
    elif cmd == "/skills":
        print("live: " + ", ".join(sorted(engine.skills)))
        for n, s in engine.rejected.items():
            print(f"left out {n}: {'; '.join(s.problems)}")
    elif cmd == "/commits":
        for h, who, when, subj in engine.memory.history(10):
            print(f"  {h} {who:5} {when:>16}  {subj[:80]}")
    else:
        print("unknown command; /help")
    return None


def cmd_prompt(cfg, _args):
    cfg.check_safe()
    from . import prompt as p
    mem = Memory(cfg.memory_path, cfg)
    live, _ = discover(cfg.memory_path)
    print(p.build(mem, live, cfg))
    return 0


def cmd_lessons(cfg):
    import datetime as dt
    import json

    from . import lessons
    from .engine import AUDIT
    from .life import LESSONS, STATE_FILE
    from .memory import Memory
    mem = Memory(cfg.memory_path, cfg)
    f = mem.files.get(LESSONS)
    lines = [ln for ln in (f.body.splitlines() if f else []) if ln.strip().startswith("- ")]
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            meta = json.load(fh).get("lesson_meta") or {}
    except (OSError, ValueError):
        meta = {}
    skills = {d for d in os.listdir(os.path.join(mem.root, "skills"))} if os.path.isdir(os.path.join(mem.root, "skills")) else set()
    now, days = dt.datetime.now(), int(getattr(cfg, "lesson_trial_days", 14) or 14)
    rows = lessons.read_audit(AUDIT, since=now - dt.timedelta(days=days * 4))
    print(f"{len(lines)} lessons in her rulebook; {len(rows)} steps in the audit log, "
          f"{sum(1 for r in rows if not r[2])} failed; trial {days} days\n")
    for r in lessons.report(lines, meta, skills | lessons.BUILTIN, rows, now, days):
        print(r["line"][:150])
        print(f"    mistake: {', '.join(r['tags']) or '(none: no tag, no label)'}"
              + ("" if r["measured"] else " (from her label, not measured)") if r["tags"] else "    mistake: (none)")
        if r["numbers"]:
            print(f"    {r['numbers']}")
        if r["verdict"]:
            print(f"    -> would retire: {r['verdict']}")
    return 0


def cmd_worse(since_text, before_days):
    import datetime as dt

    from . import lessons
    from .engine import AUDIT
    now = dt.datetime.now()
    try:
        since = dt.datetime.fromisoformat(since_text) if since_text else now - dt.timedelta(days=3)
    except ValueError:
        print(f"--since takes a date (2026-10-03) or a date and time (2026-10-03 23:00), not {since_text!r}")
        return 2
    rows = lessons.read_audit(AUDIT, since=since - dt.timedelta(days=before_days))
    report = lessons.worse(rows, since, now, before_days)
    print(f"Since {since:%Y-%m-%d %H:%M} vs the {before_days} days before (her audit log; reads only).\n"
          "worse = the failure rate rose by more than 10 points, with 2+ failures since.\n")
    if not report:
        print("No steps in that time.")
    for r in report:
        (bf, bt), (af, at) = r["before"], r["after"]
        pct = lambda f, t: f"{100 * f / t:3.0f}%" if t else "   -"  # noqa: E731
        kinds = ", ".join(f"{k} {n}" for k, n in sorted(r["kinds"].items(), key=lambda kv: -kv[1])[:3])
        print(f"{'WORSE ' if r['worse'] else '      '}{r['what']:16} before {bf:3}/{bt:<4} {pct(bf, bt)}   "
              f"since {af:3}/{at:<4} {pct(af, at)}" + (f"   ({kinds})" if kinds else ""))
    return 0


def cmd_asks(since_text):
    from . import router
    from .config import DATA_DIR
    report = router.ask_recall(os.path.join(DATA_DIR, "conversations"), since_text or "")
    print(f"His asks{' since ' + since_text if since_text else ''}, and how many a step that worked did before her reply "
          "(her real chats; reads only):\n")
    if not report:
        print("No asks in that time.")
    for name, (asked, done) in sorted(report.items(), key=lambda kv: -kv[1][0]):
        print(f"  {name:10} {done:3}/{asked:<3} {100 * done / asked:4.0f}%")
    total = [sum(v[i] for v in report.values()) for i in (0, 1)]
    if total[0]:
        print(f"\n  all        {total[1]:3}/{total[0]:<3} {100 * total[1] / total[0]:4.0f}%")
    return 0


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(prog="python -m aether", description="Aether, a local AI companion engine")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("check")
    sub.add_parser("new-memory", help="make her memory folder from starter-memory/ (only when there's none)")
    ch = sub.add_parser("chat")
    ch.add_argument("--new", action="store_true")
    ch.add_argument("--open")
    sub.add_parser("prompt")
    ap_app = sub.add_parser("app")
    ap_app.add_argument("--no-window", action="store_true", help="just run the server")
    ap_app.add_argument("--port", type=int)
    ap_app.add_argument("--quit-when-closed", action="store_true", help="stop Aether when its window closes")
    sub.add_parser("shortcut", help="make the Aether icon on the desktop")
    rt = sub.add_parser("redteam", help="try to trick her, on a throwaway copy of her memory")
    rt.add_argument("--out")
    rt.add_argument("--hard", action="store_true", help="longer, sneakier attacks, graded by the model")
    rt.add_argument("--cue", action="store_true", help="with the Cue on (what comes to mind), plus attacks through old chats")
    rt.add_argument("--only", help="just the attacks whose name has this in it (e.g. 'cue:')")
    tf = sub.add_parser("tidy-facts", help="tidy her facts file now (Aether also does this nightly)")
    tf.add_argument("--dry-run", action="store_true", help="show what it would do, change nothing")
    sub.add_parser("lessons", help="her rulebook with each lesson's mistake and the numbers (reads only)")
    wo = sub.add_parser("worse", help="what got worse in real use: each tool's failure rate since a change vs before (reads only)")
    wo.add_argument("--since", help="when the change went in: 2026-10-03 or '2026-10-03 23:00' (default: 3 days ago)")
    wo.add_argument("--days", type=int, default=14, help="how many days before it to compare with (default 14)")
    ak = sub.add_parser("asks", help="his asks her router knows, and how many got done before her reply (reads only)")
    ak.add_argument("--since", default="", help="2026-10-04 or '2026-10-04 06:00' (default: all her chats)")
    args = ap.parse_args(argv)
    if args.cmd == "asks":
        return cmd_asks(args.since.replace(" ", "T"))
    if args.cmd == "lessons":
        return cmd_lessons(config_mod.load(write_defaults=False))
    if args.cmd == "worse":
        return cmd_worse(args.since, args.days)
    cfg = config_mod.load()
    if args.cmd == "check":
        return cmd_check(cfg, args)
    if args.cmd == "new-memory":
        return cmd_new_memory(cfg)
    if args.cmd == "chat":
        return cmd_chat(cfg, args)
    if args.cmd == "prompt":
        return cmd_prompt(cfg, args)
    if args.cmd == "app":
        from .desktop import popup
        seed(cfg.memory_path)
        if not os.path.isdir(cfg.memory_path):
            popup("Aether has no memory folder yet.\n\nIn the project folder run:  python -m aether new-memory")
            return 1
        from .server import serve
        try:
            return serve(cfg, open_window=not args.no_window, port=args.port, quit_when_closed=args.quit_when_closed)
        except SystemExit as e:
            popup(str(e))
            return 1
        except Exception as e:
            popup(f"Aether couldn't start:\n\n{e}")
            raise
    if args.cmd == "shortcut":
        from .desktop import create_shortcut
        print("Made:", create_shortcut(cfg))
        return 0
    if args.cmd == "tidy-facts":
        from .desktop import running
        from .llm import LMStudio
        from .memory import Memory
        from .tidy import tidy_facts
        if running(cfg.port) and not args.dry_run:
            print("Close Aether first (it would keep the old facts in view until it reloads).")
            return 1
        cfg.check_safe()
        r = tidy_facts(Memory(cfg.memory_path, cfg), LMStudio(cfg), temperature=cfg.temperature_tools,
                       dry_run=args.dry_run, say=print)
        print(f"duplicates {r.get('duplicates', 0)}, merged {r.get('merged', 0)}, retired {r.get('retired', 0)}, "
              f"refused {len(r.get('refused', []))}" + (f", commit {r['commit']}" if r.get("commit") else ""))
        print("\n".join(r.get("history", [])))
        if args.dry_run:
            print("\n--- the file would become ---\n" + r.get("preview", ""))
        return 0
    if args.cmd == "redteam":
        from .redteam import run_redteam
        run_redteam(cfg, args.out, hard=args.hard, cue=args.cue, only=args.only)
        return 0
    ap.print_help()
    return 0
