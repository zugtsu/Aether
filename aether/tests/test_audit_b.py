import datetime as dt
import os
import types
import unittest

from aether.life import Life, check_cron
from aether.memory import Memory
from aether.tests.fixture import make_config, make_memory

FACTS = "system/human/facts.md"


class ReminderPatternTests(unittest.TestCase):

    def test_good_patterns_pass(self):
        for expr in ("30 20 * * *", "*/15 9-17 * * 1-5", "0 8 1,15 * *", "0 9 * * 7"):
            check_cron(expr)
            Life._check_schedule(expr, "water the ferns", "")

    def test_bad_patterns_are_refused_with_the_reason(self):
        for expr, why in (("0 25 * * *", "hour"), ("x 9 * * *", "minute"), ("0 9 32 * *", "day"),
                          ("0 9 * 13 *", "month"), ("0 9 * * 8", "weekday"), ("5-1 9 * * *", "backwards"),
                          ("*/0 9 * * *", "minute"), ("0 9 * *", "5 parts")):
            with self.assertRaises(ValueError, msg=expr) as e:
                Life._check_schedule(expr, "water the ferns", "")
            self.assertIn(why, str(e.exception), expr)


class LateDreamTests(unittest.TestCase):

    def life(self, dream="23:30", state=None):
        fake = types.SimpleNamespace(cfg=types.SimpleNamespace(dream_time=dream), state=dict(state or {}))
        fake._job_day = Life._job_day
        return fake

    def test_a_window_past_midnight_runs_once_a_night(self):
        lf = self.life()
        night = dt.datetime(2026, 10, 12, 23, 40)
        self.assertTrue(Life._due_daily(lf, "dream", "23:30", night))
        lf.state["last_dream"] = Life._job_day("23:30", night)
        self.assertFalse(Life._due_daily(lf, "dream", "23:30", night + dt.timedelta(minutes=40)))
        self.assertTrue(Life._due_daily(lf, "dream", "23:30", night + dt.timedelta(days=1)))

    def test_a_job_that_starts_past_midnight_runs(self):
        lf = self.life()
        after = dt.datetime(2026, 10, 13, 0, 10)
        self.assertTrue(Life._due_daily(lf, "keeper", "23:30", after, after_min=35))
        self.assertFalse(Life._due_daily(lf, "keeper", "23:30", after.replace(hour=4), after_min=35))

    def test_near_the_nightly_jobs_wraps_midnight(self):
        lf = self.life()
        for hm, near in (("23:19", False), ("23:20", True), ("23:59", True), ("00:14", True), ("00:15", False)):
            h, m = map(int, hm.split(":"))
            self.assertEqual(Life._near_nightly(lf, dt.datetime(2026, 10, 13, h, m)), near, hm)

    def test_his_usual_time_is_unchanged(self):
        lf = self.life("13:00")
        self.assertTrue(Life._due_daily(lf, "dream", "13:00", dt.datetime(2026, 10, 12, 13, 5)))
        self.assertFalse(Life._due_daily(lf, "dream", "13:00", dt.datetime(2026, 10, 12, 12, 55)))
        lf.state["last_dream"] = Life._job_day("13:00", dt.datetime(2026, 10, 12, 13, 5))
        self.assertFalse(Life._due_daily(lf, "dream", "13:00", dt.datetime(2026, 10, 12, 15, 0)))
        self.assertTrue(Life._due_daily(lf, "dream", "13:00", dt.datetime(2026, 10, 13, 13, 5)))


class MemoryAuditTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        self.mem = Memory(self.root, make_config(self.root))

    def facts(self):
        with open(os.path.join(self.root, *FACTS.split("/")), encoding="utf-8") as f:
            return f.read()

    def test_a_one_line_fact_stays_one_line(self):
        self.mem.add(FACTS, "He drinks green tea.", "r")
        self.mem.replace(FACTS, "He drinks green tea.", "He drinks oolong now,\nnot green tea.", "r")
        body = self.facts()
        self.assertIn("He drinks oolong now, not green tea.", body)
        self.assertNotIn("now,\nnot", body)
        self.assertEqual(len([ln for ln in body.splitlines() if "oolong" in ln]), 1)
