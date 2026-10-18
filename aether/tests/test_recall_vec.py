import array
import hashlib
import math
import os
import random
import tempfile
import unittest
from unittest import mock

from aether import recall as recall_mod
from aether.history import Conversation
from aether.memory import Memory
from aether.tests.fixture import make_config, make_memory


def fake_embed(texts):
    out = []
    for t in texts:
        v = [0.0] * recall_mod.DIMS
        for w in t.lower().replace(":", " ").split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % recall_mod.DIMS] += 1
        n = math.sqrt(sum(x * x for x in v)) or 1
        out.append([x / n for x in v])
    return out


def piece(i, kind="memory"):
    return {"key": f"t:{i}", "kind": kind, "text": f"piece {i}", "where": "x", "ts": ""}


def vec(seed):
    rnd = random.Random(seed)
    v = [rnd.gauss(0, 1) for _ in range(recall_mod.DIMS)]
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


class RecallVecTests(unittest.TestCase):
    def setUp(self):
        self.root = make_memory()
        self.convs = tempfile.mkdtemp()
        home = tempfile.mkdtemp()
        self.old = recall_mod.INDEX, recall_mod.VECS
        recall_mod.INDEX, recall_mod.VECS = os.path.join(home, "r.json"), os.path.join(home, "r.bin")

    def tearDown(self):
        recall_mod.INDEX, recall_mod.VECS = self.old

    def make(self):
        r = recall_mod.Recall(make_config(self.root), self.convs, Memory(self.root, make_config(self.root)))
        r.embed = fake_embed
        return r

    def ids(self, r, table):
        col = "id" if table == "pieces" else "rowid"
        return sorted(x[0] for x in r.db.execute(f"select {col} from {table}"))

    def test_insert_delete_clear_keep_both_tables_in_step(self):
        r = self.make()
        self.assertTrue(r.vec_ok)
        with r.lock:
            r._insert([piece(i) for i in range(5)], [vec(i) for i in range(5)])
            r.db.commit()
        self.assertEqual(len(self.ids(r, "pieces")), 5)
        self.assertEqual(self.ids(r, "pieces"), self.ids(r, "pieces_vec"))
        stored = r.db.execute("select embedding from pieces_vec where rowid = (select id from pieces where key = 't:2')")
        self.assertEqual(stored.fetchone()[0], array.array("f", vec(2)).tobytes())
        with r.lock:
            r._delete(["t:1", "t:3"])
            r.db.commit()
        self.assertEqual(len(self.ids(r, "pieces")), 3)
        self.assertEqual(self.ids(r, "pieces"), self.ids(r, "pieces_vec"))
        with r.lock:
            r._clear()
        self.assertEqual((self.ids(r, "pieces"), self.ids(r, "pieces_vec")), ([], []))

    def test_filled_once_from_the_pieces_already_there(self):
        r = self.make()
        with r.lock:
            r._insert([piece(i) for i in range(4)], [vec(i) for i in range(4)])
            r.db.execute("delete from pieces_vec")
            r.db.commit()
        r.close()
        r2 = self.make()
        r2.embed = None
        self.assertEqual(self.ids(r2, "pieces"), self.ids(r2, "pieces_vec"))
        self.assertEqual(len(self.ids(r2, "pieces_vec")), 4)

    def test_the_same_answers_as_the_loop(self):
        r = self.make()
        with r.lock:
            kinds = ["memory", "chat"]
            r._insert([piece(i, kinds[i % 2]) for i in range(300)], [vec(i) for i in range(300)])
            r._insert([piece(i, kinds[i % 2]) for i in range(300, 600)], [vec(i - 300) for i in range(300, 600)])
            r.db.commit()
        r.close()
        r = self.make()
        for qs in range(20):
            q = vec(10_000 + qs)
            r.embed = lambda texts, q=q: [q]
            fast = r.search("x", k=6, min_score=-1)
            fast_chat = r.search("x", k=6, min_score=-1, kinds=["chat"])
            fast_cut = r.search("x", k=6, min_score=0.05)
            r.vec_ok = False
            self.assertEqual(fast, r.search("x", k=6, min_score=-1))
            self.assertEqual(fast_chat, r.search("x", k=6, min_score=-1, kinds=["chat"]))
            self.assertEqual(fast_cut, r.search("x", k=6, min_score=0.05))
            r.vec_ok = True
        self.assertTrue(all(h["kind"] == "chat" for h in fast_chat) and len(fast_chat) == 6)

    def test_no_sqlite_vec_the_loop_still_searches(self):
        c = Conversation(self.convs)
        c.add("user", text="the seed swap moved to monday", context="")
        c.add("reply", text="noted", context="")
        logged = []
        with mock.patch.object(recall_mod, "load_vec", side_effect=ImportError("no sqlite_vec")), \
                mock.patch("aether.engine.log", logged.append):
            r = self.make()
            self.assertFalse(r.vec_ok)
            self.assertEqual(r.update(), 0)
            hits = r.search("seed swap monday", min_score=0.1)
        self.assertIn("seed swap", hits[0]["text"])
        self.assertTrue(any("sqlite-vec didn't load" in x for x in logged))
        r.close()
        r2 = self.make()
        self.assertTrue(r2.vec_ok)
        self.assertEqual(self.ids(r2, "pieces"), self.ids(r2, "pieces_vec"))
        r2.embed = fake_embed
        self.assertEqual(r2.search("seed swap monday", min_score=0.1), hits)


if __name__ == "__main__":
    unittest.main()
