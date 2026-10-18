import contextlib
import http.client
import io
import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from aether import server as server_mod
from aether.llm import LLMError, ScriptedLLM
from aether.server import TRASH_DIR, make_server
from aether.tests.fixture import git, make_config, make_memory


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        self.cfg = make_config(self.root)
        self.llm = ScriptedLLM([])
        self.httpd, self.app = make_server(self.cfg, self.llm, port=0)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def req(self, method, path, body=None, token=True, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            h["X-Aether-Token"] = self.app.token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw.decode("utf-8", "replace")

    def wait_idle(self):
        for _ in range(100):
            if not self.app.engine.busy:
                return
            time.sleep(0.05)
        self.fail("turn never finished")

    def test_compact_from_the_page(self):
        cid = self.app.new_chat()
        self.assertEqual(self.req("POST", "/api/chat/compact", {"id": cid}), (400, {"error": "Nothing to sum up yet: this chat is empty"}))
        c = self.app.conv(cid)
        c.add("user", text="hey")
        c.add("reply", text="hey yourself")
        self.llm.answers += [{"step": "reply"}, {"say": "We said hey."}]
        self.assertEqual(self.req("POST", "/api/chat/compact", {"id": cid})[0], 200)
        self.wait_idle()
        for _ in range(100):
            if not self.app.gpu.locked():
                break
            time.sleep(0.05)
        self.assertEqual([e["kind"] for e in self.app.conv(cid).events[-2:]], ["summary", "compact"])
        self.assertEqual(self.req("POST", "/api/chat/compact", {"id": cid})[1]["error"],
                         "Nothing to sum up yet: nothing new since the last /compact")
        self.assertEqual(self.req("POST", "/api/chat/compact", {"id": "heartbeat"})[0], 400)

    def test_greeting_lets_his_message_wait(self):
        app, seen = self.app, []
        app.greeting = None
        self.llm.complete = lambda *a, **k: (seen.append(app.gpu_yield),
                                             json.dumps({"greeting": "Morning.", "suggestions": []}))[1]
        self.assertEqual(app.get_greeting()["greeting"], "Morning.")
        self.assertEqual(seen, [True])
        self.assertFalse(app.gpu.locked() or app.gpu_yield)

    def test_read_ahead_waits_until_she_is_quiet_and_reads_each_change_once(self):
        app, st, seen = self.app, {"done": None, "calm": 0}, []
        self.llm.read_ahead = lambda msgs: seen.append((msgs, app.gpu_yield))
        self.assertFalse(app._read_ahead_once(st))
        self.assertTrue(app._read_ahead_once(st))
        self.assertTrue(seen[0][1])
        self.assertEqual(seen[0][0][0]["content"], app.engine.system)
        self.assertFalse(app.gpu.locked() or app.gpu_yield)
        self.assertFalse(app._read_ahead_once(st))
        app.engine.turns += 1
        app.voice.making = True
        for _ in range(4):
            self.assertFalse(app._read_ahead_once(st))
        app.voice.making = False
        app.gpu.acquire()
        for _ in range(3):
            self.assertFalse(app._read_ahead_once(st))
        app.gpu.release()
        self.assertTrue(app._read_ahead_once(st))
        self.assertEqual(len(seen), 2)

    def test_page_carries_the_key_and_api_needs_it(self):
        code, html = self.req("GET", "/", token=False)
        self.assertEqual(code, 200)
        self.assertIn(self.app.token, html)
        self.assertEqual(self.req("GET", "/api/state", token=False)[0], 401)
        self.assertEqual(self.req("POST", "/api/stop", {}, token=False)[0], 401)
        self.assertEqual(self.req("GET", "/api/state", host="evil.example:80")[0], 403)
        code, st = self.req("GET", "/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(st["agent"]["memory_mode"], "test copy")
        self.assertEqual(st["agent"]["stats"]["skills"], 4)

    def test_ui_files_cant_escape_their_folder(self):
        self.assertEqual(self.req("GET", "/ui/../server.py", token=False)[0], 404)
        self.assertEqual(self.req("GET", "/ui/app.js", token=False)[0], 200)

    def test_send_a_message_and_read_the_chat(self):
        self.llm.answers += [{"step": "skill", "skill": "echo", "args": ["hi"]}, {"step": "reply"}, {"say": "Echoed."}]
        code, r = self.req("POST", "/api/chat/new", {})
        cid = r["id"]
        self.assertEqual(self.req("POST", "/api/send", {"id": cid, "text": "echo hi"})[0], 200)
        self.wait_idle()
        code, chat = self.req("GET", f"/api/chat?id={cid}")
        kinds = [e["kind"] for e in chat["events"]]
        self.assertEqual(kinds, ["user", "step", "result", "reply"])
        self.assertEqual(chat["events"][-1]["text"], "Echoed.")
        self.assertEqual(chat["events"][0]["place"], "Aether app")

    def test_a_spoken_turn_is_timed_in_one_log_line(self):
        self.llm.answers += [{"step": "skill", "skill": "echo", "args": ["hi"]}, {"step": "reply"}, {"say": "Echoed."}]
        cid = self.req("POST", "/api/chat/new", {})[1]["id"]
        self.req("POST", "/api/send", {"id": cid, "text": "echo hi", "voice": True})
        self.wait_idle()
        logged = []
        with mock.patch.object(server_mod, "log", logged.append):
            code, r = self.req("POST", "/api/voice/timing", {"where": "pet", "chat": cid, "quiet": 0.9, "hear": 0.2,
                                                             "words": 2.4, "sound": 1.3})
        self.assertEqual(code, 200)
        self.assertRegex(r["line"], r"^voice turn \(pet\): waiting for quiet 0\.9 s · her ears 0\.2 s · to her first "
                                    r"words 2\.4 s \(model free \d+\.\d · setup \d+\.\d · 2 calls before her reply "
                                    r"\d+\.\d · her reply's first words \d+\.\d\) · to her first sound 1\.3 s · "
                                    r"total 4\.8 s$")
        self.assertEqual(logged, [r["line"]])
        self.assertIsNone(self.app.clock)
        self.llm.answers += [{"step": "reply"}, {"say": "Hi."}]
        self.req("POST", "/api/send", {"id": cid, "text": "typed"})
        self.wait_idle()
        self.assertIsNone(self.app.clock)
        line = self.req("POST", "/api/voice/timing", {"chat": cid, "quiet": 5, "hear": "x", "words": 1,
                                                      "sound": None})[1]["line"]
        self.assertEqual(line, "voice turn (app): waiting for quiet 5.0 s · to her first words 1.0 s · no sound · "
                               "total 6.0 s")

    def test_whose_voice_goes_with_a_spoken_message_only(self):
        cid = self.req("POST", "/api/chat/new", {})[1]["id"]
        for body in ({"text": "hey", "voice": True, "speaker": "user"}, {"text": "who", "voice": True, "speaker": "other"},
                     {"text": "typed", "speaker": "user"}, {"text": "x", "voice": True, "speaker": "admin"}):
            self.llm.answers += [{"step": "reply"}, {"say": "ok"}]
            self.assertEqual(self.req("POST", "/api/send", {"id": cid, **body})[0], 200)
            self.wait_idle()
        users = [e for e in self.app.conv(cid).events if e["kind"] == "user"]
        self.assertEqual([e.get("speaker") for e in users], ["user", "other", None, None])
        with mock.patch.object(self.app.ears, "learn", return_value={"speech": 18.2, "made": "2026-10-04T02:40:00"}):
            code, r = self.req("POST", "/api/voice/learn", {"data": "data:audio/wav;base64,UklGRg=="})
        self.assertEqual((code, r["ok"], r["speech"]), (200, True, 18.2))
        with mock.patch.object(self.app.ears, "learn", side_effect=ValueError("Only 4 s of talking came through")):
            self.assertEqual(self.req("POST", "/api/voice/learn", {"data": "UklGRg=="}),
                             (400, {"error": "Only 4 s of talking came through"}))

    def test_second_message_while_busy_is_refused(self):
        gate = threading.Event()

        def slow(messages, cancel):
            gate.wait(5)
            return {"step": "reply"}
        self.llm.answers += [slow, {"say": "ok"}]
        cid = self.req("POST", "/api/chat/new", {})[1]["id"]
        self.req("POST", "/api/send", {"id": cid, "text": "one"})
        code, r = self.req("POST", "/api/send", {"id": cid, "text": "two"})
        self.assertEqual(code, 400)
        self.assertIn("still working", r["error"])
        gate.set()
        self.wait_idle()

    def test_pictures_are_saved_and_sent_to_the_model(self):
        png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        self.llm.answers += [{"step": "reply"}, {"say": "Cute."}]
        cid = self.req("POST", "/api/chat/new", {})[1]["id"]
        self.req("POST", "/api/send", {"id": cid, "text": "look", "images": [{"name": "cat.png", "data": png}]})
        self.wait_idle()
        user = self.llm.calls[0]["messages"][-1]
        self.assertEqual(user["content"][1]["type"], "image_url")
        chat = self.req("GET", f"/api/chat?id={cid}")[1]
        rel = chat["events"][0]["images"][0]
        self.assertEqual(self.req("GET", f"/api/attachment?p={rel}")[0], 200)
        self.assertEqual(self.req("GET", "/api/attachment?p=../aether.json")[0], 400)
        bad = self.req("POST", "/api/send", {"id": cid, "text": "x", "images": [{"name": "run.exe", "data": png}]})
        self.assertEqual(bad[0], 400)

    def test_retry_a_message_that_failed(self):
        png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        def broken(messages, cancel):
            raise LLMError("LM Studio: Engine protocol predict request failed")
        self.llm.answers += [broken]
        cid = self.req("POST", "/api/chat/new", {})[1]["id"]
        self.req("POST", "/api/send", {"id": cid, "text": "look at the new UI", "images": [{"name": "ui.png", "data": png}]})
        self.wait_idle()
        self.assertEqual([e["kind"] for e in self.req("GET", f"/api/chat?id={cid}")[1]["events"]], ["user"])
        self.llm.answers += [{"step": "reply"}, {"say": "Ooh, fancy."}]
        self.assertEqual(self.req("POST", "/api/retry", {"id": cid})[0], 200)
        self.wait_idle()
        events = self.req("GET", f"/api/chat?id={cid}")[1]["events"]
        self.assertEqual([e["kind"] for e in events], ["user", "reply"])
        self.assertEqual(events[0]["text"], "look at the new UI")
        self.assertEqual(self.llm.calls[-2]["messages"][-1]["content"][1]["type"], "image_url")
        code, r = self.req("POST", "/api/retry", {"id": cid})
        self.assertEqual(code, 400)
        self.assertIn("already answered", r["error"])

    def test_attached_pdf_goes_in_his_library(self):
        import base64
        pdf = "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 fake").decode()
        self.llm.answers += [{"step": "reply"}, {"say": "I'll read it."}]
        cid = self.req("POST", "/api/chat/new", {})[1]["id"]
        self.req("POST", "/api/send", {"id": cid, "text": "read this", "images": [{"name": "Tax Notes.pdf", "data": pdf}]})
        self.wait_idle()
        user = self.req("GET", f"/api/chat?id={cid}")[1]["events"][0]
        self.assertEqual(user["text"], "read this\n[PDF attached: attached/Tax_Notes.pdf in your Library]")
        with open(os.path.join(self.app.cfg.library_dir, "attached", "Tax_Notes.pdf"), "rb") as f:
            self.assertEqual(f.read(), b"%PDF-1.4 fake")
        self.assertFalse(user.get("images"))
        self.assertIsInstance(self.llm.calls[0]["messages"][-1]["content"], str)

    def test_archive_a_chat(self):
        self.llm.answers += [{"step": "reply"}, {"say": "hi"}]
        cid = self.req("POST", "/api/chat/new", {})[1]["id"]
        self.req("POST", "/api/send", {"id": cid, "text": "hello"})
        self.wait_idle()
        self.req("POST", "/api/chat/pin", {"id": cid, "pinned": True})
        self.assertEqual(self.req("POST", "/api/chat/archive", {"id": cid, "archived": True})[0], 200)
        row = next(c for c in self.req("GET", "/api/state")[1]["chats"] if c["id"] == cid)
        self.assertTrue(row["archived"])
        self.assertFalse(row["pinned"])
        self.assertEqual(self.req("GET", f"/api/chat?id={cid}")[1]["events"][0]["text"], "hello")
        self.req("POST", "/api/chat/archive", {"id": cid, "archived": False})
        row = next(c for c in self.req("GET", "/api/state")[1]["chats"] if c["id"] == cid)
        self.assertFalse(row.get("archived"))
        self.req("POST", "/api/chat/archive", {"id": cid, "archived": True})
        self.req("POST", "/api/chat/pin", {"id": cid, "pinned": True})
        row = next(c for c in self.req("GET", "/api/state")[1]["chats"] if c["id"] == cid)
        self.assertFalse(row.get("archived"))
        self.assertTrue(row["pinned"])

    def test_open_library_only_opens_the_drop_box(self):
        from unittest import mock
        self.app.cfg.library_dir = os.path.join(tempfile.mkdtemp(), "not-there")
        with mock.patch("os.startfile", create=True) as opened:
            code, r = self.req("POST", "/api/open-library", {"path": "C:\\Windows"})
        self.assertEqual(code, 200)
        opened.assert_called_once_with(os.path.abspath(self.app.cfg.library_dir))
        self.assertTrue(os.path.isdir(self.app.cfg.library_dir))
        self.assertEqual(self.req("POST", "/api/open-library", {}, token=False)[0], 401)

    def test_open_workspace_only_opens_her_workspace(self):
        from unittest import mock
        self.app.cfg.workspace_dir = os.path.join(tempfile.mkdtemp(), "Aether Workspace")
        with mock.patch("os.startfile", create=True) as opened:
            code, r = self.req("POST", "/api/open-workspace", {"path": "C:\\Windows"})
        self.assertEqual(code, 200)
        opened.assert_called_once_with(os.path.abspath(self.app.cfg.workspace_dir))
        self.assertTrue(os.path.isdir(self.app.cfg.workspace_dir))
        self.assertEqual(self.req("POST", "/api/open-workspace", {}, token=False)[0], 401)

    def test_edit_and_rewind_are_commits_by_jordan(self):
        code, f = self.req("GET", "/api/file?path=system/human.md")
        self.req("POST", "/api/file", {"path": "system/human.md", "text": f["text"] + "Jordan edited this.\n"})
        self.assertIn("Jordan edited this.", self.app.engine.system)
        self.assertEqual(git(self.root, "log", "-1", "--pretty=%an|%s").strip(), "user|{USER} edited system/human.md")
        h = git(self.root, "rev-parse", "--short", "HEAD").strip()
        detail = self.req("GET", f"/api/commit?h={h}")[1]
        self.assertEqual(detail["files"][0]["added"], 1)
        code, r = self.req("POST", "/api/rewind", {"hash": h})
        self.assertEqual(code, 200)
        self.assertNotIn("Jordan edited this.", self.app.engine.system)
        self.assertEqual(self.req("POST", "/api/rewind", {"hash": "; rm -rf"})[0], 400)

    def test_the_brain_page_searches_her_files(self):
        code, f = self.req("GET", "/api/file?path=system/human.md")
        self.req("POST", "/api/file", {"path": "system/human.md", "text": f["text"] + "Loves the PHANTOM stack.\nphantom again\n"})
        code, found = self.req("GET", "/api/brain-search?q=Phantom%20Stack")
        self.assertEqual(code, 200)
        mine = next(x for x in found["files"] if x["path"] == "system/human.md")
        self.assertEqual([h["text"] for h in mine["hits"]], ["Loves the PHANTOM stack."])
        self.assertEqual(mine["count"], 1)
        lines = self.req("GET", "/api/file?path=system/human.md")[1]["text"].split("\n")
        self.assertEqual(lines[mine["hits"][0]["n"] - 1], "Loves the PHANTOM stack.")
        self.assertEqual(self.req("GET", "/api/brain-search?q=p")[1], {"files": [], "history": []})
        self.assertEqual(self.req("GET", "/api/brain-search?q=phantom", token=False)[0], 401)
        self.req("POST", "/api/file", {"path": "system/human.md", "text": f["text"]})
        found = self.req("GET", "/api/brain-search?q=phantom%20stack")[1]
        self.assertEqual(found["files"], [])
        self.assertEqual([(c["author"], c["lines"]) for c in found["history"]],
                         [("user", [["-", "Loves the PHANTOM stack."]]), ("user", [["+", "Loves the PHANTOM stack."]])])
        self.assertEqual(self.req("GET", "/api/brain-search?q=phantom.stack")[1]["history"], [])

    def test_settings_whitelist(self):
        code, s = self.req("POST", "/api/settings", {"max_steps": "5", "show_work": False})
        self.assertEqual((s["max_steps"], s["show_work"]), (5, False))
        self.assertEqual(self.req("POST", "/api/settings", {"allow_real_memory": True})[0], 400)
        self.assertEqual(self.req("POST", "/api/settings", {"temperature_talk": 9})[0], 400)
        self.assertFalse(self.cfg.allow_real_memory)

    def test_theme(self):
        self.assertIn('data-theme="astral"', self.req("GET", "/", token=False)[1])
        self.assertEqual(self.req("POST", "/api/settings", {"theme": "void"})[1]["theme"], "void")
        self.assertIn('data-theme="void"', self.req("GET", "/", token=False)[1])
        self.assertEqual(self.req("POST", "/api/settings", {"theme": "neon<script>"})[0], 400)
        self.assertNotIn("__AETHER_THEME__", self.req("GET", "/pet", token=False)[1])

    def test_mic_picker(self):
        code, s = self.req("POST", "/api/settings", {"mic_device": "Microphone (Blue Yeti)"})
        self.assertEqual((code, s["mic_device"]), (200, "Microphone (Blue Yeti)"))
        self.assertEqual(self.req("GET", "/api/state")[1]["settings"]["mic_device"], "Microphone (Blue Yeti)")
        self.assertEqual(self.req("POST", "/api/settings", {"mic_device": "x\n" * 5})[0], 400)
        self.assertEqual(self.req("POST", "/api/settings", {"mic_device": ""})[1]["mic_device"], "")

    def test_permission_levels(self):
        self.assertEqual(self.req("GET", "/api/state")[1]["agent"]["permission"], "skills only")
        code, s = self.req("POST", "/api/settings", {"permission_levels": {"app": 1}})
        self.assertEqual(s["permission_levels"], {"app": 1, "discord": 0, "avatar": 0, "own": 0})
        code, s = self.req("POST", "/api/settings", {"permission_levels": {"own": 2}})
        self.assertEqual(s["permission_levels"]["own"], 2)
        self.assertEqual(self.req("GET", "/api/state")[1]["agent"]["permission"], "look around")
        self.assertEqual(self.req("POST", "/api/settings", {"permission_levels": {"app": 7}})[0], 400)
        self.assertEqual(self.req("POST", "/api/settings", {"permission_levels": {"root": 3}})[0], 400)
        self.llm.answers += [{"step": "reply"}, {"say": "ok"}]
        cid = self.req("POST", "/api/chat/new", {})[1]["id"]
        self.req("POST", "/api/send", {"id": cid, "text": "hi"})
        self.wait_idle()
        self.assertIn("command-line permission here: level 1 (look around)", self.llm.calls[0]["messages"][-1]["content"])

    def test_chat_pin_rename_delete(self):
        self.llm.answers += [{"step": "reply"}, {"say": "hey"}]
        cid = self.req("POST", "/api/chat/new", {})[1]["id"]
        self.req("POST", "/api/send", {"id": cid, "text": "hello there"})
        self.wait_idle()
        self.req("POST", "/api/chat/pin", {"id": cid, "pinned": True})
        self.req("POST", "/api/chat/rename", {"id": cid, "title": "Greetings"})
        chat = next(c for c in self.req("GET", "/api/state")[1]["chats"] if c["id"] == cid)
        self.assertEqual((chat["pinned"], chat["title"]), (True, "Greetings"))
        hits = self.req("GET", "/api/search?q=hello")[1]
        self.assertTrue(any(h["type"] == "chat" and h["id"] == cid for h in hits))
        self.req("POST", "/api/chat/delete", {"id": cid})
        self.assertTrue(os.path.exists(os.path.join(TRASH_DIR, cid + ".jsonl")))
        self.assertEqual(self.req("GET", f"/api/chat?id={cid}")[0], 400)
        self.assertEqual(self.req("GET", "/api/chat?id=../../x")[0], 400)

    def test_brain3d(self):
        d = self.req("GET", "/api/brain3d")[1]
        core = d["nodes"][0]
        self.assertEqual((core["k"], core["file"]), ("core", "system/persona.md"))
        mems = [n for n in d["nodes"] if n["k"] == "mem"]
        self.assertTrue(mems and all(n.get("file") for n in mems))
        self.assertEqual(d["organs"]["user"]["state"], "you")
        self.assertEqual(d["organs"]["discord"]["state"], "off")
        self.assertTrue(all(0 <= a < len(d["nodes"]) and 0 <= b < len(d["nodes"]) for a, b, _ in d["links"]))
        for k in ("cue", "keeper", "nudge"):
            self.assertEqual((d["organs"][k]["state"], d["organs"][k]["label"]), ("off", "OFF"))
        self.assertIn(("next check-in", "nothing coming up"), [tuple(x) for x in d["organs"]["nudge"]["details"]])
        self.assertIn("chats", d["meta"]["regions"])
        self.assertEqual(self.app.cfg.brain_style, "tree")
        self.assertEqual(self.app.update_settings({"brain_style": "neuron"})["brain_style"], "neuron")
        self.assertEqual(self.app.update_settings({"brain_style": "constellation"})["brain_style"], "constellation")
        with self.assertRaises(ValueError):
            self.app.update_settings({"brain_style": "spaghetti"})
        with self.assertRaises(ValueError):
            self.app.update_settings({"brain_style": "tree", "max_steps": 99})
        self.assertEqual(self.app.cfg.brain_style, "constellation")

    def test_avatar_and_voice_server_settings(self):
        code, a = self.req("GET", "/api/avatar")
        self.assertEqual(code, 200)
        self.assertEqual((a["name"], a["info"]["kind"]), ("orb", "orb"))
        code, lst = self.req("GET", "/api/avatars")
        self.assertEqual((code, lst["list"], lst["current"], lst["builtin"]), (200, [], "orb", "orb"))
        code, _ = self.req("POST", "/api/avatars/use", {"name": "nobody"})
        self.assertNotEqual(code, 200)
        code, a = self.req("POST", "/api/avatars/use", {"name": "orb"})
        self.assertEqual((code, a["info"]["kind"], a["info"]["style"]), (200, "orb", "wire"))
        code, a = self.req("POST", "/api/avatars/use", {"name": "logo-orb"})
        self.assertEqual((code, a["name"], a["info"]["style"]), (200, "logo-orb", "logo"))
        self.assertEqual([b["name"] for b in self.req("GET", "/api/avatars")[1]["builtins"]], ["orb", "logo-orb"])
        self.req("POST", "/api/avatars/use", {"name": "orb"})
        code, _ = self.req("POST", "/api/avatars/frame", {"zoom": 2, "y": 0})
        self.assertNotEqual(code, 200)
        code, _ = self.req("GET", "/live2d/anything.png")
        self.assertEqual(code, 404)
        self.assertEqual(self.app.update_settings({"tts_url": "http://127.0.0.1:9000", "tts_model": "tts-1",
                                                  "voice": "alloy"})["tts_model"], "tts-1")
        for bad in ({"tts_url": "https://api.example.com"}, {"tts_url": "http://192.168.1.50:8880"},
                    {"breeze_voice": "../lucy"}, {"voice": "a;b"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.app.update_settings(bad)
        self.assertEqual(self.app.cfg.tts_url, "http://127.0.0.1:9000")

    def test_brain_and_skills(self):
        b = self.req("GET", "/api/brain")[1]
        kinds = {n["path"]: n["kind"] for n in b["nodes"]}
        self.assertEqual(kinds["system/persona.md"], "soul")
        self.assertEqual(kinds["system/human/facts.md"], "user")
        s = self.req("GET", "/api/skills")[1]
        self.assertEqual(sorted(k["name"] for k in s["live"]), ["echo", "fail", "plants", "slow"])
        self.assertIn("nofront", [k["name"] for k in s["left_out"]])

    def test_a_new_skill_gets_a_card_until_got_it(self):
        seen_file = os.path.join(tempfile.mkdtemp(), "skills_seen.json")
        with mock.patch.object(server_mod, "SKILLS_SEEN", seen_file):
            self.assertEqual(self.req("GET", "/api/skills")[1]["new"], [])
            with open(seen_file, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["seen"], ["echo", "fail", "plants", "slow"])
            with open(seen_file, "w", encoding="utf-8") as f:
                json.dump({"seen": ["fail", "plants", "slow"]}, f)
            new = self.req("GET", "/api/skills")[1]["new"]
            self.assertEqual([k["name"] for k in new], ["echo"])
            self.assertEqual(new[0]["description"], "Says back what you give it.")
            self.assertEqual(new[0]["commands"][0]["command"], "")
            self.assertIn('"skill": "echo"', new[0]["commands"][0]["example"])
            self.assertEqual(self.req("POST", "/api/skills/seen", {"names": ["echo", "nope"]})[1], {"ok": True, "new": []})
            with open(seen_file, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["seen"], ["echo", "fail", "plants", "slow"])


class QuitTests(unittest.TestCase):

    def test_the_desktop_app_asks_it_to_quit_and_comfyui_is_stopped(self):
        made, stopped = {}, []

        def make(*a, **kw):
            httpd, app = make_server(*a, **kw)
            app.imagine.stop_comfy = lambda: stopped.append(True)
            made["httpd"], made["app"] = httpd, app
            return httpd, app

        cfg = make_config(make_memory())
        with mock.patch.object(server_mod, "make_server", make), contextlib.redirect_stdout(io.StringIO()):
            run = threading.Thread(target=server_mod.serve, args=(cfg,), daemon=True,
                                   kwargs={"open_window": False, "llm": ScriptedLLM([]), "port": 0})
            run.start()
            for _ in range(200):
                if "app" in made:
                    break
                time.sleep(0.05)
            port = made["httpd"].server_address[1]

            def post(token):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                c.request("POST", "/api/quit", body=b"{}", headers={"Host": f"127.0.0.1:{port}", "X-Aether-Token": token,
                                                                    "Content-Type": "application/json"})
                status = c.getresponse().status
                c.close()
                return status

            self.assertEqual(post("wrong"), 401)
            self.assertTrue(run.is_alive())
            self.assertEqual(post(made["app"].token), 200)
            run.join(10)
        self.assertFalse(run.is_alive(), "serve() didn't end")
        self.assertEqual(stopped, [True])


if __name__ == "__main__":
    unittest.main()
