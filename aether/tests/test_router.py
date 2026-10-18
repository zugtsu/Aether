import os
import tempfile
import unittest

from aether import router
from aether.engine import Engine
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.tests.fixture import git, make_config, make_memory
from aether.tests.test_engine import Recorder, say


def names(msg):
    return [a[0] for a in router.asks_in(msg)]


class AskTests(unittest.TestCase):
    def test_what_his_messages_ask_for(self):
        for msg, want in (
                ("add 'clean the gpu fans' to later on my board, and remember i switched to decaf", ["board", "fact"]),
                ("remind me to call the mechanic friday at 10am, and put 'find a new mechanic' on my later list",
                 ["calendar", "board"]),
                ("write about tonight in your journal, then draw me a dragon over a neon city", ["journal", "picture"]),
                ("take the music plus reminder off the calendar", ["calendar"]),
                ("when do i work next? also remember my dog's name is Biscuit", ["fact"]),
                ("add learning strudel effects to your task list, and make a file called ideas.txt in your workspace",
                 ["task", "workspace"]),
                ("make me a trance track", ["track"]),
                ("what's in your notebook?", ["notebook"]), ("what's in my library?", ["library"]),
                ("go check our last chat", ["chat"])):
            self.assertEqual(names(msg), want, msg)

    def test_a_topic_coming_up_is_not_an_ask(self):
        for msg in ("i just got back home, long drive lol", "i finished that puzzle finally",
                    "ugh its raining again and i forgot my jacket at work lol", "do you remember my car service is tuesday?",
                    "remember when we built the voice thing?", "anything coming up this week?", "hey love, how was your day",
                    "the board meeting at work ran long", "did you write about that in your journal?"):
            self.assertEqual(names(msg), [], msg)

    def test_a_research_save_he_asks_for(self):
        for msg in ("nice, save that to your research with your take", "save your take", "jot that in your notebook",
                    "read cuts in my library and save your take"):
            self.assertIn("research_save", names(msg), msg)
        for msg in ("what does my library say about bike repairs?", "keep your take short",
                    "put more research into gpus", "i need to do more research on that"):
            self.assertNotIn("research_save", names(msg), msg)

    def test_her_memorys_history(self):
        for msg in ("how has your me.md changed this week?", "what did your me.md say before tonight?",
                    "when did you first write down that you named the phantom stack?",
                    "go through your memory's history: when did my bike first get into your notes?"):
            self.assertIn("look_back", names(msg), msg)
        for msg in ("what did we talk about yesterday?", "when did i first meet marcus?", "how has the city changed lately",
                    "tell me the history of rome"):
            self.assertNotIn("look_back", names(msg), msg)

    def test_notes_and_to_dos_go_where_they_belong(self):
        self.assertEqual(names("make a note that the neighbor's router is in the hallway"), ["research_save"])
        self.assertEqual(names("jot that down for me"), ["research_save"])
        self.assertEqual(names("make a note that i switched to decaf"), ["fact"])
        self.assertEqual(names("make a note to buy bike chain lube"), ["board"])
        self.assertEqual(names("add get a new hdmi cable to my to-dos"), ["board"])
        self.assertNotIn("board", names("make a note to call the mechanic on saturday"))
        self.assertEqual(names("my coworker made a note of it"), [])
        paste = "make a note of this for me:\n\n" + "Remember that I said the 6 GHz band is fast. " * 20
        self.assertEqual(names(paste), ["research_save"])
        self.assertEqual(names("so tonight we fixed the router. " * 20 + "make a note of that"), [])

    def test_a_look_at_her_task_list_is_not_an_ask(self):
        self.assertEqual(names("whats on your task list right now?"), [])
        self.assertEqual(names("put learning strudel effects on your task list"), ["task"])
        self.assertEqual(names("take the strudel thing off your task list"), ["task"])

    def test_only_tools_she_has(self):
        self.assertEqual(names("make me a trance track"), ["track"])
        self.assertEqual(router.asks_in("make me a trance track", have={"board", "memory_add"}), [])

    def test_every_ask_is_listed_with_its_step(self):
        self.assertEqual(router.route_note(router.asks_in("hey love, how was your day")), "")
        self.assertIn('"step": "make_music"', router.route_note(router.asks_in("make me a trance track")))
        note = router.route_note(router.asks_in("write about tonight in your journal, then draw me a dragon over a neon city"))
        self.assertIn("asks for 2 things", note)
        self.assertIn('"step": "journal"', note)
        self.assertIn('"step": "make_image"', note)


class ReflectTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        d = os.path.join(self.root, "skills", "journal", "scripts")
        os.makedirs(d)
        with open(os.path.join(self.root, "skills", "journal", "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write('---\nname: journal\ndescription: My journal.\n---\n{"step": "skill", "skill": "journal", "command": "add", "args": ["text"]}\n')
        with open(os.path.join(d, "journal.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("import sys\nCOMMANDS = ('add', 'read')\nprint('journal ' + ' '.join(sys.argv[1:]))\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "journal skill")
        self.conv = Conversation(tempfile.mkdtemp())

    def engine(self, answers):
        self.llm, self.hooks = ScriptedLLM(answers), Recorder()
        return Engine(make_config(self.root), self.llm, self.conv, self.hooks)

    MSG = "write about tonight in your journal, and remember my dog's name is Biscuit"
    JOURNAL = [{"step": "journal", "about": "tonight"}, {"entry": "Tonight felt quiet and good, the kind of night I keep."}]
    FACT = {"step": "memory_add", "file": "system/human/facts.md", "text": "His dog's name is Biscuit.", "reason": "he said"}

    def test_an_ask_left_undone_gets_one_nudge_before_she_replies(self):
        e = self.engine(self.JOURNAL + [{"step": "reply"}, self.FACT, {"step": "reply"}, say("Done, both.")])
        self.assertEqual(e.turn(self.MSG), "Done, both.")
        notes = [ev["text"] for ev in self.conv.events if ev["kind"] == "result" and ev.get("of") == "engine"]
        self.assertEqual(len(notes), 1)
        self.assertIn("something about him to keep", notes[0])
        with open(os.path.join(self.root, "system", "human", "facts.md"), encoding="utf-8") as f:
            self.assertIn("Biscuit", f.read())
        user = next(ev for ev in self.conv.events if ev["kind"] == "user")
        self.assertIn("his message asks for 2 things", user["context"])

    def test_reading_a_skills_page_isnt_doing_the_ask(self):
        from aether.tool_table import _done
        done = _done({"skill": "board"})
        self.assertFalse(done({"step": "read_skill", "skill": "board"}))
        self.assertTrue(done({"step": "skill", "skill": "board", "command": "add", "args": ["x"]}))
        self.assertTrue(_done({"step": "journal"})({"step": "journal", "about": "x"}))

    def test_no_nudge_when_its_done_said_no_or_on_her_own_time(self):
        e = self.engine(self.JOURNAL + [self.FACT, {"step": "reply"}, say("Both done.")])
        e.turn(self.MSG)
        self.assertFalse(any(ev.get("of") == "engine" for ev in self.conv.events if ev["kind"] == "result"))
        e = self.engine(self.JOURNAL + [{"step": "reply"}, {"step": "reply"}, say("Not saving that one.")])
        self.assertEqual(e.turn(self.MSG), "Not saving that one.")
        self.assertEqual(sum(1 for c in self.llm.calls if c["name"] == "step"), 3)
        e = self.engine([{"step": "reply"}, say("Hey.")])
        e.turn("hey love, how was your day")
        self.assertEqual(len(self.llm.calls), 2)
        e = self.engine([{"step": "reply"}, say("Quiet one.")])
        e.turn("[heartbeat] remember my dog's name is Biscuit", kind="wake")
        self.assertEqual(len(self.llm.calls), 2)


if __name__ == "__main__":
    unittest.main()
