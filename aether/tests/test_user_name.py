import http.client
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

from aether import names
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.shared_calendar import BY_USER, parse
from aether.tests.fixture import make_config, make_memory
from aether.voice import names_in


class NamesTests(unittest.TestCase):
    def test_fill_puts_the_name_everywhere_the_marker_is(self):
        cfg = make_config(make_memory(), user_name="Sam")
        msgs = [{"role": "user", "content": [{"type": "text", "text": f"{names.USER} said hi"}]},
                {"role": "system", "content": "talk to {USER}"}]
        self.assertEqual(names.fill(msgs, cfg)[0]["content"][0]["text"], "Sam said hi")
        self.assertEqual(names.fill(msgs, cfg)[1]["content"], "talk to Sam")
        self.assertEqual(names.fill("{USER}", None), "User")

    def test_the_calendar_reads_older_files_name_as_the_user(self):
        es = parse("- [c1] 2031-01-01 · Rent due · by Jordan\n- [c2] 2031-01-02 · Dentist · by user\n"
                   "- [c3] 2031-01-03 · Movie night · by Ms Kitty\n")
        self.assertEqual([e["by"] for e in es], [BY_USER, BY_USER, "Ms Kitty"])

    def test_a_voice_servers_lists_in_any_shape(self):
        self.assertEqual(names_in({"voices": ["af_sky", "af_bella", "af_sky"]}, "voices"), ["af_sky", "af_bella"])
        self.assertEqual(names_in({"object": "list", "data": [{"id": "kokoro"}]}, "models"), ["kokoro"])
        self.assertEqual(names_in([{"name": "alloy"}, "echo"], "voices"), ["alloy", "echo"])
        self.assertEqual(names_in("nonsense", "voices"), [])


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        self.cfg = make_config(self.root)
        self.httpd, self.app = make_server(self.cfg, ScriptedLLM([]), port=0)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}", "X-Aether-Token": self.app.token, "Content-Type": "application/json"}
        c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=h)
        r = c.getresponse()
        out = (r.status, json.loads(r.read()))
        c.close()
        return out

    def test_your_name_reaches_the_app_and_her_instructions(self):
        cid = self.app.new_chat()
        self.app.conv(cid).add("result", of="skill", ok=False, text="{USER} didn't allow that")
        self.assertEqual(self.req("POST", "/api/settings", {"user_name": "  Sam  "})[1]["user_name"], "Sam")
        self.assertEqual(self.req("GET", f"/api/chat?id={cid}")[1]["events"][-1]["text"], "Sam didn't allow that")
        self.assertIn("who Sam is", self.app.engine.system)
        self.assertNotIn("{USER}", self.app.engine.system)
        for bad in ("", "x" * 41, "{USER}"):
            self.assertEqual(self.req("POST", "/api/settings", {"user_name": bad})[0], 400)

    def test_no_voice_server_is_text_only(self):
        self.assertEqual(self.req("POST", "/api/settings", {"tts_url": ""})[1]["tts_url"], "")
        self.assertFalse(self.app.voice.ensure_running())
        self.assertIn("no voice server", self.app.voice.quiet_why())
        o = self.req("GET", "/api/voice/options")[1]
        self.assertEqual((o["ok"], o["models"], o["voices"]), (False, [], []))
        self.assertEqual(self.req("POST", "/api/settings", {"tts_url": "http://example.com:8880"})[0], 400)

    def test_choose_folder_sets_it_and_cancel_changes_nothing(self):
        picked = os.path.join(tempfile.mkdtemp(), "My Drop Box")
        with mock.patch.object(self.app, "_ask_folder", return_value=picked):
            r = self.req("POST", "/api/pick-folder", {"which": "library"})[1]
        self.assertEqual((r["ok"], r["path"], self.cfg.library_dir), (True, os.path.normpath(picked), os.path.normpath(picked)))
        before = self.cfg.workspace_dir
        with mock.patch.object(self.app, "_ask_folder", return_value=""):
            self.assertEqual(self.req("POST", "/api/pick-folder", {"which": "workspace"})[1], {"ok": False, "cancelled": True})
        self.assertEqual(self.cfg.workspace_dir, before)
        self.assertEqual(self.req("POST", "/api/pick-folder", {"which": "C:\\Windows"})[0], 400)
        with mock.patch.object(self.app, "_ask_folder", side_effect=RuntimeError("needs Python's tkinter")):
            code, r = self.req("POST", "/api/pick-folder", {"which": "library"})
        self.assertEqual(code, 400)
        self.assertIn("tkinter", r["error"])

    def test_a_new_skill_gets_a_card_until_got_it(self):
        self.app._write_seen(set())
        new = {k["name"]: k for k in self.req("GET", "/api/skills")[1]["new"]}
        self.assertEqual(sorted(new), sorted(self.app.engine.skills))
        self.assertEqual([c["command"] for c in new["plants"]["commands"]], ["next", "skip"])
        self.assertIn('"command": "skip"', new["plants"]["commands"][1]["example"])
        self.assertEqual(new["plants"]["description"], "Watering schedule.")
        left = self.req("POST", "/api/skills/seen", {"names": ["plants", "not-a-skill"]})[1]["new"]
        self.assertNotIn("plants", [k["name"] for k in left])
        self.assertNotIn("plants", [k["name"] for k in self.req("GET", "/api/skills")[1]["new"]])


if __name__ == "__main__":
    unittest.main()
