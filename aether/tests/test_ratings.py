import datetime as dt
import http.client
import json
import os
import tempfile
import threading
import unittest

from aether import ratings
from aether.llm import ScriptedLLM
from aether.memory import Memory, MemoryError_
from aether.server import make_server
from aether.tests.fixture import git, make_config, make_memory

TRACK = ("// SHADOW LOGIC · dark liquid dnb · 175 BPM · F#:phrygian\nsetcpm(175/4)\nconst key  = `F#:phrygian`\n"
         "const prog = `<0 1 0 -1>`\nconst lead = n(`0 2`).scale(key).s(`gm_flute`)\nconst pad = n(`0`).s(`sawtooth`)\n"
         "arrange([8, stack(lead, pad)])")
OTHER = TRACK.replace("SHADOW LOGIC", "VOID WALK").replace("175", "172")


class RatingTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        self.cfg = make_config(self.root)
        self.mem = Memory(self.root, self.cfg)
        self.now = dt.datetime(2026, 10, 4, 21, 12)

    def lines(self):
        with open(os.path.join(self.root, *ratings.REL.split("/")), encoding="utf-8") as f:
            return [ln.rstrip("\n") for ln in f if ln.startswith("- ")]

    def test_what_a_track_is_comes_from_its_own_code(self):
        self.assertEqual(ratings.summary(TRACK), "SHADOW LOGIC · dark liquid dnb · 175 BPM · F#:phrygian · "
                                                 "chords <0 1 0 -1> · sounds gm_flute, sawtooth")
        self.assertEqual(ratings.track_id(TRACK), ratings.track_id("\n" + TRACK + "\n  "))
        self.assertNotEqual(ratings.track_id(TRACK), ratings.track_id(OTHER))

    def test_a_rating_is_one_line_he_can_change_or_take_back(self):
        r = ratings.rate(self.mem, TRACK, "up", now=self.now)
        self.assertIn("commit", r["message"])
        self.assertEqual(self.lines(), [f"- 2026-10-04 9:12 PM · 👍 · {ratings.summary(TRACK)} · id {r['id']}"])
        ratings.rate(self.mem, OTHER, "down", now=self.now)
        ratings.rate(self.mem, TRACK, "down", now=self.now)
        self.assertEqual([("👎" in ln, "SHADOW" in ln) for ln in self.lines()], [(True, False), (True, True)])
        self.assertEqual(ratings.all_ratings(self.mem), {ratings.track_id(TRACK): "down", ratings.track_id(OTHER): "down"})
        ratings.rate(self.mem, TRACK, "none", now=self.now)
        self.assertEqual(len(self.lines()), 1)
        self.assertIn("{USER} took back his rating of SHADOW LOGIC", git(self.root, "log", "-1", "--format=%s"))
        with self.assertRaises(ValueError):
            ratings.rate(self.mem, TRACK, "meh")
        with self.assertRaises(MemoryError_):
            self.mem.add(ratings.REL, "- 👍 everything I make", "r")


class HerTracksTests(unittest.TestCase):

    def test_her_tracks_from_her_replies_only(self):
        from aether.history import Conversation
        folder = tempfile.mkdtemp()
        a, b = Conversation(folder), Conversation(folder)
        a.add("user", text="make me one", context="", ts="2026-10-04T00:20:00")
        a.add("result", of="skill", ok=True, text="Your starter:\n```js\n" + OTHER + "\n```", ts="2026-10-04T00:20:05")
        a.add("reply", text="Here's mine:\n```js\n" + TRACK + "\n```\nHow does it hit?", ts="2026-10-04T00:20:30")
        a.add("reply", text="A script:\n```python\nprint('stack(')\n```", ts="2026-10-04T00:21:00")
        b.add("user", text="again?", context="", ts="2026-10-04T00:40:00")
        b.add("reply", text="Same one, louder:\n```\n" + TRACK + "\n```", ts="2026-10-04T00:40:20")
        b.add("reply", text="New:\n```js\n" + OTHER + "\n```", ts="2026-10-04T00:41:00")
        got = ratings.her_tracks(folder)
        self.assertEqual([(t["title"], t["chat"], t["made"]) for t in got],
                         [("VOID WALK", b.id, "2026-10-04T00:41:00"), ("SHADOW LOGIC", a.id, "2026-10-04T00:20:30")])
        self.assertTrue(got[0]["about"].startswith("dark liquid dnb · 172 BPM"))
        self.assertEqual(got[1]["code"], TRACK)
        self.assertEqual(ratings.her_tracks(os.path.join(folder, "missing")), [])
        own, mine = TRACK.replace("SHADOW LOGIC", "NIGHT DRIVE"), TRACK.replace("SHADOW LOGIC", "FOR JORDAN")
        hb = Conversation(folder, "heartbeat")
        hb.add("reply", text="Kept this one:\n```js\n" + own + "\n```", ts="2026-10-04T01:00:00")
        hb.add("reply", text="For him:\n```js\n" + mine + "\n```", ts="2026-10-04T01:10:00")
        b.add("reach_out", text="Made you something:\n```js\n" + mine + "\n```", ts="2026-10-04T01:10:01")
        where = {t["title"]: t["chat"] for t in ratings.her_tracks(folder)}
        self.assertEqual((where["NIGHT DRIVE"], where["FOR JORDAN"]), ("heartbeat", b.id))


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        self.httpd, self.app = make_server(make_config(self.root), ScriptedLLM([]), port=0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)
        h = {"Host": f"127.0.0.1:{self.httpd.server_address[1]}", "X-Aether-Token": self.app.token}
        if body is not None:
            h["Content-Type"] = "application/json"
        c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=h)
        r = c.getresponse()
        out = r.status, json.loads(r.read())
        c.close()
        return out

    def test_the_code_box_rates_and_reads_back(self):
        code, r = self.req("POST", "/api/music/rate", {"code": TRACK, "rating": "up"})
        self.assertEqual((code, r["ok"], r["rating"]), (200, True, "up"))
        self.assertEqual(self.req("GET", "/api/music/ratings"), (200, {ratings.track_id(TRACK): "up"}))
        self.assertEqual(self.req("POST", "/api/music/rate", {"code": TRACK, "rating": "sideways"})[0], 400)
        self.assertEqual(self.req("POST", "/api/music/rate", {"code": "", "rating": "up"})[0], 400)
        code, r = self.req("GET", "/api/music/tracks")
        self.assertEqual((code, list(r)), (200, ["songs"]))


if __name__ == "__main__":
    unittest.main()
