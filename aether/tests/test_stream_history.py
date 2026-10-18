import json
import tempfile
import unittest

from aether.history import KEEP, NEXT, Conversation, image_data_url
from aether.jsonstream import SayStream


class StreamTests(unittest.TestCase):
    def feed_all(self, text, size):
        s = SayStream()
        out = "".join(s.feed(text[i:i + size]) for i in range(0, len(text), size))
        return out, s

    def test_every_chunk_size_gives_the_same_words(self):
        say = 'Menace? Me?\n"Never" \\ cafÃ© â€” done â¤ï¸ \U0001F608 / tab\tend'
        raw = json.dumps({"say": say})
        raw_utf = json.dumps({"say": say}, ensure_ascii=False)
        for r in (raw, raw_utf, '{\n  "say" :  ' + json.dumps(say) + "\n}"):
            for size in (1, 2, 3, 5, 8, 1000):
                out, s = self.feed_all(r, size)
                self.assertEqual(out, say, (r[:30], size))
                self.assertEqual(s.state, "done")

    def test_partial(self):
        s = SayStream()
        self.assertEqual(s.feed('{"sa'), "")
        self.assertEqual(s.feed('y": "Hel'), "Hel")
        self.assertEqual(s.feed("lo\\"), "lo")
        self.assertEqual(s.feed('n'), "\n")
        self.assertEqual(s.text, "Hello\n")


class HistoryTests(unittest.TestCase):
    def test_roles_alternate_and_persist(self):
        d = tempfile.mkdtemp()
        c = Conversation(d)
        c.add("user", text="hi", context="<context>t</context>")
        c.add("step", step={"step": "skill", "skill": "news", "args": []})
        c.add("result", of="skill", ok=True, text="sunny")
        c.add("reply", text="It's sunny.")
        c.add("user", text="thanks")
        c.add("reply", text="half a sent", stopped=True)
        c.add("user", text="again")
        msgs = Conversation(d, c.id).to_messages(10000)
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["user", "assistant", "user", "assistant", "user"])
        self.assertTrue(msgs[0]["content"].startswith("<context>t</context>\nhi"))
        self.assertNotIn("sunny\n</result>", "".join(m["content"] for m in msgs))
        self.assertIn("It's sunny.", msgs[1]["content"])
        self.assertIn("[{USER} stopped me here]", msgs[3]["content"])

    def test_trim_starts_on_a_user_message(self):
        c = Conversation(tempfile.mkdtemp())
        for i in range(30):
            c.add("user", text=f"message {i} " + "x" * 200)
            c.add("step", step={"step": "read_skill", "skill": "w"})
            c.add("result", of="read_skill", ok=True, text="y" * 200)
            c.add("reply", text="ok " + "z" * 200)
        msgs = c.to_messages(3000)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertIn("out of view", msgs[0]["content"])
        self.assertIn("message 29", msgs[-4]["content"])
        self.assertTrue(msgs[-1]["content"].startswith("ok "))
        self.assertLess(sum(len(m["content"]) for m in msgs), 3500)


class JournalOutOfViewTests(unittest.TestCase):
    def test_an_earlier_journal_step_leaves_her_view_and_this_turns_stays(self):
        c = Conversation(tempfile.mkdtemp())
        c.add("user", text="rough day at the store", context="")
        c.add("step", step={"step": "journal", "about": "his rough day"})
        c.add("result", of="journal", ok=True, text="saved 9:55 PM")
        c.add("step", step={"step": "recall", "query": "store"})
        c.add("result", of="recall", ok=True, text="found it")
        c.add("reply", text="That sounds brutal.")
        c.add("user", text="anyway how was your night?", context="")
        c.add("step", step={"step": "skill", "skill": "journal", "command": "add", "args": ["x"]})
        c.add("result", of="skill", ok=True, text="saved 10:20 PM")
        seen = json.dumps(c.to_messages(100000))
        self.assertNotIn("his rough day", seen)
        self.assertNotIn("saved 9:55 PM", seen)
        self.assertIn("rough day at the store", seen)
        self.assertIn("That sounds brutal.", seen)
        self.assertNotIn("found it", seen)
        self.assertIn("saved 10:20 PM", seen)
        roles = [m["role"] for m in c.to_messages(100000)]
        self.assertTrue(all(a != b for a, b in zip(roles, roles[1:])))


class WindowTests(unittest.TestCase):

    def size(self, c, a, b):
        return sum(len(Conversation._message(e)[1] or "") for e in c.events[a:b])

    def test_the_start_stays_put_for_several_turns(self):
        c, budget, starts = Conversation(tempfile.mkdtemp()), 10000, []
        for i in range(40):
            c.add("user", text=f"message {i} " + "x" * 900)
            starts.append(c.window(budget)[0])
            c.add("reply", text=f"reply {i} " + "z" * 900)
        moves = [k for k in range(1, 40) if starts[k] != starts[k - 1]]
        self.assertGreater(len(moves), 3)
        self.assertTrue(all(b - a >= 3 for a, b in zip(moves, moves[1:])), moves)
        for k in range(40):
            self.assertLessEqual(self.size(c, starts[k], 2 * k), budget)
            if k in moves:
                self.assertLessEqual(self.size(c, starts[k], 2 * k), budget * KEEP)
                self.assertGreater(self.size(c, starts[k - 1], 2 * k), budget)

    def test_the_turn_in_progress_never_moves_the_start(self):
        c = Conversation(tempfile.mkdtemp())
        for i in range(12):
            c.add("user", text=f"message {i} " + "x" * 900)
            c.add("reply", text="z" * 900)
        c.add("user", text="read me the big file")
        first = c.window(10000)[0]
        for _ in range(3):
            c.add("step", step={"step": "read_file", "path": "reference/big.md"})
            c.add("result", of="read_file", ok=True, text="y" * 6000)
        self.assertEqual(c.window(10000)[0], first)
        self.assertEqual(c.events[first]["kind"], "user")

    def test_a_turn_bigger_than_the_window_is_kept_whole(self):
        c = Conversation(tempfile.mkdtemp())
        c.add("user", text="hi")
        c.add("reply", text="hey")
        c.add("user", text="w" * 30000)
        self.assertEqual(c.window(10000)[1][-1][1], "w" * 30000)
        c.add("reply", text="that's a lot")
        c.add("user", text="sorry")
        first, picked = c.window(10000)
        self.assertEqual((first, [p[1] for p in picked]), (4, ["sorry"]))

    def test_the_read_ahead_is_what_the_next_turn_starts_with(self):
        c, budget = Conversation(tempfile.mkdtemp()), 10000
        for i in range(30):
            c.add("user", text=f"message {i} " + "x" * 900, memories=f"[came to mind] thing {i}")
            if i % 4 == 3:
                c.add("step", step={"step": "read_skill", "skill": "w"})
                c.add("result", of="read_skill", ok=True, text="y" * 500)
            c.add("reply", text=f"reply {i} " + "z" * 900)
            if i == 20:
                c.add("made_video", caption="for you", prompt="a gate")
            ahead = c.to_messages(budget, upcoming=True)
            self.assertNotIn(f"thing {i}", json.dumps(ahead))
            self.assertNotIn(NEXT, json.dumps(ahead))
            probe = Conversation.__new__(Conversation)
            probe.id, probe.path, probe.events = c.id, c.path, c.events + [{"kind": "user", "text": "next"}]
            nxt = probe.to_messages(budget)
            n = len(ahead)
            self.assertEqual(nxt[:n - 1], ahead[:n - 1], i)
            self.assertTrue(nxt[n - 1]["content"].startswith(ahead[n - 1]["content"]), i)
            self.assertTrue(nxt[-1]["content"].endswith("next"), i)


if __name__ == "__main__":
    unittest.main()

class ImageTests(unittest.TestCase):
    def test_big_pictures_are_shrunk_for_the_model(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("no Pillow")
        import base64
        import io
        import os
        p = os.path.join(tempfile.mkdtemp(), "shot.png")
        Image.new("RGB", (1614, 978), "purple").save(p)
        url = image_data_url(p)
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))
        im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
        self.assertEqual(max(im.size), 1280)
        small = os.path.join(os.path.dirname(p), "small.png")
        Image.new("RGB", (400, 300)).save(small)
        self.assertTrue(image_data_url(small).startswith("data:image/png;base64,"))
