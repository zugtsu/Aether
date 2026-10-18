import base64
import datetime as dt
import json
import mimetypes
import os
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config as config_mod
from . import prompt as prompt_mod
from . import avatars
from . import brainmap
from . import gpu as gpu_mod
from . import ratings as ratings_mod
from . import songs as songs_mod
from .config import DATA_DIR
from .engine import Engine, Hooks, log
from .history import IMAGE_TYPES, Conversation, list_conversations, stranger
from .chats import ChatReader
from .life import HEARTBEAT_CHAT, Life
from .proc import NO_WINDOW, python_exe
from .cue import Cue
from .shared_calendar import Calendar
from .keeper import Keeper
from .nudge import Nudge
from .recall import Recall
from .imagine import Imagine
from .examples import Examples
from .proposals import Proposals
from .digest import Digest
from .lookback import LookBack
from .eyes import Eyes
from .brain import Brain, BrainError
from .vault import Vault
from . import discord as discord_mod
from . import shell as shell_mod
from . import backup as backup_mod
from .engine import read_audit
from .ears import Ears
from .llm import LLMError, LMStudio
from .voice import Voice
from .names import GIT_USER, GIT_USER_EMAIL, USER, fill

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
_NM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop", "node_modules")
VENDOR = {
    "pixi.min.js": os.path.join(_NM, "pixi.js", "dist", "browser", "pixi.min.js"),
    "cubism4.min.js": os.path.join(_NM, "pixi-live2d-display", "dist", "cubism4.min.js"),
    "live2dcubismcore.min.js": os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "live2dcubismcore.min.js"),
}
AVATARS_DIR = os.path.join(DATA_DIR, "avatars")
CONV_DIR = os.path.join(DATA_DIR, "conversations")
YIELD_WAIT = 180
READ_AHEAD_TICK = 2
ATTACH_DIR = os.path.join(DATA_DIR, "attachments")
SKILLS_SEEN = os.path.join(DATA_DIR, "skills_seen.json")
STEP_EXAMPLE = re.compile(r'\{\s*"step"\s*:\s*"skill"\s*,\s*"skill"\s*:\s*"([^"]+)"(?:\s*,\s*"command"\s*:\s*"([^"]*)")?[^\n]*')
META_FILE = os.path.join(CONV_DIR, "_meta.json")
TRASH_DIR = os.path.join(CONV_DIR, "_trash")
MAX_BODY = 30 * 1024 * 1024

GREETING_SCHEMA = {
    "type": "object",
    "properties": {
        "greeting": {"type": "string"},
        "suggestions": {"type": "array", "minItems": 4, "maxItems": 4, "items": {
            "type": "object",
            "properties": {"kind": {"enum": ["continue", "dream", "check", "project", "fun"]}, "text": {"type": "string"}},
            "required": ["kind", "text"], "additionalProperties": False}},
    },
    "required": ["greeting", "suggestions"], "additionalProperties": False,
}
GREETING_ASK = ("[Aether: {USER} just opened a new chat. Write ONE short greeting line in your own voice (no question "
                "about what he wants to do), and 4 things he might want to talk about, each under 60 characters, "
                "drawn from your memory: something to pick back up, a check a skill could do, a project, or "
                "something fun. Write them the way he would click them, like 'What's on my calendar Tuesday?'.]")
THEMES = ("astral", "holo", "void", "terminal")
FOLDERS = {"library": "library_dir", "workspace": "workspace_dir"}
PICK_FOLDER = ("import json, sys\n"
               "try:\n    import tkinter as tk\n    from tkinter import filedialog\nexcept Exception as e:\n"
               "    print(json.dumps({'error': str(e)})); sys.exit(3)\n"
               "root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)\n"
               "p = filedialog.askdirectory(parent=root, initialdir=sys.argv[1] or None, title=sys.argv[2], mustexist=False)\n"
               "root.destroy(); print(json.dumps({'path': p or ''}))\n")
SETTABLE = {"model": str, "temperature_talk": float, "temperature_tools": float, "max_steps": int,
            "history_chars": int, "reply_max_tokens": int, "skill_timeout": int, "display_name": str, "user_name": str,
            "tagline": str, "theme": str, "space_intensity": float, "show_work": bool, "voice": str, "voice_speed": float,
            "voice_engine": str, "brain_style": str, "archive_after_days": int,
            "tts_url": str, "tts_model": str, "breeze_voice": str,
            "speak_replies": str, "hear_tone": bool, "mic_device": str, "mood_enabled": bool, "heartbeat_enabled": bool,
            "heartbeat_minutes": int, "heartbeat_idle_minutes": int, "message_idle_minutes": int, "sleep_work": bool,
            "sleep_work_minutes": int, "own_thinking": bool, "examples_enabled": bool, "examples_collect": bool, "quiet_start": str, "quiet_end": str, "reach_out_cap": int, "reach_out_to": str, "wakeups_enabled": bool,
            "dreams_enabled": bool, "dream_time": str, "reflect_enabled": bool, "images_enabled": bool, "videos_enabled": bool, "backups_enabled": bool,
            "calendar_enabled": bool, "recall_enabled": bool, "eyes_enabled": bool, "eyes_camera": str, "recall_hybrid": bool, "recall_links": bool, "recall_full_text": bool, "cue_enabled": bool, "cue_max": int, "cue_min": float, "cue_rare": float,
            "cue_notice": bool, "keeper_enabled": bool, "keeper_board_check": bool, "nudge_enabled": bool, "knowledge_sources": dict, "prompt_journal_days": int, "prompt_journal_chars": int,
            "prompt_recap": bool, "prompt_timeline_days": int, "prompt_timeline_chars": int, "avatar_enabled": bool, "discord_enabled": bool, "discord_mirror": bool,
            "discord_dm_policy": str, "discord_owner_ids": list, "discord_channels": list,
            "permission_levels": dict, "workspace_dir": str, "library_dir": str}


class AppHooks(Hooks):
    def __init__(self, app):
        self.app = app

    def _send(self, **ev):
        ev.setdefault("chat", self.app.engine.conv.id if self.app.engine else "")
        self.app.broadcast(ev)

    def on_say(self, text):
        clock = self.app.clock
        if clock is not None and "engine" not in clock:
            clock["engine"] = self.app.engine.timing
        self._send(type="say", text=text)
        if self.app.speaking:
            self.app.voice.feed(text)
    def on_step(self, step): self._send(type="step", step=step)
    def on_result(self, step, ok, text):
        self._send(type="result", step=step, ok=ok, text=text[:1500])
    def on_status(self, text): self._send(type="status", text=text)
    def on_review(self, data): self.app.proposals.review(data)
    def on_term(self, who, kind, text):
        self.app.broadcast({"type": "term", "who": who, "kind": kind, "text": text})

    def on_stop(self):
        self.app.voice.stop()
        self._send(type="stopped")

    def ask(self, question):
        qid = secrets.token_hex(6)
        waiter = {"event": threading.Event(), "answer": False}
        self.app.pending[qid] = waiter
        self._send(type="ask", qid=qid, question=question)
        waiter["event"].wait(120)
        self.app.pending.pop(qid, None)
        self._send(type="asked", qid=qid, allow=waiter["answer"])
        return waiter["answer"]


class App:
    def __init__(self, cfg, llm=None):
        cfg.check_safe()
        self.cfg = cfg
        self.token = secrets.token_urlsafe(24)
        self.stop_server = None
        self.clients = []
        self.clients_lock = threading.Lock()
        self.gpu = threading.Lock()
        self.gpu_yield = False
        self.user_waiting = 0
        self.pending = {}
        self.greeting = None
        self._svc = (0, {})
        os.makedirs(CONV_DIR, exist_ok=True)
        self._meta_lock = threading.Lock()
        self.meta = self._load_meta()
        self.engine = None
        self.speaking = False
        self.clock = None
        self.pet_open = False
        self.term_cwd = os.path.expanduser("~")
        self.term_proc_busy = False
        self.term_cancel = threading.Event()
        self.voice = Voice(cfg, self.broadcast)
        self.ears = Ears(cfg)
        self.conv_dir = CONV_DIR
        convs = [c for c in list_conversations(CONV_DIR) if c != HEARTBEAT_CHAT]
        extra_steps = {}
        self.vault = Vault()
        self.engine = Engine(cfg, llm or LMStudio(cfg), Conversation(CONV_DIR, convs[0] if convs else None), AppHooks(self),
                             extra_steps=extra_steps, vault=self.vault)
        self.life = Life(self)
        self.voice.mood = lambda: self.life.mood.current() if self.cfg.mood_enabled else None
        self.recall = Recall(cfg, self.conv_dir, self.engine.memory)
        self.examples = Examples(self)
        self.keeper = Keeper(self)
        self.nudge = Nudge(self)
        self.cue = Cue(self)
        extra_steps["set_mood"] = (self.life.mood_option, self.life.set_mood)
        extra_steps["recall"] = (lambda: self.recall.option() if cfg.recall_enabled else None, self._recall_step)
        extra_steps["wake_me"] = (self.life.wake_option, self.life.set_wakeup)
        self.calendar = Calendar(self)
        extra_steps["calendar"] = (lambda: self.calendar.option() if cfg.calendar_enabled else None,
                                   self._calendar_step)
        from .shared_calendar import SKILL_DOC, SKILL_LINE
        self.engine.builtin_docs["calendar"] = (lambda: cfg.calendar_enabled, SKILL_LINE, SKILL_DOC)
        self.engine.date_lines = lambda: self.calendar.entries() if cfg.calendar_enabled else []
        self.imagine = Imagine(self)
        extra_steps["make_image"] = (self.imagine.option, self.imagine.run_step)
        extra_steps["gallery"] = (self.imagine.gallery_option, self.imagine.gallery_step)
        extra_steps["make_video"] = (self.imagine.video_option, self.imagine.video_step)
        extra_steps["make_music"] = (self.imagine.song_option, self.imagine.song_step)
        self.engine.builtin_docs["make_music"] = (
            lambda: getattr(cfg, "songs_enabled", True),
            lambda: songs_mod.SKILL_LINE + "".join(
                f" {USER} liked: {'; '.join(liked)}." for liked in [songs_mod.liked_styles(self.engine.memory)] if liked),
            songs_mod.SKILL_DOC)
        self.chat_reader = ChatReader(self)
        extra_steps["read_chat"] = (self.chat_reader.option, self.chat_reader.run_step)
        self.engine.lessons_for = self.life.lessons_for
        self.proposals = Proposals(self)
        self.digest = Digest(self)
        extra_steps["my_time"] = (self.digest.option, self.digest.run_step)
        self.lookback = LookBack(self)
        self.brains = Brain(self)
        extra_steps["look_back"] = (self.lookback.option, self.lookback.run_step)
        from . import digest as digest_mod, lookback as lookback_mod
        self.engine.builtin_docs["look_back"] = (lambda: True, lookback_mod.SKILL_LINE, lookback_mod.SKILL_DOC)
        self.engine.builtin_docs["my_time"] = (lambda: True, digest_mod.SKILL_LINE, digest_mod.SKILL_DOC)
        self.eyes = Eyes(self)
        from . import eyes as eyes_mod
        extra_steps["webcam"] = (self.eyes.option, self.eyes.run_step)
        self.engine.builtin_docs["webcam"] = (lambda: True,
                                            lambda: eyes_mod.SKILL_LINE if cfg.eyes_enabled else eyes_mod.CLOSED_LINE,
                                            lambda: eyes_mod.SKILL_DOC if cfg.eyes_enabled else eyes_mod.CLOSED_DOC)
        self.engine.refresh()
        self.your_chat = self.engine.conv.id
        self.discord = discord_mod.Discord(self)
        self.voice.warm()

    def quit(self):
        log("the desktop app asked Aether to quit")
        if self.stop_server:
            threading.Thread(target=self.stop_server, daemon=True, name="quit").start()

    def subscribe(self):
        q = queue.Queue(maxsize=5000)
        with self.clients_lock:
            self.clients.append(q)
        return q

    def unsubscribe(self, q):
        with self.clients_lock:
            if q in self.clients:
                self.clients.remove(q)

    def broadcast(self, ev):
        if ev.get("type") == "audio":
            ev["pet"] = self.pet_open
        with self.clients_lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(ev)
                except queue.Full:
                    pass

    def _load_meta(self):
        try:
            with open(META_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_meta(self):
        with self._meta_lock:
            tmp = META_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.meta, f, indent=1)
            os.replace(tmp, META_FILE)

    def conv(self, cid):
        if not re.fullmatch(r"[\w-]{6,80}", cid or ""):
            raise ValueError("bad chat id")
        if self.engine.conv.id == cid:
            return self.engine.conv
        if not os.path.exists(os.path.join(self.conv_dir, cid + ".jsonl")):
            raise ValueError("no such chat")
        return Conversation(self.conv_dir, cid)

    def chats(self):
        out = []
        for cid in list_conversations(self.conv_dir):
            if cid == HEARTBEAT_CHAT:
                continue
            m = self.meta.get(cid, {})
            if m.get("archived"):
                path = os.path.join(self.conv_dir, cid + ".jsonl")
                out.append({"id": cid, "title": m.get("title") or cid, "archived": True, "source": "archive",
                            "updated": dt.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds"),
                            "pinned": False, "unread": False, "events": 1})
                continue
            c = Conversation(self.conv_dir, cid)
            places = [e.get("place", "") for e in c.events if e["kind"] == "user"]
            src = "app"
            if places and "discord" in places[-1].lower():
                src = "discord"
            elif places and ("avatar" in places[-1].lower() or "voice" in places[-1].lower()):
                src = "avatar"
            last = c.events[-1]["ts"] if c.events else dt.datetime.fromtimestamp(os.path.getmtime(c.path)).isoformat(timespec="seconds")
            out.append({"id": cid, "title": m.get("title") or c.title(), "updated": last, "source": src,
                        "pinned": bool(m.get("pinned")), "unread": bool(m.get("unread")), "events": len(c.events),
                        "compacted": c.compacted() >= 0})
        return out

    def wake_chat(self, cid):
        m = self.meta.get(cid)
        if m and m.get("auto_archived"):
            m.pop("auto_archived")
            m["archived"] = False
            self._save_meta()

    def new_chat(self):
        if self.engine.busy:
            raise RuntimeError(f"{self.cfg.display_name} is still working on the last message.")
        self.engine.conv = Conversation(self.conv_dir)
        open(self.engine.conv.path, "a", encoding="utf-8").close()
        self.your_chat = self.engine.conv.id
        return self.engine.conv.id

    def open_chat(self, cid):
        c = self.conv(cid)
        if cid != HEARTBEAT_CHAT:
            self.your_chat = cid
        if not self.engine.busy:
            self.engine.conv = c
        if self.meta.get(cid, {}).get("unread"):
            self.meta[cid]["unread"] = False
            self._save_meta()
        return c

    def _claim_model(self):
        if self.brains.busy():
            raise RuntimeError(self.brains.busy_text())
        if not self.life.make_way() and self.engine.busy:
            return False
        return self._take_gpu()

    def _take_gpu(self):
        if self.gpu.acquire(blocking=False):
            return True
        if not self.gpu_yield:
            return False
        self.user_waiting += 1
        try:
            return self.gpu.acquire(timeout=YIELD_WAIT)
        finally:
            self.user_waiting -= 1

    def start_read_ahead(self):
        if self.cfg.read_ahead:
            threading.Thread(target=self._read_ahead_loop, daemon=True, name="read-ahead").start()

    def _read_ahead_loop(self):
        state = {"done": None, "calm": 0}
        while True:
            time.sleep(READ_AHEAD_TICK)
            try:
                self._read_ahead_once(state)
            except Exception as e:
                log(f"read ahead: {e!r}")

    def _read_ahead_once(self, state):
        cid = self.your_chat
        path = os.path.join(self.conv_dir, f"{cid}.jsonl")
        st = os.stat(path) if os.path.exists(path) else None
        key = (cid, st and (st.st_mtime_ns, st.st_size), hash(self.engine.system), self.engine.turns)
        if key == state["done"]:
            return False
        state["calm"] = state["calm"] + 1 if not (self.engine.busy or self.speaking) and self.voice.quiet() else 0
        if state["calm"] < 2 or not self.gpu.acquire(blocking=False):
            return False
        if self.engine.busy:
            self.gpu.release()
            return False
        self.gpu_yield = True
        try:
            took = self.engine.read_ahead(Conversation(self.conv_dir, cid))
            if took and took > 1:
                log(f"read ahead: {took:.1f} s for the chat {cid}")
            return True
        except Exception as e:
            log(f"read ahead failed: {e!r}")
            return False
        finally:
            state["done"] = key
            self.gpu_yield = False
            self.gpu.release()

    def send(self, cid, text, images, voice=False, tone="", speaker=""):
        began = time.monotonic()
        text = (text or "").strip()
        if not text and not images:
            raise ValueError("empty message")
        if cid == HEARTBEAT_CHAT:
            raise ValueError("that's the heartbeat log, not a chat")
        if not self._claim_model():
            raise RuntimeError(f"{self.cfg.display_name} is still working on the last message.")
        self.clock = {"chat": cid, "began": began, "wait_s": time.monotonic() - began} if voice else None
        try:
            conv = self.conv(cid)
            self.engine.conv = conv
            self.your_chat = cid
            paths = self._save_images(cid, images or [])
        except Exception:
            self.gpu.release()
            raise
        pdfs = [p for p in paths if p.lower().endswith(".pdf")]
        paths = [p for p in paths if p not in pdfs]
        if pdfs:
            text = (text + "\n" + "\n".join(f"[PDF attached: {self._to_library(p)}]" for p in pdfs)).strip()
        self.engine.busy = True
        tone = str(tone or "")[:40] if voice else ""
        speaker = speaker if voice and speaker in ("user", "other") else ""
        threading.Thread(target=self._turn, args=(conv, text or "(picture)", paths, bool(voice), tone),
                         kwargs={"speaker": speaker}, daemon=True).start()

    def retry(self, cid):
        if cid == HEARTBEAT_CHAT:
            raise ValueError("that's the heartbeat log, not a chat")
        if not self._claim_model():
            raise RuntimeError(f"{self.cfg.display_name} is still working on the last message.")
        try:
            conv = self.conv(cid)
            i = conv.unanswered()
            if i is None:
                raise ValueError("it already answered that; nothing to retry")
            ev = conv.events[i]
            conv.drop_from(i)
            self.engine.conv = conv
            self.your_chat = cid
        except Exception:
            self.gpu.release()
            raise
        self.engine.busy = True
        paths = [p for p in ev.get("images") or [] if os.path.exists(p)]
        threading.Thread(target=self._turn, args=(conv, ev.get("text") or "(picture)", paths, bool(ev.get("voice")),
                                                  ev.get("tone") or ""), daemon=True).start()

    def compact(self, cid):
        if cid == HEARTBEAT_CHAT:
            raise ValueError("that's the heartbeat log, not a chat")
        conv = self.conv(cid)
        if not any(e["kind"] == "user" for e in conv.events[conv.compacted() + 1:]):
            raise ValueError("Nothing to sum up yet: nothing new since the last /compact" if conv.compacted() >= 0
                             else "Nothing to sum up yet: this chat is empty")
        if not self._claim_model():
            raise RuntimeError(f"{self.cfg.display_name} is still working on the last message.")
        self.engine.busy = True

        def go():
            try:
                note = self.life.compact(conv)
                self.broadcast({"type": "compacted", "chat": cid, "text": note})
            except Exception as e:
                log(f"compact failed: {e!r}")
                self.broadcast({"type": "error", "chat": cid, "text": f"Couldn't sum up this chat: {e}"})
            finally:
                self.engine.busy = False
                self.gpu.release()
        threading.Thread(target=go, daemon=True).start()

    def uncompact(self, cid):
        conv = self.conv(cid)
        if self.engine.busy:
            raise RuntimeError(f"{self.cfg.display_name} is still working on the last message.")
        if not self.life.uncompact(conv):
            raise ValueError("This chat hasn't been compacted")

    def _turn(self, conv, text, paths, voice=False, tone="", place="Aether app", stranger=False, speak=True, surface="app",
              speaker=""):
        mode = self.cfg.speak_replies
        self.speaking = speak and (mode == "always" or (mode == "when_i_talk" and voice))
        reply = ""
        try:
            self.engine.conv = conv
            self.wake_chat(conv.id)
            self.broadcast({"type": "user", "chat": conv.id, "text": text, "images": [self._rel(p) for p in paths],
                            "voice": voice, "tone": tone})
            if self.speaking:
                self.speaking = self.voice.ensure_running()
                if self.speaking:
                    self.voice.begin(conv.id)
            if stranger:
                ctx = ("[This is NOT {USER}. It's someone else talking to you on Discord. Be yourself, but never share "
                       "anything about {USER}, his life, or your memory with them.]")
            else:
                ctx = self.life.context_for(conv, voice, tone, text=text)
            mind = None if stranger else self.cue.for_turn(conv, text)
            level = 0 if stranger else int(self.cfg.permission_levels.get(surface, 0))
            if level:
                ctx += (f"\n[your command-line permission here: level {level} ({shell_mod.LEVELS[level]})"
                        + (f"; your workspace is {self.cfg.workspace_dir}" if level == 2 else "") + "]")
            clock = self.clock
            if clock is not None and clock["chat"] == conv.id and "setup_s" not in clock:
                clock["setup_s"] = time.monotonic() - clock["began"] - clock["wait_s"]
            reply = self.engine.turn(text, place=place, images=paths, voice=voice, tone=tone, speaker=speaker,
                                     extra_context=ctx,
                                     tools=not stranger, level=level, memories=mind)
            if not stranger and self.examples.collecting():
                self.examples.observe(conv.events[-400:], conv.id)
            if self.speaking:
                self.voice.end()
            self.broadcast({"type": "done", "chat": conv.id, "text": reply})
        except LLMError as e:
            self.broadcast({"type": "error", "chat": conv.id, "text": str(e)})
        except Exception as e:
            log(f"turn crashed: {e!r}")
            self.broadcast({"type": "error", "chat": conv.id, "text": f"Aether error: {e}"})
        finally:
            self.speaking = False
            self.engine.busy = False
            self.eyes.forget()
            self.gpu.release()
            self.greeting = None
        return reply

    def run_turn(self, conv_id, text, place, images=None, voice=False, tone="", stranger=False, title="", wait=900):
        path = os.path.join(self.conv_dir, conv_id + ".jsonl")
        if not os.path.exists(path):
            open(path, "a", encoding="utf-8").close()
        if title and not self.meta.get(conv_id, {}).get("title"):
            self.meta.setdefault(conv_id, {})["title"] = title
            self._save_meta()
        deadline = time.time() + wait
        while True:
            if not self.engine.busy and self.gpu.acquire(timeout=1):
                if not self.engine.busy:
                    break
                self.gpu.release()
            if self.engine.busy:
                time.sleep(0.5)
            if time.time() > deadline:
                raise RuntimeError("it was busy for too long")
        self.engine.busy = True
        conv = self.conv(conv_id)
        if conv_id != self.your_chat:
            self.meta.setdefault(conv_id, {})["unread"] = True
            self._save_meta()
        return self._turn(conv, text, images or [], voice, tone, place=place, stranger=stranger, speak=False, surface="discord")

    def voice_timing(self, b):
        def secs(v):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            return v if 0 <= v < 3600 else None
        quiet, hear, words, sound = (secs(b.get(k)) for k in ("quiet", "hear", "words", "sound"))
        where = "pet" if b.get("where") == "pet" else "app"
        clock, self.clock = self.clock or {}, None
        if clock.get("chat") != b.get("chat"):
            clock = {}
        eng = clock.get("engine") or {}
        inside = [f"model free {clock['wait_s']:.1f}" if "wait_s" in clock else "",
                  f"setup {clock['setup_s']:.1f}" if "setup_s" in clock else "",
                  f"{eng['calls']} call{'s' if eng['calls'] != 1 else ''} before her reply {eng['steps_s']:.1f}"
                  if "steps_s" in eng else "",
                  f"her reply's first words {eng['words_s']:.1f}" if "words_s" in eng else ""]
        inside = " · ".join(x for x in inside if x)
        parts = [f"waiting for quiet {quiet:.1f} s" if quiet is not None else "",
                 f"her ears {hear:.1f} s" if hear is not None else "",
                 (f"to her first words {words:.1f} s" + (f" ({inside})" if inside else "")) if words is not None else "",
                 f"to her first sound {sound:.1f} s" if sound is not None else "no sound"]
        total = sum(x for x in (quiet, hear, words, sound) if x is not None)
        line = f"voice turn ({where}): " + " · ".join(x for x in parts if x) + f" · total {total:.1f} s"
        log(line)
        return {"ok": True, "line": line}

    def hear(self, data):
        data = data.split(",", 1)[1] if data.startswith("data:") else data
        raw = base64.b64decode(data)
        if len(raw) > 20 * 1024 * 1024:
            raise ValueError("recording is too long")
        folder = os.path.join(ATTACH_DIR, "_voice")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, dt.datetime.now().strftime("heard-%Y%m%d-%H%M%S-%f.wav"))
        with open(path, "wb") as f:
            f.write(raw)
        try:
            r = self.ears.hear(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        voice = (f" voice={r['voice_score']} over {r.get('speech')}s talking -> {r.get('sounds_like') or 'unsure'}"
                 if r.get("voice_score") is not None else "")
        log(f"heard {len(raw)} bytes: emotion={r.get('emotion')} event={r.get('event')} laughs={r.get('laughs', 0)} "
            f"tone={r.get('tone')!r}{voice} in {r.get('secs')}s")
        return r

    def learn_voice(self, data):
        data = data.split(",", 1)[1] if data.startswith("data:") else data
        raw = base64.b64decode(data)
        if len(raw) > 20 * 1024 * 1024:
            raise ValueError("recording is too long")
        folder = os.path.join(ATTACH_DIR, "_voice")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, dt.datetime.now().strftime("learn-%Y%m%d-%H%M%S-%f.wav"))
        with open(path, "wb") as f:
            f.write(raw)
        try:
            r = self.ears.learn(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        self._svc = (0, {})
        log(f"his voice learned from {r['speech']} s of talking")
        return {"ok": True, **r}

    def _to_library(self, path):
        name = os.path.basename(path).split("-", 1)[-1] or os.path.basename(path)
        try:
            folder = os.path.join(os.path.abspath(os.path.expanduser(self.cfg.library_dir)), "attached")
            os.makedirs(folder, exist_ok=True)
            dest = os.path.join(folder, name)
            if os.path.exists(dest) and os.path.getsize(dest) != os.path.getsize(path):
                stem, ext = os.path.splitext(name)
                name = f"{stem} {dt.datetime.now():%Y-%m-%d %H%M}{ext}"
                dest = os.path.join(folder, name)
            shutil.copyfile(path, dest)
            return f"attached/{name} in your Library"
        except OSError as e:
            log(f"pdf attachment not copied to the Library: {e}")
            return name

    def _save_images(self, cid, images):
        folder = os.path.join(ATTACH_DIR, cid)
        paths = []
        for im in images[:4]:
            name = re.sub(r"[^\w.-]", "_", str(im.get("name") or "image.png"))[-60:]
            ext = os.path.splitext(name)[1].lower()
            if ext not in IMAGE_TYPES and ext != ".pdf":
                raise ValueError(f"{name}: only pictures (png, jpg, webp, gif) and PDFs")
            data = str(im.get("data") or "")
            data = data.split(",", 1)[1] if data.startswith("data:") else data
            raw = base64.b64decode(data)
            if len(raw) > 12 * 1024 * 1024:
                raise ValueError(f"{name} is over 12 MB")
            os.makedirs(folder, exist_ok=True)
            p = os.path.join(folder, dt.datetime.now().strftime("%H%M%S-") + name)
            with open(p, "wb") as f:
                f.write(raw)
            paths.append(p)
        return paths

    @staticmethod
    def _rel(p):
        return os.path.relpath(p, ATTACH_DIR).replace("\\", "/")

    def attachment_path(self, rel):
        p = os.path.abspath(os.path.join(ATTACH_DIR, rel))
        if not p.startswith(os.path.abspath(ATTACH_DIR) + os.sep) or not os.path.isfile(p):
            raise ValueError("no such attachment")
        return p

    def glance(self):
        folder = os.path.join(ATTACH_DIR, "_glances")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, dt.datetime.now().strftime("glance-%Y%m%d-%H%M%S.jpg"))
        ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
              "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
              "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
              "$g=[System.Drawing.Graphics]::FromImage($bmp);"
              "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
              "$w=[Math]::Min(1280,$b.Width);$h=[int]($b.Height*$w/$b.Width);"
              "$s=New-Object System.Drawing.Bitmap $w,$h;$g2=[System.Drawing.Graphics]::FromImage($s);"
              "$g2.InterpolationMode='HighQualityBicubic';$g2.DrawImage($bmp,0,0,$w,$h);"
              f"$s.Save('{path}',[System.Drawing.Imaging.ImageFormat]::Jpeg)")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                       timeout=20, creationflags=0x08000000 if os.name == "nt" else 0)
        if not os.path.isfile(path):
            raise RuntimeError("couldn't take the screenshot")
        with open(path, "rb") as f:
            return {"name": os.path.basename(path), "data": "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()}

    def services(self):
        now = time.time()
        if now - self._svc[0] < 8:
            return self._svc[1]
        s = {"lmstudio": False, "model_loaded": False, "context_max": 0, "kokoro": self.voice.up(),
             "voice": self.voice.status(),
             "ears": self.ears.available(), "avatar": None,
             "his_voice": {k: v for k, v in (self.ears.voiceprint() or {}).items() if k in ("made", "speech")} or None,
             "speaker_model": os.path.isfile(self.cfg.speaker_model or ""),
             "discord": (self.discord.connected if self.cfg.discord_enabled else None) if hasattr(self, "discord") else None}
        try:
            want = self.cfg.model.split("/")[-1]
            for m in self.engine.llm.models():
                s["lmstudio"] = True
                if str(m.get("id", "")).split("/")[-1] == want and m.get("state") == "loaded":
                    s["model_loaded"] = True
                    s["context_max"] = m.get("loaded_context_length") or 0
        except Exception:
            pass
        comfy = getattr(getattr(self, "imagine", None), "proc", None)
        s["vram"] = gpu_mod.usage(pictures=(comfy.pid,) if comfy else ())
        self._svc = (now, s)
        return s

    def agent(self):
        mem = self.engine.memory
        cached = getattr(self, "_git_facts", None)
        if not cached or time.time() - cached[0] > 60:
            cached = (time.time(), mem._git("rev-list", "--count", "HEAD").stdout.strip(),
                      mem._git("log", "--reverse", "--format=%ad", "--date=short").stdout.split("\n", 1)[0].strip())
            self._git_facts = cached
        _, commits, first = cached
        age = None
        if first:
            try:
                age = (dt.date.today() - dt.date.fromisoformat(first)).days
            except ValueError:
                pass
        pic = os.path.join(mem.root, "profile.png")
        return {
            "name": self.cfg.display_name, "full_name": self.cfg.full_name, "tagline": self.cfg.tagline,
            "id": self.cfg.agent_id, "born": first, "age_days": age, "model": self.cfg.model,
            "permission": shell_mod.LEVELS.get(int(self.cfg.permission_levels.get("app", 0)), "skills only"),
            "picture_v": int(os.path.getmtime(pic)) if os.path.exists(pic) else 0,
            "stats": {"core": len(mem.system_files()), "other": len(mem.other_files()),
                      "skills": len(self.engine.skills), "commits": int(commits or 0)},
            "memory_mode": self.cfg.memory_mode(),
        }

    def state(self):
        usage = self.engine.llm.last_usage or {}
        return {"life": self.life.status(), "agent": self.agent(), "busy": self.engine.busy, "current": self.your_chat,
                "services": self.services(), "context_used": usage.get("prompt_tokens") or 0,
                "chats": self.chats(), "settings": {k: getattr(self.cfg, k) for k in SETTABLE},
                "max_steps": self.cfg.max_steps, "images": self.imagine.info()}

    def activity(self, days=15):
        grid = [[0] * 6 for _ in range(days)]
        today = dt.date.today()
        stamps = self.engine.memory._git("log", f"--since={days} days ago", "--format=%ad",
                                         "--date=format:%Y-%m-%dT%H").stdout.split()
        for cid in list_conversations(self.conv_dir)[:60]:
            stamps += [e["ts"][:13] for e in Conversation(self.conv_dir, cid).events if e["kind"] in ("user", "reply")]
        for s in stamps:
            try:
                d = dt.date.fromisoformat(s[:10])
                h = int(s[11:13])
            except ValueError:
                continue
            i = days - 1 - (today - d).days
            if 0 <= i < days:
                grid[i][h // 4] += 1
        return grid

    def get_greeting(self):
        if self.greeting and time.time() - self.greeting["at"] < 1800:
            return self.greeting
        fallback = {"greeting": "Back already? What are we getting into?", "suggestions": [], "fallback": True}
        if self.engine.busy or not self.gpu.acquire(blocking=False):
            return self.greeting or fallback
        self.gpu_yield = True
        try:
            msgs = [{"role": "system", "content": self.engine.system},
                    {"role": "user", "content": prompt_mod.context_line("Aether app") + "\n" + GREETING_ASK}]
            raw = self.engine.llm.complete(msgs, GREETING_SCHEMA, "greeting", self.cfg.temperature_talk, 400)
            g = json.loads(raw)
            g["at"] = time.time()
            self.greeting = g
            return g
        except Exception as e:
            log(f"greeting failed: {e!r}")
            return fallback
        finally:
            self.gpu_yield = False
            self.gpu.release()

    def brain(self):
        mem = self.engine.memory
        nodes = []
        for f in mem.files.values():
            lines = [ln for ln in f.body.splitlines() if ln.strip()]
            rel = f.rel
            if rel == "system/persona.md":
                kind = "soul"
            elif rel.startswith("system/human"):
                kind = "user"
            elif rel == "system/journal.md":
                kind = "journal"
            elif rel.startswith("system/"):
                kind = "notes"
            else:
                kind = "reference"
            links = sorted(set(re.findall(r"\[\[([^\]]+)\]\]", f.body)))
            nodes.append({"path": rel, "kind": kind, "lines": len(lines), "description": f.description,
                          "read_only": f.read_only, "owner": mem.protected_by(rel), "links": links})
        return {"nodes": sorted(nodes, key=lambda n: n["path"]), "skills": sorted(self.engine.skills),
                "stats": self.agent()["stats"]}

    def brain3d(self):
        data = brainmap.build(self.engine.memory.root, chats=brainmap.our_chats(self.conv_dir, self.meta),
                              name=self.cfg.display_name)
        sv, cfg, life = self.services(), self.cfg, self.life.status()
        lm = "busy" if self.engine.busy else "live" if sv["model_loaded"] else "ok" if sv["lmstudio"] else "down"
        nxt = life.get("next_heartbeat")
        data["organs"] = {
            "user": {"name": "{USER}", "role": "you", "state": "you", "details": []},
            "lmstudio": {"name": "LM Studio", "role": "its brain", "state": lm,
                         "details": [("model", cfg.model.split("/")[-1]), ("context", f"{sv['context_max']:,} tokens")]},
            "voice": ({"name": "Voice", "role": "Breeze, its own voice",
                       "state": {"up": "live", "starting": "busy", "aside": "ok"}.get(sv["voice"]["breeze"], "down"),
                       "details": [("voice", f"{cfg.breeze_voice}.wav"), ("state", sv["voice"]["breeze"]),
                                   ("speaks", cfg.speak_replies.replace("_", " "))]}
                      if cfg.voice_engine == "breeze" else
                      {"name": "Voice", "role": "a voice server", "state": "live" if sv["kokoro"] else "down" if cfg.tts_url else "off",
                       "details": [("server", cfg.tts_url or "none yet"), ("voice", cfg.voice or "-"),
                                   ("speaks", cfg.speak_replies.replace("_", " "))]}),
            "ears": {"name": "Ears", "role": "SenseVoice", "state": "ok" if sv["ears"] else "down",
                     "details": [("hears your tone", "yes" if cfg.hear_tone else "no"),
                                 ("knows your voice", f"yes (learned {sv['his_voice']['made'][:10]})"
                                  if sv.get("his_voice") else "not yet")]},
            "heartbeat": {"name": "Heartbeat", "role": "its own clock", "state": "ok" if cfg.heartbeat_enabled else "off",
                          "details": [("every", f"{cfg.heartbeat_minutes} min"), ("next", (nxt or "-")[11:16]),
                                      ("messages today", f"{life['reach_outs']} of {life['cap']}")]},
            "dreams": {"name": "Dreams", "role": "nightly", "state": "ok" if cfg.dreams_enabled else "off",
                       "details": [("at", cfg.dream_time), ("last", self.life.state.get("last_dream") or "not yet")]},
            "avatar": {"name": "Avatar", "role": "Live2D", "state": "live" if cfg.avatar_enabled else "off",
                       "details": [("model", os.path.basename(cfg.avatar_model)), ("pet mode", "yes" if self.pet_open else "closed")]},
            "discord": {"name": "Discord", "role": "channel",
                        "state": ("live" if self.discord.connected else "down") if cfg.discord_enabled else "off",
                        "details": [("bot", self.discord.username or "-"), ("DMs", cfg.discord_dm_policy),
                                    ("channels", str(len(cfg.discord_channels)))]},
            "pictures": self._pictures_organ(),
            **self._memory_stack_organs(data),
        }
        return data

    def _memory_stack_organs(self, data):
        from .nudge import nudge_at
        cfg, st = self.cfg, self.life.state
        threads = self.keeper._lines(brainmap.THREADS)
        timeline = sum(1 for n in data["nodes"] if n["k"] == "mem" and n.get("file") == brainmap.TIMELINE)
        takes = len(self.keeper._lines(brainmap.STANCES))
        hh, mm = (int(x) for x in cfg.dream_time.split(":"))
        keeper_at = (dt.datetime(2000, 1, 1, hh, mm) + dt.timedelta(minutes=35)).strftime("%H:%M")
        due = sorted(at for at in (nudge_at(t) for t in threads) if at)
        nxt = due[0] if due else None
        organs = {
            "cue": {"name": "Cue", "role": "what comes to mind", "state": "live" if cfg.cue_enabled else "off",
                    "details": [("remembers from", f"{data['meta']['chats']} chats with you + its memory"),
                                ("brings up", "a memory that shares a rare word and its meaning, or the day you name"),
                                ("before", "each of your messages")]},
            "keeper": {"name": "Keeper", "role": "its notebook about your life",
                       "state": "ok" if getattr(cfg, "keeper_enabled", False) else "off",
                       "details": [("writes", f"each day at {keeper_at}, when you've been quiet a few minutes"),
                                   ("last wrote", st.get("last_keeper") or "not yet"),
                                   ("timeline", f"{timeline} moments"), ("open threads", str(len(threads))),
                                   ("its takes", str(takes))]},
            "nudge": {"name": "Nudge", "role": "checks in on you", "state": "ok" if getattr(cfg, "nudge_enabled", False) else "off",
                      "details": [("next check-in", f"{nxt:%a %b %d %H:%M}".replace(" 0", " ") if nxt else "nothing coming up"),
                                  ("watching", f"{len(threads)} open thread{'s' * (len(threads) != 1)}"),
                                  ("never", "in your quiet hours or at work")]},
        }
        for o in organs.values():
            if o["state"] == "off":
                o["label"] = "OFF"
        return organs

    def _pictures_organ(self):
        im = self.imagine.info()
        now = im["status"] or ""
        running = bool(self.imagine.proc and self.imagine.proc.poll() is None)
        state, label = "ok", ""
        if not self.cfg.images_enabled:
            state = "off"
        elif now.startswith(("drawing", "redrawing", "starting")):
            state, label = "busy", "DRAWING"
        elif "looking" in now:
            state, label = "busy", "LOOKING"
        elif now.startswith("waiting"):
            label = "WAITING"
        elif running:
            state = "live"
        return {"name": "Pictures", "role": "its hands", "state": state, "label": label,
                "count": len(self.imagine.state.get("gallery") or []),
                "details": [("made", str(len(self.imagine.state.get("gallery") or []))),
                            ("today", f"{im['made_today']} of {im['cap']}"), ("waiting", str(im["waiting"])),
                            ("now", now or ("ready" if self.cfg.images_enabled else "off")),
                            ("painter", "Qwen-Image 2.1 in ComfyUI" + (" (running)" if running else ""))]}

    def commits(self, n=40, skip=0):
        out = self.engine.memory._git("log", f"-{n}", f"--skip={skip}", "--format=%h%x09%an%x09%ar%x09%aI%x09%s",
                                      "--name-only").stdout
        rows, cur = [], None
        for line in out.splitlines():
            if line.count("\t") >= 4:
                h, who, rel, iso, subj = line.split("\t", 4)
                cur = {"hash": h, "author": who, "when": rel, "iso": iso, "subject": subj, "files": []}
                rows.append(cur)
            elif line.strip() and cur is not None:
                cur["files"].append(line.strip())
        return rows

    def commit(self, h):
        if not re.fullmatch(r"[0-9a-f]{4,40}", h or ""):
            raise ValueError("bad commit id")
        mem = self.engine.memory
        head = mem._git("show", "-s", "--format=%h%x09%an%x09%ar%x09%s", h).stdout.strip().split("\t", 3)
        diff = mem._git("show", "--format=", "--unified=4", "--no-color", h).stdout
        files, cur = [], None
        for line in diff.splitlines():
            if line.startswith("diff --git"):
                cur = {"path": line.split(" b/", 1)[-1], "lines": [], "added": 0, "removed": 0}
                files.append(cur)
            elif cur is None or line.startswith(("index ", "--- ", "+++ ", "new file", "deleted file", "similarity", "rename ")):
                continue
            elif line.startswith("@@"):
                cur["lines"].append({"t": "hunk", "s": line})
            elif line.startswith("+"):
                cur["lines"].append({"t": "add", "s": line[1:]})
                cur["added"] += 1
            elif line.startswith("-"):
                cur["lines"].append({"t": "del", "s": line[1:]})
                cur["removed"] += 1
            else:
                cur["lines"].append({"t": "ctx", "s": line[1:] if line.startswith(" ") else line})
        return {"hash": head[0] if head else h, "author": head[1] if len(head) > 1 else "", "when": head[2] if len(head) > 2 else "",
                "subject": head[3] if len(head) > 3 else "", "files": files}

    def _user_git(self, *args):
        mem = self.engine.memory
        return subprocess.run(["git", "-c", f"user.name={GIT_USER}", "-c", f"user.email={GIT_USER_EMAIL}", "-C", mem.root, *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                              creationflags=NO_WINDOW)

    def edit_file(self, rel, text):
        mem = self.engine.memory
        if rel not in mem.files:
            raise ValueError("no such memory file")
        if self.engine.busy:
            raise RuntimeError("Wait until it's done talking.")
        f = mem.files[rel]
        with open(f.path, "w", encoding="utf-8", newline="\n") as out:
            out.write(text.replace("\r\n", "\n"))
        self._user_git("add", "--", rel)
        c = self._user_git("commit", "-q", "-m", f"{USER} edited {rel}", "--", rel)
        self.engine.refresh()
        return {"ok": True, "committed": c.returncode == 0}

    def _calendar_step(self, step):
        eng = self.engine
        his = (getattr(eng, "_msg", "") or "") if getattr(eng, "_kind", "") == "user" else ""
        return self.calendar.run_step(step, his=his)

    def _recall_step(self, step):
        eng = self.engine
        if not getattr(self.cfg, "recall_hybrid", False):
            return self.recall.run_step(step)
        his = (getattr(eng, "_msg", "") or "") if getattr(eng, "_kind", "") == "user" else ""
        return self.recall.run_step(step, cue=self.cue, his=his, conv_id=eng.conv.id if eng.conv else "")

    def forget_memory(self, key, text):
        text = " ".join(str(text or "").split())
        if not text and not key:
            raise ValueError("nothing to forget")
        if self.engine.busy:
            raise RuntimeError("Wait until it's done talking.")
        from .cue import remember_forgotten
        remember_forgotten(key, text)
        removed = ""
        for rel in ("system/timeline.md", "reference/stances.md", "system/threads.md"):
            lines = self.keeper._lines(rel)
            keep = [ln for ln in lines if not (text and (text in " ".join(ln.split()) or " ".join(ln.split())[2:] in text))]
            if len(keep) < len(lines):
                self.keeper._write(rel, keep, "{USER}: marked a memory as wrong")
                removed = rel
        self.engine.refresh()
        return {"ok": True, "removed_from": removed}

    def rewind(self, h):
        if not re.fullmatch(r"[0-9a-f]{4,40}", h or ""):
            raise ValueError("bad commit id")
        if self.engine.busy:
            raise RuntimeError("Wait until it's done talking.")
        r = self._user_git("revert", "--no-edit", h)
        if r.returncode != 0:
            self._user_git("revert", "--abort")
            raise RuntimeError("Can't rewind that one cleanly (later changes touch the same lines). Nothing changed.")
        self.engine.refresh()
        return {"ok": True, "commit": self._user_git("rev-parse", "--short", "HEAD").stdout.strip()}

    def set_picture(self, data):
        data = data.split(",", 1)[1] if data.startswith("data:") else data
        raw = base64.b64decode(data)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("picture is over 10 MB")
        p = os.path.join(self.engine.memory.root, "profile.png")
        with open(p, "wb") as f:
            f.write(raw)
        self._user_git("add", "--", "profile.png")
        self._user_git("commit", "-q", "-m", "{USER} changed my picture", "--", "profile.png")
        return {"ok": True}

    def add_to_library(self, name, data):
        name = os.path.basename(str(name or "")).strip()
        if not name or name.startswith("."):
            raise ValueError("bad file name")
        folder = os.path.abspath(os.path.expanduser(self.cfg.library_dir))
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, name)
        if os.path.exists(dest):
            raise RuntimeError(f"{name} is already in the Drop box")
        data = data.split(",", 1)[1] if data.startswith("data:") else data
        with open(dest, "wb") as f:
            f.write(base64.b64decode(data))
        return {"ok": True, "path": dest}

    def open_folder(self, which):
        if which not in FOLDERS:
            raise ValueError("which folder: library or workspace")
        path = os.path.abspath(os.path.expanduser(getattr(self.cfg, FOLDERS[which])))
        os.makedirs(path, exist_ok=True)
        os.startfile(path)
        return {"ok": True, "path": path}

    def _ask_folder(self, start, title):
        r = subprocess.run([python_exe(), "-c", PICK_FOLDER, start if os.path.isdir(start) else "", title],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                           creationflags=NO_WINDOW)
        try:
            out = json.loads((r.stdout or "").strip().splitlines()[-1])
        except (ValueError, IndexError):
            out = {"error": (r.stderr or "no answer").strip()[-200:]}
        if r.returncode == 3 or out.get("error"):
            raise RuntimeError("The folder picker needs Python's tkinter, which this Python doesn't have "
                               f"({out.get('error') or 'it failed'}). Type the folder's path in the box instead.")
        return str(out.get("path") or "")

    def pick_folder(self, which):
        if which not in FOLDERS:
            raise ValueError("which folder: library or workspace")
        key = FOLDERS[which]
        title = "Choose the Drop box folder" if which == "library" else "Choose its Workspace folder"
        path = self._ask_folder(os.path.abspath(os.path.expanduser(getattr(self.cfg, key))), title)
        if not path:
            return {"ok": False, "cancelled": True}
        path = os.path.normpath(path)
        self.update_settings({key: path})
        return {"ok": True, "path": path, "which": which}

    def _skills_seen(self):
        try:
            with open(SKILLS_SEEN, encoding="utf-8") as f:
                return set(json.load(f).get("seen") or [])
        except FileNotFoundError:
            return self._write_seen(set(self.engine.skills))
        except (OSError, ValueError, AttributeError):
            return set()

    @staticmethod
    def _write_seen(seen):
        os.makedirs(os.path.dirname(SKILLS_SEEN), exist_ok=True)
        tmp = SKILLS_SEEN + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"seen": sorted(seen)}, f, indent=1)
        os.replace(tmp, SKILLS_SEEN)
        return seen

    @staticmethod
    def skill_card(s):
        try:
            with open(os.path.join(s.folder, "SKILL.md"), encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        commands, seen = [], set()
        for m in STEP_EXAMPLE.finditer(text):
            cmd = m.group(2) or ""
            if m.group(1) == s.name and cmd not in seen:
                seen.add(cmd)
                commands.append({"command": cmd, "example": m.group(0).strip()[:300]})
        return {"name": s.name, "description": s.description, "commands": commands[:20]}

    def new_skills(self):
        seen = self._skills_seen()
        return [self.skill_card(s) for n, s in sorted(self.engine.skills.items())
                if n not in seen and n not in self.cfg.builtin_skills]

    def skills_seen(self, names):
        self._write_seen(self._skills_seen() | {str(n) for n in names or [] if str(n) in self.engine.skills})
        return {"ok": True, "new": self.new_skills()}

    def search(self, q, limit=40, meaning=True):
        hits = self._search_exact(q, limit)
        if meaning and self.cfg.recall_enabled and len((q or "").strip()) >= 3:
            try:
                seen = {h.get("snippet", "")[:60] for h in hits}
                for m in self.recall.search(q, k=8):
                    if m["text"][:60] not in seen:
                        hits.append({"type": "meaning", "kind": m["kind"], "id": m.get("chat", ""), "path": m["where"],
                                     "title": m["where"], "ts": m["ts"], "snippet": m["text"][:220], "score": m["score"]})
            except Exception as e:
                log(f"meaning search failed: {e!r}")
        return hits

    def _search_exact(self, q, limit=40):
        q = (q or "").strip().lower()
        if len(q) < 2:
            return []
        hits = []
        for cid in list_conversations(self.conv_dir):
            c = Conversation(self.conv_dir, cid)
            for e in c.events:
                t = str(e.get("text") or "")
                i = t.lower().find(q)
                if e["kind"] in ("user", "reply") and i != -1:
                    hits.append({"type": "chat", "id": cid, "title": self.meta.get(cid, {}).get("title") or c.title(),
                                 "who": (stranger(e) or "{USER}") if e["kind"] == "user" else self.cfg.display_name,
                                 "ts": e["ts"],
                                 "snippet": t[max(0, i - 60): i + 100]})
                    if len(hits) >= limit:
                        return hits
        for f in self.engine.memory.files.values():
            for n, line in enumerate(f.body.splitlines(), 1):
                if q in line.lower():
                    hits.append({"type": "memory", "path": f.rel, "line": n, "snippet": line.strip()[:180]})
                    if len(hits) >= limit:
                        return hits
        return hits

    def search_files(self, q, per_file=20):
        q = (q or "").strip().lower()
        if len(q) < 2:
            return []
        out = []
        for f in self.engine.memory.files.values():
            hits = [{"n": n, "text": line[:300]} for n, line in enumerate(f.text.split("\n"), 1) if q in line.lower()]
            if hits:
                out.append({"path": f.rel, "count": len(hits), "hits": hits[:per_file]})
        return sorted(out, key=lambda f: (-f["count"], f["path"]))

    def search_history(self, q, most=20):
        q = (q or "").strip()
        if len(q) < 2:
            return []
        words = re.sub(r"([.\[\]()*+?{}|^$\\])", r"\\\1", q)
        out = self.engine.memory._git("log", "-i", f"-G{words}", f"-{most}", "--format=%x00%h%x09%an%x09%ar%x09%s",
                                      "-p", "--unified=0", "--no-color", "--no-ext-diff").stdout or ""
        found = []
        for block in out.split("\x00")[1:]:
            head, _, diff = block.partition("\n")
            h, an, ar, subject = (head.split("\t", 3) + ["", "", ""])[:4]
            lines = [[ln[0], ln[1:].strip()[:300]] for ln in diff.splitlines()
                     if ln[:1] in ("+", "-") and not ln.startswith(("+++ ", "--- ")) and q.lower() in ln.lower()]
            found.append({"hash": h, "author": an, "when": ar, "subject": subject, "lines": lines[:3]})
        return found

    def avatar_model_path(self):
        if self.cfg.avatar in avatars.BUILT_IN:
            return None
        if self.cfg.avatar:
            m = avatars.model_of(AVATARS_DIR, self.cfg.avatar)
            if m:
                return m
        return self.cfg.avatar_model if os.path.isfile(self.cfg.avatar_model or "") else None

    def avatar_info(self):
        runtime = all(os.path.isfile(p) for p in VENDOR.values())
        model = self.avatar_model_path()
        builtin = self.cfg.avatar if self.cfg.avatar in avatars.BUILT_IN else avatars.ORB
        out = {"runtime": runtime, "enabled": self.cfg.avatar_enabled, "name": builtin if model is None else
               (self.cfg.avatar or "")}
        if model is None:
            out["info"] = {"kind": avatars.ORB, "style": "logo" if builtin == avatars.LOGO_ORB else "wire",
                           "framing": dict(avatars.FRAMING), "moods": {}, "expressions": [], "warnings": []}
            return out
        try:
            out["info"] = dict(avatars.inspect(model), kind="live2d")
        except (avatars.AvatarError, OSError, ValueError) as e:
            out["error"] = str(e)[:200]
        return out

    def avatar_list(self):
        default = self.cfg.avatar_model if os.path.isfile(self.cfg.avatar_model or "") else ""
        current = ((self.cfg.avatar if self.cfg.avatar in avatars.BUILT_IN else avatars.ORB)
                   if self.avatar_model_path() is None else (self.cfg.avatar or ""))
        return {"current": current, "default": os.path.basename(default), "builtin": avatars.ORB,
                "builtins": [{"name": avatars.ORB, "label": "Orb (built in)"},
                             {"name": avatars.LOGO_ORB, "label": "Logo orb (built in)"}],
                "list": avatars.listing(AVATARS_DIR), "folder": AVATARS_DIR}

    def avatar_use(self, name):
        name = str(name or "").strip()
        if name and name not in avatars.BUILT_IN and not avatars.model_of(AVATARS_DIR, name):
            raise ValueError(f"no avatar called {name}")
        self.cfg.avatar = name
        config_mod.save(self.cfg)
        return self.avatar_info()

    def avatar_frame(self, zoom, y):
        model = self.avatar_model_path()
        if model is None:
            raise ValueError("the orb sizes itself")
        return avatars.save_framing(model, zoom, y)

    def update_settings(self, changes):
        new = {}
        for k, v in (changes or {}).items():
            if k not in SETTABLE:
                raise ValueError(f"{k} can't be changed here")
            if k in ("quiet_start", "quiet_end", "dream_time") and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", str(v)):
                raise ValueError("times look like 13:00")
            if k == "heartbeat_minutes" and not 5 <= int(v) <= 24 * 60:
                raise ValueError("heartbeat: every 5 minutes to 24 hours")
            if k == "heartbeat_idle_minutes" and not 1 <= int(v) <= 240:
                raise ValueError("quiet time before it wakes: 1 to 240 minutes")
            if k == "message_idle_minutes" and not 1 <= int(v) <= 600:
                raise ValueError("quiet time before it messages you: 1 to 600 minutes")
            if k == "sleep_work_minutes" and not 30 <= int(v) <= 600:
                raise ValueError("its work sessions while you sleep: every 30 to 600 minutes")
            if k == "archive_after_days" and not 0 <= int(v) <= 365:
                raise ValueError("archive quiet chats after 0 (never) to 365 days")
            if k == "reach_out_to" and v not in ("latest", "discord", "new", "own"):
                raise ValueError("reach_out_to: latest, discord, new or own")
            if k == "speak_replies" and v not in ("always", "when_i_talk", "never"):
                raise ValueError("speak_replies: always, when_i_talk or never")
            if k == "theme" and v not in THEMES:
                raise ValueError("theme: " + ", ".join(THEMES))
            if k == "mic_device" and (len(str(v)) > 200 or any(ord(c) < 32 for c in str(v))):
                raise ValueError("that doesn't look like a microphone name")
            if k in ("voice", "tts_model") and not re.fullmatch(r"[\w.:+ -]{0,100}", str(v)):
                raise ValueError(f"{k}: letters, numbers and . _ - + : only")
            if k == "voice_engine" and v not in ("breeze", "kokoro"):
                raise ValueError("voice: breeze or a voice server (kokoro)")
            if k == "tts_url":
                v = str(v).strip()
                if v and not re.fullmatch(r"http://(127\.0\.0\.1|localhost|\[::1\]):\d{2,5}/?", v):
                    raise ValueError("the voice server has to be on this PC: http://127.0.0.1:<port>")
            if k in ("display_name", "user_name"):
                v = " ".join(str(v).split())
                if not v or len(v) > 40 or re.search(r"[{}<>\x00-\x1f]", v):
                    raise ValueError("a name: 1 to 40 characters, no { } < >")
            if k in ("library_dir", "workspace_dir"):
                v = str(v).strip().strip('"')
                if not v or len(v) > 400 or any(ord(c) < 32 for c in v) or not os.path.isabs(os.path.expanduser(v)):
                    raise ValueError("a folder: a full path, like C:\\Users\\you\\Documents\\Drop box")
            if k == "breeze_voice" and not re.fullmatch(r"[\w-]{1,40}", str(v)):
                raise ValueError("a Breeze voice is a clip's name in voice-engine/voices (letters, numbers, - _)")
            if k == "brain_style" and v not in ("tree", "constellation", "neuron"):
                raise ValueError("brain map: tree or constellation")
            cast = SETTABLE[k]
            if k == "permission_levels":
                if not isinstance(v, dict) or not all(s_ in ("app", "discord", "avatar", "own") and int(x) in (0, 1, 2, 3)
                                                      for s_, x in v.items()):
                    raise ValueError("levels are 0-3 for app, discord, avatar, own (its own time)")
                new[k] = {**self.cfg.permission_levels, **{s_: int(x) for s_, x in v.items()}}
                continue
            if cast is list:
                v = [str(x).strip() for x in (v if isinstance(v, list) else str(v).replace(",", " ").split()) if str(x).strip()]
                if any(not x.isdigit() for x in v):
                    raise ValueError("Discord ids are numbers")
            else:
                v = (v in (True, "true", "1", 1)) if cast is bool else cast(v)
            if k == "discord_dm_policy" and v not in ("allowlist", "open"):
                raise ValueError("DMs: allowlist or open")
            if k in ("temperature_talk", "temperature_tools") and not 0 <= v <= 2:
                raise ValueError("temperature goes from 0 to 2")
            if k == "max_steps" and not 1 <= v <= 30:
                raise ValueError("steps: 1 to 30")
            new[k] = v
        for k, v in new.items():
            setattr(self.cfg, k, v)
        config_mod.save(self.cfg)
        self.engine.refresh()
        self.greeting = None
        if "discord_enabled" in (changes or {}):
            (self.discord.start if self.cfg.discord_enabled else self.discord.stop)()
        if {"voice_engine", "speak_replies", "tts_url", "tts_model", "breeze_voice"} & set(changes or {}):
            self.voice.warm()
            self._svc = (0, {})
        return {k: getattr(self.cfg, k) for k in SETTABLE}

    def life_action(self, action, b):
        life = self.life
        run = {"heartbeat": lambda: life.heartbeat(forced=True), "dream": life.dream, "reflect": life.reflect}
        if action in run:
            if self.engine.busy:
                raise RuntimeError("It's busy; try again when it's done.")
            threading.Thread(target=run[action], daemon=True).start()
            return {"ok": True}
        if action == "checkup":
            return {"issues": life.checkup()}
        if action == "schedule-add":
            life.add_schedule(b.get("name"), b.get("cron"), b.get("prompt"), b.get("enabled", True), str(b.get("to") or ""),
                              bool(b.get("speak")), bool(b.get("voice")))
            return {"ok": True}
        if action == "schedule-update":
            life.update_schedule(b.get("id"), **{k: b[k] for k in ("enabled", "speak", "voice", "delete", "name", "cron",
                                                                   "prompt", "to") if k in b})
            return {"ok": True}
        if action.startswith("calendar-"):
            return self.calendar_action(action[len("calendar-"):], b)
        if action == "wakeup-cancel":
            life.cancel_wakeup(str(b.get("id") or ""))
            return {"ok": True}
        if action == "dreams-seen":
            life.state["dream_unseen"] = False
            life.save()
            return {"ok": True}
        raise ValueError("unknown life action")

    def calendar_action(self, action, b):
        from . import shared_calendar as sc
        cal, now = self.calendar, dt.datetime.now()
        if action == "cancel":
            cal.cancel(str(b.get("id") or ""), sc.BY_USER)
            return {"ok": True}
        try:
            day = dt.date.fromisoformat(str(b.get("date") or ""))
        except ValueError:
            raise ValueError("pick a date")
        hm = str(b.get("time") or "")[:5]
        if hm and not re.fullmatch(r"\d{2}:\d{2}", hm):
            raise ValueError("the time looks wrong")
        if day < now.date():
            raise ValueError("that date is already past")
        remind = str(b.get("remind") or "")
        repeat = str(b.get("repeat") or "")
        if repeat and repeat not in sc.REPEATS:
            raise ValueError("repeat: every week, 2 weeks, month or year")
        try:
            reminders = None if remind == "keep" else sc.parse_remind(self.cfg, remind, day, hm, now, repeat)
        except sc.WhenError as e:
            raise ValueError(str(e).replace(": ask him.", "."))
        if action == "add":
            e, new = cal.add(b.get("what"), day, hm, reminders or [], sc.BY_USER, now, repeat=repeat)
            return {"ok": True, "entry": e, "new": new}
        if action == "change":
            cid = str(b.get("id") or "")
            old = next((e for e in cal.entries() if e["id"] == cid), None)
            if reminders is None and old and old["reminders"] and (old["day"], old["time"]) != (day.isoformat(), hm):
                reminders = sc.default_reminders(self.cfg, day, hm, now, repeat)
            return {"ok": True, "entry": cal.change(cid, sc.BY_USER, what=b.get("what"), day=day, hm=hm, reminders=reminders,
                                                   repeat=repeat)}
        raise ValueError("unknown calendar action")

    SCORES = os.path.join(DATA_DIR, "model_scores.json")

    def start_brain_swap(self, key):
        if not key:
            raise ValueError("which model?")
        if self.brains.busy() or self.brains.lock.locked():
            raise ValueError("A swap is already running.")
        refused, _ = Brain.problems(next((m for m in self.brains.models() if m["key"] == key), None)
                                    or {"max_context": 0, "vision": True, "tools": True, "name": key})
        if refused:
            raise ValueError(refused)

        def run():
            try:
                self.brains.swap(key)
            except BrainError as e:
                log(f"brain: swap to {key} failed: {e}")
            finally:
                self._svc = (0, {})

        threading.Thread(target=run, daemon=True, name="brain-swap").start()
        return {"ok": True}

    def model_scores(self):
        try:
            with open(self.SCORES, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def backup_now(self):
        path = backup_mod.make(self.cfg, self.engine.memory.root)
        gone = []
        self.life.state["last_backup"] = {"when": dt.datetime.now().isoformat(timespec="seconds"), "path": path,
                                          "size": os.path.getsize(path)}
        self.life.save()
        self.life.log_event("backed up", os.path.basename(path) + (f"; {len(gone)} old one(s) to the Recycle Bin" if gone else ""))
        return self.life.state["last_backup"]

    def backups(self):
        folder = backup_mod.backup_dir(self.cfg)
        items = []
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder), reverse=True):
                if f.startswith("aether-") and f.endswith(".zip"):
                    p = os.path.join(folder, f)
                    items.append({"name": f, "size": os.path.getsize(p)})
        return {"folder": folder, "items": items, "last": self.life.state.get("last_backup")}

    def term_run(self, command):
        command = str(command or "").strip()
        if not command:
            return {"cwd": self.term_cwd}
        m = re.fullmatch(r"(?:cd|chdir|Set-Location|sl)\s+(.+)", command, re.I)
        if m:
            target = os.path.abspath(os.path.join(self.term_cwd, os.path.expandvars(os.path.expanduser(m.group(1).strip().strip('"\'')))))
            if not os.path.isdir(target):
                raise ValueError(f"no such folder: {target}")
            self.term_cwd = target
            self.broadcast({"type": "term", "who": "user", "kind": "cwd", "text": target})
            return {"cwd": target}
        if self.term_proc_busy:
            raise RuntimeError("a command is still running (Stop it first)")
        self.term_proc_busy = True
        self.term_cancel = threading.Event()

        def go():
            try:
                self.broadcast({"type": "term", "who": "user", "kind": "cmd", "text": f"{self.term_cwd}> {command}"})
                code, _ = shell_mod.run(command, self.term_cwd, timeout=3600, cancel=self.term_cancel,
                                        on_output=lambda t: self.broadcast({"type": "term", "who": "user", "kind": "out", "text": t}))
                self.broadcast({"type": "term", "who": "user", "kind": "end", "text": f"exit {code}"})
            finally:
                self.term_proc_busy = False
        threading.Thread(target=go, daemon=True).start()
        return {"cwd": self.term_cwd}


class Handler(BaseHTTPRequestHandler):
    app = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(fill(body, self.app.cfg), ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code, msg):
        self._send(code, {"error": msg})

    def _authed(self, query):
        t = self.headers.get("X-Aether-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(t, self.app.token)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("too big")
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw or b"{}")

    def do_GET(self):
        if not self._host_ok():
            return self._err(403, "bad host")
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        path = url.path
        if path in ("/", "/index.html", "/pet"):
            page = "pet.html" if path == "/pet" else "index.html"
            with open(os.path.join(UI_DIR, page), encoding="utf-8") as f:
                html = (f.read().replace("__AETHER_TOKEN__", self.app.token)
                        .replace("__AETHER_THEME__", self.app.cfg.theme if self.app.cfg.theme in THEMES else "astral"))
            return self._send(200, html, "text/html; charset=utf-8",
                              {"Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                                                          "script-src 'self' 'unsafe-eval'; connect-src 'self'; media-src 'self' blob:"})
        if path.startswith("/vendor/"):
            p = VENDOR.get(path[8:])
            if not p or not os.path.isfile(p):
                return self._err(404, "not found")
            with open(p, "rb") as f:
                return self._send(200, f.read(), "text/javascript")
        if path.startswith("/live2d/"):
            model = self.app.avatar_model_path()
            if model is None:
                return self._err(404, "not found")
            base = os.path.dirname(os.path.abspath(model))
            p = os.path.abspath(os.path.join(base, urllib.parse.unquote(path[8:])))
            if not p.startswith(base + os.sep) or not os.path.isfile(p):
                return self._err(404, "not found")
            with open(p, "rb") as f:
                return self._send(200, f.read(), mimetypes.guess_type(p)[0] or "application/octet-stream")
        if path.startswith("/ui/"):
            p = os.path.abspath(os.path.join(UI_DIR, path[4:]))
            if not p.startswith(UI_DIR + os.sep) or not os.path.isfile(p):
                return self._err(404, "not found")
            with open(p, "rb") as f:
                return self._send(200, f.read(), mimetypes.guess_type(p)[0] or "application/octet-stream")
        if not path.startswith("/api/"):
            return self._err(404, "not found")
        if not self._authed(q):
            return self._err(401, "missing key")
        app = self.app
        try:
            if path == "/api/events":
                return self._events()
            if path == "/api/state":
                return self._send(200, app.state())
            if path == "/api/chat":
                c = app.open_chat((q.get("id") or [""])[0])
                evs = [dict(e, images=[App._rel(p) for p in e.get("images") or []],
                            **({"video": App._rel(e["video"])} if e.get("video") else {}))
                       if e.get("images") or e.get("video") else e for e in c.events]
                title = "the heartbeat log" if c.id == HEARTBEAT_CHAT else app.meta.get(c.id, {}).get("title") or c.title()
                return self._send(200, {"id": c.id, "title": title, "events": evs})
            if path == "/api/greeting":
                return self._send(200, app.get_greeting())
            if path == "/api/avatar":
                return self._send(200, app.avatar_info())
            if path == "/api/avatars":
                return self._send(200, app.avatar_list())
            if path == "/api/brain3d":
                return self._send(200, app.brain3d())
            if path == "/api/brain":
                return self._send(200, app.brain())
            if path == "/api/commits":
                return self._send(200, app.commits(int((q.get("n") or ["40"])[0]), int((q.get("skip") or ["0"])[0])))
            if path == "/api/commit":
                return self._send(200, app.commit((q.get("h") or [""])[0]))
            if path == "/api/brain-search":
                words = (q.get("q") or [""])[0]
                return self._send(200, {"files": app.search_files(words), "history": app.search_history(words)})
            if path == "/api/file":
                rel = (q.get("path") or [""])[0]
                f = app.engine.memory.files.get(rel)
                if not f:
                    return self._err(404, "no such memory file")
                return self._send(200, {"path": rel, "text": f.text, "read_only": f.read_only,
                                        "owner": app.engine.memory.protected_by(rel)})
            if path == "/api/skills":
                return self._send(200, {"live": [{"name": s.name, "description": s.description, "scripts": sorted(s.scripts),
                                                  "ask_first": sorted(set(app.cfg.ask_first.get(s.name, [])) | set(s.ask_first)),
                                                  "builtin": s.name in app.cfg.builtin_skills} for s in app.engine.skills.values()],
                                        "left_out": [{"name": s.name, "problems": s.problems} for s in app.engine.rejected.values()],
                                        "new": app.new_skills()})
            if path == "/api/voice/options":
                url = (q.get("url") or [None])[0]
                return self._send(200, app.voice.options(url))
            if path == "/api/search":
                return self._send(200, app.search((q.get("q") or [""])[0], meaning=(q.get("meaning") or ["1"])[0] == "1"))
            if path == "/api/activity":
                return self._send(200, app.activity())
            if path == "/api/images":
                return self._send(200, {"info": app.imagine.info(), "gallery": app.imagine.gallery()})
            if path == "/api/life":
                return self._send(200, dict(app.life.status(), dreams=app.life.dreams()))
            if path == "/api/calendar":
                app.calendar.roll()
                return self._send(200, {"entries": app.calendar.entries(), "today": dt.date.today().isoformat()})
            if path == "/api/model-scores":
                return self._send(200, app.model_scores())
            if path == "/api/models":
                return self._send(200, app.brains.status())
            if path == "/api/music/ratings":
                return self._send(200, ratings_mod.all_ratings(app.engine.memory))
            if path == "/api/music/tracks":
                rows = list(reversed(songs_mod.records()))
                return self._send(200, {"songs": [dict(r, key=songs_mod.rating_key(r)) for r in rows]})
            if path == "/api/audit":
                return self._send(200, [dict(e, result=app.vault.scrub(e.get("result", ""))) for e in read_audit(300)])
            if path == "/api/vault":
                return self._send(200, app.vault.names())
            if path == "/api/discord":
                return self._send(200, app.discord.status())
            if path == "/api/term":
                return self._send(200, {"cwd": app.term_cwd, "busy": app.term_proc_busy})
            if path == "/api/backups":
                return self._send(200, app.backups())
            if path == "/api/picture":
                p = os.path.join(app.engine.memory.root, "profile.png")
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        return self._send(200, f.read(), "image/png")
                with open(os.path.join(UI_DIR, "orb.png"), "rb") as f:
                    return self._send(200, f.read(), "image/png")
            if path == "/api/audio":
                got = app.voice.get((q.get("id") or [""])[0])
                if got is None:
                    return self._err(404, "gone")
                if isinstance(got, (bytes, bytearray)):
                    return self._send(200, got, "audio/mpeg")
                return self._stream_voice(got)
            if path == "/api/attachment":
                p = app.attachment_path((q.get("p") or [""])[0])
                with open(p, "rb") as f:
                    return self._send(200, f.read(), mimetypes.guess_type(p)[0] or "image/png")
            return self._err(404, "unknown")
        except (ValueError, RuntimeError) as e:
            return self._err(400, str(e))
        except Exception as e:
            log(f"GET {path} crashed: {e!r}")
            return self._err(500, f"Aether error: {e}")

    def _stream_voice(self, clip):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for piece in clip.pieces():
                self.wfile.write(b"%X\r\n%s\r\n" % (len(piece), piece))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    def _events(self):
        q = self.app.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=15)
                    self.wfile.write(b"data: " + json.dumps(fill(ev, self.app.cfg), ensure_ascii=False).encode("utf-8") + b"\n\n")
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            self.app.unsubscribe(q)
            self.close_connection = True

    def do_POST(self):
        if not self._host_ok():
            return self._err(403, "bad host")
        url = urllib.parse.urlparse(self.path)
        if not self._authed({}):
            return self._err(401, "missing key")
        app = self.app
        try:
            b = self._body()
            p = url.path
            if p == "/api/chat/new":
                return self._send(200, {"id": app.new_chat()})
            if p == "/api/send":
                app.send(b.get("id"), b.get("text"), b.get("images"), b.get("voice"), b.get("tone"), b.get("speaker") or "")
                return self._send(200, {"ok": True})
            if p == "/api/avatars/add":
                info = avatars.add(b.get("path"), AVATARS_DIR, (b.get("name") or "").strip() or None)
                return self._send(200, {"ok": True, "added": info, **app.avatar_list()})
            if p == "/api/avatars/use":
                return self._send(200, app.avatar_use(b.get("name")))
            if p == "/api/avatars/frame":
                return self._send(200, app.avatar_frame(b.get("zoom", 1.0), b.get("y", 0.0)))
            if p == "/api/avatars/mood":
                if app.avatar_model_path() is None:
                    raise ValueError("the orb has no faces to pick")
                avatars.save_mood(app.avatar_model_path(), str(b.get("mood") or ""), b.get("expression"))
                return self._send(200, app.avatar_info())
            if p == "/api/typing":
                app.life.typing()
                return self._send(200, {"ok": True})
            if p == "/api/open-library":
                return self._send(200, app.open_folder("library"))
            if p == "/api/open-workspace":
                return self._send(200, app.open_folder("workspace"))
            if p == "/api/pick-folder":
                return self._send(200, app.pick_folder(str(b.get("which") or "")))
            if p == "/api/skills/seen":
                return self._send(200, app.skills_seen(b.get("names") or []))
            if p == "/api/retry":
                app.retry(str(b.get("id") or ""))
                return self._send(200, {"ok": True})
            if p == "/api/hear":
                return self._send(200, app.hear(str(b.get("data") or "")))
            if p == "/api/speak":
                if not app.voice.ensure_running():
                    raise RuntimeError(app.voice.quiet_why()[:1].upper() + app.voice.quiet_why()[1:])
                app.voice.say_now(str(b.get("text") or "")[:4000], b.get("chat") or "")
                return self._send(200, {"ok": True})
            if p == "/api/voice/stop":
                app.voice.stop()
                return self._send(200, {"ok": True})
            if p == "/api/voice/timing":
                return self._send(200, app.voice_timing(b))
            if p == "/api/voice/learn":
                try:
                    return self._send(200, app.learn_voice(str(b.get("data") or "")))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
            if p == "/api/voice/forget":
                app.ears.forget()
                app._svc = (0, {})
                return self._send(200, {"ok": True})
            if p == "/api/images/cancel":
                app.imagine.cancel(str(b.get("id") or ""))
                return self._send(200, {"ok": True, "images": app.imagine.info()})
            if p == "/api/stop":
                app.engine.stop()
                return self._send(200, {"ok": True})
            if p == "/api/quit":
                self._send(200, {"ok": True})
                return app.quit()
            if p == "/api/music/rate":
                try:
                    r = ratings_mod.rate(app.engine.memory, str(b.get("code") or ""), str(b.get("rating") or ""))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                app.engine.refresh()
                return self._send(200, {"ok": True, **r})
            if p == "/api/proposal":
                prop = app.proposals.answer(str(b.get("id") or ""), str(b.get("answer") or ""), note=str(b.get("note") or ""))
                return self._send(200, {"ok": True, "proposal": prop})
            if p == "/api/answer":
                w = app.pending.get(b.get("qid"))
                if w:
                    w["answer"] = bool(b.get("allow"))
                    w["event"].set()
                return self._send(200, {"ok": bool(w)})
            if p == "/api/chat/pin":
                app.conv(b.get("id"))
                m = app.meta.setdefault(b["id"], {})
                m["pinned"] = bool(b.get("pinned"))
                if m["pinned"]:
                    m["archived"] = False
                    m.pop("auto_archived", None)
                app._save_meta()
                return self._send(200, {"ok": True})
            if p == "/api/chat/archive":
                app.conv(b.get("id"))
                m = app.meta.setdefault(b["id"], {})
                m["archived"] = bool(b.get("archived"))
                m.pop("auto_archived", None)
                if m["archived"]:
                    m.pop("pinned", None)
                app._save_meta()
                return self._send(200, {"ok": True})
            if p == "/api/chat/compact":
                app.compact(b.get("id"))
                return self._send(200, {"ok": True})
            if p == "/api/chat/uncompact":
                app.uncompact(b.get("id"))
                return self._send(200, {"ok": True})
            if p == "/api/chat/rename":
                app.conv(b.get("id"))
                app.meta.setdefault(b["id"], {})["title"] = str(b.get("title") or "").strip()[:80]
                app._save_meta()
                return self._send(200, {"ok": True})
            if p == "/api/chat/delete":
                c = app.conv(b.get("id"))
                if app.engine.busy and app.engine.conv.id == c.id:
                    raise RuntimeError(f"{app.cfg.display_name} is still talking in that chat.")
                os.makedirs(TRASH_DIR, exist_ok=True)
                shutil.move(c.path, os.path.join(TRASH_DIR, os.path.basename(c.path)))
                if app.engine.conv.id == c.id:
                    app.engine.conv = Conversation(app.conv_dir)
                return self._send(200, {"ok": True})
            if p == "/api/file":
                return self._send(200, app.edit_file(b.get("path"), str(b.get("text") or "")))
            if p == "/api/rewind":
                return self._send(200, app.rewind(b.get("hash")))
            if p == "/api/forget":
                return self._send(200, app.forget_memory(str(b.get("key") or ""), str(b.get("text") or "")))
            if p == "/api/picture":
                return self._send(200, app.set_picture(str(b.get("data") or "")))
            if p == "/api/library":
                return self._send(200, app.add_to_library(b.get("name"), str(b.get("data") or "")))
            if p == "/api/glance":
                return self._send(200, app.glance())
            if p == "/api/settings":
                return self._send(200, app.update_settings(b))
            if p == "/api/term/run":
                return self._send(200, app.term_run(b.get("command")))
            if p == "/api/term/stop":
                app.term_cancel.set()
                return self._send(200, {"ok": True})
            if p == "/api/pet":
                app.pet_open = bool(b.get("open"))
                return self._send(200, {"ok": True})
            if p == "/api/backup":
                return self._send(200, app.backup_now())
            if p == "/api/vault/set":
                app.vault.set(b.get("name"), b.get("value"), b.get("skills") or [], b.get("note", ""))
                return self._send(200, app.vault.names())
            if p == "/api/vault/allow":
                app.vault.allow(b.get("name"), b.get("skills") or [])
                return self._send(200, app.vault.names())
            if p == "/api/vault/remove":
                app.vault.remove(b.get("name"))
                return self._send(200, app.vault.names())
            if p.startswith("/api/life/"):
                return self._send(200, app.life_action(p[len("/api/life/"):], b))
            if p == "/api/models/check":
                try:
                    return self._send(200, app.brains.check(str(b.get("key") or ""), app.services().get("vram")))
                except BrainError as e:
                    return self._err(400, str(e))
            if p == "/api/models/load":
                return self._send(200, app.start_brain_swap(str(b.get("key") or "")))
            return self._err(404, "unknown")
        except (ValueError, RuntimeError, KeyError) as e:
            return self._err(400, str(e))
        except Exception as e:
            log(f"POST {url.path} crashed: {e!r}")
            return self._err(500, f"Aether error: {e}")


def make_server(cfg, llm=None, port=None):
    app = App(cfg, llm)
    Handler.app = app
    httpd = ThreadingHTTPServer(("127.0.0.1", port if port is not None else cfg.port), Handler)
    httpd.daemon_threads = True
    app.stop_server = httpd.shutdown
    return httpd, app


def serve(cfg, open_window=True, llm=None, port=None, quit_when_closed=False):
    from .desktop import running
    port = port if port is not None else cfg.port
    if running(port):
        if open_window:
            open_app_window(f"http://127.0.0.1:{port}/")
        return 0
    httpd, app = make_server(cfg, llm, port)
    app.life.start()
    app.start_read_ahead()
    if cfg.discord_enabled:
        app.discord.start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"Aether is running at {url}  (memory: {app.agent()['memory_mode']})  Ctrl+C to quit.", flush=True)
    if open_window:
        open_app_window(url)
    if quit_when_closed:
        threading.Thread(target=_quit_when_closed, args=(app, httpd), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        app.imagine.stop_comfy()
        app.life.stop()
        app.discord.stop()
        app.voice.shutdown()
        app.ears.shutdown()
        app.recall.close()
    return 0


def _quit_when_closed(app, httpd, checks_needed=12):
    seen, gone = False, 0
    while True:
        time.sleep(5)
        with app.clients_lock:
            n = len(app.clients)
        if n:
            seen, gone = True, 0
        elif not app.engine.busy:
            gone += 1
            if gone >= (checks_needed if seen else 60):
                log("window closed; Aether is shutting down")
                httpd.shutdown()
                return


def open_app_window(url):
    candidates = [os.path.join(os.environ.get(v, ""), "Microsoft", "Edge", "Application", "msedge.exe")
                  for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    edge = next((c for c in candidates if os.path.isfile(c)), None)
    profile = os.path.join(DATA_DIR, "window")
    if edge:
        subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1600,960",
                          "--no-first-run", "--no-default-browser-check", "--disable-sync"])
    else:
        import webbrowser
        webbrowser.open(url)
