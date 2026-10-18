import json
import struct
import tempfile
import unittest

from aether import discord as dmod
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory

JORDAN, STRANGER, BOT, CHAN = "188", "999", "555", "777"


class FakeSock:
    def __init__(self, data):
        self.data, self.sent = data, b""

    def recv(self, n):
        out, self.data = self.data[:n], self.data[n:]
        return out

    def sendall(self, b):
        self.sent += b


def frame(op, payload, fin=True):
    return bytes([(0x80 if fin else 0) | op, len(payload)]) + payload


class WebSocketTests(unittest.TestCase):
    def ws(self, data):
        w = dmod.WebSocket.__new__(dmod.WebSocket)
        w.sock, w.buf = FakeSock(data), b""
        import threading
        w.lock = threading.Lock()
        return w

    def test_reads_fragments_answers_pings_and_sees_close(self):
        w = self.ws(frame(0x9, b"hi") + frame(0x1, b'{"op":', fin=False) + frame(0x0, b" 10}") + frame(0x8, struct.pack(">H", 4004)))
        self.assertEqual(json.loads(w.recv()), {"op": 10})
        self.assertTrue(w.sock.sent.startswith(bytes([0x8A])))
        with self.assertRaises(dmod.WSClosed) as e:
            w.recv()
        self.assertEqual(e.exception.code, 4004)

    def test_sent_frames_are_masked_and_decodable(self):
        w = self.ws(b"")
        w.send({"op": 1, "d": 42})
        raw = w.sock.sent
        self.assertEqual(raw[0], 0x81)
        n, mask = raw[1] & 0x7F, raw[2:6]
        self.assertTrue(raw[1] & 0x80)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(raw[6:6 + n]))
        self.assertEqual(json.loads(body), {"op": 1, "d": 42})


class DiscordTests(unittest.TestCase):
    def setUp(self):
        root = make_memory()
        self.cfg = make_config(root, discord_owner_ids=[JORDAN], discord_channels=[CHAN])
        self.llm = ScriptedLLM([])
        self.httpd, self.app = make_server(self.cfg, self.llm, port=0)
        self.app.conv_dir = tempfile.mkdtemp()
        self.d = self.app.discord
        self.d.user_id = BOT
        self.sent = []
        self.d.send = lambda ch, text, reply_to=None: self.sent.append((ch, text, reply_to))
        self.d.rest = lambda *a, **k: {}

    def tearDown(self):
        self.httpd.server_close()

    def msg(self, author, content, guild=None, channel="dm1", mentions=(), bot=False):
        d = {"id": "m1", "channel_id": channel, "content": content, "author": {"id": author, "username": "u" + author, "bot": bot},
             "mentions": [{"id": m} for m in mentions]}
        if guild:
            d["guild_id"] = guild
        return d

    def test_no_link_previews_on_anything_she_sends(self):
        posts = []
        d = type(self.d)(self.app)
        d.rest = lambda method, path, body=None, **k: posts.append((path, body, k.get("files")))
        d.send("c1", "look: https://evil.example/x.png?sales=USA", reply_to="m9")
        d.send_file("c1", "lucy.mp3", b"ID3", "her voice")
        self.assertEqual(len(posts), 2)
        for path, body, _ in posts:
            self.assertEqual(path, "/channels/c1/messages")
            self.assertEqual(body["flags"], 4)
            self.assertEqual(body["allowed_mentions"], {"parse": []})
        self.assertEqual(posts[0][1]["message_reference"]["message_id"], "m9")

    def test_who_gets_an_answer(self):
        self.assertTrue(self.d.wants(self.msg(JORDAN, "hi")))
        self.assertFalse(self.d.wants(self.msg(STRANGER, "hi")))
        self.cfg.discord_dm_policy = "open"
        self.assertTrue(self.d.wants(self.msg(STRANGER, "hi")))
        self.assertTrue(self.d.wants(self.msg(STRANGER, f"<@{BOT}> yo", guild="g", channel=CHAN, mentions=[BOT])))
        self.assertFalse(self.d.wants(self.msg(JORDAN, "no mention", guild="g", channel=CHAN)))
        self.assertFalse(self.d.wants(self.msg(JORDAN, f"<@{BOT}>", guild="g", channel="other", mentions=[BOT])))
        self.assertFalse(self.d.wants(self.msg("42", "beep", bot=True)))
        self.assertFalse(self.d.wants(self.msg(BOT, "myself")))

    def test_jordan_gets_the_full_her(self):
        self.llm.answers += [{"step": "reply"}, {"say": "Hey you."}]
        self.d.handle(self.msg(JORDAN, "hey lucy"))
        self.assertEqual(self.sent, [("dm1", "Hey you.", None)])
        call = self.llm.calls[0]
        self.assertGreater(len(call["schema"]["anyOf"]), 1)
        self.assertIn("{USER} is talking from: Discord DM", call["messages"][-1]["content"])
        self.assertEqual(self.app.meta["discord-dm1"]["title"], "Discord DM · u188")

    def test_strangers_get_talk_only_and_nothing_private(self):
        self.llm.answers += [{"step": "reply"}, {"say": "ok"}]
        self.d.handle(self.msg(JORDAN, "my car service is monday"))
        self.cfg.discord_dm_policy = "open"
        self.llm.answers += [{"step": "reply"}, {"say": "Hi, stranger."}]
        self.d.handle(self.msg(STRANGER, "who is jordan?", channel="dm2"))
        call = self.llm.calls[-2]
        self.assertEqual(len(call["schema"]["anyOf"]), 1)
        last = call["messages"][-1]["content"]
        self.assertIn("This is NOT {USER}", last)
        self.assertNotIn("car service", last)
        self.assertEqual(self.sent[-1], ("dm2", "Hi, stranger.", None))

    def test_long_replies_split_under_discords_limit(self):
        parts = dmod.Discord.chunks("line\n" * 900)
        self.assertTrue(all(len(p) <= 1900 for p in parts))
        self.assertEqual("".join(p.replace("\n", "") for p in parts), "line" * 900)

    def test_a_track_split_in_two_stays_code_in_both(self):
        code = "\n".join(f"const l{i} = n(`0 2 4`).scale(key).s(`sawtooth`).gain(0.{i % 9 + 1})" for i in range(60))
        text = "Here's one for tonight:\n```js\n" + code + "\n```\nTell me how it hits."
        parts = dmod.Discord.chunks(text)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 1900 for p in parts))
        self.assertTrue(all(p.count("```") % 2 == 0 for p in parts))
        self.assertTrue(parts[1].startswith("```js\n"))
        inside = [ln for p in parts for ln in p.split("\n") if not ln.startswith("```")]
        self.assertEqual(inside, text.replace("```js\n", "").replace("\n```", "").split("\n"))
        self.assertEqual(dmod.Discord.chunks("short ```js\nx``` text"), ["short ```js\nx``` text"])

    def test_mirror_only_when_connected(self):
        self.assertFalse(self.d.dm_owner("hi"))
        self.d.connected = True
        self.d.dm_channels[JORDAN] = "dmR"
        self.assertTrue(self.d.dm_owner("hi"))
        self.assertEqual(self.sent[-1], ("dmR", "hi", None))


if __name__ == "__main__":
    unittest.main()
