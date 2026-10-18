import os
import re
import unittest

from aether import config, router, tool_table
from aether.skills import check_skill

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS = os.path.join(PROJECT, "skills")


def skill_commands(name):
    for folder in (os.path.join(SKILLS, name),):
        if os.path.isdir(folder):
            return check_skill(folder).commands
    return None


def skill_sources(name):
    for folder in (os.path.join(SKILLS, name, "scripts"),):
        if os.path.isdir(folder):
            for f in os.listdir(folder):
                if f.endswith(".py"):
                    with open(os.path.join(folder, f), encoding="utf-8") as fh:
                        yield fh.read()


def step_commands(step):
    found = []
    for part in step.split('"command":')[1:]:
        found += re.findall(r'"([\w-]+)"', part.split('"args"')[0])
    return found


class ToolTableTests(unittest.TestCase):
    def test_every_example_ask_routes_the_way_its_row_says(self):
        for tool in tool_table.TOOLS:
            for ask in tool.get("asks", []):
                for msg in ask["yes"]:
                    self.assertIn(ask["name"], [a[0] for a in router.asks_in(msg)], f"{ask['name']}: {msg}")
                for msg in ask["no"]:
                    self.assertNotIn(ask["name"], [a[0] for a in router.asks_in(msg)], f"{ask['name']}: {msg}")

    def test_every_command_a_row_names_is_real(self):
        for tool in tool_table.TOOLS:
            if tool["kind"] != "skill":
                continue
            have = skill_commands(tool["tool"])
            if have is None:
                continue
            for cmd in tool.get("ask_first", []):
                self.assertTrue(any(f'"{cmd}"' in src for src in skill_sources(tool["tool"])),
                                f"{tool['tool']}'s script has no command {cmd!r}")
            named = list(tool.get("reads", []))
            for ask in tool.get("asks", []):
                named += step_commands(ask["step"])
            for cmd in named:
                if have:
                    self.assertIn(cmd, have, f"{tool['tool']} has no command {cmd!r} (its page and script: {have})")

    def test_one_row_per_tool_and_ask(self):
        tools = [t["tool"] for t in tool_table.TOOLS]
        self.assertEqual(len(tools), len(set(tools)))
        names = [a[0] for a in tool_table.asks()]
        self.assertEqual(len(names), len(set(names)))
        for tool in tool_table.TOOLS:
            for ask in tool.get("asks", []):
                self.assertEqual(set(ask) - {"why"}, {"name", "what", "step", "trigger", "done", "yes", "no"}, ask["name"])
                self.assertTrue(ask["yes"], f"{ask['name']} has no example ask")

    def test_the_router_and_the_settings_are_built_from_it(self):
        self.assertEqual([a[0] for a in router.ASKS], [a[0] for a in tool_table.asks()])
        self.assertEqual(router.NEEDS, {a[0]: a[5] for a in tool_table.asks()})
        c = config.Config()
        self.assertEqual(c.lookup_commands, tool_table.lookup_commands())
        self.assertEqual(c.outside_skills, tool_table.outside_skills())
        self.assertEqual(c.ask_first, tool_table.ask_first())
