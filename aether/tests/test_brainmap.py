import json
import os
import tempfile
import unittest

from aether import brainmap


def write(root, rel, text):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def chat(folder, cid, events):
    write(folder, cid + ".jsonl", "".join(json.dumps(e) + "\n" for e in events))


class BrainMapTests(unittest.TestCase):
    def setUp(self):
        self.mem = tempfile.mkdtemp()
        write(self.mem, "system/persona.md", "---\ndescription: me\n---\nI'm Lucy.\n")
        timeline = [f"- 2026-09-{d:02d} 12:00 · helper · Something happened on day {d} worth a line." for d in range(7, 22)]
        write(self.mem, "system/timeline.md", "---\ndescription: his timeline\n---\n" + "\n".join(timeline + [
            "- an old line with no date on it, still his story"]) + "\n")
        write(self.mem, "system/threads.md", "- [t1] open since 2026-09-27 · due 2026-09-29 09:00 · early meeting at the office\n"
                                             "- [t2] open since 2026-09-27 · due 2026-09-30 · car service appointment\n"
                                             "- [t3] open since 2026-09-27 · when: \"soon\" · a third monitor\n")
        write(self.mem, "reference/stances.md", "- monitors · Make sure there's room for it on the desk first.\n"
                                                "- sleep · Sleep beats one more hour of debugging, every time.\n"
                                                "- coffee · Coffee after 3pm is a crime against tomorrow you.\n")
        self.conv = tempfile.mkdtemp()
        chat(self.conv, "b-later", [{"kind": "user", "text": "second one", "ts": "2026-09-20T10:00:00", "place": "Aether app"},
                                    {"kind": "reply", "text": "hi", "ts": "2026-09-20T10:01:00"}])
        chat(self.conv, "a-first", [{"kind": "user", "text": "the very first thing he said to her", "ts": "2026-09-13T09:00:00"},
                                    {"kind": "reply", "text": "hey", "ts": "2026-09-14T09:00:00"}])
        chat(self.conv, "discord-99", [{"kind": "user", "text": "yo bot", "ts": "2026-09-21T10:00:00",
                                        "place": "Discord DM from bob"}])
        chat(self.conv, "heartbeat", [{"kind": "user", "text": "(her log)", "ts": "2026-09-21T10:00:00"}])
        chat(self.conv, "heartbeat-old", [{"kind": "reply", "text": "I tidied my notes.", "ts": "2026-09-27T10:00:00"}])
        write(self.conv, "_meta.json", json.dumps({"a-first": {"title": "Letta · first night", "archived": True}}))

    def test_our_chats_are_only_his_oldest_first(self):
        got = brainmap.our_chats(self.conv)
        self.assertEqual([c["id"] for c in got], ["a-first", "b-later"])
        self.assertEqual((got[0]["title"], got[0]["archived"], got[0]["messages"]), ("Letta · first night", True, 2))
        self.assertEqual(got[1]["title"], "second one")

    def test_notebook_timeline_by_week_and_stances_are_hers(self):
        d = brainmap.build(self.mem, chats=brainmap.our_chats(self.conv))
        n = d["nodes"]
        weeks = [x for x in n if x.get("group")]
        self.assertEqual([w["short"] for w in weeks], ["Sep 7", "Sep 14", "Sep 21"])
        self.assertEqual([w["text"] for w in weeks], ["His timeline, the week of Sep 7: 7 moments",
                                                      "His timeline, the week of Sep 14: 7 moments",
                                                      "His timeline, the week of Sep 21: 1 moment"])
        sparks = [x for x in n if x["k"] == "mem" and x["file"] == "system/timeline.md"]
        self.assertEqual(len(sparks), 16)
        self.assertEqual(sum(1 for s in sparks if s["at"] == "system/timeline.md"), 1)
        self.assertTrue(all(s["region"] == "notebook" for s in sparks))
        region = {x["label"]: x["region"] for x in n if x["k"] == "file" and not x.get("group")}
        self.assertEqual((region["system/timeline.md"], region["system/threads.md"], region["reference/stances.md"]),
                         ("notebook", "notebook", "self"))
        self.assertEqual(d["meta"]["files"], 3)
        self.assertTrue(all(0 <= a < len(n) and 0 <= b < len(n) for a, b, _ in d["links"]))

    def test_our_chats_are_stars_strung_in_time(self):
        d = brainmap.build(self.mem, chats=brainmap.our_chats(self.conv))
        chats = [x for x in d["nodes"] if x["k"] == "chat"]
        self.assertEqual([c["chat"] for c in chats], ["a-first", "b-later"])
        self.assertEqual(chats[0]["text"], "Sun Sep 13 2026 to Mon Sep 14 2026 · 2 messages · archived")
        self.assertTrue(chats[0]["old"] and not chats[1]["old"])
        hub = next(i for i, x in enumerate(d["nodes"]) if x["k"] == "region" and x["region"] == "chats")
        idx = {c["chat"]: c["i"] for c in chats}
        self.assertIn([hub, idx["a-first"], "tree"], d["links"])
        self.assertIn([idx["a-first"], idx["b-later"], "leaf"], d["links"])
        self.assertEqual(d["meta"]["chats"], 2)
        self.assertEqual(brainmap.build(self.mem)["meta"]["chats"], 0)


if __name__ == "__main__":
    unittest.main()
