import unittest

from aether.gpu import GB, summary

BIG, SMALL = "luid_0x00000000_0x000119B2_phys_0", "luid_0x00000000_0x0000A1C3_phys_0"


class VramTests(unittest.TestCase):

    def test_the_big_card_and_what_uses_it(self):
        programs = {10: ("llama-server.exe", 1), 11: ("audiocpp_server.exe", 2), 12: ("game.exe", 3),
                    13: ("electron.exe", 4), 20: ("python.exe", 2), 21: ("python.exe", 20),
                    30: ("dwm.exe", 1), 31: ("Discord.exe", 1)}
        procs = {(10, BIG): 5 * GB, (11, BIG): 2 * GB, (12, BIG): GB, (13, BIG): GB // 2, (21, BIG): 3 * GB // 2,
                 (30, BIG): 8 * GB,
                 (31, SMALL): GB}
        v = summary({BIG: 11 * GB, SMALL: 2 * GB}, procs, programs, total=12 * GB, card="Example GPU 12GB",
                    pictures=(20,))
        self.assertEqual((v["used"], v["total"], v["card"]), (11 * GB, 12 * GB, "Example GPU 12GB"))
        self.assertEqual([(p["name"], p["bytes"]) for p in v["parts"]],
                         [("Gemma", 5 * GB), ("voice", 2 * GB), ("pictures", 3 * GB // 2),
                          ("the Aether window", GB // 2), ("everything else", 2 * GB)])

    def test_nothing_to_read(self):
        self.assertIsNone(summary({}, {}, {}))
        v = summary({BIG: GB}, {}, {})
        self.assertEqual(v["parts"], [{"name": "everything else", "bytes": GB}])


if __name__ == "__main__":
    unittest.main()
