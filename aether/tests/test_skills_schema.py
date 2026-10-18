import os
import threading
import time
import unittest

from aether.memory import Memory
from aether.schema import step_schema
from aether.skills import Cancelled, clean_args, discover, run
from aether.tests.fixture import git, make_config, make_memory


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        self.live, self.rejected = discover(self.root)

    def test_check_lets_good_skills_in_and_keeps_bad_ones_out(self):
        self.assertEqual(sorted(self.live), ["echo", "fail", "plants", "slow"])
        self.assertIn("frontmatter", " ".join(self.rejected["nofront"].problems))
        self.assertIn("no scripts", " ".join(self.rejected["noscript"].problems))
        self.assertIn("does not compile", " ".join(self.rejected["badpy"].problems))

    def test_run_passes_args_without_a_shell(self):
        code, out = run(self.live["echo"], "", ["hi there", "a && del *", "$HOME"], self.root)
        self.assertEqual(code, 0)
        self.assertIn("ARGS=hi there|a && del *|$HOME", out)
        self.assertIn("MEM=" + self.root, out)

    def test_failure_code(self):
        code, out = run(self.live["fail"], "", [], self.root)
        self.assertEqual(code, 3)
        self.assertIn("broken on purpose", out)

    def test_timeout(self):
        t = time.time()
        code, out = run(self.live["slow"], "", [], self.root, timeout=1)
        self.assertEqual(code, 124)
        self.assertLess(time.time() - t, 10)

    def test_stop_kills_script(self):
        cancel = threading.Event()
        threading.Timer(0.5, cancel.set).start()
        t = time.time()
        with self.assertRaises(Cancelled):
            run(self.live["slow"], "", [], self.root, cancel=cancel)
        self.assertLess(time.time() - t, 10)

    def test_commands_come_from_the_doc_and_the_script(self):
        self.assertEqual(self.live["plants"].commands, ["next", "skip"])
        self.assertEqual(self.live["echo"].commands, [])

    def test_clean_args(self):
        self.assertEqual(clean_args(None, ["python", "$MEMORY_DIR/skills/w/scripts/w.py", "--tomorrow"]), ["--tomorrow"])
        self.assertEqual(clean_args(None, ["w.py", "add", "later", "x"]), ["add", "later", "x"])
        self.assertEqual(clean_args(None, None), [])
        self.assertEqual(clean_args(None, ["later", "'fine-tune gemma'", '"x"', "it's", "'"]), ["later", "fine-tune gemma", "x", "it's", "'"])


class SchemaTests(unittest.TestCase):
    def test_enums_are_the_real_names(self):
        root = make_memory()
        mem = Memory(root, make_config(root))
        live, _ = discover(root)
        opts = {o["properties"]["step"]["const"] + ":" + o["properties"].get("skill", {}).get("const", ""): o
                for o in step_schema(mem, live)["anyOf"]}
        add = opts["memory_add:"]["properties"]["file"]["enum"]
        self.assertEqual(add, ["reference/almanac/frost.md", "reference/garden.md", "system/human/facts.md"])
        self.assertEqual(opts["memory_replace:"]["properties"]["file"]["enum"],
                         ["reference/almanac/frost.md", "reference/garden.md", "system/human.md", "system/human/facts.md"])
        self.assertEqual(opts["read_skill:"]["properties"]["skill"]["enum"], ["echo", "fail", "plants", "slow"])
        self.assertIn("skill:echo", opts)
        self.assertEqual(opts["skill:plants"]["properties"]["command"]["enum"], ["next", "skip"])
        self.assertNotIn("command", opts["skill:echo"]["properties"])
        self.assertNotIn("skill:nofront", opts)
        for o in opts.values():
            self.assertFalse(o["additionalProperties"])
        only = step_schema(mem, live, allow_tools=False)["anyOf"]
        self.assertEqual(len(only), 1)

    def test_her_notebook_has_one_door(self):
        root = make_memory()
        p = os.path.join(root, "reference", "research", "raffle.md")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("---\ndescription: My research notes on raffle.\n---\n# raffle\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "notebook")
        mem = Memory(root, make_config(root))

        def readable(skills):
            o = next(o for o in step_schema(mem, skills)["anyOf"] if o["properties"]["step"].get("const") == "read_file")
            return o["properties"]["path"]["enum"]
        self.assertIn("reference/research/raffle.md", readable({}))
        from aether.skills import Skill
        nb = {"notebook": Skill("notebook", "")}
        self.assertNotIn("reference/research/raffle.md", readable(nb))
        self.assertIn("reference/garden.md", readable(nb))


if __name__ == "__main__":
    unittest.main()
