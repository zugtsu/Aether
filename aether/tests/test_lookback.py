import os
import subprocess
import unittest

from aether import lookback
from aether.memory import Memory
from aether.tests.fixture import make_config, make_memory


def commit(root, who, msg, rel, text, mode="a"):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, mode, encoding="utf-8", newline="\n") as f:
        f.write(text)
    subprocess.run(["git", "-c", f"user.name={who}", "-c", "user.email=x@x", "-C", root, "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-c", f"user.name={who}", "-c", "user.email=x@x", "-C", root, "commit", "-qm", msg], capture_output=True,
                   check=True)


class LookBackTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        facts = "system/human/facts.md"
        commit(self.root, "Lucy", f"add {facts}: he told me", facts, "- 2026-09-14: Owns a bike. Wants route advice to fit.\n")
        commit(self.root, "Lucy", f"add {facts}: he told me", facts, "- 2026-09-18: Pays $48 club dues on the 1st.\n")
        with open(os.path.join(self.root, *facts.split("/")), encoding="utf-8") as f:
            body = f.read().replace("$48 club dues", "$50 club dues")
        commit(self.root, "Lucy", f"replace {facts}: dues went up", facts, body, mode="w")
        commit(self.root, "Lucy", "Aether: timeline 2026-09-28", "system/timeline.md",
               "- 2026-09-28 03:31 · Jordan told Lucy about his bike. (4)\n")
        commit(self.root, "Jordan", "Jordan edited system/me.md", "system/me.md",
               "---\ndescription: me\n---\n- 2026-10-02: My own voice is Breeze.\n", mode="w")
        commit(self.root, "Lucy", "add system/me.md: new", "system/me.md", "- 2026-10-02: I like thunderstorms.\n")
        self.mem = Memory(self.root, make_config(self.root))
        app = type("App", (), {})()
        app.engine = type("E", (), {"memory": self.mem})()
        self.step = lookback.LookBack(app).run_step

    def test_when_did_i_learn_it(self):
        ok, text = self.step({"step": "look_back", "about": "when did you learn about my bike"})
        self.assertTrue(ok)
        lines = text.splitlines()
        self.assertIn("with bike", lines[0])
        self.assertTrue(lines[1].startswith("2026-"))
        self.assertIn("· you · system/human/facts.md · added: Owns a bike. Wants route advice to fit.", lines[1])
        self.assertIn("· Aether · system/timeline.md · added:", text)

    def test_a_change_shows_was_and_now_and_a_word_finds_its_start_only(self):
        ok, text = self.step({"step": "look_back", "about": "dues"})
        self.assertIn("added: Pays $48 club dues on the 1st.", text)
        self.assertIn("changed: Pays $48 club dues on the 1st. -> now: Pays $50 club dues on the 1st.", text)
        _, text = self.step({"step": "look_back", "about": "dues"})
        self.assertNotIn("current", text.lower())

    def test_a_file_shows_its_newest_changes_and_who(self):
        ok, text = self.step({"step": "look_back", "about": "me.md"})
        self.assertTrue(ok)
        self.assertIn("changes to system/me.md", text)
        self.assertIn("· {USER} · system/me.md · added: My own voice is Breeze.", text)
        self.assertIn("· you · system/me.md · added: I like thunderstorms.", text)
        self.assertNotIn("description:", text)

    def test_she_writes_a_sentence_instead_of_a_word(self):
        _, text = self.step({"step": "look_back", "about": "what system/me.md said before"})
        self.assertIn("changes to system/me.md", text)
        _, text = self.step({"step": "look_back", "about": "Checking the history of the dues entry"})
        self.assertIn("with dues,", text.splitlines()[0] + ",")
        self.assertIn("Pays $48 club dues", text)
        self.assertEqual(lookback.LookBack(None).option()["properties"]["about"]["maxLength"], lookback.ABOUT_MAX)
        ok, text = self.step({"step": "look_back", "about": "Checking my own history to see what was'"})
        self.assertFalse(ok)
        self.assertIn("a word or two", text)
        long = "reference/research/voice-recognition-for-the-avatar-to-uniquely-ide.md"
        self.assertLessEqual(len(long), lookback.ABOUT_MAX)
        self.assertEqual(lookback.FILE_IN.search(f"what {long} said before").group(0), long)

    def test_nothing_found_and_nothing_asked(self):
        ok, text = self.step({"step": "look_back", "about": "xyzzy"})
        self.assertTrue(ok)
        self.assertIn("never reached your memory files", text)
        ok, text = self.step({"step": "look_back", "about": "when did you"})
        self.assertFalse(ok)

    def test_a_line_moved_between_files_is_one_line(self):
        jr = "system/journal.md"
        commit(self.root, "Lucy", "journal: entry", jr, "- 2026-09-20: A quiet night, thinking about the lighthouse.\n")
        with open(os.path.join(self.root, *jr.split("/")), encoding="utf-8") as f:
            body = f.read().replace("- 2026-09-20: A quiet night, thinking about the lighthouse.\n", "")
        os.makedirs(os.path.join(self.root, "reference", "journal"), exist_ok=True)
        with open(os.path.join(self.root, "reference", "journal", "2026-09.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("- 2026-09-20: A quiet night, thinking about the lighthouse.\n")
        commit(self.root, "Lucy", "journal roll-over: 1 entry", jr, body, mode="w")
        _, text = self.step({"step": "look_back", "about": "lighthouse"})
        self.assertIn("· Aether · system/journal.md -> reference/journal/2026-09.md · moved: A quiet night", text)
        self.assertEqual(text.count("A quiet night"), 2)


class LookBackInTheAppTests(unittest.TestCase):
    def test_it_is_on_her_menu_and_in_her_skills_list_and_only_reads(self):
        import tempfile
        from aether.history import Conversation
        from aether.llm import ScriptedLLM
        from aether.server import make_server
        root = make_memory()
        commit(root, "Lucy", "add system/human/facts.md: he told me", "system/human/facts.md", "- 2026-09-14: Owns a bike.\n")
        llm = ScriptedLLM([{"step": "look_back", "about": "bike"}, {"step": "reply"}, {"say": "Since 9/14."}])
        httpd, app = make_server(make_config(root), llm, port=0)
        try:
            app.engine.conv = Conversation(tempfile.mkdtemp())
            head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
            app.engine.turn("when did i first tell you about my bike?")
            res = next(e for e in app.engine.conv.events if e["kind"] == "result")
            self.assertTrue(res["ok"])
            self.assertIn("· you · system/human/facts.md · added: Owns a bike.", res["text"])
            self.assertIn("look_back", llm.calls[0]["messages"][0]["content"])
            self.assertTrue(app.engine._is_lookup({"step": "look_back", "about": "x"}))
            self.assertEqual(subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True,
                                            text=True).stdout, head)
        finally:
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
