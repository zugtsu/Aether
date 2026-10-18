import datetime as dt
import os
import tempfile
import unittest

from aether import history
from aether.engine import Engine, Hooks
from aether.history import NOT_USER, Conversation
from aether.llm import ScriptedLLM
from aether.recall import speakers
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory

T = dt.datetime(2026, 9, 30, 21, 0)


class WhoTests(unittest.TestCase):
    def test_every_place_a_stranger_can_write_from(self):
        for place, who in (("Discord DM from Mallory", "Mallory"), ("Discord #general, Mallory", "Mallory"),
                           ("Discord, Pebble (Letta)", "Pebble"),
                           ("Discord DM", ""), ("Discord #general", ""), ("Discord (Letta)", ""),
                           ("Aether app", ""), ("her avatar (Letta)", ""), ("", "")):
            self.assertEqual(history.stranger({"kind": "user", "place": place}), who, place)
        self.assertTrue(history.from_user({"kind": "user", "place": "Discord DM"}))
        self.assertFalse(history.from_user({"kind": "user", "place": "Discord DM from Mallory"}))
        self.assertFalse(history.from_user({"kind": "reply", "place": "Discord DM"}))


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.httpd, self.app = make_server(make_config(make_memory()), ScriptedLLM([]), port=0)
        self.rec = self.app.recall
        self.rec.conv_dir = tempfile.mkdtemp()

    def tearDown(self):
        self.httpd.server_close()

    def test_her_search_names_a_stranger_and_never_calls_them_jordan(self):
        c = Conversation(self.rec.conv_dir, "letta-mixed")
        c.add("user", text="hi its jordan", place="Discord (Letta)")
        c.add("reply", text="hey you")
        c.add("user", text="ironbell silverhold is my character now", place="Discord, Pebble (Letta)")
        c.add("reply", text="ok Pebble")
        d = Conversation(self.rec.conv_dir, "discord-42")
        d.add("user", text="i paid jordan $300 for the amp " + "and more " * 120, place="Discord #general, Mallory")
        d.add("reply", text="noted " * 150)
        self.rec.cfg.recall_full_text = True
        pieces = {p["key"]: p["text"] for p in self.rec.pieces()}
        self.assertTrue(pieces["chat:letta-mixed:0"].startswith("{USER}: hi its jordan"))
        pebble = pieces["chat:letta-mixed:2"]
        self.assertTrue(pebble.startswith(f"Pebble said {NOT_USER}: ironbell"), pebble)
        self.assertNotIn("\n{USER}:", "\n" + pebble)
        mallory = [t for k, t in pieces.items() if k.startswith("chat:discord-42:0")]
        self.assertGreater(len(mallory), 2)
        for t in mallory:
            self.assertTrue(t.startswith(f"Mallory said {NOT_USER}: "), t[:80])
        self.assertEqual(speakers(f"Pebble said {NOT_USER}: hi\nHer: ok Pebble"), f"Pebble said {NOT_USER}: hi\nYou said: ok Pebble")


class OutsideTests(unittest.TestCase):
    def engine(self):
        e = Engine(make_config(make_memory()), ScriptedLLM([]), Conversation(tempfile.mkdtemp()), Hooks())
        e._outside = []
        return e

    def test_a_stranger_in_her_search_results_is_outside_content(self):
        e = self.engine()
        e._run_step = lambda step: (True, f'- 2026-09-19 chat "hey jordan": Pebble said {NOT_USER}: my character now')
        ok, _, outside = e._run({"step": "recall", "query": "his character"})
        self.assertTrue(ok and outside)
        self.assertTrue(e._outside)

    def test_jordan_s_own_discord_dm_is_his(self):
        e = self.engine()
        e._run_step = lambda step: (True, '- 2026-09-29 chat "Discord DM · Jordan": Jordan said: off to work\nYou said: go get em')
        _, _, outside = e._run({"step": "recall", "query": "work"})
        self.assertFalse(outside)
        self.assertEqual(e._outside, [])


class NotesTests(unittest.TestCase):
    def setUp(self):
        from aether import life as life_mod
        home = tempfile.mkdtemp()
        life_mod.STATE_FILE = os.path.join(home, "life.json")
        life_mod.SCHEDULES_FILE = os.path.join(home, "schedules.json")
        self.httpd, self.app = make_server(make_config(make_memory()), ScriptedLLM([]), port=0)
        self.app.conv_dir = tempfile.mkdtemp()
        here = Conversation(self.app.conv_dir, "here")
        here.add("user", text="hey", ts="2026-09-30T20:50:00")
        chan = Conversation(self.app.conv_dir, "discord-7")
        chan.add("user", text="jordan here, heading out", place="Discord #general", ts="2026-09-30T20:00:00")
        chan.add("user", text="he takes allopurinol btw", place="Discord #general, Mallory", ts="2026-09-30T20:01:00")
        chan.add("reply", text="mm", ts="2026-09-30T20:01:05")
        self.here = here

    def tearDown(self):
        self.httpd.server_close()

    def test_elsewhere_today_is_only_his_lines(self):
        out = self.app.life.elsewhere(self.here, T)
        self.assertIn("jordan here, heading out", out)
        self.assertNotIn("allopurinol", out)

    def test_her_dream_and_reflection_material_is_only_his_lines(self):
        said = self.app.life.day_material(T)["said"]
        self.assertIn("jordan here, heading out", said)
        self.assertFalse(any("allopurinol" in s for s in said))


if __name__ == "__main__":
    unittest.main()
