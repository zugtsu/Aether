import datetime as dt
import math
import os
import re
import tempfile
import unittest

from aether import examples as X
from aether import life as life_mod
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory

T = dt.datetime(2026, 10, 2, 12, 0)


def ev(kind, ts, **kw):
    return {"kind": kind, "ts": ts.isoformat(timespec="seconds"), **kw}


def turn(ts, said, step, ok=True, reply="Done.", **step_kw):
    return [ev("user", ts, text=said, context=""), ev("step", ts, step=step, **step_kw),
            ev("result", ts, of=step.get("step"), ok=ok, text="ok" if ok else "exit code 1"), ev("reply", ts, text=reply)]


NEWS = {"step": "skill", "skill": "news", "command": "now", "args": []}


def embed(texts):
    out = []
    for t in texts:
        v = [0.0] * 64
        for w in re.findall(r"[a-z]+", t.lower().replace(X.PREFIX, "")):
            v[hash(w) % 64] += 1
        n = math.sqrt(sum(x * x for x in v)) or 1
        out.append([x / n for x in v])
    return out


class HarvestTests(unittest.TestCase):

    def test_a_clean_ask_and_its_step(self):
        evs = turn(T, "whats the news like?", NEWS) + [ev("user", T, text="cool thanks", context="")]
        got = X.harvest(evs, "c1")
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["said"], got[0]["tool"]), ("whats the news like?", "news"))
        self.assertEqual(got[0]["step"], {"step": "skill", "skill": "news", "command": "now", "args": []})

    def test_what_never_becomes_one(self):
        cases = {
            "stranger": [ev("user", T, text="news?", context="", place="Discord DM from bob")]
                        + turn(T, "x", NEWS)[1:] + [ev("user", T, text="ok", context="")],
            "failed step": turn(T, "whats the news like?", NEWS, ok=False) + [ev("user", T, text="ok", context="")],
            "his next words say no": turn(T, "whats the news like?", NEWS) + [ev("user", T, text="no, i meant tomorrow",
                                                                                     context="")],
            "an answer to her question": [ev("reply", T, text="Want me to check the news?")]
                                         + turn(T, "sure go ahead", NEWS) + [ev("user", T, text="ok", context="")],
            "outside content before": [ev("result", T, of="skill", ok=True, text="page", outside="research")]
                                      + turn(T, "whats the news like?", NEWS) + [ev("user", T, text="k", context="")],
            "Aether took the step": turn(T, "whats the news like?", NEWS, auto="reply")
                                    + [ev("user", T, text="ok", context="")],
            "names another tool": turn(T, "pull up the project board please", {"step": "recall", "query": "board"})
                                  + [ev("user", T, text="ok", context="")],
            "last turn, not over": turn(T, "whats the news like?", NEWS),
        }
        for why, evs in cases.items():
            self.assertEqual(X.harvest(evs, "c1"), [], why)
        self.assertEqual(len(X.harvest(cases["last turn, not over"], "c1", final=True)), 1)

    def test_only_the_shape_of_a_step_is_kept(self):
        cal = {"step": "calendar", "do": "add", "title": "Car service", "when": "2026-10-14 15:00"}
        self.assertEqual(X.shape(cal), {"step": "calendar", "do": "add"})
        self.assertEqual(X.shape({"step": "make_image", "prompt": "a cat", "shape": "square", "caption": "x"}),
                         {"step": "make_image"})
        self.assertEqual(X.shown({"step": "skill", "skill": "board", "command": "add", "args": ["later", "fix it"]}),
                         'board skill (command: add; args: "later", "fix it")')


class StoreTests(unittest.TestCase):
    def setUp(self):
        home = tempfile.mkdtemp()
        X.STORE = os.path.join(home, "examples.json")
        life_mod.STATE_FILE = os.path.join(home, "life.json")
        life_mod.SCHEDULES_FILE = os.path.join(home, "schedules.json")
        self.root = make_memory()
        self.cfg = make_config(self.root, examples_enabled=True, examples_min=0.7)
        self.httpd, self.app = make_server(self.cfg, ScriptedLLM([]), port=0)
        self.app.conv_dir = tempfile.mkdtemp()
        self.ex = self.app.examples
        self.skills = {"plants": self.app.engine.skills["plants"]}

    def tearDown(self):
        self.httpd.server_close()

    def plants_turn(self, said, ts):
        return turn(ts, said, {"step": "skill", "skill": "plants", "command": "next", "args": []}) + \
            [ev("user", ts, text="thanks", context="")]

    def test_a_day_old_checked_example_joins_and_comes_back_for_a_message_like_it(self):
        self.ex.observe(self.plants_turn("when do i water the plants next?", T), "c1")
        self.assertEqual(len(self.ex.pending), 1)
        yes = lambda said, step: True  # noqa: E731
        self.assertEqual(self.ex.mature(T + dt.timedelta(hours=5), embed, self.skills, yes), (0, 0))
        self.assertEqual(self.ex.mature(T + dt.timedelta(days=1, minutes=1), embed, self.skills, yes), (1, 0))
        self.ex.observe(self.plants_turn("when do i water the plants next?", T), "c1")
        self.assertEqual(self.ex.pending, [])
        found = self.ex.matches("when do i water the plants next week?", embed, self.skills)
        self.assertEqual([c["tool"] for _, c in found], ["plants"])
        note = self.ex.note(found)
        self.assertIn('he said "when do i water the plants next?" -> you used: plants skill (command: next)', note)
        self.assertEqual(self.ex.matches("i love rainy days", embed, self.skills), [])

    def test_what_the_check_or_the_skill_rules_out(self):
        self.ex.observe(self.plants_turn("when do i water the plants next?", T), "c1")
        self.ex.observe(self.plants_turn("are they due tonight?", T + dt.timedelta(minutes=5)), "c2")
        no = lambda said, step: said != "are they due tonight?"  # noqa: E731
        self.assertEqual(self.ex.mature(T + dt.timedelta(days=2), embed, self.skills, no), (1, 1))
        self.ex.observe(self.plants_turn("whens my next watering?", T), "c3")
        changed = {"plants": T + dt.timedelta(hours=1)}
        self.assertEqual(self.ex.mature(T + dt.timedelta(days=2), embed, self.skills, lambda s, t: True, changed), (0, 1))
        self.ex.items[0]["doc"] = "something else"
        self.assertEqual(self.ex.matches("when do i water the plants next?", embed, self.skills), [])

    def test_his_message_gets_the_note_in_its_hidden_lines_only_when_switched_on(self):
        self.app.recall.embed = embed
        self.ex.observe(self.plants_turn("when do i water the plants next?", T), "c1")
        self.ex.mature(T + dt.timedelta(days=2), embed, self.app.engine.skills, lambda s, t: True)
        c = Conversation(self.app.conv_dir)
        self.assertIn("Steps that worked before", self.app.life.context_for(c, text="when do i water the plants next?"))
        self.cfg.examples_enabled = False
        self.assertNotIn("Steps that worked before", self.app.life.context_for(c, text="when do i water the plants next?"))

    def test_collecting_in_the_background_never_shows_her_one(self):
        self.cfg.examples_enabled, self.cfg.examples_collect = False, True
        self.app.recall.embed = embed
        self.assertTrue(self.ex.collecting())
        self.assertFalse(self.ex.on())
        base = dt.datetime.now() + dt.timedelta(minutes=1)
        self.ex.observe(self.plants_turn("when do i water the plants next?", base), "c1")
        self.ex.backfilled = True
        self.app.engine.llm.answers += [{"fits": "yes"}]
        self.app.life.state["last_user"] = (base - dt.timedelta(hours=3)).isoformat()
        self.cfg.quiet_start = self.cfg.quiet_end = "00:00"
        self.app.life.examples_tick(base + dt.timedelta(days=2))
        self.assertEqual([c["said"] for c in self.ex.items], ["when do i water the plants next?"])
        self.assertFalse(self.app.gpu.locked() or self.app.gpu_yield)
        c = Conversation(self.app.conv_dir)
        self.assertNotIn("Steps that worked before", self.app.life.context_for(c, text="when do i water the plants next?"))
        self.cfg.examples_collect = False
        self.assertFalse(self.ex.collecting())

    def test_caps_and_forget(self):
        for i in range(X.PER_TOOL + 3):
            self.ex.observe(self.plants_turn(f"when do i water the plants number {i}?", T + dt.timedelta(minutes=i)), f"c{i}")
        self.ex.mature(T + dt.timedelta(days=2), embed, self.skills, lambda s, t: True, budget=50)
        self.assertEqual(len(self.ex.items), X.PER_TOOL)
        self.assertEqual(self.ex.items[0]["said"], f"when do i water the plants number {X.PER_TOOL + 2}?")
        gone = self.ex.forget(0)
        self.assertNotIn(gone, self.ex.items)
        self.ex.observe(self.plants_turn(gone["said"], dt.datetime.fromisoformat(gone["ts"])), gone["chat"])
        self.assertEqual(self.ex.pending, [])


if __name__ == "__main__":
    unittest.main()
