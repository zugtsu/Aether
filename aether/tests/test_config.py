import json
import os
import tempfile
import unittest

from aether import config as config_mod
from aether.config import Config


class SafetyListsFromCodeTests(unittest.TestCase):

    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "aether.json")

    def test_save_leaves_them_out(self):
        config_mod.save(Config(display_name="Lucy"), self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["display_name"], "Lucy")
        for k in config_mod.FROM_CODE:
            self.assertNotIn(k, data)

    def test_an_old_copy_in_the_file_is_ignored(self):
        code = Config()
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"display_name": "Lucy", "ask_first": {"board": []}, "lookup_commands": {"rain-gauge": ["readings"]},
                       "outside_skills": []}, f)
        cfg = config_mod.load(self.path)
        self.assertEqual(cfg.display_name, "Lucy")
        self.assertEqual(cfg.ask_first, code.ask_first)
        self.assertEqual(cfg.lookup_commands, code.lookup_commands)
        self.assertEqual(sorted(cfg.outside_skills), sorted(code.outside_skills))

    def test_saves_from_two_threads_dont_collide(self):
        import threading
        errors = []

        def many():
            try:
                for _ in range(100):
                    config_mod.save(Config(), self.path)
            except Exception as e:
                errors.append(e)
        ts = [threading.Thread(target=many) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])
        config_mod.load(self.path)


if __name__ == "__main__":
    unittest.main()
