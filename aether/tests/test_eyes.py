import json
import os
import tempfile
import unittest
from unittest import mock

from aether import eyes
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory
from aether.tests.test_imagine import tiny_png

STEP = {"step": "webcam", "about": "what he's holding"}


def saw(msgs):
    return any(isinstance(m["content"], list) and any(p["type"] == "image_url" for p in m["content"]) for m in msgs)


class EyesTests(unittest.TestCase):
    def setUp(self):
        self.httpd, self.app = make_server(make_config(make_memory()), ScriptedLLM([]), port=0)
        self.app.engine.conv = Conversation(tempfile.mkdtemp())
        self.frame = os.path.join(tempfile.mkdtemp(), "look-1.jpg")
        with open(self.frame, "wb") as f:
            f.write(tiny_png())
        self.shots = []
        fake = lambda cfg, slot: self.shots.append(slot) or (self.frame, None)  # noqa: E731
        self.patch = mock.patch.object(eyes, "snapshot", fake)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.httpd.server_close()

    def eyes_on(self, on=True):
        self.app.cfg.eyes_enabled = on
        self.app.engine.refresh()

    def test_closed_until_he_switches_them_on(self):
        self.assertNotIn('{"const": "webcam"}', json.dumps(self.app.engine.schema))
        self.assertFalse(self.app.eyes.run_step(STEP)[0])
        self.assertIn("are switched OFF in Settings: you can't see him", self.app.engine.messages()[0]["content"])
        self.eyes_on()
        self.assertIn('{"const": "webcam"}', json.dumps(self.app.engine.schema))
        self.assertIn("your webcam step shows you a picture from his webcam", self.app.engine.messages()[0]["content"])

    def test_she_sees_the_picture_when_he_asks(self):
        self.eyes_on()
        self.app.engine.llm = ScriptedLLM([STEP, {"step": "reply"}, {"say": "A mug. Coffee at 10 PM, really?"}])
        self.app.engine.turn("what am i holding?", place="Aether app")
        calls = self.app.engine.llm.calls
        self.assertFalse(saw(calls[0]["messages"]))
        self.assertTrue(saw(calls[1]["messages"]))
        self.assertTrue(saw(calls[2]["messages"]))
        res = next(e for e in self.app.engine.conv.events if e["kind"] == "result")
        self.assertTrue(res["ok"])
        self.assertEqual(self.shots, [1])
        self.assertTrue(self.app.engine._is_lookup(STEP))

    def test_a_frame_is_outside_content(self):
        self.eyes_on()
        asked = []
        self.app.engine.hooks.ask = lambda q: asked.append(q) or False
        self.app.engine.llm = ScriptedLLM([STEP, {"step": "memory_add", "file": "system/human/facts.md",
                                                  "text": "He keeps his keys on a blue hook.", "reason": "the picture"},
                                           {"step": "reply"}, {"say": "A blue hook, noted... or not."}])
        self.app.engine.turn("look through the webcam and remember where i keep my keys", place="Aether app")
        res = [e for e in self.app.engine.conv.events if e["kind"] == "result"]
        self.assertTrue(res[0]["ok"])
        self.assertEqual(res[0].get("outside"), "webcam")
        self.assertFalse(res[1]["ok"])
        self.assertIn("outside content in this reply (what your webcam showed)", res[1]["text"])
        self.assertEqual(asked, [])

    def test_never_over_discord_or_on_her_own_time(self):
        self.eyes_on()
        self.app.engine.llm = ScriptedLLM([STEP, {"step": "reply"}, {"say": "I can't from here."}, {"step": "reply"}, {"say": "I can't from here."}])
        self.app.engine.turn("can you see me?", place="Discord DM")
        self.app.engine._kind = "wake"
        self.app.engine._place = "app"
        self.assertFalse(self.app.eyes.run_step(STEP)[0])
        res = next(e for e in self.app.engine.conv.events if e["kind"] == "result")
        self.assertFalse(res["ok"])
        self.assertIn("Discord", res["text"])
        self.assertEqual(self.shots, [])

    def test_three_frames_reused_in_turn(self):
        self.eyes_on()
        self.app.engine._kind, self.app.engine._place = "user", "app"
        self.app.engine._asks = [("webcam", "", "", None)]
        for _ in range(4):
            self.app.eyes.run_step(STEP)
        self.assertEqual(self.shots, [1, 2, 3, 1])

    def test_frames_are_gone_once_she_has_answered(self):
        self.eyes_on()
        os.makedirs(eyes.EYES_DIR, exist_ok=True)
        for name in ("look-1.jpg", "look-2.jpg", "keep.txt"):
            with open(os.path.join(eyes.EYES_DIR, name), "wb") as f:
                f.write(tiny_png())
        self.app.broadcast = lambda ev: None
        self.app.engine.llm = ScriptedLLM([STEP, {"step": "reply"}, {"say": "A mug."}])
        self.app.new_chat()
        self.app.gpu.acquire()
        self.app._turn(self.app.engine.conv, "what am i holding?", [], speak=False)
        self.assertEqual(self.shots, [1])
        self.assertEqual(sorted(os.listdir(eyes.EYES_DIR)), ["keep.txt"])
        with open(os.path.join(eyes.EYES_DIR, "look-3.jpg"), "wb") as f:
            f.write(tiny_png())
        eyes.Eyes(self.app)
        self.assertEqual(sorted(os.listdir(eyes.EYES_DIR)), ["keep.txt"])

    def test_only_when_his_message_asks(self):
        self.eyes_on()
        self.app.engine.llm = ScriptedLLM([STEP, {"step": "reply"}, {"say": "Still you."}, {"step": "reply"}, {"say": "x"}])
        self.app.engine.turn("oh so thats how i look, cool", place="Aether app")
        res = next(e for e in self.app.engine.conv.events if e["kind"] == "result")
        self.assertFalse(res["ok"])
        self.assertIn("doesn't ask you to look", res["text"])
        self.assertEqual(self.shots, [])

    def test_a_camera_name_is_one_argument(self):
        self.patch.stop()
        cfg = make_config(make_memory())
        cfg.eyes_camera = 'Cam" & calc & "'
        with mock.patch.object(eyes.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=1, stderr="no", stdout="")
            eyes.snapshot(cfg, 1)
        args = run.call_args_list[0][0][0]
        self.assertIsInstance(args, list)
        self.assertIn('video=Cam" & calc & "', args)
        self.assertNotIn("shell", run.call_args_list[0][1])
        self.patch.start()


if __name__ == "__main__":
    unittest.main()
