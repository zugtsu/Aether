import datetime as dt
import json
import os
import tempfile
import unittest

from aether import engine as engine_mod
from aether import lessons as L
from aether import life as life_mod
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import git, make_config, make_memory

T = dt.datetime(2026, 10, 2, 13, 20)
REAL = ["- 2026-09-27: prioritize the most critical technical hurdles when he's pushing for progress (to avoid hitting step limits).",
        "- 2026-09-27: library_skill: verify the file name or use a broader search first.",
        "- 2026-09-28: library_access: Use the research skill (search) to access his Lucy Library files; read_file is only for my own memory files.",
        "- 2026-09-29: shell: When using Get-Content with paths containing spaces (like Aether Workspace), I must ensure the path is wrapped in quotes.",
        "- 2026-10-01: news/radio_skills: If a key is missing for these skills, I must treat it as a failure."]


class TagTests(unittest.TestCase):

    def test_tags_from_real_failures(self):
        board = {"step": "skill", "skill": "board", "command": "add"}
        cases = [
            (board, 'exit code 2\nusage: board.py add [-h] section text\nboard.py add: error: the following arguments are '
                    'required: text', "board: wrong arguments"),
            (board, 'exit code 1 {"ok":false,"error":"\'next\' matches 3 lines; be more specific"}', "board: matches several lines"),
            (board, 'exit code 1 {"ok":false,"error":"no line on the board contains \'x\'"}', "board: no such line"),
            ({"step": "calendar"}, "You already took exactly this step in this turn; its result is above.", "calendar: repeat"),
            ({"step": "calendar"}, "I couldn't tell when to remind him from 'a couple days before': ask him.",
             "calendar: couldn't read the date"),
            ({"step": "save_research"}, engine_mod.READ_FIRST, "save_research: save before reading"),
            ({"step": "turn"}, "You've used all your steps for this turn. Reply to Jordan now", "turn: step limit"),
            ({"step": "skill", "skill": "fail"}, "exit code 3\nbroken on purpose", "fail: script failed"),
            ({"step": "task"}, "Nothing changed: you already did t12 in this reply, the one his message names. Don't "
                               "change another task: reply to him.", "task: not the one he named"),
            ({"step": "task"}, "Nothing changed: t4, t5 aren't open on your list (already done or dropped). Don't change "
                               "another task: tell him they're already gone.", "task: not the one he named"),
            ({"step": "task"}, "Not that one: his message names t12, not t13. Nothing changed. Take the step again with "
                               "the id he means.", "task: not the one he named"),
            ({"step": "calendar"}, "Not that one: his message names c2, not c7. Nothing changed.",
             "calendar: not the one he named"),
        ]
        for step, result, want in cases:
            self.assertEqual(L.tag(step, result), want, result[:40])
        self.assertEqual(L.tag(board, "exit code 3\nboom" + L.hint(["- 2026-09-01: usage: be careful"])), "board: script failed")

    def test_the_label_she_puts_in_front(self):
        self.assertEqual([L.guess_what(x) for x in REAL], [None, "library", "library", "shell", "news"])
        self.assertEqual([L.skill_label(x) for x in REAL], [None, "library", None, None, "news"])

    def test_measure_before_and_after(self):
        def row(day, ok, t=None, what="board"):
            return (dt.datetime(2026, 10, day, 12), what, ok, t)
        rows = ([row(d, False, "board: wrong arguments") for d in (1, 2, 3)] + [row(d, True) for d in (1, 2, 3)]
                + [row(d, False, "board: wrong arguments") for d in (6, 7, 8)] + [row(d, True) for d in (6, 7, 8)]
                + [row(2, False, "board: no such line"), row(2, True, what="news")])
        m = L.measure(rows, ["board: wrong arguments"], "2026-10-05", dt.datetime(2026, 10, 9), days=4)
        self.assertEqual((m["before"], m["after"]), ((3, 7), (3, 6)))
        self.assertEqual(L.verdict(m, days=4), "didn't help")
        early = L.measure(rows, ["board: wrong arguments"], "2026-10-05", dt.datetime(2026, 10, 7), days=4)
        self.assertIsNone(L.verdict(early, days=4))
        m = L.measure(rows, ["board: any"], "2026-10-05", dt.datetime(2026, 10, 9), days=4)
        self.assertEqual(m["before"], (4, 7))
        quiet = [r for r in rows if r[0].day < 5 or r[2]]
        self.assertIsNone(L.verdict(L.measure(quiet, ["board: wrong arguments"], "2026-10-05",
                                              dt.datetime(2026, 10, 9), days=4), days=4))


class WorseTests(unittest.TestCase):

    def test_a_tool_that_got_worse_is_flagged_and_steady_ones_arent(self):
        since, now = dt.datetime(2026, 10, 3), dt.datetime(2026, 10, 5)
        day = dt.timedelta(days=1)
        rows = ([(since - 3 * day, "board", True, None)] * 9 + [(since - 3 * day, "board", False, "board: wrong arguments")]
                + [(since + day, "board", True, None)] * 2 + [(since + day, "board", False, "board: wrong arguments")] * 2
                + [(since - day, "news", False, "news: other")] + [(since - day, "news", True, None)] * 3
                + [(since + day, "news", False, "news: other")] + [(since + day, "news", True, None)] * 3
                + [(since + day, "shell", False, "shell: command refused")] + [(since + day, "shell", True, None)]
                + [(since - 30 * day, "calendar", False, "calendar: other")] * 5)
        r = {x["what"]: x for x in L.worse(rows, since, now)}
        self.assertEqual((r["board"]["before"], r["board"]["after"], r["board"]["worse"]), ((1, 10), (2, 4), True))
        self.assertEqual(r["board"]["kinds"], {"wrong arguments": 2})
        self.assertFalse(r["news"]["worse"])
        self.assertFalse(r["shell"]["worse"])
        self.assertNotIn("calendar", r)
        self.assertEqual(L.worse(rows, since, now)[0]["what"], "board")


class LifeLessonTests(unittest.TestCase):
    def setUp(self):
        home = tempfile.mkdtemp()
        life_mod.STATE_FILE = os.path.join(home, "life.json")
        life_mod.SCHEDULES_FILE = os.path.join(home, "schedules.json")
        engine_mod.AUDIT = os.path.join(home, "audit.jsonl")
        self.root = make_memory()
        self.cfg = make_config(self.root)
        self.llm = ScriptedLLM([])
        self.httpd, self.app = make_server(self.cfg, self.llm, port=0)
        self.app.conv_dir = tempfile.mkdtemp()
        self.life = self.app.life

    def tearDown(self):
        self.httpd.server_close()

    def body(self, rel):
        with open(os.path.join(self.root, *rel.split("/")), encoding="utf-8") as f:
            return f.read()

    def failed_chat(self):
        c = Conversation(self.app.conv_dir)
        c.add("user", text="put the bike on the board", context="", ts=(T - dt.timedelta(hours=2)).isoformat())
        c.add("step", step={"step": "skill", "skill": "board", "command": "add"}, ts=(T - dt.timedelta(hours=2)).isoformat())
        c.add("result", of="skill", ok=False, text="exit code 2\nusage: board.py add [-h] section text",
              ts=(T - dt.timedelta(hours=2)).isoformat())
        c.add("reply", text="hm", ts=(T - dt.timedelta(hours=2)).isoformat())
        return c

    def test_reflection_ties_each_lesson_to_one_of_todays_mistakes(self):
        self.failed_chat()
        self.llm.answers += [{"changes": [], "lessons": [
            {"mistake": "board: wrong arguments", "text": "board_skill: add needs the section first, then the text."}]}]
        self.assertTrue(self.life.reflect(T))
        ask = self.llm.calls[-1]["messages"][-1]["content"]
        self.assertIn("[board: wrong arguments] exit code 2", ask)
        enum = self.llm.calls[-1]["schema"]["properties"]["lessons"]["items"]["properties"]["mistake"]["enum"]
        self.assertEqual(enum, ["board: wrong arguments", "other"])
        meta = self.life.state["lesson_meta"]
        info = meta[L.norm("- 2026-10-02: board_skill: add needs the section first, then the text.")]
        self.assertEqual(info, {"tags": ["board: wrong arguments"], "added": "2026-10-02"})

    def test_a_newer_lesson_on_the_same_mistake_replaces_the_older(self):
        self.life._add_lessons([("board_skill: give the section, then the text.", "board: wrong arguments")], T)
        self.life._add_lessons([("board_skill: add takes a section name and the line's text after it.",
                                 "board: wrong arguments")], T + dt.timedelta(days=2))
        rules = self.body("reference/lessons.md")
        self.assertIn("a section name and the line's text", rules)
        self.assertNotIn("give the section, then the text", rules)
        self.assertIn("replaced by a newer lesson on the same mistake: 2026-10-02: board_skill: give the section",
                      self.body(L.HISTORY))
        self.assertIn("give the section, then the text", self.body("reference/lessons-archive.md"))
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "--", L.HISTORY).strip(),
                         "reflection: 1 lesson(s), 1 replaced by a newer lesson on the same mistake")
        self.life._add_lessons(["Answer what he asked first.", "Keep heartbeat messages short."], T + dt.timedelta(days=3))
        self.assertIn("Answer what he asked first.", self.body("reference/lessons.md"))

    def test_review_retires_what_didnt_help_and_what_names_a_gone_skill(self):
        self.life._write_lessons(REAL, None, "her rulebook")
        self.life._add_lessons([("fail_skill: give it the go argument.", "fail: wrong arguments")],
                               dt.datetime(2026, 9, 20, 13, 20))
        with open(engine_mod.AUDIT, "w", encoding="utf-8") as f:
            for day in (14, 15, 16, 22, 25, 28):
                f.write(json.dumps({"ts": f"2026-09-{day}T12:00:00", "step": {"step": "skill", "skill": "fail"},
                                    "ok": False, "result": "exit code 2\nusage: fail.py go"}) + "\n")
        self.assertEqual(self.life.review_lessons(T), 2)
        self.cfg.lesson_trial_days = 10
        self.assertEqual(self.life.review_lessons(T), 1)
        rules, hist = self.body("reference/lessons.md"), self.body(L.HISTORY)
        self.assertNotIn("library_skill", rules)
        self.assertIn("library_access", rules)
        self.assertIn("names the library skill, which she no longer has", hist)
        self.assertIn("names the news skill", hist)
        self.assertIn("didn't help (before: 3 of 3 tries; after (10 days): 3 of 3 tries): 2026-09-20: fail_skill: give", hist)
        self.assertIn("shell: When using Get-Content", rules)
        self.assertEqual(self.life.state["life_log"][-1]["what"], "lessons retired")
        self.assertEqual(self.life.review_lessons(T), 0)

    def test_a_failed_step_brings_back_her_lessons_on_that_tool(self):
        self.life._write_lessons(["- 2026-09-30: fail_skill: it needs its go argument; check the page first.",
                                  "- 2026-09-30: news: say the city."],
                                 ["- 2026-09-20: fail_skill: an old one from the archive about the same tool."], "rules")
        self.app.engine.memory.reload()
        c = Conversation(self.app.conv_dir)
        self.app.engine.conv = c
        self.llm.answers += [{"step": "skill", "skill": "fail", "args": ["go"]}, {"step": "reply"}, {"say": "it broke"}]
        self.app.engine.turn("run the fail thing")
        res = next(e for e in c.events if e["kind"] == "result")
        self.assertTrue(res["text"].startswith("exit code 3"))
        self.assertIn("[Lessons you wrote before", res["text"])
        self.assertIn("it needs its go argument", res["text"])
        self.assertIn("an old one from the archive", res["text"])
        self.assertNotIn("say the city", res["text"])
        with open(engine_mod.AUDIT, encoding="utf-8") as f:
            row = [json.loads(ln) for ln in f][-1]
        self.assertEqual(row["tag"], "fail: script failed")
        self.cfg.lesson_hints = False
        self.assertEqual(self.life.lessons_for({"step": "skill", "skill": "fail"}, "exit code 3"), "")

    def test_a_memory_lesson_comes_back_only_for_its_own_file(self):
        facts_lesson = ("- 2026-09-29: memory_management: Facts are for Jordan's life; my own workspace and personal "
                        "notes belong in system/workspace.md, not facts.")
        self.life._write_lessons([facts_lesson, "- 2026-10-01: memory_management: quote the whole line of me.md when "
                                  "I take one out."], None, "rules")
        exists = "notes/origin-story.md already exists. To add to it: memory_add with file notes/origin-story.md. ..."
        self.assertEqual(L.tag({"step": "memory_create"}, exists), "memory: file already exists")
        self.assertEqual(self.life.lessons_for({"step": "memory_create", "path": "notes/origin-story.md"}, exists), "")
        back = self.life.lessons_for({"step": "memory_replace", "file": "system/human/facts.md"},
                                     "No line in system/human/facts.md matches")
        self.assertIn("Facts are for Jordan's life", back)
        self.assertNotIn("me.md", back)
        back = self.life.lessons_for({"step": "memory_remove", "file": "system/me.md"}, "No line in system/me.md matches")
        self.assertIn("quote the whole line of me.md", back)
        self.assertNotIn("Facts are for", back)

    def test_nothing_comes_back_for_a_repeat_or_from_a_retired_lesson(self):
        self.life._write_lessons(["- 2026-09-30: calendar: ask him for the day."], None, "rules")
        self.assertEqual(self.life.lessons_for({"step": "calendar"}, "You already took exactly this step in this turn"), "")
        self.assertIn("ask him for the day", self.life.lessons_for({"step": "calendar"}, "I couldn't tell a day"))
        self.life.state["lesson_meta"] = {L.norm("- 2026-09-30: calendar: ask him for the day."): {"retired": "didn't help"}}
        self.assertEqual(self.life.lessons_for({"step": "calendar"}, "I couldn't tell a day"), "")


if __name__ == "__main__":
    unittest.main()
