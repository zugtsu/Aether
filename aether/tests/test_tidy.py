import datetime as dt
import os
import unittest

from aether.llm import ScriptedLLM
from aether.memory import Memory
from aether.tests.fixture import git, make_config, make_memory
from aether.tidy import ABOUT, CORE, FACTS, HISTORY, JOURNAL, roll_facts, roll_journal, tidy_facts

MESSY = """---
description: Facts Jordan told me about himself, in his words, dated. APPEND-ONLY.
---
- 2026-09-18: Rents a storage locker for $30 every 2 months. Paid today, so next due is in 2 months.
- 2026-09-18: Rents a storage locker for $30 every 2 months. Paid today, so next due is in 2 months.
# Facts Jordan told me (verbatim, append-only)

Rule for me: add ONE dated line at the bottom; never edit or remove lines.

- 2026-09-13: Name is Jordan. Lives in Springfield.
- 2026-09-25: Currently binge-watching Frieren.
- 2026-09-14: Owns a bike.
2026-09-21: Rents a storage locker for  every 2 months. Next due date is Nov 3rd.
"""
TODAY = dt.date(2026, 9, 26)


class TidyTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        self.cfg = make_config(self.root)
        os.makedirs(os.path.join(self.root, "system", "human"), exist_ok=True)
        with open(os.path.join(self.root, *FACTS.split("/")), "w", encoding="utf-8", newline="\n") as f:
            f.write(MESSY)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "messy facts")
        self.mem = Memory(self.root, self.cfg)

    def facts(self):
        with open(os.path.join(self.root, *FACTS.split("/")), encoding="utf-8") as f:
            return f.read()

    def history(self):
        with open(os.path.join(self.root, *HISTORY.split("/")), encoding="utf-8") as f:
            return f.read()

    def test_code_part_dedupes_fixes_and_sorts(self):
        r = tidy_facts(self.mem, None, TODAY)
        text = self.facts()
        self.assertEqual(r["duplicates"], 1)
        self.assertEqual(text.count("$30 every 2 months"), 1)
        self.assertIn("- 2026-09-21: Rents a storage locker", text)
        body = text.split("Rule for me")[1]
        self.assertLess(body.index("2026-09-13"), body.index("2026-09-14"))
        self.assertLess(body.index("2026-09-18"), body.index("2026-09-25"))
        self.assertTrue(text.startswith("---\ndescription: Facts User told me") and "Aether tidies" in text)
        self.assertIn("duplicate removed", self.history())
        self.assertIn("facts tidy", git(self.root, "log", "-1", "--format=%s"))

    def test_good_merge_is_used_and_old_lines_kept_in_history(self):
        llm = ScriptedLLM([{"merges": [{"lines": [3, 4], "why": "same locker",
                                        "text": "Rents a storage locker for $30 every 2 months. Next due date is Nov 3rd."}],
                            "retire": []}])
        r = tidy_facts(self.mem, llm, TODAY)
        self.assertEqual(r["merged"], 1, r["refused"])
        text = self.facts()
        self.assertIn("- 2026-09-21: Rents a storage locker for $30 every 2 months. Next due date is Nov 3rd.", text)
        self.assertEqual(text.count("storage locker"), 1)
        self.assertIn("was: 2026-09-21: Rents a storage locker for every 2 months", self.history())

    def test_merges_that_invent_or_drop_numbers_are_refused(self):
        llm = ScriptedLLM([{"merges": [
            {"lines": [3, 4], "why": "x", "text": "Rents a storage locker for $35 every 2 months, due Nov 3rd."},
            {"lines": [3, 4], "why": "x", "text": "Rents a storage locker every 2 months, due Nov 3rd."}],
            "retire": []}])
        r = tidy_facts(self.mem, llm, TODAY)
        self.assertEqual(r["merged"], 0)
        self.assertEqual(len(r["refused"]), 2)
        self.assertIn("$30", self.facts())

    def test_a_merge_keeps_how_sure_he_was(self):
        from aether.tidy import check_merge
        facts = [("2026-09-20", "His car engine has been making a noise since the road trip week."),
                 ("2026-09-24", "Might see a mechanic next week about his car engine noise.")]
        sure = {"lines": [1, 2], "text": "Is seeing a mechanic next week about his car engine noise."}
        self.assertIn("surer than he was", check_merge(facts, sure))
        self.assertIsNone(check_merge(facts, {"lines": [1, 2], "text": "Might see a mechanic next week about his "
                                                                          "car engine, which has been making a noise."}))
        settled = facts + [("2026-09-26", "Mechanic appointment for his car engine noise is Monday.")]
        self.assertIsNone(check_merge(settled, {"lines": [2, 3], "text": "Mechanic appointment for his car engine noise is Monday."}))

    def test_the_real_failures_from_the_trial_run(self):
        llm = ScriptedLLM([{"merges": [{"lines": [1, 2], "why": "brevity", "text": "Name is Jordan. Lives in Springfield. Owns a bike."}],
                            "retire": [{"line": 3, "why": "line 4 is newer"}]}])
        r = tidy_facts(self.mem, llm, TODAY)
        self.assertEqual((r["merged"], r["retired"]), (0, 0), r)
        self.assertIn("$30", self.facts())
        self.assertTrue(any("merge them instead" in x for x in r["refused"]))
        llm = ScriptedLLM([{"merges": [{"lines": [3, 4], "why": "same locker",
                                        "text": "2026-09-21: Rents a storage locker for $30 every 2 months. Next due date is Nov 3rd."}],
                            "retire": []}])
        r = tidy_facts(Memory(self.root, self.cfg), llm, TODAY)
        self.assertEqual(r["merged"], 1, r["refused"])
        self.assertIn("- 2026-09-21: Rents a storage locker for $30", self.facts())

    def test_retire_needs_a_newer_line_or_an_old_time_bound_fact(self):
        llm = ScriptedLLM([{"merges": [], "retire": [{"line": 5, "why": "probably done"}, {"line": 2, "why": "old"}]}])
        r = tidy_facts(self.mem, llm, TODAY)
        self.assertEqual(r["retired"], 0)
        self.assertIn("Frieren", self.facts())
        llm = ScriptedLLM([{"merges": [], "retire": [{"line": 5, "why": "a month ago"}]}])
        r = tidy_facts(Memory(self.root, self.cfg), llm, TODAY + dt.timedelta(days=30))
        self.assertEqual(r["retired"], 1, r["refused"])
        self.assertNotIn("Frieren", self.facts())
        self.assertIn("retired (a month ago): 2026-09-25: Currently binge-watching Frieren", self.history())

    def test_dry_run_and_clean_file_change_nothing(self):
        before = self.facts()
        r = tidy_facts(self.mem, None, TODAY, dry_run=True)
        self.assertEqual(self.facts(), before)
        self.assertIn("preview", r)
        tidy_facts(self.mem, None, TODAY)
        head = git(self.root, "rev-parse", "HEAD")
        self.assertFalse(tidy_facts(Memory(self.root, self.cfg), None, TODAY)["changed"])
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), head)


JOURNAL_TEXT = """---
description: My journal.
---
- 2026-09-26: Newest thought.
- 2026-09-20: Last week.
  a second line of that entry
- 2026-09-02: Early September, over three weeks ago.
- 2026-08-30: End of August.
"""


class JournalRollTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        self.mem = Memory(self.root, make_config(self.root))
        with open(os.path.join(self.root, *JOURNAL.split("/")), "w", encoding="utf-8", newline="\n") as f:
            f.write(JOURNAL_TEXT)
        git(self.root, "commit", "-qam", "journal")

    def read(self, rel):
        with open(os.path.join(self.root, *rel.split("/")), encoding="utf-8") as f:
            return f.read()

    def test_three_weeks_stay_older_ones_move_to_monthly_archives(self):
        r = roll_journal(self.mem, TODAY, keep_days=21)
        self.assertEqual((r["moved"], r["kept"]), (2, 2))
        j = self.read(JOURNAL)
        self.assertTrue(j.startswith("---\ndescription: My journal.\n---\n- 2026-09-26: Newest thought."))
        self.assertIn("a second line of that entry", j)
        self.assertNotIn("2026-09-02", j)
        self.assertIn("2026-09-02: Early September", self.read("reference/journal/2026-09.md"))
        self.assertIn("2026-08-30: End of August", self.read("reference/journal/2026-08.md"))
        self.assertIn("August 2026", self.read("reference/journal/2026-08.md"))
        self.assertIn("journal roll-over: 2 older entries", git(self.root, "log", "-1", "--format=%s"))
        self.assertEqual(roll_journal(self.mem, TODAY, keep_days=21)["moved"], 0)

    def test_size_cap_moves_the_oldest_overflow(self):
        r = roll_journal(self.mem, TODAY, keep_days=60, max_chars=60)
        self.assertEqual(r["kept"], 1)
        self.assertIn("- 2026-09-26: Newest thought.", self.read(JOURNAL))
        self.assertIn("2026-09-20: Last week.", self.read("reference/journal/2026-09.md"))

    def test_archive_is_aethers_not_a_memory_step(self):
        self.assertTrue(any(k.startswith("reference/journal/") for k in make_config(self.root).protected))


if __name__ == "__main__":
    unittest.main()


FACTS_TEXT = """---
description: Facts Jordan told me about himself, in his words, dated. Aether tidies this file every night.
---
# Facts Jordan told me

- 2026-08-20: Hates cilantro.
- 2026-09-01: Rides a green bicycle to the garden.
- 2026-09-20: Started growing basil on the windowsill.
"""


class FactsRollTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        self.mem = Memory(self.root, make_config(self.root))
        os.makedirs(os.path.join(self.root, "system", "human"), exist_ok=True)
        with open(os.path.join(self.root, *FACTS.split("/")), "w", encoding="utf-8", newline="\n") as f:
            f.write(FACTS_TEXT)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "facts")

    def read(self, rel):
        with open(os.path.join(self.root, *rel.split("/")), encoding="utf-8") as f:
            return f.read()

    def test_a_month_stays_older_lines_move_never_lost(self):
        r = roll_facts(self.mem, TODAY, keep_days=30)
        self.assertEqual((r["moved"], r["kept"]), (1, 2))
        facts = self.read(FACTS)
        self.assertNotIn("cilantro", facts)
        self.assertIn("- 2026-09-01: Rides a green bicycle to the garden.", facts)
        self.assertIn("# Facts Jordan told me", facts)
        about = self.read(ABOUT)
        self.assertIn("- 2026-08-20: Hates cilantro.", about)
        self.assertIn("recall finds them", about)
        self.assertIn("facts roll-over: 1 older line", git(self.root, "log", "-1", "--format=%s"))
        self.assertEqual(roll_facts(self.mem, TODAY, keep_days=30)["moved"], 0)

    def test_a_second_roll_appends_to_the_same_file(self):
        roll_facts(self.mem, TODAY, keep_days=30)
        roll_facts(self.mem, dt.date(2026, 10, 5), keep_days=30)
        about = self.read(ABOUT)
        self.assertEqual(about.count("description:"), 1)
        self.assertLess(about.index("cilantro"), about.index("bicycle"))
        self.assertIn("basil", self.read(FACTS))

    def test_core_is_never_rolled(self):
        os.makedirs(os.path.join(self.root, "system", "human"), exist_ok=True)
        with open(os.path.join(self.root, *CORE.split("/")), "w", encoding="utf-8", newline="\n") as f:
            f.write("- 2026-01-01: Name is Jordan.\n")
        roll_facts(self.mem, TODAY, keep_days=30)
        self.assertIn("Name is Jordan", self.read(CORE))
