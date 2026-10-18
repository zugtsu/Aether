import hashlib
import math
import os
import tempfile
import unittest
import zipfile

from aether import backup as backup_mod
from aether import engine as engine_mod
from aether import recall as recall_mod
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.memory import Memory
from aether.tests.fixture import make_config, make_memory
from aether.vault import Vault, protect, unprotect


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "vault.dat")
        self.v = Vault(self.path)

    def test_windows_locks_it(self):
        self.assertEqual(unprotect(protect(b"hello")), b"hello")
        self.v.set("MAPS_KEY", "abc123secretvalue", ["maps"])
        with open(self.path, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"abc123secretvalue", raw)
        self.assertEqual(Vault(self.path).get("MAPS_KEY"), "abc123secretvalue")

    def test_names_never_show_values_and_only_allowed_skills_get_it(self):
        self.v.set("MAPS_KEY", "abc123secretvalue", ["maps"])
        self.assertNotIn("abc123secretvalue", repr(self.v.names()))
        self.assertEqual(self.v.env_for("maps"), {"AETHER_SECRET_MAPS_KEY": "abc123secretvalue"})
        self.assertEqual(self.v.env_for("music"), {})
        self.assertEqual(self.v.scrub("key=abc123secretvalue ok"), "key=•••• ok")
        for bad in ("X", "1ABC", "HAS SPACE"):
            with self.assertRaises(ValueError):
                self.v.set(bad, "longenough")
        self.v.remove("MAPS_KEY")
        self.assertEqual(self.v.names(), [])


class EngineVaultAuditTests(unittest.TestCase):
    def test_skill_gets_secret_but_output_is_masked_and_audited(self):
        root = make_memory()
        with open(os.path.join(root, "skills", "echo", "scripts", "echo.py"), "a", encoding="utf-8") as f:
            f.write("print('KEY=' + os.environ.get('AETHER_SECRET_ECHO_KEY', 'none'))\n")
        v = Vault(os.path.join(tempfile.mkdtemp(), "v.dat"))
        v.set("ECHO_KEY", "topsecret-9876", ["echo"])
        engine_mod.AUDIT = os.path.join(tempfile.mkdtemp(), "audit.jsonl")
        llm = ScriptedLLM([{"step": "skill", "skill": "echo", "args": ["hi"]}, {"step": "reply"}, {"say": "done"}])
        e = engine_mod.Engine(make_config(root), llm, Conversation(tempfile.mkdtemp()), vault=v)
        e.turn("x")
        result = e.conv.events[2]["text"]
        self.assertIn("KEY=••••", result)
        self.assertNotIn("topsecret", result)
        a = engine_mod.read_audit()
        self.assertEqual((a[0]["step"]["skill"], a[0]["ok"]), ("echo", True))
        self.assertNotIn("topsecret", repr(a))


class BackupTests(unittest.TestCase):
    def test_zip_has_her_whole_memory_and_rotates_to_the_bin(self):
        root = make_memory()
        data = tempfile.mkdtemp()
        os.makedirs(os.path.join(data, "conversations"))
        with open(os.path.join(data, "conversations", "c.jsonl"), "w") as f:
            f.write("{}\n")
        cfg = make_config(root, backup_dir=tempfile.mkdtemp())
        path = backup_mod.make(cfg, root, data_dir=data)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        self.assertIn("memory.bundle", names)
        self.assertIn("aether/conversations/c.jsonl", names)
        self.assertIn("RESTORE.txt", names)
        recycled = []
        backup_mod.recycle = recycled.append
        for i in range(3):
            open(os.path.join(cfg.backup_dir, f"aether-2020010{i}-000000.zip"), "w").close()
        gone = backup_mod.rotate(cfg, keep=2)
        self.assertEqual(len(gone), 2)
        self.assertEqual(recycled, gone)


class RecallTests(unittest.TestCase):
    def test_index_updates_and_searches(self):
        root = make_memory()
        convs = tempfile.mkdtemp()
        c = Conversation(convs)
        c.add("user", text="my car service moved to monday", context="")
        c.add("reply", text="noted", context="")
        home = tempfile.mkdtemp()
        recall_mod.INDEX, recall_mod.VECS = os.path.join(home, "r.json"), os.path.join(home, "r.bin")

        def fake_embed(texts):
            out = []
            for t in texts:
                v = [0.0] * recall_mod.DIMS
                for w in t.lower().replace(":", " ").split():
                    v[int(hashlib.md5(w.encode()).hexdigest(), 16) % recall_mod.DIMS] += 1
                n = math.sqrt(sum(x * x for x in v)) or 1
                out.append([x / n for x in v])
            return out
        r = recall_mod.Recall(make_config(root), convs, Memory(root, make_config(root)))
        r.embed = fake_embed
        self.assertEqual(r.update(), 0)
        n = len(r.meta)
        self.assertTrue(any(m["kind"] == "chat" for m in r.meta) and any(m["kind"] == "memory" for m in r.meta))
        hits = r.search("car service monday", min_score=0.1)
        self.assertEqual(hits[0]["kind"], "chat")
        self.assertIn("car service", hits[0]["text"])
        ok, text = r.run_step({"step": "recall", "query": "my car service moved to monday"})
        self.assertTrue(ok)
        self.assertIn("car service", text)
        r2 = recall_mod.Recall(make_config(root), convs, Memory(root, make_config(root)))
        self.assertEqual(len(r2.meta), n)
        os.makedirs(os.path.join(root, "notes"), exist_ok=True)
        with open(os.path.join(root, "notes", "dupes.md"), "w", encoding="utf-8") as f:
            f.write("---\ndescription: a list with a repeat\n---\n- the blue mug goes on the top shelf\n"
                    "- the blue mug goes on the top shelf\n- the kettle stays by the window sill\n")
        r3 = recall_mod.Recall(make_config(root), convs, Memory(root, make_config(root)))
        r3.embed = fake_embed
        self.assertEqual(r3.update(), 0)
        self.assertEqual(sum("blue mug" in m["text"] for m in r3.meta), 1)
        self.assertTrue(any("kettle" in m["text"] for m in r3.meta))


if __name__ == "__main__":
    unittest.main()
