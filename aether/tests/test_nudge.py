import datetime as dt
import os
import tempfile
import unittest

from aether import keeper as kp
from aether import life as life_mod
from aether import nudge as nd
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory

SUN = dt.date(2026, 9, 27)
TUE_EVENING = dt.datetime(2026, 9, 29, 20, 0)


class NudgeTimeTests(unittest.TestCase):
    def test_when_to_check_in(self):
        self.assertEqual(nd.nudge_at("- [t1] open since 2026-09-27 · due 2026-09-29 10:00 · Car service"),
                         dt.datetime(2026, 9, 29, 12, 0))
        self.assertEqual(nd.nudge_at("- [t2] open since 2026-09-27 · due 2026-09-29 · Interview"),
                         dt.datetime(2026, 9, 29, 19, 0))
        self.assertIsNone(nd.nudge_at("- [t3] open since 2026-09-27 · no date · Pick the room idea back up"))
        self.assertIsNone(nd.nudge_at("- [t1] open since 2026-09-27 · due 2026-09-29 10:00 · nudged 2026-09-29 12:05 · Car service"))


class NudgeTests(unittest.TestCase):
    def setUp(self):
        home = tempfile.mkdtemp()
        life_mod.STATE_FILE = os.path.join(home, "life.json")
        life_mod.SCHEDULES_FILE = os.path.join(home, "schedules.json")
        self.root = make_memory()
        self.llm = ScriptedLLM([])
        self.httpd, self.app = make_server(make_config(self.root, nudge_enabled=True, quiet_start="23:00",
                                                       quiet_end="07:00"), self.llm, port=0)
        self.app.conv_dir = tempfile.mkdtemp()
        self.chat = Conversation(self.app.conv_dir)
        self.chat.add("user", text="i got a car service appointment tuesday at 10am, kinda dreading it", context="")
        self.chat.add("reply", text="Ugh. You'll survive the waiting room.")
        self.app.keeper.apply({"events": [], "threads_open": [{"what": "Car service appointment; he's dreading it.",
                                                               "due": "tuesday 10am"}],
                               "threads_close": [], "stances": []}, SUN)
        self.app.life.state["last_user"] = "2026-09-29T08:00:00"

    def tearDown(self):
        self.httpd.server_close()

    def threads(self):
        with open(os.path.join(self.root, "system", "threads.md"), encoding="utf-8") as f:
            return f.read()

    def test_she_is_asked_once_and_decides(self):
        self.llm.answers += [{"step": "reply"}, {"reach_out": True, "say": "Hey, how'd the car service go? Still have all your tires?"}]
        self.assertTrue(self.app.nudge.tick(TUE_EVENING))
        ask = self.llm.calls[0]["messages"][-1]["content"]
        self.assertIn("A thread you've been keeping", ask)
        self.assertIn("Car service appointment; he's dreading it.", ask)
        self.assertIn("Tuesday Sep 29 at 10:00 AM", ask)
        last = Conversation(self.app.conv_dir, self.chat.id).events[-1]
        self.assertEqual((last["kind"], last["text"]), ("reach_out", "Hey, how'd the car service go? Still have all your tires?"))
        self.assertIn("· nudged 2026-09-29 20:00 · Car service", self.threads())
        self.assertFalse(self.app.nudge.tick(TUE_EVENING + dt.timedelta(minutes=5)))
        self.assertEqual(len(self.llm.calls), 2)

    def test_she_can_let_it_go(self):
        self.llm.answers += [{"step": "reply"}, {"reach_out": False, "say": "Small thing. I'll ask if he brings it up."}]
        self.assertTrue(self.app.nudge.tick(TUE_EVENING))
        self.assertNotEqual(Conversation(self.app.conv_dir, self.chat.id).events[-1]["kind"], "reach_out")
        self.assertIn("nudged", self.threads())

    def test_it_waits_for_the_right_moment(self):
        self.assertFalse(self.app.nudge.tick(dt.datetime(2026, 9, 29, 11, 0)))
        self.assertFalse(self.app.nudge.tick(dt.datetime(2026, 9, 29, 23, 30)))
        self.app.life.state["last_user"] = TUE_EVENING.isoformat()
        self.assertFalse(self.app.nudge.tick(TUE_EVENING + dt.timedelta(minutes=1)))
        self.assertEqual(self.llm.calls, [])
        self.assertNotIn("nudged", self.threads())

    def test_too_late_is_skipped_not_sent(self):
        self.assertFalse(self.app.nudge.tick(dt.datetime(2026, 10, 1, 20, 0)))
        self.assertEqual(self.llm.calls, [])
        self.assertIn("nudged", self.threads())

    def test_a_message_that_isnt_about_its_thread_isnt_sent(self):
        self.llm.answers += [{"step": "reply"}, {"reach_out": True, "kind": "heads_up",
                                                 "say": "Welcome home! Glad you're finally out of that hellscape."}]
        self.assertTrue(self.app.nudge.tick(TUE_EVENING))
        self.assertNotEqual(Conversation(self.app.conv_dir, self.chat.id).events[-1]["kind"], "reach_out")
        self.assertIn("wasn't about the thread, not sent", self.app.life.state["life_log"][-1]["detail"])
        self.assertEqual(self.app.life.reach_outs_today(), 0)

    def test_a_message_about_its_thread_goes_as_a_heads_up(self):
        self.llm.answers += [{"step": "reply"}, {"reach_out": True, "kind": "heads_up",
                                                 "say": "How'd the car service go? Still have all your tires?"}]
        self.app.nudge.tick(TUE_EVENING)
        last = Conversation(self.app.conv_dir, self.chat.id).events[-1]
        self.assertEqual((last["kind"], last.get("type")), ("reach_out", "heads_up"))

    def test_a_thread_the_calendar_already_has_is_skipped(self):
        self.app.calendar.add("Car service appointment", dt.date(2026, 10, 29), "10:00", [], "user", repeat="month",
                              now=dt.datetime(2026, 9, 28, 9, 0))
        self.assertFalse(self.app.nudge.tick(TUE_EVENING))
        self.assertEqual(self.llm.calls, [])
        self.assertIn("· nudged 2026-09-29 20:00 · Car service", self.threads())
        self.assertIn("nudge skipped, the calendar has it", self.app.engine.memory._git("log", "-1", "--format=%s").stdout)
        self.assertIn("the calendar has it (Car service appointment)", self.app.life.state["life_log"][-1]["detail"])

    def test_off_means_off(self):
        self.app.cfg.nudge_enabled = False
        self.assertFalse(self.app.nudge.tick(TUE_EVENING))
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(kp.THREADS, "system/threads.md")


if __name__ == "__main__":
    unittest.main()
