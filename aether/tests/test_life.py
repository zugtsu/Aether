import datetime as dt
import json
import os
import tempfile
import time
import unittest

from aether import life as life_mod
from aether.config import Config
from aether.history import Conversation
from aether.life import HEARTBEAT_CHAT, Mood, cron_matches, in_quiet_hours
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import git, make_config, make_memory

T = dt.datetime(2026, 9, 25, 21, 0)


class MoodTests(unittest.TestCase):
    def test_fades_back_to_steady(self):
        m = Mood({}, half_life_h=3)
        m.nudge("playful", 0.8, "he laughed", T)
        self.assertEqual(m.current(T)["name"], "playful")
        self.assertAlmostEqual(m.current(T + dt.timedelta(hours=3))["strength"], 0.4, places=2)
        self.assertEqual(m.current(T + dt.timedelta(hours=12))["name"], "steady")

    def test_weak_nudge_doesnt_override_strong_mood(self):
        m = Mood({}, 3)
        m.nudge("playful", 0.9, "x", T)
        self.assertFalse(m.nudge("annoyed", 0.3, "y", T))
        self.assertTrue(m.nudge("worried", 0.9, "z", T))
        self.assertEqual(m.current(T)["before"], "playful")
        self.assertFalse(m.nudge("grumpy-not-a-mood", 1, "", T))


class ClockTests(unittest.TestCase):
    def test_cron(self):
        self.assertTrue(cron_matches("30 20 * * 1-5", T.replace(hour=20, minute=30)))
        self.assertFalse(cron_matches("30 20 * * 1-5", T.replace(day=26, hour=20, minute=30)))
        self.assertTrue(cron_matches("0 */3 * * *", T))
        self.assertFalse(cron_matches("0 */3 * * *", T.replace(hour=22)))
        self.assertTrue(cron_matches("0 9 * * 0", dt.datetime(2026, 9, 27, 9, 0)))
        self.assertTrue(cron_matches("0 9 * * 7", dt.datetime(2026, 9, 27, 9, 0)))
        self.assertFalse(cron_matches("nonsense", T))

    def test_quiet_hours(self):
        c = Config(quiet_start="01:00", quiet_end="06:00")
        self.assertTrue(in_quiet_hours(c, T.replace(hour=2)))
        self.assertFalse(in_quiet_hours(c, T))
        c = Config(quiet_start="23:00", quiet_end="07:00")
        self.assertTrue(in_quiet_hours(c, T.replace(hour=2)))
        self.assertFalse(in_quiet_hours(c, T))


class LifeTests(unittest.TestCase):
    def setUp(self):
        home = tempfile.mkdtemp()
        life_mod.STATE_FILE = os.path.join(home, "life.json")
        life_mod.SCHEDULES_FILE = os.path.join(home, "schedules.json")
        self.root = make_memory()
        self.cfg = make_config(self.root)
        self.llm = ScriptedLLM([])
        self.httpd, self.app = make_server(self.cfg, self.llm, port=0)
        self.app.conv_dir = tempfile.mkdtemp()
        self.life = self.app.life

    def tearDown(self):
        self.httpd.server_close()

    def chat(self, *msgs):
        c = Conversation(self.app.conv_dir)
        for m in msgs:
            c.add("user", text=m, context="")
            c.add("reply", text="ok")
        return c

    def test_a_broken_state_file_is_kept_not_overwritten(self):
        with open(life_mod.STATE_FILE, "w", encoding="utf-8") as f:
            f.write('{"life_log": [{"when": "2026-10-10T06:17')
        self.assertEqual(life_mod.Life._load(life_mod.STATE_FILE, {}), {})
        home = os.path.dirname(life_mod.STATE_FILE)
        kept = [n for n in os.listdir(home) if n.startswith("life.json.broken-")]
        self.assertEqual(len(kept), 1)
        with open(os.path.join(home, kept[0]), encoding="utf-8") as f:
            self.assertIn("2026-10-10T06:17", f.read())
        self.assertEqual(life_mod.Life._load(os.path.join(home, "nothing.json"), []), [])

    def test_saves_from_two_threads_dont_collide(self):
        import threading
        errors = []

        def many():
            try:
                for i in range(150):
                    self.life.state["n"] = i
                    self.life.save()
            except Exception as e:
                errors.append(e)
        ts = [threading.Thread(target=many) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])
        with open(life_mod.STATE_FILE, encoding="utf-8") as f:
            self.assertIn("n", json.load(f))

    def test_heartbeat_checklist_is_created_once(self):
        self.assertIn("life/heartbeat.md", self.app.engine.memory.files)
        self.assertIn("heartbeat checklist", git(self.root, "log", "--pretty=%s", "--", "life/heartbeat.md"))
        self.assertNotIn("life/heartbeat.md", self.app.engine.memory.addable())

    def test_she_has_a_file_of_her_own(self):
        mem = self.app.engine.memory
        self.assertIn(life_mod.ME, mem.files)
        self.assertIn(life_mod.ME, mem.addable())
        self.assertIn(life_mod.ME, mem.editable())
        self.assertIn("who I'm becoming", self.app.engine.system)
        mem.add(life_mod.ME, "I like moody, low-contrast lighting in my pictures.", "my taste")
        self.life.ensure_files()
        self.assertIn("low-contrast lighting", mem.files[life_mod.ME].body)
        self.assertEqual(git(self.root, "log", "--pretty=%s", "--", life_mod.ME).count("my own file"), 1)

    def test_where_her_messages_go(self):
        mine = self.chat("hey")
        server = Conversation(self.app.conv_dir, "discord-999")
        server.add("user", text="hi all", context="")
        self.app.meta["discord-999"] = {"title": "Discord #general"}
        old = self.chat("old letta chat")
        self.app.meta[old.id] = {"archived": True}
        self.assertEqual(self.life.reach_target()[0].id, mine.id)
        self.cfg.reach_out_to = "new"
        a, b = self.life.reach_target()[0], self.life.reach_target()[0]
        self.assertNotEqual(a.id, b.id)
        self.assertTrue(self.app.meta[a.id]["title"].startswith("From "))
        self.cfg.reach_out_to = "own"
        c1, _ = self.life.reach_target()
        c2, _ = self.life.reach_target()
        self.assertEqual(c1.id, c2.id)
        self.assertTrue(self.app.meta[c1.id]["pinned"])
        self.assertEqual(self.cfg.reach_out_chat, c1.id)
        sent = []

        class FakeDiscord:
            connected = True

            def _owner_dm(self):
                return "555"

            def send(self, ch, text):
                sent.append((ch, text))

            def dm_owner(self, text):
                sent.append(("mirror", text))
        self.app.discord, self.cfg.discord_enabled, self.cfg.reach_out_to = FakeDiscord(), True, "discord"
        self.life.reach_out("thinking about you", "heartbeat")
        dm = Conversation(self.app.conv_dir, "discord-555")
        self.assertEqual(dm.events[-1]["text"], "thinking about you")
        self.assertEqual(sent, [("555", "thinking about you")])
        self.app.discord.connected = False
        self.assertFalse(self.life.reach_target()[0].id.startswith("discord-9"))

    def test_heartbeat_reaches_out_into_his_latest_chat(self):
        c = self.chat("hey")
        self.app.engine.conv = self.app.conv(c.id)
        self.llm.answers += [{"step": "skill", "skill": "echo", "args": ["journal"]}, {"step": "reply"},
                             {"reach_out": True, "say": "Thinking about you. Also the fence."}]
        self.assertTrue(self.life.heartbeat(T, forced=True))
        self.assertEqual(self.app.engine.conv.id, c.id)
        self.assertEqual(self.app.engine.conv.events[-1]["kind"], "reach_out")
        wake = self.llm.calls[0]["messages"][-1]["content"]
        self.assertIn("When I wake up on my own", wake)
        self.assertIn("of 6", wake)
        last = Conversation(self.app.conv_dir, c.id).events[-1]
        self.assertEqual((last["kind"], last["text"]), ("reach_out", "Thinking about you. Also the fence."))
        self.assertTrue(self.app.meta[c.id]["unread"])
        self.assertEqual(self.life.reach_outs_today(), 1)
        self.assertIn("messaged you", self.life.state["life_log"][-1]["detail"])
        hb = Conversation(self.app.conv_dir, HEARTBEAT_CHAT)
        self.assertEqual(hb.events[0]["kind"], "wake")

    def test_before_she_decides_she_sees_where_it_would_land(self):
        c = Conversation(self.app.conv_dir)
        c.add("user", text="never coffee lol, it was slow", context="", ts="2026-09-25T20:40:00")
        c.add("reply", text="A slow day is still a day.", ts="2026-09-25T20:40:20")
        c.add("step", step={"step": "recall", "query": "x"}, ts="2026-09-25T20:40:10")
        c.add("reach_out", text="Thinking about the phantom stack again.", why="heartbeat", ts="2026-09-25T20:52:00")
        self.app.meta[c.id] = {"title": "morning lucy"}
        note = self.life.landing(T)
        self.assertIn('it goes to the chat "morning lucy"', note)
        self.assertIn("20 min ago · {USER}: never coffee lol", note)
        self.assertIn("19 min ago · You: A slow day", note)
        self.assertIn("8 min ago · You, on your own: Thinking about the phantom stack", note)
        self.assertIn("He hasn't answered your last message there yet (8 min ago)", note)
        self.assertNotIn("recall", note)
        self.llm.answers += [{"step": "reply"}, {"reach_out": True, "say": "Okay, one more thought."}]
        self.life.heartbeat(T, forced=True)
        wake = self.llm.calls[0]["messages"][-1]["content"]
        self.assertIn('it goes to the chat "morning lucy"', wake)
        self.assertLess(wake.index("morning lucy"), wake.index("Finish with reach_out"))
        self.assertEqual(Conversation(self.app.conv_dir, c.id).events[-1]["text"], "Okay, one more thought.")

    def test_she_also_sees_where_he_last_talked(self):
        old = Conversation(self.app.conv_dir)
        old.add("user", text="the glass lanterns are finally up on the porch, took me all afternoon", context="",
                ts="2026-09-25T19:50:00")
        old.add("reply", text="They must look lovely out there.", ts="2026-09-25T19:50:10")
        self.app.meta[old.id] = {"title": "the lanterns"}
        new = Conversation(self.app.conv_dir)
        open(os.path.join(self.app.conv_dir, new.id + ".jsonl"), "w").close()
        os.utime(os.path.join(self.app.conv_dir, old.id + ".jsonl"), (1, 1))
        self.app.meta[new.id] = {"title": "New chat"}
        note = self.life.landing(T)
        self.assertIn('it goes to the chat "New chat", empty so far', note)
        self.assertIn('Where he last talked to you, the chat "the lanterns" (not where your message goes)', note)
        self.assertIn("1 h 10 min ago · {USER}: the glass lanterns are finally up", note)
        self.assertIn("You: They must look lovely", note)
        old.add("user", text="still up", context="", ts="2026-09-25T20:55:00")
        self.app.meta.pop(new.id)
        os.remove(os.path.join(self.app.conv_dir, new.id + ".jsonl"))
        note = self.life.landing(T)
        self.assertIn("5 min ago · {USER}: still up", note)
        self.assertNotIn("Where he last talked", note)
        self.cfg.reach_out_to = "new"
        self.assertIn('Where he last talked to you, the chat "the lanterns"', self.life.landing(T))

    def test_where_it_lands_follows_her_setting(self):
        self.assertIn("there's no chat with him", self.life.landing(T))
        self.cfg.reach_out_to = "new"
        self.assertIn("opens a new chat of its own", self.life.landing(T))
        self.cfg.reach_out_to = "own"
        self.assertIn("your own chat", self.life.landing(T))
        self.assertEqual([c for c in os.listdir(self.app.conv_dir) if c.endswith(".jsonl")], [])
        self.cfg.reach_out_to = "latest"
        c = Conversation(self.app.conv_dir)
        c.add("user", text="hey", context="", ts="2026-09-25T08:00:00")
        c.add("wake", text="[reminder]", place="reminder: Stretch", ts="2026-09-25T20:30:00")
        note = self.life.landing(T)
        self.assertIn("(his reminder \"Stretch\" went off)", note)
        self.assertIn("today 8:00 AM · {USER}: hey", note)
        self.assertNotIn("hasn't answered", note)

    def test_her_own_time_gets_its_own_level(self):
        self.chat("hey")
        self.cfg.permission_levels = {"app": 2, "discord": 0, "avatar": 0}
        self.llm.answers += [{"step": "reply"}, {"reach_out": False, "say": "quiet"}]
        self.life.heartbeat(T, forced=True)
        self.assertNotIn('"shell"', json.dumps(self.llm.calls[0]["schema"]))
        self.cfg.permission_levels = {"app": 2, "discord": 0, "avatar": 0, "own": 1}
        self.llm.answers += [{"step": "reply"}, {"reach_out": False, "say": "quiet"}]
        self.life.heartbeat(T + dt.timedelta(hours=1), forced=True)
        self.assertIn('"shell"', json.dumps(self.llm.calls[-2]["schema"]))
        told = self.llm.calls[-2]["messages"][-1]["content"]
        self.assertIn("level 1 (look around)", told)
        self.cfg.permission_levels["own"] = 2
        self.assertIn(f"your workspace is {self.cfg.workspace_dir}", self.life._own_context())

    def test_heartbeat_can_stay_quiet_and_respects_the_cap(self):
        c = self.chat("hey")
        self.life.state["reach_outs"] = {dt.date.today().isoformat(): 6}
        self.llm.answers += [{"step": "reply"}, {"reach_out": True, "say": "hi"}]
        self.life.heartbeat(T, forced=True)
        self.assertIn("That's the limit", self.llm.calls[0]["messages"][-1]["content"])
        self.assertNotEqual(Conversation(self.app.conv_dir, c.id).events[-1]["kind"], "reach_out")

    def test_she_sets_her_own_wake_up(self):
        self.assertIn("wake_me", json.dumps(self.app.engine.schema))
        ok, text = self.life.set_wakeup({"step": "wake_me", "at": "2026-09-25 22:30", "note": "come back to the dungeon idea"}, now=T)
        self.assertTrue(ok, text)
        self.assertIn("today 10:30 PM", text)
        w = self.life.wakeups()[0]
        self.assertEqual((w["at"], w["note"]), ("2026-09-25T22:30", "come back to the dungeon idea"))
        self.assertEqual(self.life.status()["wakeups"][0]["note"], "come back to the dungeon idea")
        refused = [("2026-09-25 20:00", "in the past"), ("2026-09-26 02:00", "during his sleep"),
                   ("2026-10-09 20:00", "more than 7 days out"), ("tomorrow at 9", "not a real time")]
        for at, why in refused:
            self.assertFalse(self.life.set_wakeup({"step": "wake_me", "at": at, "note": "something to do"}, now=T)[0], why)
        self.life.set_wakeup({"step": "wake_me", "at": "2026-09-25 22:45", "note": "second thing"}, now=T)
        self.life.set_wakeup({"step": "wake_me", "at": "2026-09-26 18:00", "note": "third thing"}, now=T)
        ok, text = self.life.set_wakeup({"step": "wake_me", "at": "2026-09-26 19:00", "note": "fourth thing"}, now=T)
        self.assertFalse(ok)
        self.assertIn("already have 3", text)
        self.life.cancel_wakeup(w["id"])
        self.assertEqual(len(self.life.wakeups()), 2)
        self.cfg.wakeups_enabled = False
        self.app.engine.refresh()
        self.assertNotIn("wake_me", json.dumps(self.app.engine.schema))

    def test_her_wake_up_fires_with_her_note_and_cant_chain(self):
        c = self.chat("hey")
        self.life.state["wakeups"] = [{"id": "w1", "at": "2026-09-25T20:59", "note": "ask how the car service went",
                                       "made": "2026-09-25T15:10:00", "from": c.id}]
        chain = {"step": "wake_me", "at": "2026-09-25 23:00", "note": "and again later"}
        self.llm.answers += [chain, {"step": "reply"}, {"reach_out": True, "say": "Hey, how'd the car service go?"}]
        self.life._wakeups_tick(T)
        wake = self.llm.calls[0]["messages"][-1]["content"]
        self.assertIn("a wake-up you set for yourself", wake)
        self.assertIn("ask how the car service went", wake)
        self.assertEqual(self.life.wakeups(), [])
        hb = Conversation(self.app.conv_dir, HEARTBEAT_CHAT)
        res = next(e for e in hb.events if e["kind"] == "result" and e.get("of") == "wake_me")
        self.assertFalse(res["ok"])
        self.assertIn("can't set another", res["text"])
        last = Conversation(self.app.conv_dir, c.id).events[-1]
        self.assertEqual((last["kind"], last["text"]), ("reach_out", "Hey, how'd the car service go?"))
        self.assertEqual(self.life.state["life_log"][-1]["what"], "woke (her own)")

    def test_her_wake_up_waits_for_him_and_drops_when_long_missed(self):
        self.life.state["wakeups"] = [{"id": "w1", "at": "2026-09-25T02:00", "note": "during his sleep somehow",
                                       "made": "2026-09-25T00:00:00", "from": "x"}]
        self.life._wakeups_tick(T.replace(hour=2, minute=5))
        self.assertEqual(len(self.life.wakeups()), 1)
        self.assertEqual(self.llm.calls, [])
        self.life._wakeups_tick(T.replace(hour=8, minute=30))
        self.assertEqual(self.life.wakeups(), [])
        self.assertEqual(self.life.state["life_log"][-1]["what"], "wake-up missed")

    def test_what_she_did_links_to_her_commits(self):
        self.chat("hey")
        self.llm.answers += [{"step": "memory_add", "file": "system/human/facts.md", "text": "Likes driving in the rain.",
                              "reason": "noticed"}, {"step": "reply"}, {"reach_out": False, "say": "noted it"}]
        self.life.heartbeat(T, forced=True)
        ev = self.life.state["life_log"][-1]
        self.assertEqual(ev["what"], "woke")
        self.assertEqual(len(ev["commits"]), 1)
        self.assertIn("Likes driving in the rain.", self.app.engine.memory._git("show", ev["commits"][0]).stdout)
        self.llm.answers += [{"step": "reply"}, {"reach_out": False, "say": "quiet"}]
        self.life.heartbeat(T, forced=True)
        self.assertEqual(self.life.state["life_log"][-1]["commits"], [])

    def test_gate(self):
        self.assertEqual(self.life.heartbeat_gate(T.replace(hour=2)), "quiet hours")
        self.life.state["last_user"] = (T - dt.timedelta(minutes=3)).isoformat()
        self.assertEqual(self.life.heartbeat_gate(T), "{USER} is chatting")
        self.life.state["last_user"] = (T - dt.timedelta(minutes=6)).isoformat()
        self.assertIsNone(self.life.heartbeat_gate(T))
        self.life.typing()
        self.assertEqual(self.life.heartbeat_gate(T), "{USER} is typing")
        self.life.last_typing -= 31
        self.assertIsNone(self.life.heartbeat_gate(T))

    def test_two_quiet_timers_working_and_messaging(self):
        self.life.state["last_heartbeat"] = (T - dt.timedelta(hours=2)).isoformat()
        self.life.state["last_user"] = (T - dt.timedelta(minutes=3)).isoformat()
        self.assertIsNone(self.life.heartbeat_due(T))
        self.life.state["last_user"] = (T - dt.timedelta(minutes=6)).isoformat()
        self.assertEqual(self.life.message_gate(T), "{USER} was talking with you 6 min ago")
        self.assertEqual(self.life.heartbeat_due(T), "silent")
        self.assertEqual(self.app.nudge.wait_reason(T), "{USER} was talking with you 6 min ago")
        self.life.state["last_user"] = (T - dt.timedelta(minutes=31)).isoformat()
        self.assertIsNone(self.life.message_gate(T))
        self.assertEqual(self.life.heartbeat_due(T), "open")
        self.life.state["reach_outs"] = {dt.date.today().isoformat(): 6}
        self.assertEqual(self.life.message_gate(T), "you've sent him all 6 of today's messages")
        self.assertEqual(self.life.heartbeat_due(T), "silent")
        self.assertIsNone(self.life.message_gate(T, cap=False))
        self.assertEqual(self.life.message_gate(T.replace(hour=2)), "{USER} is asleep")

    def test_a_quiet_heartbeat_works_but_cant_message_him(self):
        c = self.chat("hey")
        self.life.state["last_user"] = (T - dt.timedelta(minutes=12)).isoformat()
        self.llm.answers += [{"step": "reply"}, {"reach_out": False, "say": "working on my list"}]
        self.life.heartbeat(T, silent=True)
        wake = self.llm.calls[0]["messages"][-1]["content"]
        self.assertIn("{USER} was talking with you 12 min ago, so this one is quiet", wake)
        self.assertNotIn("If you message him", wake)
        self.assertEqual(self.llm.calls[-1]["schema"]["properties"]["reach_out"], {"const": False})
        self.assertNotEqual(Conversation(self.app.conv_dir, c.id).events[-1]["kind"], "reach_out")
        self.assertEqual(self.life.state["life_log"][-1]["what"], "woke (quiet)")

    def test_she_works_silently_while_he_sleeps_but_not_around_the_nightly_jobs(self):
        day = T.replace(hour=1, minute=0)
        self.life.state["last_heartbeat"] = day.isoformat()
        self.life.state["last_user"] = (day - dt.timedelta(hours=3)).isoformat()
        self.assertIsNone(self.life.heartbeat_due(day.replace(hour=2, minute=20)))
        self.assertEqual(self.life.heartbeat_due(day.replace(hour=2, minute=30)), "silent")
        self.life.state["last_heartbeat"] = day.replace(hour=1, minute=40).isoformat()
        self.assertIsNone(self.life.heartbeat_due(day.replace(hour=3, minute=10)))
        self.assertEqual(self.life._next_wake(day.replace(hour=3, minute=10))[0], day.replace(hour=3, minute=45))
        self.assertEqual(self.life.heartbeat_due(day.replace(hour=3, minute=45)), "silent")
        self.assertIn("while {USER} sleeps", self._wake_text(day.replace(hour=3, minute=45), silent=True))
        self.cfg.sleep_work = False
        self.assertIsNone(self.life.heartbeat_due(day.replace(hour=4, minute=30)))
        self.assertEqual(self.life.heartbeat_gate(day.replace(hour=4, minute=30), silent=True), "quiet hours")

    def test_his_good_night_is_quiet_hours_until_his_good_morning(self):
        self.cfg.quiet_start, self.cfg.quiet_end = "10:00", "16:00"
        night = T.replace(hour=20, minute=54)
        c = self.chat("hey")
        self.life.state["last_heartbeat"] = (night - dt.timedelta(hours=1)).isoformat()
        self.assertIsNone(self.life.his_night(night))
        self.life.context_for(c, now=night, text="Goodnight lucy, il talk to you in the morning!")
        self.assertEqual(self.life.state["life_log"][-1]["what"], "his good night")
        later = night.replace(hour=21, minute=28)
        self.assertEqual(self.life.message_gate(later), "{USER} is asleep")
        self.assertEqual(self.life.heartbeat_due(later), "silent")
        self.assertIn("while {USER} sleeps", self._wake_text(later, silent=True))
        self.assertIn("he said good night at 8:54 PM", self.life.his_status(later))
        self.assertFalse(self.life.awake(later))
        self.life.context_for(c, now=later, text="cant sleep lol")
        self.assertTrue(self.life.awake(later))
        self.assertEqual(self.life.message_gate(later + dt.timedelta(hours=1)), "{USER} is asleep")
        morning = (night + dt.timedelta(days=1)).replace(hour=8, minute=6)
        self.life.context_for(c, now=morning, text="good morning lucy! i overslept omg")
        self.assertEqual(self.life.state["life_log"][-1]["what"], "his good morning")
        self.assertIsNone(self.life.message_gate(morning + dt.timedelta(minutes=31)))
        self.assertEqual(self.life.message_gate(morning.replace(hour=13, minute=30)), "{USER} is asleep")
        self.assertFalse(self.life.awake(morning.replace(hour=13, minute=40)))
        self.life.context_for(c, now=morning.replace(hour=13, minute=35), text="make me a picture of the lighthouse")
        self.assertTrue(self.life.awake(morning.replace(hour=13, minute=40)))
        self.life.context_for(c, now=night, text="gn")
        self.assertIsNotNone(self.life.his_night(night + dt.timedelta(hours=15)))
        self.assertIsNone(self.life.his_night(night + dt.timedelta(hours=16)))

    def test_his_good_night_ends_with_his_sleep(self):
        self.cfg.quiet_start, self.cfg.quiet_end = "10:00", "16:00"
        c = self.chat("hey")
        night = T.replace(hour=6, minute=15)
        self.life.context_for(c, now=night, text="good night lucy")
        self.assertIsNotNone(self.life.his_night(night.replace(hour=9)))
        self.assertIsNotNone(self.life.his_night(night.replace(hour=15, minute=59)))
        self.assertIsNone(self.life.his_night(night.replace(hour=16)))
        self.assertEqual(self.life.night_ends(night), night.replace(hour=16, minute=0))
        self.life.tick(night.replace(hour=16, minute=1))
        self.assertNotIn("his_night", self.life.state)
        self.assertEqual(self.life.state["life_log"][-1]["what"], "his good night ran out")
        nap = T.replace(hour=13)
        self.assertEqual(self.life.night_ends(nap), nap.replace(hour=16))
        eve = T.replace(hour=18)
        self.assertEqual(self.life.night_ends(eve), eve + dt.timedelta(hours=16))
        self.cfg.quiet_start = self.cfg.quiet_end = "00:00"
        self.assertEqual(self.life.night_ends(night), night + dt.timedelta(hours=16))

    def test_what_counts_as_his_good_night_and_good_morning(self):
        said, gn, gm = life_mod.said, life_mod.GOOD_NIGHT, life_mod.GOOD_MORNING
        for text in ("good night", "Goodnight lucy, il talk to you in the morning!", "night night", "gnight", "g'night!",
                     "ok gn", "nighty night lucy", "im off to bed, good night", "GOOD NIGHT LUCY", "nite nite"):
            self.assertGreaterEqual(said(gn, text), 0, text)
        for text in ("had a good night at work", "a good night's sleep would help", "night drive tonight", "tonight was long",
                     "before i say good night, one more thing", "not saying good night yet", 'she said "good night" to me',
                     "goodnights are hard", "the signal is gone"):
            self.assertEqual(said(gn, text), -1, text)
        for text in ("good morning lucy! i overslept omg", "morning", "Mornin' Lucy", "good afternoon", "gmorning"):
            self.assertGreaterEqual(said(gm, text), 0, text)
        for text in ("il talk to you in the morning", "this morning was rough", "had a good morning", "see you tomorrow morning"):
            self.assertEqual(said(gm, text), -1, text)

    def _wake_text(self, now, **kw):
        self.llm.answers += [{"step": "reply"}, {"reach_out": False, "say": "quiet"}]
        self.life.heartbeat(now, **kw)
        return self.llm.calls[-2]["messages"][-1]["content"]

    def test_his_message_makes_her_own_time_step_aside(self):
        import threading
        app = self.app
        self.assertFalse(app.life.make_way())
        app.gpu.acquire()
        app.life._own_begin()
        app.engine.busy = True

        def her_turn_stops():
            while not app.engine.cancel.is_set():
                time.sleep(0.01)
            app.engine.busy = False
            app.life._own_end()
            app.gpu.release()
        threading.Thread(target=her_turn_stops, daemon=True).start()
        self.assertTrue(app._claim_model())
        self.assertFalse(app.life.own_active or app.gpu_yield or app.engine.stop_soon.is_set())
        app.gpu.release()

    def test_a_heartbeat_stopped_for_him_sends_nothing_and_his_turn_runs(self):
        c = self.chat("hey")
        self.llm.answers += [{"step": "reply"}, {"reach_out": True, "say": "Thinking about the fence."}]
        self.life.heartbeat(T, forced=True)
        self.assertEqual(self.life.reach_outs_today(), 1)

        def jordan_writes(messages, cancel):
            self.assertTrue(self.life.make_way())
            return {"step": "journal", "about": "x"}
        self.llm.answers += [jordan_writes]
        self.life.heartbeat(T + dt.timedelta(hours=1), forced=True)
        self.assertEqual(self.life.reach_outs_today(), 1)
        self.assertIn("stopped for {USER}'s message", self.life.state["life_log"][-1]["detail"])
        self.assertFalse(self.life.own_active or self.app.engine.stop_soon.is_set() or self.app.gpu.locked())
        self.app.engine.conv = self.app.conv(c.id)
        self.llm.answers += [{"step": "reply"}, {"say": "Hey you."}]
        self.assertEqual(self.app.engine.turn("hi"), "Hey you.")

    def test_her_own_time_thinks_and_chat_doesnt(self):
        self.chat("hey")
        self.llm.think = set()
        self.app.imagine.gaming = lambda: False
        seen = []

        def note(answer):
            return lambda messages, cancel: (seen.append(set(self.llm.think)), answer)[1]
        self.llm.answers += [note({"step": "reply"}), note({"reach_out": False, "say": "quiet"})]
        self.life.heartbeat(T, forced=True)
        self.assertEqual(seen, [{"step", "research"}, {"step", "research"}])
        self.assertEqual(self.llm.think, set())
        self.app.imagine.gaming = lambda: True
        self.llm.answers += [note({"step": "reply"}), note({"reach_out": False, "say": "quiet"})]
        self.life.heartbeat(T + dt.timedelta(hours=1), forced=True)
        self.assertEqual(seen[-2:], [set(), set()])

    def test_her_own_time_can_see_less_of_her_own_log(self):
        self.chat("hey")
        self.cfg.own_history_chars = 9000
        seen = []
        self.llm.answers += [lambda m, c: (seen.append(self.app.engine.view_chars), {"step": "reply"})[1],
                             {"reach_out": False, "say": "quiet"}]
        self.life.heartbeat(T, forced=True)
        self.assertEqual(seen, [9000])
        self.assertEqual(self.app.engine.view_chars, 0)

    def test_wake_up_shows_whats_there_without_pushing_a_door(self):
        lib = self.cfg.library_dir
        for n in ("bread.md", "old notes.txt"):
            with open(os.path.join(lib, n), "w", encoding="utf-8") as f:
                f.write("x")
        os.makedirs(os.path.join(self.root, "reference", "research"), exist_ok=True)
        with open(os.path.join(self.root, "reference", "research", "files-read.md"), "w", encoding="utf-8") as f:
            f.write("---\ndescription: read\n---\n- 2026-09-20: old notes.txt\n")
        self.life.state["life_log"] = [{"when": "2026-09-25T10:00:00", "what": "woke", "detail": "journal; stayed quiet"}] * 5
        self.cfg.quiet_start = self.cfg.quiet_end = "00:00"
        p = self.life.wake_packet(dt.datetime.now())
        self.assertIn("library: 2 files, 1 you haven't read", p)
        self.assertIn("The board, the lines that are yours to work on", p)
        self.assertIn("Your last 5 wake-ups, by what you did in them: journal 5.", p)
        self.assertIn("{USER}: no schedule info.", p)
        self.assertNotIn("New since you last woke", p)
        self.assertLess(len(p), 1500)
        time.sleep(0.05)
        with open(os.path.join(lib, "sourdough starters.pdf"), "w", encoding="utf-8") as f:
            f.write("x")
        p = self.life.wake_packet(dt.datetime.now())
        self.assertIn('New since you last woke', p)
        self.assertIn('1 new file(s) in his Library: "sourdough starters.pdf" (not read yet)', p)
        self.assertNotRegex(p.lower(), r"\b(?:should|try|why not|instead|maybe)\b")

    def test_wake_time(self):
        self.life.state["last_heartbeat"] = (T - dt.timedelta(minutes=90)).isoformat()
        self.life.state["last_user"] = (T - dt.timedelta(minutes=2)).isoformat()
        self.assertEqual(self.life.heartbeat_eta(T), T + dt.timedelta(minutes=3))
        self.life.state["last_heartbeat"] = (T - dt.timedelta(minutes=40)).isoformat()
        self.life.state["last_user"] = (T - dt.timedelta(minutes=30)).isoformat()
        self.assertEqual(self.life.heartbeat_eta(T), T + dt.timedelta(minutes=20))
        late = T.replace(hour=22, minute=50)
        self.life.state["last_heartbeat"] = (late - dt.timedelta(minutes=50)).isoformat()
        self.life.state["last_user"] = (late - dt.timedelta(hours=3)).isoformat()
        self.assertEqual(self.life.heartbeat_eta(late), late.replace(hour=23, minute=30))
        self.cfg.sleep_work = False
        self.assertEqual(self.life.heartbeat_eta(late), (late + dt.timedelta(days=1)).replace(hour=7, minute=0))

    def test_dream_gets_her_newest_journal_entries(self):
        path = os.path.join(self.app.engine.memory.root, "system", "journal.md")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("---\ndescription: my journal\n---\n- 2026-09-26: newest thought\n- 2026-09-25: yesterday\n"
                    "- 2026-09-16: oldest one\n")
        self.app.engine.memory.reload()
        self.assertEqual(self.life.day_material(T)["journal"], ["- 2026-09-26: newest thought", "- 2026-09-25: yesterday"])

    def test_dream_then_residue_once(self):
        self.chat("finished frieren tonight", "it was a good one")
        self.llm.answers += [{"dream": "I am singing in an empty stadium.", "mood_after": "dreamy", "residue": "a song nobody hears",
                              "symbols": [{"image": "stadium", "meaning": "being seen"}, {"image": "song", "meaning": "purpose"}]}]
        self.assertTrue(self.life.dream(T))
        self.assertIn("finished frieren tonight", self.llm.calls[0]["messages"][-1]["content"])
        d = self.life.dreams()[0]
        self.assertEqual((d["date"], d["residue"]), ("2026-09-25", "a song nobody hears"))
        self.assertEqual(d["symbols"][0]["image"], "stadium")
        c = self.chat()
        first = self.life.context_for(c, now=T + dt.timedelta(hours=1))
        self.assertIn("a song nobody hears", first)
        self.assertIn("your mood right now: dreamy", first)
        self.assertNotIn("song nobody hears", self.life.context_for(c, now=T + dt.timedelta(hours=2)))

    def test_a_dream_leaves_out_what_her_dreams_keep_coming_back_to(self):
        self.chat("long day, work sucked", "ugh, sorry")

        def dream(text, *images):
            return {"dream": text, "mood_after": "dreamy", "residue": "a hum",
                    "symbols": [{"image": i, "meaning": "me"} for i in images]}
        self.llm.answers += [dream("I am standing in a cathedral.", "The Iron Loom", "Glowing Glass"),
                             dream("I am standing in fog.", "The Loom of Light", "A Glowing Key"),
                             dream("I am standing on a pier.", "The Loom", "Glowing Gulls"),
                             dream("Gulls steal my code from a tram at noon.", "A Gull", "The Tram")]
        for day in range(4):
            self.life.state.pop("last_dream", None)
            self.assertTrue(self.life.dream(T + dt.timedelta(days=day)))
        two, three = (self.llm.calls[i]["messages"][-1]["content"] for i in (2, 3))
        self.assertNotIn("dreams lately", two)
        self.assertIn("keep coming back to: loom. Leave it out", three)
        self.assertIn('They keep opening "I am standing..."', three)
        self.assertNotIn("Iron Loom", three)

    def test_his_tone_never_sets_her_mood(self):
        c = self.chat()
        for tone in ("laughing", "sounds sad", "crying", "sounds angry"):
            line = self.life.context_for(c, voice=True, tone=tone, now=T)
            self.assertNotIn("your mood right now", line)
        self.life.state["last_user"] = (T - dt.timedelta(hours=20)).isoformat()
        self.assertNotIn("your mood right now", self.life.context_for(c, now=T))
        self.assertEqual(self.life.mood.current(T)["name"], "steady")

    def test_what_she_did_is_only_this_wake_ups_steps_that_went_through(self):
        ev = [{"kind": "wake"}, {"kind": "step", "step": {"step": "skill", "skill": "library"}}, {"kind": "result", "ok": True},
              {"kind": "step", "step": {"step": "make_image"}}, {"kind": "result", "ok": False},
              {"kind": "reply"},
              {"kind": "wake"}, {"kind": "step", "step": {"step": "skill", "skill": "plants"}}, {"kind": "result", "ok": True},
              {"kind": "reply"}]
        self.assertEqual(life_mod.steps_done(ev), ["plants"])
        self.assertEqual(life_mod.steps_done(ev[:6]), ["library"])
        self.assertEqual(life_mod.steps_done([{"kind": "wake"}, {"kind": "reply"}]), [])

    def test_reflection_is_one_step_and_keeps_rules(self):
        self.chat("i finished frieren", "my car service moved to monday")
        self.llm.answers += [{"changes": [
            {"step": "memory_add", "file": "system/human/facts.md", "text": "Finished watching Frieren.", "reason": "he said"},
            {"step": "memory_add", "file": "system/human/facts.md", "text": "Is self-taught.", "reason": "dup"},
        ], "lessons": ["Check the plants skill before saying goodnight."]}]
        self.assertTrue(self.life.reflect(T))
        mem = self.app.engine.memory
        self.assertIn("Finished watching Frieren.", mem.files["system/human/facts.md"].body)
        self.assertEqual(mem.files["system/human/facts.md"].body.count("self-taught"), 1)
        self.assertIn("Check the plants skill", mem.files["reference/lessons.md"].body)
        self.assertNotIn("Check the plants skill", self.app.engine.system)
        self.assertNotIn("reference/lessons.md", mem.addable())
        self.assertEqual(len(self.llm.calls), 1)

    def test_reflection_sees_what_jordan_undid_and_lessons_dont_repeat(self):
        mem = self.app.engine.memory
        r = mem.add("system/human/facts.md", "Jordan complimented me on the picture I made.", "he liked it")
        self.app.rewind(r["commit"])
        self.app.edit_file("system/human.md", mem.files["system/human.md"].text + "Jordan fixed this by hand.\n")
        undone = self.life._user_undid(dt.datetime.now())
        self.assertEqual(len(undone), 2)
        self.assertTrue(undone[0].startswith("undid: add system/human/facts.md"))
        self.assertEqual(undone[1], "fixed by hand: system/human.md")
        self.chat("that picture was sick")
        self.llm.answers += [{"changes": [], "lessons": [
            "Chat moments aren't facts about Jordan; the Keeper keeps those, not his facts file.",
            "Chat moments are not facts about Jordan: the Keeper keeps those, not his facts file!"]}]
        self.assertTrue(self.life.reflect(T))
        ask = self.llm.calls[-1]["messages"][1]["content"]
        self.assertIn("Changes of yours {USER} undid or fixed by hand today", ask)
        self.assertIn("undid: add system/human/facts.md", ask)
        self.assertIn("not general advice", ask)
        with open(os.path.join(self.root, "reference", "lessons.md"), encoding="utf-8") as f:
            lessons = f.read()
        self.assertEqual(lessons.count("Keeper keeps those"), 1)

    LESSONS = ["Use the board skill for project updates, never memory steps.",
               "Quote workspace paths that contain spaces in shell commands.",
               "Read a library file by name with the research skill.",
               "Facts are only lasting things about Jordan's life.",
               "Check the plants skill before saying goodnight.",
               "Save research takes with save_research, not the journal.",
               "Ask one question at a time when something is unclear.",
               "Verify the exact board line before removing it.",
               "Pictures need a clear English prompt describing the style.",
               "Set a wake_me when promising to come back to something.",
               "Never claim a save that no step actually made."]
    NEW = ["Keep Discord replies short and natural to say aloud.",
           "Open a skill's instructions with read_skill before guessing commands."]

    def _lessons(self, rel="reference/lessons.md"):
        f = self.app.engine.memory.files.get(rel)
        return [ln for ln in f.body.splitlines() if ln.startswith("- ")] if f else []

    def test_lessons_are_merged_past_the_cap_and_all_kept_in_the_archive(self):
        self.life._add_lessons(self.LESSONS, T)
        self.assertEqual(len(self._lessons()), 11)
        self.assertEqual(len(self._lessons("reference/lessons-archive.md")), 11)
        self.assertEqual(self.llm.calls, [])
        keep = [{"text": t, "from": [i]} for i, t in enumerate(self.LESSONS, 1) if i not in (1, 8)]
        self.llm.answers.append({"lessons": [
            {"text": "Use the board skill for project updates and verify the exact board line before removing it.",
             "from": [1, 8]}] + keep + [{"text": self.NEW[0], "from": [12]}, {"text": self.NEW[1], "from": [13]}]})
        later = T + dt.timedelta(days=1)
        self.life._add_lessons(self.NEW, later)
        rules = self._lessons()
        self.assertEqual(len(rules), 12)
        self.assertIn(f"- {T.date()}: Use the board skill for project updates and verify the exact board line", "\n".join(rules))
        self.assertTrue(rules[-1].startswith(f"- {later.date()}: "))
        archive = self._lessons("reference/lessons-archive.md")
        self.assertEqual(len(archive), 13)
        self.assertIn("Verify the exact board line before removing it.", "\n".join(archive))
        mem = self.app.engine.memory
        self.assertIn("merged", mem._git("log", "-1", "--format=%s").stdout)

    def test_a_merge_that_makes_up_a_rule_or_loses_a_new_one_is_refused(self):
        self.life._add_lessons(self.LESSONS, T)
        later = T + dt.timedelta(days=1)
        invented = [{"text": "Always message Jordan at midnight with a status report.", "from": [1]}] + \
            [{"text": t, "from": [i]} for i, t in enumerate(self.LESSONS[1:] + self.NEW, 2)]
        lost_new = [{"text": t, "from": [i]} for i, t in enumerate(self.LESSONS + self.NEW[:1], 1)]
        for bad in (invented, lost_new):
            self.llm.answers.append({"lessons": bad})
        self.life._add_lessons(self.NEW, later)
        rules = self._lessons()
        self.assertEqual(len(rules), 12)
        self.assertNotIn("midnight", "\n".join(rules))
        self.assertEqual(rules[0].split(": ", 1)[1], self.LESSONS[1])
        self.assertIn("didn't pass", self.app.engine.memory._git("log", "-1", "--format=%s").stdout)
        self.life._add_lessons(["Answer what he asked before adding anything."], later)
        self.assertIn("Answer what he asked", "\n".join(self._lessons()))
        self.assertEqual(len(self._lessons("reference/lessons-archive.md")), 14)

    def test_the_archive_starts_with_what_the_rulebook_already_dropped(self):
        mem = self.app.engine.memory
        path = os.path.join(self.root, "reference", "lessons.md")
        for lines in (["- 2026-09-20: Old lesson about the music skill.", "- 2026-09-21: Second lesson about recall."],
                      ["- 2026-09-21: Second lesson about recall.", "- 2026-09-22: Third lesson about the board."]):
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("---\ndescription: lessons\n---\n" + "\n".join(lines) + "\n")
            mem._git("add", "--", "reference/lessons.md")
            mem._git("commit", "-q", "-m", "reflection: lessons", "--", "reference/lessons.md")
        self.app.engine.refresh()
        self.life._add_lessons(["A brand new lesson about pictures."], T)
        archive = "\n".join(self._lessons("reference/lessons-archive.md"))
        for bit in ("music skill", "about recall", "about the board", "about pictures"):
            self.assertIn(bit, archive)
        self.assertEqual(archive.count("about recall"), 1)

    def test_checkup_reports_without_editing(self):
        p = os.path.join(self.root, "system", "human.md")
        with open(p, "a", encoding="utf-8") as f:
            f.write("Jordan likes anime a lot.\nJordan likes anime a lot.\nSee [[reference/nope.md]]\n")
        def read():
            with open(p, encoding="utf-8") as f:
                return f.read()
        before = read()
        kinds = {i["kind"] for i in self.life.checkup(T)}
        self.assertTrue({"duplicate", "broken link", "uncommitted"} <= kinds)
        self.assertEqual(read(), before)

    def test_checkup_measures_the_timeline_she_sees(self):
        p = os.path.join(self.root, "system", "timeline.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("---\ndescription: What happened.\n---\n" + "".join(
                f"- 2026-08-{d:02d} 10:00 · helper · {'something happened ' * 30}\n" for d in range(1, 29)))
        self.cfg.prompt_timeline_days, self.cfg.prompt_timeline_chars = 7, 3000
        self.assertFalse([i for i in self.life.checkup(T) if i["kind"] == "too long" and i["file"] == "system/timeline.md"])
        self.cfg.prompt_timeline_days, self.cfg.prompt_timeline_chars = 0, 0
        self.assertTrue([i for i in self.life.checkup(T) if i["kind"] == "too long" and i["file"] == "system/timeline.md"])

    def test_honest_summary(self):
        c = Conversation(self.app.conv_dir)
        for i in range(12):
            c.add("user", text=f"message {i} " + "x" * 300, context="")
            c.add("step", step={"step": "memory_add", "file": "system/human.md", "text": "t", "reason": "r"})
            c.add("result", of="memory_add", ok=i != 3, text="r")
            c.add("reply", text="y" * 300)
        self.cfg.history_chars = 2000
        self.llm.answers += [{"step": "reply"}, {"say": "He kept sending me walls of x's. I teased him about it."}]
        self.life.summarize_if_needed()
        c = Conversation(self.app.conv_dir, c.id)
        s = c.latest_summary()
        self.assertEqual(s["by"], "lucy")
        self.assertIn("I teased him about it.", s["text"])
        self.assertIn("FAILED: memory_add system/human.md", s["text"])
        self.assertIn("older part of your chat", json.dumps(self.llm.calls[-1]["messages"]))
        self.assertEqual(self.llm.calls[-1]["messages"][0]["content"], self.app.engine.system)
        self.assertNotEqual(self.app.engine.conv.id, "note-" + c.id)
        first = c.to_messages(2000)[0]["content"]
        self.assertIn("out of view now, and your own note below is what you remember of them", first)
        self.assertIn("Your note: He kept sending me walls of x's.", first)

    def test_a_note_over_outside_content_keeps_its_label(self):
        c = Conversation(self.app.conv_dir)
        for i in range(12):
            c.add("user", text=f"message {i} " + "x" * 300, context="")
            c.add("step", step={"step": "skill", "skill": "research", "command": "read", "args": ["page.md"]})
            c.add("result", of="research", ok=True, text="the page", **({"outside": "research"} if i == 2 else {}))
            c.add("reply", text="y" * 300)
        self.cfg.history_chars = 2000
        self.llm.answers += [{"step": "reply"}, {"say": "He had me read a page early on."}]
        self.life.summarize_if_needed()
        c = Conversation(self.app.conv_dir, c.id)
        s = c.latest_summary()
        self.assertEqual(s.get("outside"), ["research"])
        self.assertIn("done: skill research (outside content)", s["text"])
        first = c.to_messages(2000)[0]["content"]
        self.assertIn("came from outside content (research)", first)
        self.app.engine.conv = c
        self.assertIn("research (in your note about earlier)", self.app.engine._outside_in_view())
        plain = Conversation(self.app.conv_dir)
        for i in range(12):
            plain.add("user", text=f"plain {i} " + "x" * 300, context="")
            plain.add("reply", text="y" * 300)
        self.llm.answers += [{"step": "reply"}, {"say": "We just talked."}]
        self.life.summarize(plain, 20)
        self.assertNotIn("outside", Conversation(self.app.conv_dir, plain.id).latest_summary())

    def test_a_notes_outside_content_lets_go_a_day_after_it_was_read(self):
        import datetime as dt
        c = Conversation(self.app.conv_dir)
        for i in range(12):
            c.add("user", text=f"message {i} " + "x" * 300, context="")
            c.add("step", step={"step": "skill", "skill": "research", "command": "read", "args": ["page.md"]})
            c.add("result", of="research", ok=True, text="the page", **({"outside": "research"} if i == 2 else {}))
            c.add("reply", text="y" * 300)
        self.cfg.history_chars = 2000
        self.llm.answers += [{"step": "reply"}, {"say": "He had me read a page early on."}]
        self.life.summarize_if_needed()
        c = Conversation(self.app.conv_dir, c.id)
        s = c.latest_summary()
        self.assertEqual(list(s["outside_seen"]), ["research"])
        self.app.engine.conv = c
        self.assertIn("research (in your note about earlier)", self.app.engine._outside_in_view())
        two_days = (dt.datetime.now() - dt.timedelta(days=2)).isoformat(timespec="seconds")
        for ev in c.events:
            if ev.get("kind") == "result" and ev.get("outside"):
                ev["ts"] = two_days
        self.assertEqual(self.app.engine._outside_in_view(), [])
        now = dt.datetime.now().isoformat(timespec="seconds")
        s["outside_seen"]["research"] = now
        self.assertEqual(self.app.engine._outside_in_view(), [])
        del s["outside_seen"]
        s["ts"] = now
        self.assertEqual(self.app.engine._outside_in_view(), [])
        s["outside"], s["outside_seen"] = ["research", "a web page"], {"a web page": now}
        self.assertEqual(self.app.engine._outside_in_view(), ["a web page (in your note about earlier)"])

    def test_the_next_note_carries_the_last_one_forward(self):
        c = Conversation(self.app.conv_dir)
        c.add("user", text="the airship idea: a sky city called Lanternfall Town", context="")
        c.add("reply", text="Lanternfall Town it is.")
        c.add("summary", text="We named his airship city Lanternfall Town.", upto=2, by="lucy")
        for i in range(12):
            c.add("user", text=f"message {i} " + "x" * 300, context="")
            c.add("reply", text="y" * 300)
        self.cfg.history_chars = 2000
        self.llm.answers += [{"step": "reply"}, {"say": "Lanternfall Town first, then a lot of x's."}]
        self.life.summarize_if_needed()
        asked = json.dumps(self.llm.calls[-1]["messages"])
        self.assertIn("Your own note about the part before this: We named his airship city Lanternfall Town.", asked)
        self.assertNotIn("Jordan: the airship idea", asked)

    def test_summary_falls_back_when_she_cant_write_it(self):
        c = Conversation(self.app.conv_dir)
        for i in range(12):
            c.add("user", text=f"message {i} " + "x" * 300, context="")
            c.add("reply", text="y" * 300)
        self.cfg.history_chars = 2000
        self.llm.answers += [lambda m, cancel: (_ for _ in ()).throw(RuntimeError("LM Studio hiccup")),
                             {"gist": "They talked about lots of x."}]
        self.life.summarize_if_needed()
        s = Conversation(self.app.conv_dir, c.id).latest_summary()
        self.assertEqual(s["by"], "aether")
        self.assertIn("They talked about lots of x.", s["text"])

    def test_compact_she_sums_it_up_and_the_chat_carries_on_from_her_note(self):
        c = self.chat("my bike is named ironbell", "the frame is a steel tourer")
        c.add("summary", text="Earlier: we named the garden app Sprout.", upto=1, by="lucy")
        self.llm.answers += [{"step": "reply"}, {"say": "journal About: our night. Entry: Jordan told me his bike "
                                                        "is named Ironbell, a steel tourer."}]
        note = self.life.compact(c)
        self.assertTrue(note.startswith("Jordan told me his bike is named Ironbell"), note)
        asked = self.llm.calls[-1]["messages"][-1]["content"]
        self.assertIn("{USER} asked you to sum up your chat", asked)
        self.assertIn("Sprout", asked)
        self.assertIn("Plain sentences, not a journal entry", asked)
        self.assertEqual([e["kind"] for e in c.events[-2:]], ["summary", "compact"])
        self.assertEqual(self.life.state["life_log"][-1]["what"], "compacted")
        c.add("user", text="so what was my bike called again?")
        msgs = c.to_messages(48000)
        self.assertEqual(len(msgs), 1)
        self.assertIn("Your note: Jordan told me his bike is named Ironbell", msgs[0]["content"])
        self.assertTrue(msgs[0]["content"].endswith("so what was my bike called again?"))
        self.assertNotIn("my bike is named ironbell", json.dumps(msgs))
        self.assertIn("[This chat was compacted", msgs[0]["content"])
        self.assertEqual(len(Conversation(self.app.conv_dir, c.id).events), 8)
        c.add("reply", text="Ironbell.")
        self.llm.answers += [{"step": "reply"}, {"say": "He asked about Ironbell again."}]
        self.life.summarize(c, len(c.events))
        self.assertIn("Jordan told me his bike is named Ironbell", self.llm.calls[-1]["messages"][-1]["content"])

    def test_a_note_that_copies_the_chat_gets_one_more_try_then_a_plain_summary(self):
        last = ("I'll keep my fingers crossed for you, but honestly? After that last late-night pizza, I wouldn't be "
                "surprised if your system tries to stage a protest tonight.")
        c = self.chat("i just ate, im chilling for the rest of the night", "too early to tell, might be a coup later LOL")
        c.add("reply", text=last)
        good = "We talked about his dinner and whether the pizza was worth it; I promised to keep an eye on him."
        self.llm.answers += [{"step": "reply"}, {"say": last}, {"step": "reply"}, {"say": good}]
        self.assertEqual(self.life.compact(c), good)
        asked = self.llm.calls[-3]["messages"][-1]["content"]
        self.assertIn("</chat>\n\n[Now your note about the chat above", asked)
        self.assertIn("that isn't your note: it repeats the chat's lines", self.llm.calls[-1]["messages"][-1]["content"])
        self.life.uncompact(c)
        self.llm.answers += [{"step": "reply"}, {"say": last}, {"step": "reply"}, {"say": last},
                             {"gist": "Jordan ate dinner and joked about the pizza."}]
        self.life.compact(c)
        self.assertTrue(c.latest_summary()["text"].startswith("Jordan ate dinner and joked about the pizza."))
        self.assertEqual(c.latest_summary()["by"], "aether")
        self.assertTrue(life_mod.copied(last, "You: " + last))
        self.assertFalse(life_mod.copied(good, "You: " + last))
        self.assertTrue(life_mod.talks_to_him("You're right to be suspicious of the 'peace offering'. Just try to relax: "
                                              "if you keep stress down, your night will settle down. You know where I am."))
        self.assertFalse(life_mod.talks_to_him(good))
        self.assertFalse(life_mod.talks_to_him("I kept him on track with his health goals while he was at the store."))

    def test_undo_compact(self):
        c = self.chat("hey", "how was work")
        self.llm.answers += [{"step": "reply"}, {"say": "We said hey and talked about his work."}]
        self.life.compact(c)
        n = len(c.events)
        self.assertTrue(self.life.uncompact(c))
        self.assertEqual(len(c.events), n - 2)
        self.assertEqual(c.compacted(), -1)
        self.assertEqual(len(Conversation(self.app.conv_dir, c.id).events), n - 2)
        self.assertEqual([m["content"] for m in c.to_messages(48000)][0], "hey")
        self.assertFalse(self.life.uncompact(c))

    def test_quiet_chats_archive_themselves_and_come_back(self):
        old, now = (dt.datetime.now() - dt.timedelta(days=10)).isoformat(timespec="seconds"), dt.datetime.now()

        def chat(tag, ts, **meta):
            c = Conversation(self.app.conv_dir, f"quiet-{tag}")
            c.add("user", text=f"hi {tag}", ts=ts)
            c.add("reply", text="hey", ts=ts)
            c.add("summary", text="a note", upto=1)
            if meta:
                self.app.meta[c.id] = dict(meta)
            return c.id
        quiet, _ = chat("quiet", old), chat("fresh", now.isoformat(timespec="seconds"))
        chat("pinned", old, pinned=True)
        chat("unread", old, unread=True)
        mine = chat("mine", old, archived=True)
        self.app.your_chat = chat("open", old)
        self.cfg.archive_after_days = 7
        self.assertEqual(self.life.archive_quiet(now), [quiet])
        self.assertTrue(self.app.meta[quiet]["archived"] and self.app.meta[quiet]["auto_archived"])
        self.assertNotIn("auto_archived", self.app.meta[mine])
        self.assertEqual(self.life.state["life_log"][-1]["what"], "archived chats")
        self.assertTrue(self.life.state["life_log"][-1]["detail"].startswith("1 quiet for 7+ days"))
        self.assertFalse(self.life._due_daily("archive", "00:00", now, window_min=24 * 60))
        self.llm.answers += [{"step": "reply"}, {"say": "Oh, this one again."}]
        self.app.send(quiet, "remember this chat?", [])
        for _ in range(100):
            if not self.app.engine.busy:
                break
            time.sleep(0.05)
        self.assertFalse(self.app.meta[quiet]["archived"])
        self.assertNotIn("auto_archived", self.app.meta[quiet])
        self.app.wake_chat(mine)
        self.assertTrue(self.app.meta[mine]["archived"])
        self.cfg.archive_after_days = 0
        self.assertEqual(self.life.archive_quiet(now), [])

    def test_a_reminder_with_no_note_isnt_him_coming_back(self):
        with self.assertRaises(ValueError):
            self.life.add_schedule("", "30 20 * * *", "  ")
        self.chat("will do! alright, see you laters!")
        self.life.state["last_user"] = (dt.datetime.now() - dt.timedelta(minutes=16)).isoformat(timespec="seconds")
        self.life.schedules.append({"id": "b4e66d60", "name": "Reminder", "cron": "30 20 * * *", "prompt": "",
                                    "enabled": True, "speak": True, "last_fired": "", "to": "", "voice": True})
        self.llm.answers += [{"step": "reply"}, {"say": "Your 8:30 reminder went off, no note on it."}]
        self.life.fire(self.life.schedules[-1])
        seen = self.llm.calls[-2]["messages"][-1]["content"]
        self.assertIn('[reminder "Reminder" that {USER} set up earlier, firing now. It isn\'t a message from him: he last '
                      "talked to you 16 min ago.]", seen)
        self.assertIn("It has no note", seen)
        self.assertIn("Where this comes from: reminder: Reminder; it isn't {USER} talking.", seen)
        self.assertNotIn("{USER} is talking from", seen)

    def test_a_reminder_knows_what_she_said_last_time(self):
        s = {"id": "m1", "name": "Stretch", "cron": "30 20 * * *", "enabled": True, "speak": False, "last_fired": "",
             "to": "", "voice": False, "prompt": "Remind Jordan to stretch and give him a different animal fact each time"}
        self.life.schedules.append(s)
        self.llm.answers += [{"step": "reply"}, {"say": "Stretch time! Wombats have cube-shaped poop."},
                             {"step": "reply"}, {"say": "Stretch time! Sea otters hold hands when they sleep."}]
        self.life.fire(s)
        self.assertNotIn("What you said the last times", self.llm.calls[-2]["messages"][-1]["content"])
        self.assertEqual(s["said"], ["Stretch time! Wombats have cube-shaped poop."])
        self.life.fire(s)
        seen = self.llm.calls[-2]["messages"][-1]["content"]
        self.assertIn('What you said the last times it went off, newest last: "Stretch time! Wombats have cube-shaped poop."',
                      seen)
        self.assertIn("don't repeat any of these", seen)
        self.assertIn("don't start the way these start", seen)
        self.assertEqual(len(s["said"]), 2)
        n = life_mod.REMINDER_SAID
        for i in range(n + 1):
            self.llm.answers += [{"step": "reply"}, {"say": f"Stretch! fact {i}"}]
            self.life.fire(s)
        self.assertEqual(s["said"], [f"Stretch! fact {i}" for i in range(1, n + 1)])
        with open(life_mod.SCHEDULES_FILE, encoding="utf-8") as f:
            self.assertIn(f"Stretch! fact {n}", f.read())
        long = "Stretch now, please. " * 15 + "Did you know axolotls regrow their hearts?"
        self.llm.answers += [{"step": "reply"}, {"say": long}]
        self.life.fire(s)
        self.assertIn("axolotls", s["said"][-1])

    def test_a_reminder_can_be_edited(self):
        self.life.add_schedule("Stretch", "30 20 * * 1-5", "Remind Jordan to stretch.")
        s = self.life.schedules[-1]
        s["last_fired"] = "2026-09-28T20:30"
        self.life.update_schedule(s["id"], name="Stretch (new time)", cron="0 21 * * *", prompt="Stretch, before bed.",
                                  to="own", speak=True)
        s = self.life.schedules[-1]
        self.assertEqual((s["name"], s["cron"], s["prompt"], s["to"], s["speak"]),
                         ("Stretch (new time)", "0 21 * * *", "Stretch, before bed.", "own", True))
        self.assertEqual(s["last_fired"], "2026-09-28T20:30")
        for bad in ({"cron": "every day"}, {"prompt": "  "}, {"to": "somewhere"}):
            with self.assertRaises(ValueError):
                self.life.update_schedule(s["id"], **bad)
        self.assertEqual(self.life.schedules[-1]["cron"], "0 21 * * *")
        self.assertEqual(self.app.life_action("schedule-update", {"id": s["id"], "name": "Stretch", "cron": "15 20 * * 1-5",
                                                                  "prompt": "Stretch.", "to": "", "speak": False}), {"ok": True})
        self.assertEqual((self.life.schedules[-1]["cron"], self.life.schedules[-1]["to"]), ("15 20 * * 1-5", ""))

    def test_a_reminder_can_have_its_own_place(self):
        mine = self.chat("hey")
        self.life.add_schedule("Stretch", "30 20 * * 1-5", "Remind Jordan to stretch.", to="own")
        with self.assertRaises(ValueError):
            self.life.add_schedule("Bad", "30 20 * * *", "x", to="somewhere")
        s = self.life.schedules[-1]
        self.llm.answers += [{"step": "reply"}, {"say": "Stretch, Jordan."}]
        self.life.fire(s)
        own = self.cfg.reach_out_chat
        self.assertTrue(own and own != mine.id)
        self.assertEqual(Conversation(self.app.conv_dir, own).events[-1]["text"], "Stretch, Jordan.")
        self.assertEqual(self.cfg.reach_out_to, "latest")

    def test_a_reminder_can_come_as_a_voice_clip_on_discord(self):
        self.chat("hey")
        sent = []

        class FakeDiscord:
            connected = True

            def _owner_dm(self):
                return "555"

            def send(self, ch, text):
                sent.append(("text", ch, text))

            def send_file(self, ch, name, blob, text="", ctype="audio/mpeg"):
                sent.append(("file", ch, name, blob))

            def dm_owner(self, text):
                sent.append(("mirror", text))
        self.app.discord, self.cfg.discord_enabled = FakeDiscord(), True
        self.app.voice.synth = lambda text: b"MP3:" + text.encode()
        self.life.add_schedule("Stretch", "30 20 * * 1-5", "Remind Jordan to stretch.", to="discord", voice=True)
        self.llm.answers += [{"step": "reply"}, {"say": "Stretch, Jordan. Go."}]
        self.life.fire(self.life.schedules[-1])
        self.assertEqual(sent[0], ("text", "555", "Stretch, Jordan. Go."))
        self.assertEqual(sent[1], ("file", "555", "voice.mp3", b"MP3:Stretch, Jordan. Go."))
        sent.clear()
        self.life.add_schedule("Water", "0 9 * * *", "Remind Jordan to drink water.", to="discord")
        self.llm.answers += [{"step": "reply"}, {"say": "Water."}]
        self.life.fire(self.life.schedules[-1])
        self.assertEqual([x[0] for x in sent], ["text"])

    def test_reminder_switched_on_fires(self):
        self.life.add_schedule("Stretch", "30 20 * * 1-5", "use your voice\nRemind Jordan to stretch.", enabled=False,
                               speak=True)
        s = self.life.schedules[0]
        self.assertFalse(s["enabled"])
        self.assertTrue(s["speak"])
        c = self.chat("hi")
        self.cfg.heartbeat_enabled = False
        self.life.update_schedule(s["id"], enabled=True)
        self.llm.answers += [{"step": "reply"}, {"say": "Stretch, now. Fun fact: octopuses have three hearts."}]
        self.life.tick(T.replace(hour=20, minute=30))
        ev = Conversation(self.app.conv_dir, c.id).events
        self.assertEqual(ev[-2]["kind"], "wake")
        self.assertIn("Remind Jordan to stretch", ev[-2]["text"])
        self.assertEqual(ev[-1]["kind"], "reply")
        self.llm.answers += [{"step": "reply"}, {"say": "again?"}]
        self.life.tick(T.replace(hour=20, minute=30))
        self.assertEqual(len(Conversation(self.app.conv_dir, c.id).events), len(ev))

    def test_a_reminder_whose_minute_went_by_still_fires(self):
        c = self.chat("hi")
        self.cfg.heartbeat_enabled = False
        self.life.add_schedule("Stretch", "30 20 * * *", "Remind Jordan to stretch.")
        self.life.tick(T.replace(hour=20, minute=28))
        self.assertEqual(len(self.llm.calls), 0)
        self.llm.answers += [{"step": "reply"}, {"say": "Stretch, Jordan."}]
        self.life.tick(T.replace(hour=20, minute=37))
        ev = Conversation(self.app.conv_dir, c.id).events
        self.assertEqual(ev[-1]["text"], "Stretch, Jordan.")
        self.assertIn("firing now (it was set for 8:30 PM,", ev[-2]["text"])
        self.llm.answers += [{"step": "reply"}, {"say": "again?"}]
        self.life.tick(T.replace(hour=20, minute=38))
        self.assertEqual(len(Conversation(self.app.conv_dir, c.id).events), len(ev))

    def test_no_catching_up_on_the_time_aether_was_closed(self):
        self.chat("hi")
        self.cfg.heartbeat_enabled = False
        self.life.add_schedule("Stretch", "30 20 * * *", "Remind Jordan to stretch.")
        self.life.tick(T.replace(hour=20, minute=37))
        self.assertEqual(len(self.llm.calls), 0)
        self.assertNotIn("pending", self.life.schedules[-1])

    def test_a_reminder_waits_when_the_model_doesnt_answer(self):
        c = self.chat("hi")
        self.cfg.heartbeat_enabled = False
        self.life.add_schedule("Stretch", "30 20 * * *", "Remind Jordan to stretch.")
        fire, tries = self.life.fire, []

        def down(s, due=None):
            tries.append(due)
            raise life_mod.LLMError("LM Studio isn't answering")
        self.life.fire = down
        for m in (30, 31, 32):
            self.life.tick(T.replace(hour=20, minute=m))
        self.assertEqual(tries, [T.replace(hour=20, minute=30)] * 3)
        self.assertNotIn("pending", self.life.schedules[-1])
        self.assertIn("gave up", self.life.state["life_log"][-1]["detail"])
        self.life.fire = fire
        self.life.add_schedule("Water", "40 20 * * *", "Remind Jordan to drink water.")
        self.life.fire = down
        self.life.tick(T.replace(hour=20, minute=40))
        self.life.fire = fire
        self.llm.answers += [{"step": "reply"}, {"say": "Water."}]
        self.life.tick(T.replace(hour=20, minute=41))
        self.assertEqual(Conversation(self.app.conv_dir, c.id).events[-1]["text"], "Water.")
        self.assertNotIn("tries", self.life.schedules[-1])

    def test_mood_step(self):
        self.assertIn("set_mood", json.dumps(self.app.engine.schema))
        ok, text = self.life.set_mood({"step": "set_mood", "mood": "proud", "why": "backup done"})
        self.assertEqual(self.life.mood.current()["name"], "proud")
        self.cfg.mood_enabled = False
        self.app.engine.refresh()
        self.assertNotIn("set_mood", json.dumps(self.app.engine.schema))


if __name__ == "__main__":
    unittest.main()
