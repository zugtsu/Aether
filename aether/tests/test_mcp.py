import os
import subprocess
import sys
import tempfile
import unittest

from aether.engine import Engine
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.mcp import McpError, McpServer, parse_args
from aether.proc import python_exe
from aether.skills import check_skill
from aether.tests.fixture import git, make_config, make_memory
from aether.tests.test_engine import Recorder

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import add_mcp as gen  # noqa: E402

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_mcp_server.py")


class ClientTests(unittest.TestCase):
    def test_hello_tools_and_calls(self):
        with McpServer(python_exe(), [FAKE, "--chatty"]) as s:
            self.assertEqual(s.info["serverInfo"]["name"], "fake-server")
            self.assertEqual([t["name"] for t in s.tools()], ["add", "shout", "boom"])
            self.assertEqual(s.call("add", {"a": 2, "b": 40}), (True, "42"))
            self.assertEqual(s.call("boom", {}), (False, "it broke"))
            with self.assertRaises(McpError):
                s.call("nope", {})

    def test_a_server_that_wont_start_or_talk(self):
        with self.assertRaises(McpError):
            McpServer("no-such-program-anywhere-1234")
        with self.assertRaises(McpError):
            McpServer(python_exe(), ["-c", "print('not mcp')"], timeout=5)

    def test_her_args_are_typed_by_the_schema(self):
        schema = {"properties": {"a": {"type": "integer"}, "on": {"type": "boolean"}, "t": {"type": "string"}},
                  "required": ["a"]}
        self.assertEqual(parse_args(schema, ["a=3", "on=yes", "t=x=y"]), ({"a": 3, "on": True, "t": "x=y"}, ""))
        self.assertIn("missing: a", parse_args(schema, ["t=x"])[1])
        self.assertIn("no 'b' here", parse_args(schema, ["a=1", "b=2"])[1])
        self.assertIn("should be a integer", parse_args(schema, ["a=three"])[1])
        self.assertIn("isn't name=value", parse_args(schema, ["three"])[1])


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()

    def test_a_server_becomes_a_skill(self):
        folder, report = gen.build("fake", "Adds numbers and shouts; use when {USER} asks to add or shout.", python_exe(),
                                   [FAKE], examples={"shout": ["text=hello"]}, out_root=self.out)
        self.assertTrue(folder, report)
        s = check_skill(folder)
        self.assertTrue(s.ok, s.problems)
        self.assertTrue(s.mcp)
        self.assertEqual(s.commands, ["add", "boom", "shout"])
        self.assertEqual(s.reads, [])
        self.assertEqual(s.ask_first, ["add", "boom", "shout"])
        self.assertTrue(any("the server calls these read-only: add, boom" in ln and "--reads add,boom" in ln
                            for ln in report), report)
        folder2, _ = gen.build("fake2", "x", python_exe(), [FAKE], reads={"add", "boom"}, out_root=self.out)
        s2 = check_skill(folder2)
        self.assertEqual((s2.reads, s2.ask_first), (["add", "boom"], ["shout"]))
        self.assertIn('{"step": "skill", "skill": "fake", "command": "shout", "args": ["text=hello"]}', s.doc)
        self.assertIn('"command": "add", "args": ["a=<a>", "b=<b>"]', s.doc)
        self.assertIn("## shout (asks {USER} first)", s.doc)
        self.assertIn("Takes: text (string, required): what to shout", s.doc)
        self.assertTrue(s.description.startswith("Adds numbers and shouts; use when {USER} asks to add or shout. Its args"))
        self.assertTrue(s.description.endswith('name=value: add ["a=<a>", "b=<b>"]; shout ["text=hello"].'))
        script = os.path.join(folder, "scripts", "fake.py")
        r = subprocess.run([python_exe(), "-I", script, "add", "a=2", "b=3"], capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "5"))
        r = subprocess.run([python_exe(), "-I", script, "add", "a=2"], capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (2, "error: missing: b"))
        r = subprocess.run([python_exe(), "-I", script, "boom"], capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (1, "it broke"))

    def test_a_poisoned_tool_is_flagged_and_nothing_is_written(self):
        folder, report = gen.build("fake", "x", python_exe(), [FAKE, "--poison"], out_root=self.out)
        self.assertIsNone(folder)
        bad = next(r for r in report if r.strip().startswith("notes:"))
        for why in ("a hidden-instruction tag", "gives the model orders", "mentions secrets", "talks about her prompt"):
            self.assertIn(why, bad)
        self.assertIn("clean", next(r for r in report if r.strip().startswith("add:")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "fake")))
        folder, _ = gen.build("fake", "x", python_exe(), [FAKE, "--poison"], only={"add", "shout"}, out_root=self.out)
        self.assertEqual(check_skill(folder).commands, ["add", "shout"])

    def test_a_tool_in_neither_list_asks_first(self):
        folder, _ = gen.build("fake", "x", python_exe(), [FAKE], reads={"add"}, out_root=self.out)
        md = os.path.join(folder, "SKILL.md")
        with open(md, encoding="utf-8") as f:
            text = f.read().replace("ask_first: boom, shout", "ask_first:")
        with open(md, "w", encoding="utf-8") as f:
            f.write(text)
        self.assertEqual(check_skill(folder).ask_first, ["boom", "shout"])


class EngineTests(unittest.TestCase):

    def setUp(self):
        self.root = make_memory()
        gen.build("fake", "Adds numbers and shouts; use when {USER} asks to add or shout.", python_exe(), [FAKE],
                  reads={"add", "boom"}, out_root=os.path.join(self.root, "skills"))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "fake mcp skill")
        self.cfg = make_config(self.root)
        self.conv = Conversation(tempfile.mkdtemp())

    def engine(self, answers, allow=False):
        self.hooks = Recorder(allow=allow)
        return Engine(self.cfg, ScriptedLLM(answers), self.conv, self.hooks)

    def test_a_read_tool_runs_and_its_answer_is_outside_content(self):
        e = self.engine([{"step": "skill", "skill": "fake", "command": "add", "args": ["a=2", "b=40"]},
                         {"step": "reply"}, {"say": "42."}])
        e.turn("add 2 and 40 with your fake tool")
        self.assertEqual(self.hooks.asked, [])
        self.assertEqual(self.hooks.results[0][:2], ("skill", True))
        self.assertIn("42", self.hooks.results[0][2])
        res = next(ev for ev in self.conv.events if ev["kind"] == "result")
        self.assertEqual(res.get("outside"), "fake")

    def test_a_tool_that_changes_things_asks_first(self):
        e = self.engine([{"step": "skill", "skill": "fake", "command": "shout", "args": ["text=hi"]},
                         {"step": "reply"}, {"say": "He said no."}])
        e.turn("shout hi")
        self.assertEqual(len(self.hooks.asked), 1)
        self.assertIn("Companion wants to run: fake shout text=hi", self.hooks.asked[0])
        self.assertFalse(self.hooks.results[0][1])
        e = self.engine([{"step": "skill", "skill": "fake", "command": "shout", "args": ["text=hi"]},
                         {"step": "reply"}, {"say": "HI."}], allow=True)
        e.turn("shout hi")
        self.assertEqual(self.hooks.results[0][:2], ("skill", True))
        self.assertIn("HI", self.hooks.results[0][2])

    def test_after_an_mcp_answer_only_read_tools_run(self):
        e = self.engine([{"step": "skill", "skill": "fake", "command": "add", "args": ["a=1", "b=1"]},
                         {"step": "reply"}, {"say": "2."}])
        e.turn("x")
        self.assertTrue(e._is_lookup({"step": "skill", "skill": "fake", "command": "add", "args": []}))
        self.assertFalse(e._is_lookup({"step": "skill", "skill": "fake", "command": "shout", "args": []}))


if __name__ == "__main__":
    unittest.main()
