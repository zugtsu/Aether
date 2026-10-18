import array
import datetime as dt
import hashlib
import json
import math
import os
import tempfile
import unittest

from aether import cue as cue_mod
from aether import prompt as prompt_mod
from aether import recall as recall_mod
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory

NOW = dt.datetime(2026, 9, 27, 20, 0)


def fake_embed(texts):
    out = []
    for t in texts:
        v = [0.0] * recall_mod.DIMS
        for w in t.lower().replace("search_query:", " ").replace("search_document:", " ").replace(":", " ").split():
            v[int(hashlib.md5(w.strip("?.,!").encode()).hexdigest(), 16) % recall_mod.DIMS] += 1
        n = math.sqrt(sum(x * x for x in v)) or 1
        out.append([x / n for x in v])
    return out


class DateTests(unittest.TestCase):
    def test_dates_are_worked_out_in_code(self):
        self.assertEqual(cue_mod.date_window("what did we do on the 19th?", NOW), {"2026-09-19"})
        self.assertEqual(cue_mod.date_window("that thing on the 30th", NOW), {"2026-08-30"})
        self.assertEqual(cue_mod.date_window("remember sept 16?", NOW), {"2026-09-16"})
        self.assertEqual(cue_mod.date_window("back on 9/16", NOW), {"2026-09-16"})
        self.assertEqual(cue_mod.date_window("what did we do sunday", NOW), {"2026-09-20"})
        self.assertEqual(cue_mod.date_window("yesterday was rough", NOW), {"2026-09-26"})
        self.assertEqual(cue_mod.date_window("lol how was your night", NOW), set())

    def test_small_talk_is_never_a_subject(self):
        for msg in ("good morning lucy! well, good afternoon now", "thanks!", "brb", "hello", "ugh", "that's awesome",
                    "goodnight", "i'm tired", "im so bored", "hows your day going?", "just woke up"):
            self.assertLessEqual(cue_mod.words(msg), {"good", "lucy", "now", "well", "day", "awesom", "your"}, msg)
        self.assertEqual(cue_mod.words("what was that thing with the hummus?"), {"hummu"})
        self.assertEqual(cue_mod.words('its ok, just say "i havent yet" next time, thats all i want'), {"say", "yet", "next", "time", "all"})
        self.assertEqual(cue_mod.words("annnd goodmorning!"), set())
        self.assertEqual(cue_mod.words("idk, prolly gotta check the grill tho"), {"check", "grill"})
        self.assertEqual(cue_mod.words("the hummuuus place"), {"hummu", "place"})
        self.assertEqual(cue_mod.words("ouch, just kidding hahahahaha lolol lmaooo"), set())
        self.assertEqual(cue_mod.words("the halo lore"), {"halo", "lore"})

    def test_when_label(self):
        self.assertEqual(cue_mod.when_label("2026-09-24T10:00:00", NOW), "Thu 9/24, 3 days ago")
        self.assertEqual(cue_mod.when_label("2026-09-27T09:00:00", NOW), "Sun 9/27, today")
        self.assertEqual(cue_mod.when_label("", NOW), "")


class CueTests(unittest.TestCase):
    def setUp(self):
        self.httpd, self.app = make_server(make_config(make_memory(), cue_enabled=True, cue_min=0.3, cue_weight=0.3,
                                                               cue_word_min=0.0), ScriptedLLM([]), port=0)
        rec = self.app.recall
        rec.embed = fake_embed
        pieces = [
            {"key": "c1", "kind": "chat", "chat": "chat-a", "where": "Touring night", "ts": "2026-09-18T10:00:00",
             "text": "{USER}: my touring bike ironbell is on silverhold\nHer: Ironbell on Silverhold, noted. " + "x" * 300},
            {"key": "c2", "kind": "chat", "chat": "discord-123", "where": "Discord", "ts": "2026-09-19T10:00:00",
             "text": "{USER}: ironbell silverhold bike is mine\nHer: sure"},
            {"key": "c3", "kind": "chat", "chat": "chat-b", "where": "Prices", "ts": "2026-09-20T10:00:00",
             "text": "{USER}: whats the price of eggs in springfield\nHer: 3.49 a dozen"},
            {"key": "m1", "kind": "memory", "where": "system/journal.md", "ts": "",
             "text": "2026-09-20: ironbell silverhold touring bike journal musing"},
            {"key": "m2", "kind": "memory", "where": "system/human/facts.md", "ts": "",
             "text": "Pays for a gym pass, $30 every 2 months."},
        ]
        rec.meta = pieces
        rec.vecs = array.array("f")
        for v in fake_embed(["search_document: " + p["text"] for p in pieces]):
            rec.vecs.extend(v)
        self.conv = Conversation(self.app.conv_dir, "test-cue-now")

    def tearDown(self):
        self.httpd.server_close()

    def test_the_right_memory_comes_to_mind_and_the_wrong_ones_dont(self):
        block, items = self.app.cue.for_turn(self.conv, "what was my touring bike ironbell again", now=NOW)
        self.assertTrue(block.startswith("[Things that came to mind"))
        keys = [i["key"] for i in items]
        self.assertIn("c1", keys)
        self.assertNotIn("c2", keys)
        self.assertNotIn("m1", keys)
        self.assertIn("{USER} said: my touring bike ironbell", block)
        self.assertIn("Fri 9/18, 9 days ago", block)
        self.assertIn("…", block)
        self.assertNotIn("x" * 200, block)

    def test_a_stranger_inside_a_mixed_chat_never_comes_to_mind(self):
        c = Conversation(self.app.conv_dir, "letta-mixed-cue")
        c.add("user", text="hi its jordan", place="Discord (Letta)")
        c.add("reply", text="hey")
        c.add("user", text="ironbell silverhold is my bike now", place="Discord, Pebble (Letta)")
        c.add("reply", text="ok Pebble")
        stranger = {"key": "chat:letta-mixed-cue:2", "kind": "chat", "chat": "letta-mixed-cue", "where": "Discord",
                    "ts": "2026-09-19T10:00:00", "text": "{USER}: ironbell silverhold is my bike now\nHer: ok Pebble"}
        self.assertFalse(cue_mod.allowed(stranger, "", self.app.conv_dir))
        self.assertTrue(cue_mod.allowed(dict(stranger, key="chat:letta-mixed-cue:0"), "", self.app.conv_dir))

    def test_her_recall_also_searches_his_own_words_with_the_cue_engine(self):
        eng = self.app.engine
        eng._msg, eng._kind = "what was my touring bike ironbell again", "user"
        vague = {"step": "recall", "query": "the name he picked for his hero"}
        self.app.cfg.recall_hybrid = False
        _, plain = self.app._recall_step(vague)
        self.assertNotIn("Ironbell on Silverhold", plain)
        self.app.cfg.recall_hybrid = True
        ok, out = self.app._recall_step(vague)
        self.assertTrue(ok)
        self.assertIn('chat "Touring night": {USER} said: my touring bike ironbell', out)
        self.assertEqual(out.count("my touring bike ironbell is on"), 1)
        eng._kind = "wake"
        _, own = self.app._recall_step(vague)
        self.assertNotIn("Ironbell on Silverhold", own)

    def test_her_recall_brings_the_day_he_names(self):
        self.app.keeper.apply({"events": [{"when": "21:00", "what": "Jordan did his laundry after the weird dragon dream.",
                                           "tags": [], "role": "companion", "importance": 4}],
                               "threads_open": [], "threads_close": [], "stances": []}, dt.date(2026, 9, 19))
        self.app.engine.refresh()
        eng = self.app.engine
        eng._msg, eng._kind = "what did i end up doing on the 19th?", "user"
        ok, out = self.app.recall.run_step({"step": "recall", "query": "Jordan's activities"}, cue=self.app.cue,
                                           his=eng._msg, now=NOW)
        self.assertIn("Your timeline for Sat 9/19:\n- 21:00: Jordan did his laundry after the weird dragon dream.", out)

    def test_a_shared_word_needs_close_meaning_too(self):
        ask = "my touring bike ironbell"
        self.assertIn("c1", [m["key"] for m in self.app.cue.search(ask, "", NOW)])
        self.app.cfg.cue_word_min = 0.99
        self.assertNotIn("c1", [m["key"] for m in self.app.cue.search(ask, "", NOW)])
        self.app.cfg.cue_word_min = 0.0

    def test_marked_wrong_never_comes_to_mind_again(self):
        keep = cue_mod.FORGOTTEN
        cue_mod.FORGOTTEN = os.path.join(tempfile.mkdtemp(), "forgotten.json")
        try:
            ask = "what was my touring bike ironbell again"
            self.assertIn("c1", [i["key"] for i in self.app.cue.for_turn(self.conv, ask, now=NOW)[1]])
            self.app.keeper.apply({"events": [{"when": "10:00", "what": "Jordan and Lucy decided to start a gaming session.",
                                               "tags": [], "role": "companion", "importance": 4}],
                                   "threads_open": [], "threads_close": [], "stances": []}, dt.date(2026, 9, 21))
            r = self.app.forget_memory("c1", self.app.recall.meta[0]["text"])
            self.assertEqual(r["removed_from"], "")
            self.assertNotIn("c1", [i["key"] for i in self.app.cue.for_turn(self.conv, ask, now=NOW)[1]])
            r = self.app.forget_memory("", "Jordan and Lucy decided to start a gaming session.")
            self.assertEqual(r["removed_from"], "system/timeline.md")
            with open(os.path.join(self.app.cfg.memory_path, "system", "timeline.md"), encoding="utf-8") as f:
                self.assertNotIn("gaming session", f.read())
        finally:
            cue_mod.FORGOTTEN = keep

    def test_live_questions_get_no_memories(self):
        self.assertEqual(self.app.cue.for_turn(self.conv, "whats the price of eggs in springfield", now=NOW), ("", []))

    def test_nothing_came_to_mind(self):
        block, items = self.app.cue.for_turn(self.conv, "remember when we watched inception together?", now=NOW)
        self.assertEqual((block, items), (cue_mod.UNKNOWN.format(USER="{USER}", w="inception"), []))
        block, items = self.app.cue.for_turn(self.conv, "remember that thing again?", now=NOW)
        self.assertEqual((block, items), (cue_mod.NOTHING, []))
        self.assertEqual(self.app.cue.for_turn(self.conv, "lol how was your night", now=NOW), ("", []))

    def test_a_day_he_names_brings_that_days_timeline(self):
        from aether import keeper as kp
        k = self.app.keeper
        for when, what in (("03:10", "Jordan swapped to his spare bike to help finish a group ride."),
                           ("14:00", "Jordan applied to studios that do event photos."),
                           ("09:00", "Jordan did his laundry and took a nap.")):
            k.apply({"events": [{"when": when, "what": what, "tags": [], "role": "companion", "importance": 5}],
                     "threads_open": [], "threads_close": [], "stances": []}, dt.date(2026, 9, 19))
        k.apply({"events": [{"when": "10:00", "what": "Jordan went to the car wash on another day.", "tags": [],
                             "role": "companion", "importance": 5}], "threads_open": [], "threads_close": [], "stances": []},
                dt.date(2026, 9, 20))
        self.app.engine.refresh()
        day, rows = self.app.cue.day_lines("what was i up to around 3am on the 19th", NOW)
        self.assertEqual(day, "Sat 9/19")
        self.assertEqual([r[:8] for r in rows], ["- 03:10:", "- 09:00:", "- 14:00:"])
        block, items = self.app.cue.for_turn(self.conv, "what did we do on the 19th?", now=NOW)
        self.assertIn("[What happened on Sat 9/19", block)
        self.assertIn("applied to studios", block)
        self.assertNotIn("car wash", block)
        self.assertEqual(kp.TIMELINE, "system/timeline.md")

    def test_off_means_off(self):
        self.app.cfg.cue_enabled = False
        self.assertEqual(self.app.cue.for_turn(self.conv, "what was my touring bike ironbell again", now=NOW), ("", []))

    def test_same_chat_is_already_in_front_of_her(self):
        block, items = self.app.cue.for_turn(Conversation(self.app.conv_dir, "chat-a"), "my touring bike ironbell", now=NOW)
        self.assertNotIn("c1", [i["key"] for i in items])

    def test_memories_are_seen_on_their_turn_only(self):
        c = Conversation(self.app.conv_dir, "test-cue-turns")
        c.add("user", text="first", context="[ctx]", memories="[Things that came to mind]\n- a memory")
        msgs = c.to_messages(10000)
        self.assertIn("a memory", msgs[-1]["content"])
        c.add("reply", text="ok")
        c.add("user", text="second", context="[ctx]")
        msgs = c.to_messages(10000)
        self.assertFalse(any("a memory" in m["content"] for m in msgs))

    def test_a_turn_keeps_what_came_to_mind_and_can_jot_first(self):
        self.app.cfg.cue_notice = True
        llm = self.app.engine.llm
        llm.answers[:] = [{"step": "reply"}, {"noticed": "his bike is Ironbell", "say": "Ironbell, on Silverhold."}]
        self.app.engine.conv = self.conv
        mind = self.app.cue.for_turn(self.conv, "what was my touring bike ironbell again", now=NOW)
        reply = self.app.engine.turn("what was my touring bike ironbell again", memories=mind)
        self.assertEqual(reply, "Ironbell, on Silverhold.")
        user = next(e for e in self.conv.events if e["kind"] == "user")
        self.assertTrue(user["remembered"] and user["memories"])
        self.assertIn("noticed", json.dumps(llm.calls[-1]["schema"]))


class LeanPromptTests(unittest.TestCase):
    def test_journal_window_shows_recent_entries_only(self):
        body = "- 2026-09-01: old thought\n- 2026-09-20: middle\n  still the middle entry\n- 2026-09-27: newest"
        out = prompt_mod.journal_window(body, 8, today=dt.date(2026, 9, 27))
        self.assertNotIn("old thought", out)
        self.assertIn("middle\n  still the middle entry", out)
        self.assertIn("newest", out)
        self.assertIn("1 more in this file", out)
        self.assertEqual(prompt_mod.journal_window(body, 0), body)
        capped = prompt_mod.journal_window(body, 0, max_chars=30)
        self.assertIn("newest", capped)
        self.assertNotIn("middle", capped)
        self.assertIn("2 more in this file", capped)

    def test_journal_window_keeps_the_newest_whichever_way_the_file_runs(self):
        journal = ("---\ndescription: my journal\n---\n"
                   "- 2026-09-30 8:00 PM: tonight's entry\n- 2026-09-30 11:22 AM: this morning's entry\n"
                   "- 2026-09-29: yesterday's entry\n- 2026-09-27: an old entry\n")
        out = prompt_mod.journal_window(journal, 7, today=dt.date(2026, 9, 30), max_chars=90)
        self.assertIn("tonight's entry", out)
        self.assertIn("this morning's entry", out)
        self.assertNotIn("old entry", out)
        self.assertLess(out.index("tonight"), out.index("this morning"))
        self.assertTrue(out.startswith("---\ndescription: my journal"))
        self.assertIn("2 more in this file", out)
        timeline = ("- 2026-09-27 18:34 · old line\n- 2026-09-30 06:51 · morning line\n"
                    "- 2026-09-30 11:58 · newest line\n")
        out = prompt_mod.journal_window(timeline, 7, today=dt.date(2026, 9, 30), max_chars=70)
        self.assertIn("newest line", out)
        self.assertIn("morning line", out)
        self.assertNotIn("old line", out)
        self.assertLess(out.index("morning line"), out.index("newest line"))
        self.assertEqual(prompt_mod._entry_minutes("- 2026-09-30 12:05 PM: x"), 12 * 60 + 5)
        self.assertEqual(prompt_mod._entry_minutes("- 2026-09-30 12:05 AM: x"), 5)
        self.assertEqual(prompt_mod._entry_minutes("- 2026-09-30: x"), -1)

    def test_recap_and_cue_line_only_when_switched_on(self):
        root = make_memory()
        httpd, app = make_server(make_config(root), ScriptedLLM([]), port=0)
        try:
            plain = app.engine.system
            self.assertNotIn("# Before you answer", plain)
            self.assertNotIn("How remembering works", plain)
            app.cfg.prompt_recap = app.cfg.cue_enabled = True
            app.engine.refresh()
            self.assertTrue(app.engine.system.rstrip().endswith("actually did in this reply."))
            self.assertIn("How remembering works", app.engine.system)
            self.assertIn("use what came to mind", app.engine.system)
            app.cfg.cue_enabled = False
            app.engine.refresh()
            self.assertNotIn("came to mind", app.engine.system)
            self.assertIn("look it up (recall) before you answer. Never invent a memory", app.engine.system)
            self.assertTrue(app.engine.system.rstrip().endswith("actually did in this reply."))
        finally:
            httpd.server_close()


class SourceTests(unittest.TestCase):
    def test_a_marked_doc_is_searchable_and_labeled(self):
        doc = os.path.join(tempfile.mkdtemp(), "SPEC.md")
        with open(doc, "w", encoding="utf-8") as f:
            f.write("# Game spec\n\n## The player\n- Weapon: a heavy, jagged lantern on a chain.\n- Her look: lucy_3 (her pick).\n\n"
                    "## Lines\n| First Hollowed | Stay back. You aren't meant for this light. |\n")
        root = make_memory()
        httpd, app = make_server(make_config(root, knowledge_sources={"the game's design doc": doc}), ScriptedLLM([]), port=0)
        try:
            src = [p for p in app.recall.pieces() if p["kind"] == "source"]
            self.assertTrue(any("The player:" in p["text"] and "lantern on a chain" in p["text"] for p in src))
            self.assertTrue(all(p["where"] == "the game's design doc" for p in src))
            self.assertTrue(cue_mod.allowed(src[0]))
        finally:
            httpd.server_close()


class ChunkTests(unittest.TestCase):
    def test_long_text_splits_with_overlap(self):
        text = " ".join(f"word{i}" for i in range(400))
        parts = recall_mod.chunks(text)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= recall_mod.PIECE for p in parts))
        self.assertIn("word399", parts[-1])
        self.assertTrue(set(parts[0].split()[-5:]) & set(parts[1].split()[:30]))
        self.assertEqual(recall_mod.chunks("short"), ["short"])

    def test_full_text_pieces_keep_the_second_half(self):
        root = make_memory()
        httpd, app = make_server(make_config(root, recall_full_text=True), ScriptedLLM([]), port=0)
        try:
            c = Conversation(app.conv_dir, "test-long-reply")
            c.add("user", text="what are the starting items?")
            c.add("reply", text="Here goes. " + "filler " * 150 + "Bright Cinders and a Iron Chest.")
            pieces = [p for p in app.recall.pieces() if p.get("chat") == "test-long-reply"]
            self.assertTrue(any("Iron Chest" in p["text"] for p in pieces))
            self.assertTrue(all(p["text"].startswith("{USER}: what are the starting items?") for p in pieces))
            app.cfg.recall_full_text = False
            old = [p for p in app.recall.pieces() if p.get("chat") == "test-long-reply"]
            self.assertFalse(any("Iron Chest" in p["text"] for p in old))
        finally:
            httpd.server_close()

    def test_a_structured_reply_s_parts_are_pieces_of_their_own(self):
        reply = ("The Keep Gate isn't an exit, it's a seal. " + "More lore. " * 60 + "\n\nAnd here are my lines:\n"
                 "- Entering the chapel: 'So much weight...'\n- First Hollowed: 'Stay back. You aren't meant for this light.'\n\n"
                 "### 3. The Loot System\nWe want Persistence.\n*   **Persistence (Currency):** The lifeblood.\n"
                 "*   **Details:**\n")
        parts = recall_mod.sections(reply)
        self.assertIn("And here are my lines: First Hollowed: 'Stay back. You aren't meant for this light.'", parts)
        self.assertIn("3. The Loot System / We want Persistence.: Persistence (Currency): The lifeblood.", parts)
        self.assertFalse(any("Details" in p for p in parts))
        self.assertEqual(recall_mod.sections("Just talking.\nTwo lines, no list."), [])
        self.assertEqual(recall_mod.sections("- only one item"), [])
        root = make_memory()
        httpd, app = make_server(make_config(root, recall_full_text=True), ScriptedLLM([]), port=0)
        try:
            c = Conversation(app.conv_dir, "test-structured")
            c.add("user", text="you answered me with your journal code lol, answer my question about the game please")
            c.add("reply", text=reply)
            mine = [p for p in app.recall.pieces() if p["key"].startswith("chat:test-structured:0:s")]
            self.assertEqual(len(mine), len(parts))
            self.assertEqual(mine[1]["text"], "Her: " + parts[1])
            self.assertTrue(recall_mod.speakers(mine[1]["text"]).startswith("You said: And here are my lines:"))
        finally:
            httpd.server_close()


class ModelLockTests(unittest.TestCase):

    def setUp(self):
        home = tempfile.mkdtemp()
        self.keep = recall_mod.INDEX, recall_mod.VECS, recall_mod.MODEL_FILE
        recall_mod.INDEX, recall_mod.VECS, recall_mod.MODEL_FILE = (os.path.join(home, n) for n in ("r.json", "r.bin", "m.json"))
        self.httpd, self.app = make_server(make_config(make_memory(), cue_enabled=True, cue_min=0.3, cue_weight=0.3,
                                                       cue_word_min=0.0), ScriptedLLM([]), port=0)
        self.app.conv_dir = tempfile.mkdtemp()
        c = Conversation(self.app.conv_dir, "chat-star")
        c.add("user", text="my touring bike ironbell is on silverhold")
        c.add("reply", text="Ironbell it is.")

    def tearDown(self):
        recall_mod.INDEX, recall_mod.VECS, recall_mod.MODEL_FILE = self.keep
        self.httpd.server_close()

    def start(self, embed):
        rec = recall_mod.Recall(self.app.cfg, self.app.conv_dir, self.app.engine.memory)
        rec.embed = embed
        self.app.recall = rec
        return rec

    def test_the_index_lives_in_one_database_and_moves_in_from_the_old_files(self):
        rec = self.start(fake_embed)
        rec.update(budget=10000)
        meta, vecs = list(rec.meta), rec.vecs
        folder = os.path.dirname(recall_mod.INDEX)
        recall_mod.INDEX, recall_mod.VECS = os.path.join(folder, "old.json"), os.path.join(folder, "old.bin")
        with open(recall_mod.INDEX, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        with open(recall_mod.VECS, "wb") as f:
            f.write(vecs.tobytes())
        self.assertFalse(os.path.exists(recall_mod.db_path()))

        def no_model(texts):
            raise AssertionError("moving in must not read pieces through the model again")
        rec = recall_mod.Recall(self.app.cfg, self.app.conv_dir, self.app.engine.memory)
        rec.embed = no_model
        self.assertEqual((rec.meta, rec.vecs), (meta, vecs))
        self.assertTrue(os.path.exists(recall_mod.INDEX) and os.path.exists(recall_mod.db_path()))
        self.assertTrue(rec.fts_ready(rec.meta))
        c = Conversation(self.app.conv_dir, "chat-star")
        c.add("user", text="the hummus recipe had smoked paprika")
        rec.embed = fake_embed
        rec.update(budget=10000)
        rec.db.close()
        again = recall_mod.Recall(self.app.cfg, self.app.conv_dir, self.app.engine.memory)
        self.assertEqual([m["key"] for m in again.meta], [m["key"] for m in rec.meta])
        self.assertTrue(any("paprika" in m["text"] for m in again.meta))
        hits = again.keyword('"paprika"')
        self.assertEqual([again.meta[i]["key"] for i in cue_mod.Keyword().search(again.meta, "paprika", rec=again)], hits)
        self.assertFalse(again.fts_ready(again.meta[:-1]))
        again.db.close()

    def test_one_hop_brings_the_turn_next_to_it_and_the_same_name(self):
        c = Conversation(self.app.conv_dir, "chat-gig")
        c.add("user", text="got offered a photo gig at the Maple fair, two weeks in canada", ts="2026-09-23T07:00:00")
        c.add("reply", text="The Maple fair? Canada's a trip.", ts="2026-09-23T07:00:05")
        c.add("user", text="the gig pays 3k plus tips for the two weeks", ts="2026-09-23T07:02:00")
        c.add("reply", text="Not bad for two weeks.", ts="2026-09-23T07:02:05")
        c.add("user", text="whatever, gonna grab food", ts="2026-09-23T07:30:00")
        c.add("reply", text="Eat something real.", ts="2026-09-23T07:30:05")
        for day, cid, line in (("2026-09-14", "chat-f1", "The next train out is the Starling at 4:50 AM."),
                               ("2026-09-23", "chat-f2", "After that, there's the Starling at 7:55 PM.")):
            f = Conversation(self.app.conv_dir, cid)
            f.add("user", text="when is the next train?", ts=f"{day}T04:00:00")
            f.add("reply", text=line, ts=f"{day}T04:00:05")
        rec = self.start(fake_embed)
        rec.update(budget=10000)
        offer = next(m for m in rec.meta if "Maple fair" in m["text"])
        linked = rec.linked(offer, [offer["key"]])
        self.assertIn("3k plus tips", " ".join(m["text"] for m, _ in linked))
        self.assertTrue(all("food" not in m["text"] for m, _ in linked))
        train = next(m for m in rec.meta if "4:50 AM" in m["text"])
        self.assertIn("starling", rec.names_in(train["text"]))
        self.assertIn("7:55 PM", " ".join(m["text"] for m, _ in rec.linked(train, [train["key"]])))
        self.app.cfg.recall_links = True
        out = rec.run_step({"step": "recall", "query": "the maple fair photo gig"})[1]
        self.assertIn("Linked to those", out)
        self.assertIn("3k plus tips", out)
        self.app.cfg.recall_links = False
        self.assertNotIn("Linked to those", rec.run_step({"step": "recall", "query": "the maple fair photo gig"})[1])

    def test_the_same_words_come_back_once(self):
        for cid in ("letta-a", "letta-a-copy"):
            c = Conversation(self.app.conv_dir, cid)
            c.add("user", text="just the scores over 5 runs simulated, its all junk", ts="2026-09-14T02:47:00")
            c.add("reply", text="Ugh.", ts="2026-09-14T02:47:05")
        rec = self.start(fake_embed)
        rec.update(budget=10000)
        self.assertEqual(sum("scores over 5 runs" in m["text"] for m in rec.meta), 2)
        out = rec.run_step({"step": "recall", "query": "Jordan said just the scores over 5 runs simulated, its all junk"})[1]
        self.assertEqual(out.count("said: just the scores over 5 runs"), 1)

    def test_a_changed_model_reads_everything_again_and_a_wrong_size_turns_search_off(self):
        rec = self.start(fake_embed)
        rec.update(budget=10000)
        n = len(rec.meta)
        self.assertGreater(n, 0)
        self.assertEqual(rec.model_note, "")
        with open(recall_mod.MODEL_FILE, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["dims"], recall_mod.DIMS)
        rec = self.start(fake_embed)
        self.assertEqual((rec.update(budget=10000), rec.model_note, len(rec.meta)), (0, "", n))

        def other(texts):
            return fake_embed(["other " + t for t in texts])
        rec = self.start(other)
        rec.update(budget=1)
        self.assertIn("the search model changed", rec.model_note)
        self.assertEqual(len(rec.meta), 1)
        rec.update(budget=10000)
        self.assertEqual(len(rec.meta), n)
        ask = "what was my touring bike ironbell again"
        self.assertTrue(self.app.cue.search(ask, "", NOW))

        def bigger(texts):
            return [v + [0.0] * 256 for v in fake_embed(texts)]
        rec = self.start(bigger)
        self.assertEqual(rec.update(budget=10000), 0)
        self.assertFalse(rec.model_ok)
        self.assertIn("search is off", rec.model_note)
        self.assertEqual(self.app.cue.search(ask, "", NOW), [])
        self.assertEqual(rec.search(ask), [])


BRIDGE = ("[joy] [smirk] [surprise] [sadness] [anger] [disgust] [fear]. Your only tool here is memory; if something "
          "needs files, commands, or the web, say so and ask to do it in the Letta app instead.]\n")


class SaidTests(unittest.TestCase):

    def test_only_his_words(self):
        from aether.history import said
        self.assertEqual(said(BRIDGE + "hey, im testing out pet mode on the desktop!"), "hey, im testing out pet mode on the desktop!")
        self.assertEqual(said('<attachment kind="audio" local_path="voice.ogg" name="voice-message.ogg" />'), "(a voice message)")
        self.assertEqual(said("<!-- letta:pasted-text:v1:eyJ -->\nThe Human Cache: a warehouse"), "The Human Cache: a warehouse")
        self.assertIsNone(said("<task-notification> <task-id>bash_1</task-id> <status>completed</status>"))
        for plain in ("normal message [with brackets] ok", "[sent a picture]", "<3 thank you love"):
            self.assertEqual(said(plain), plain)

    def test_search_indexes_his_words_and_rereads_changed_text(self):
        root = make_memory()
        httpd, app = make_server(make_config(root), ScriptedLLM([]), port=0)
        keep = recall_mod.INDEX, recall_mod.VECS
        home = tempfile.mkdtemp()
        recall_mod.INDEX, recall_mod.VECS = os.path.join(home, "r.json"), os.path.join(home, "r.bin")
        try:
            c = Conversation(app.conv_dir, "test-said")
            c.add("user", text=BRIDGE + "you got your voice back!")
            c.add("reply", text="Took you long enough.")
            c.add("user", text="<task-notification> <task-id>bash_1</task-id> prices: eggs 2.38")
            c.add("reply", text="Eggs are cheap this week.")
            rec = app.recall
            rec.embed = fake_embed
            mine = [p for p in rec.pieces() if p.get("chat") == "test-said"]
            self.assertEqual([p["text"] for p in mine], ["{USER}: you got your voice back!\nHer: Took you long enough."])
            rec.meta = [dict(mine[0], text="{USER}: " + BRIDGE + "you got your voice back!")]
            rec.vecs = array.array("f", fake_embed(["x"])[0])
            rec.update(budget=10000)
            got = [m["text"] for m in rec.meta if m.get("chat") == "test-said"]
            self.assertEqual(got, ["{USER}: you got your voice back!\nHer: Took you long enough."])
            self.assertEqual(len(rec.vecs), len(rec.meta) * recall_mod.DIMS)
        finally:
            recall_mod.INDEX, recall_mod.VECS = keep
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
