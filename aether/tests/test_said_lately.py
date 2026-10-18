import datetime as dt
import os
import tempfile
import unittest

from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory

T = dt.datetime(2026, 10, 10, 1, 13)


class SaidLatelyTests(unittest.TestCase):
    def setUp(self):
        from aether import life as life_mod
        home = tempfile.mkdtemp()
        life_mod.STATE_FILE = os.path.join(home, "life.json")
        life_mod.SCHEDULES_FILE = os.path.join(home, "schedules.json")
        self.httpd, self.app = make_server(make_config(make_memory()), ScriptedLLM([]), port=0)
        self.app.conv_dir = tempfile.mkdtemp()

    def tearDown(self):
        self.httpd.server_close()

    def test_her_messages_from_any_chat_in_full_and_whether_he_answered(self):
        a = Conversation(self.app.conv_dir, "webcam")
        a.add("user", text="i know you wanted eyes, so now you have em!", ts="2026-10-09T22:18:49")
        a.add("reach_out", text="I saw the greenhouse watering plan land in the library while I was awake. " + "x" * 200,
              ts="2026-10-10T00:14:17")
        b = Conversation(self.app.conv_dir, "older")
        b.add("reach_out", text="Hey, I was thinking about that webcam update", ts="2026-10-09T22:13:40")
        Conversation(self.app.conv_dir, "heartbeat").add("reach_out", text="not a chat with him", ts="2026-10-10T00:30:00")
        out = self.app.life._said_lately(T)
        self.assertIn("Don't send the same thing again", out)
        self.assertIn("(he hasn't answered): \"I saw the greenhouse watering plan", out)
        self.assertIn("x" * 200, out)
        self.assertNotIn("webcam update\" (he hasn't", out)
        self.assertIn("ago: \"Hey, I was thinking about that webcam update\"", out)
        self.assertNotIn("not a chat with him", out)
        self.assertEqual(self.app.life._said_lately(dt.datetime(2026, 10, 9, 20, 0)), "")


if __name__ == "__main__":
    unittest.main()
