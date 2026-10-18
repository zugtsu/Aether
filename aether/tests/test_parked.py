import os
import tempfile
import unittest

from aether import parked

BOARD = ("---\ndescription: b\n---\n## Active\n**SeedSwap** | active | next: seed list\n\n## Parked\n"
         "**Moss Tea Garden** | parked 2026-09-28 | an idea\n**greenhouse-monitor** | parked 2026-10-14 | next: audit\n"
         "\n## Done\n**Her eyes** | done\n")


class ParkedTests(unittest.TestCase):

    def setUp(self):
        self.ws = tempfile.mkdtemp()
        folder = os.path.join(self.ws, "greenhouse-monitor")
        os.makedirs(folder)
        for f in ("watering_rules.md", "notification_logic.md", "humidity_logic.md", "known_good_sensors.md", "research.md"):
            open(os.path.join(folder, f), "w").close()

    def test_parked_projects_are_read_off_her_board(self):
        self.assertEqual(parked.parked_projects(BOARD), {"moss-tea-garden", "greenhouse-monitor"})
        self.assertEqual(parked.parked_projects("## Active\n**X** | y\n"), set())
        self.assertEqual(parked.parked_projects(""), set())

    def test_a_parked_projects_words_come_from_its_slug_and_its_folder(self):
        w = parked.words_for("greenhouse-monitor", self.ws)
        self.assertTrue({"greenhouse", "monitor", "watering", "notification", "humidity", "sensors"} <= w, w)
        self.assertNotIn("research", w)
        self.assertEqual(parked.words_for("moss-tea-garden", self.ws), {"garden"})

    def test_a_texts_words_point_at_the_parked_project(self):
        words = parked.parked_words(BOARD, self.ws)
        self.assertEqual(parked.which_parked("Develop watering sync script. Create PowerShell script to read sensors", words),
                         "greenhouse-monitor")
        self.assertEqual(parked.which_parked("compare seed catalog prices", words), "")
        self.assertEqual(parked.which_parked("read the greenhouse-monitor plan", words), "greenhouse-monitor")


if __name__ == "__main__":
    unittest.main()
