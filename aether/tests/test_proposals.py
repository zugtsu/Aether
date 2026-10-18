import datetime as dt
import json
import os
import tempfile
import unittest

from aether import digest as dg
from aether import life as life_mod
from aether import proposals as pr
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory

T = dt.datetime(2026, 10, 2, 19, 0)
IDEA = {"step": "propose", "kind": "do", "title": "Tidy the Later list", "why": "Three lines there are done already.",
        "plan": "Move the voice, the brain map and the Godot demo lines to Done.", "brief": "none"}


class StageThreeTests(unittest.TestCase):
    def setUp(self):
        home = tempfile.mkdtemp()
        pr.STORE = os.path.join(home, "proposals.json")
        life_mod.STATE_FILE = os.path.join(home, "life.json")
        life_mod.SCHEDULES_FILE = os.path.join(home, "schedules.json")
        self.root = make_memory()
        self.cfg = make_config(self.root)
        self.llm = ScriptedLLM([])
        self.httpd, self.app = make_server(self.cfg, self.llm, port=0)
        self.app.conv_dir = tempfile.mkdtemp()
        self.life, self.props = self.app.life, self.app.proposals
        self.props.items = []
        self.chat = Conversation(self.app.conv_dir)
        self.chat.add("user", text="hey", context="", ts=(T - dt.timedelta(hours=3)).isoformat())
        self.chat.add("reply", text="hey you", ts=(T - dt.timedelta(hours=3)).isoformat())
        self.life.state["last_user"] = (T - dt.timedelta(hours=3)).isoformat()

    def tearDown(self):
        self.httpd.server_close()

    def own_time(self, now=T):
        eng = self.app.engine
        eng._kind, eng._outside, eng._stale_outside = "wake", [], []
        self.props.clock = lambda: now
        real = self.life.message_gate
        self.life.message_gate = lambda n, cap=True: real(now, cap)
        try:
            return self.props.run_step(dict(IDEA))
        finally:
            self.life.message_gate = real

    def test_in_a_chat_the_card_goes_right_there_and_his_answer_comes_back(self):
        eng = self.app.engine
        eng.conv, eng._kind, eng._outside, eng._stale_outside = self.app.conv(self.chat.id), "user", [], []
        ok, out = self.props.run_step(dict(IDEA))
        self.assertTrue(ok, out)
        self.assertIn("in this chat, as a card", out)
        card = self.app.conv(self.chat.id).events[-1]
        self.assertEqual((card["kind"], card["title"], card["pid"]), ("proposal", "Tidy the Later list", "p1"))
        self.assertEqual(self.life.reach_outs_today(), 0)
        self.props.answer("p1", "yes")
        ans = self.app.conv(self.chat.id).events[-1]
        self.assertEqual((ans["kind"], ans["answer"]), ("proposal_answer", "yes"))
        role, text = Conversation._message(ans)
        self.assertEqual(role, "user")
        self.assertIn('{USER} answered your proposal "Tidy the Later list" with the Yes button', text)
        self.assertEqual(Conversation._message(card)[0], "assistant")
        with self.assertRaises(ValueError):
            self.props.answer("p1", "no")
        with self.assertRaises(ValueError):
            self.props.answer("p1", "maybe")

    def test_on_her_own_time_it_waits_for_a_moment_she_could_message_him(self):
        self.life.state["last_user"] = (T - dt.timedelta(minutes=10)).isoformat()
        ok, out = self.own_time()
        self.assertIn("waiting for a moment you could message him", out)
        self.assertEqual(self.props.items[0]["delivered"], "")
        self.assertFalse(self.props.tick(T + dt.timedelta(minutes=5)))
        self.assertTrue(self.props.tick(T + dt.timedelta(minutes=25)))
        self.assertEqual(self.app.conv(self.chat.id).events[-1]["kind"], "proposal")
        self.assertEqual(self.life.reach_outs_today(), 1)
        self.assertFalse(self.props.tick(T + dt.timedelta(minutes=30)))

    def test_limits_and_the_build_rule(self):
        self.own_time()
        self.assertFalse(self.own_time()[0])
        for t in ("Clean up the garden notes", "Ask about the beach house"):
            idea = dict(IDEA, title=t)
            self.props.run_step(idea)
        ok, out = self.props.run_step(dict(IDEA, title="A fourth idea entirely"))
        self.assertFalse(ok)
        self.assertIn("You have 3 proposals waiting", out)
        self.props.items = []
        build = dict(IDEA, kind="build", title="Pet price tracker", brief="pet-price-tracker")
        self.assertIn("needs its architect plan", self.props.run_step(build)[1])
        folder = os.path.join(self.cfg.workspace_dir, "plans")
        os.makedirs(folder, exist_ok=True)
        filled = "# Pet price tracker\n" + "".join(f"## {s}\nSomething real.\n\n" for s in pr.BRIEF_SECTIONS)
        with open(os.path.join(folder, "pet-price-tracker.md"), "w", encoding="utf-8") as f:
            f.write(filled.replace("## Risks\nSomething real.", "## Risks\n(empty) What could go wrong."))
        ok, out = self.props.run_step(build)
        self.assertFalse(ok)
        self.assertIn("Risks still empty", out)
        with open(os.path.join(folder, "pet-price-tracker.md"), "w", encoding="utf-8") as f:
            f.write(filled)
        self.assertTrue(self.props.run_step(build)[0])

    def test_made_after_outside_content_says_so(self):
        eng = self.app.engine
        eng.conv, eng._kind, eng._outside, eng._stale_outside = self.app.conv(self.chat.id), "user", ["the research skill"], []
        self.props.run_step(dict(IDEA))
        self.assertEqual(self.app.conv(self.chat.id).events[-1]["after_outside"], ["the research skill"])
        self.assertTrue(eng._is_lookup({"step": "propose"}))

    def test_she_sees_his_answers_and_his_no_reaches_her_reflection(self):
        self.own_time()
        self.props.clock = lambda: T + dt.timedelta(hours=1)
        self.props.answer("p1", "no")
        self.assertIn('"Tidy the Later list" (do): he said no', "\n".join(self.props.lines(T)))
        self.app.engine.memory
        self.life.state["last_look"] = T.isoformat()
        self.assertIn("he said no", self.life.wake_packet(T + dt.timedelta(hours=2)))
        self.chat.add("user", text="lets clean up today", context="", ts=(T + dt.timedelta(hours=1)).isoformat())
        later = (T + dt.timedelta(hours=1)).timestamp()
        os.utime(self.chat.path, (later, later))
        self.llm.answers += [{"changes": [], "lessons": []}]
        self.life.reflect(T + dt.timedelta(hours=18))
        ask = self.llm.calls[-1]["messages"][-1]["content"]
        self.assertIn('[proposal: {USER} said no] Your proposals he said no to today:\n- do: "Tidy the Later list"', ask)
        enum = self.llm.calls[-1]["schema"]["properties"]["lessons"]["items"]["properties"]["mistake"]["enum"]
        self.assertIn("proposal: {USER} said no", enum)

    def test_a_message_is_the_kind_her_steps_back_up(self):
        k = life_mod.Life._message_kind
        self.assertEqual(k("finding", ["journal"], "heartbeat"), "check_in")
        self.assertEqual(k("finding", ["journal", "save_research"], "heartbeat"), "finding")
        self.assertEqual(k("proposal", ["propose"], "heartbeat"), "proposal")
        self.assertEqual(k("proposal", ["journal"], "heartbeat"), "check_in")
        self.assertEqual(k("heads_up", [], "heartbeat"), "check_in")
        self.assertEqual(k("heads_up", [], "a thread you're keeping"), "heads_up")
        self.llm.answers += [{"step": "reply"}, {"reach_out": True, "kind": "finding", "say": "Found something cool."}]
        self.life.heartbeat(T, forced=True)
        sent = self.app.conv(self.chat.id).events[-1]
        self.assertEqual((sent["kind"], sent["type"]), ("reach_out", "check_in"))
        self.assertIn("messaged you (check_in)", self.life.state["life_log"][-1]["detail"])
        schema = self.llm.calls[-1]["schema"]
        self.assertEqual(schema["properties"]["kind"]["enum"], list(life_mod.MESSAGE_KINDS))

    def test_since_he_was_last_here(self):
        folder = tempfile.mkdtemp()
        c = Conversation(folder)
        for h, m in ((8, 0), (8, 10), (17, 30), (17, 31)):
            c.add("user", text="hi", context="", ts=dt.datetime(2026, 10, 2, h, m).isoformat())
        os.utime(c.path, (T.timestamp(), T.timestamp()))
        self.assertEqual(dg.last_visit_end(folder, dt.datetime(2026, 10, 2, 17, 32)), dt.datetime(2026, 10, 2, 8, 10))

    def test_my_time_tells_her_from_her_records(self):
        now = dt.datetime.now()
        self.life.state["life_log"] = [
            {"when": (now - dt.timedelta(hours=3)).isoformat(timespec="seconds"), "what": "woke (quiet)",
             "detail": "research, save_research, task; stayed quiet"},
            {"when": (now - dt.timedelta(hours=80)).isoformat(timespec="seconds"), "what": "woke", "detail": "old one"}]
        with open(os.path.join(self.cfg.workspace_dir, "ideas.md"), "w", encoding="utf-8") as f:
            f.write("x")
        self.props.items = [{"id": "p1", "kind": "do", "title": "Tidy the Later list", "why": "w", "plan": "p",
                             "status": "open", "delivered": "", "answered": ""}]
        ok, out = self.app.digest.run_step({"step": "my_time", "since": "the last 3 days"})
        self.assertTrue(ok)
        self.assertIn("from your records, not your memory", out)
        self.assertIn("woke (quiet): research, save_research, task; stayed quiet", out)
        self.assertNotIn("old one", out)
        self.assertIn('"ideas.md"', out)
        self.assertIn('"Tidy the Later list" (do): waiting for his answer, not sent yet', out)
        self.life.state["life_log"] = []
        empty = self.app.digest.records(now + dt.timedelta(minutes=1), now + dt.timedelta(minutes=2))
        self.assertFalse([ln for ln in empty if not ln.startswith(("Your task list", "Your proposals"))])

    def test_what_aether_did_by_itself_isnt_credited_to_her(self):
        mem = self.app.engine.memory
        with open(os.path.join(self.root, "notes.md"), "w", encoding="utf-8") as f:
            f.write("x")
        mem._git("add", "notes.md")
        mem._git("commit", "-q", "-m", "calendar: next time for Gym $30 (2026-11-01)")
        out = "\n".join(self.app.digest.records(dt.datetime.now() - dt.timedelta(minutes=5), dt.datetime.now()))
        self.assertRegex(out, r"Done by Aether on its own, not by you \(\d\): calendar: next time for Gym")
        self.assertNotIn("What YOU saved", out)

    def test_her_new_abilities_are_in_her_skills_list(self):
        prompt = self.app.engine.system
        self.assertIn("- `my_time`:", prompt)
        for gone in ("propose", "task"):
            self.assertNotIn(f"- `{gone}`:", prompt)
        enum = next(o for o in self.app.engine.schema["anyOf"] if o["properties"]["step"].get("const") == "read_skill")
        self.assertIn("my_time", enum["properties"]["skill"]["enum"])
        self.assertNotIn("propose", enum["properties"]["skill"]["enum"])

    def test_status_lists_whats_waiting_for_his_yes(self):
        self.own_time()
        self.assertEqual([p["title"] for p in self.life.status()["proposals"]], ["Tidy the Later list"])
        code = json.dumps(self.life.status())
        self.assertIn("Tidy the Later list", code)


if __name__ == "__main__":
    unittest.main()
