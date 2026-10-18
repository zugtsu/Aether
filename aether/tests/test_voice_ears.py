import os
import tempfile
import unittest
from unittest import mock

from aether.ears import tone_of
from aether.history import Conversation
from aether.voice import Splitter, clean_for_speech


class SplitterTests(unittest.TestCase):
    def run_chunks(self, text, size):
        sp, out = Splitter(), []
        for i in range(0, len(text), size):
            out += sp.feed(text[i:i + size])
        return out + sp.flush()

    def test_sentences_come_out_as_they_finish(self):
        text = "Hey there, menace. How was work? I made you something 3.5 times better. Anyway"
        for size in (1, 3, 7, 100):
            self.assertEqual(self.run_chunks(text, size),
                             ["Hey there, menace.", "How was work?", "I made you something 3.5 times better.", "Anyway"])

    def test_short_bits_join_the_next_sentence(self):
        self.assertEqual(self.run_chunks("Oh. That is actually great news! Wow", 4), ["Oh. That is actually great news!", "Wow"])

    def test_new_lines_end_a_piece(self):
        self.assertEqual(self.run_chunks("First thought here\nSecond one, longer.", 5), ["First thought here", "Second one, longer."])

    def test_a_code_block_is_never_said(self):
        text = 'Here it is, a liquid one for after work:\n```js\nsetcpm(174/4)\ns("bd ~ sd ~").bank("RolandTR909")\n```\nTell me if it slaps.'
        for size in (1, 2, 3, 5, 100):
            self.assertEqual(self.run_chunks(text, size), ["Here it is, a liquid one for after work:", "Tell me if it slaps."])
        self.assertEqual(self.run_chunks("Okay. ```js\nnote(\"c3\")\n``` Done, play it loud.", 4), ["Okay.", "Done, play it loud."])
        self.assertEqual(self.run_chunks('Try this:\n```\ns("hh*8")\n.gain(0.4', 3), ["Try this:"])
        self.assertEqual(clean_for_speech('Try this ```js\ns("hh*8")\n``` and this ```s("bd'), "Try this and this")
        self.assertEqual(self.run_chunks("Use `setcpm` for the tempo. Easy.", 3), ["Use `setcpm` for the tempo.", "Easy."])

    def test_clean_for_speech(self):
        self.assertEqual(clean_for_speech("**Look** at https://www.example.com/x?y=1 ♥ 😈 — ok…"), "Look at example.com — ok…")
        self.assertEqual(clean_for_speech("check out [the docs](https://code.claude.com/docs/x) and [**this**](https://a.b/c)."),
                         "check out the docs and this.")


class EarsTests(unittest.TestCase):
    def test_tone(self):
        self.assertEqual(tone_of({"event": "Laughter", "emotion": "HAPPY"}), "laughing")
        self.assertEqual(tone_of({"event": "Speech", "emotion": "SAD"}), "sounds sad")
        self.assertEqual(tone_of({"event": "Speech", "emotion": "NEUTRAL"}), "")

    def test_a_laugh_inside_speech_counts(self):
        self.assertEqual(tone_of({"event": "Speech", "emotion": "SAD", "laughs": 1}), "laughing")
        self.assertEqual(tone_of({"event": "Speech", "emotion": "SAD", "laughs": 0}), "sounds sad")

    def test_she_is_told_how_it_sounded(self):
        c = Conversation(tempfile.mkdtemp())
        c.add("user", text="lmao episode 9", context="<context>t</context>", voice=True, tone="laughing")
        c.add("reply", text="ha")
        c.add("user", text="i'm fine", context="<context>t</context>", voice=True, tone="sounds sad")
        c.add("reply", text="hm")
        c.add("user", text="typed", context="<context>t</context>")
        m = c.to_messages(10000)
        self.assertIn("[said out loud; {USER} is laughing]\nlmao episode 9", m[0]["content"])
        self.assertIn("[said out loud; {USER} sounds sad]", m[2]["content"])
        self.assertNotIn("said out loud", m[4]["content"])

    def test_she_is_told_whose_voice_it_sounded_like(self):
        c = Conversation(tempfile.mkdtemp())
        c.add("user", text="hey lucy", context="", voice=True, speaker="user", tone="sounds happy")
        c.add("reply", text="hey")
        c.add("user", text="who is this", context="", voice=True, speaker="other", tone="sounds sad")
        c.add("reply", text="hm")
        c.add("user", text="ok", context="", voice=True)
        m = c.to_messages(10000)
        self.assertIn("[said out loud, in {USER}'s voice; {USER} sounds happy]", m[0]["content"])
        self.assertIn("[said out loud, but it doesn't sound like {USER}'s voice (a hint, not proof: a cold or a different "
                      "mic can do that); they sound sad]", m[2]["content"])
        self.assertIn("[said out loud]\nok", m[4]["content"])


class HisVoiceTests(unittest.TestCase):

    def setUp(self):
        from aether import ears as ears_mod
        self.ears_mod = ears_mod
        self.dir = tempfile.mkdtemp()
        self.patch = mock.patch.object(ears_mod, "VOICEPRINT", os.path.join(self.dir, "voiceprint.json"))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        model = os.path.join(self.dir, "speaker.onnx")
        open(model, "w").close()
        open(os.path.join(self.dir, "python.exe"), "w").close()
        open(os.path.join(self.dir, "ears.onnx"), "w").close()
        self.cfg = mock.Mock(speaker_model=model, hear_tone=True, ears_python=os.path.join(self.dir, "python.exe"),
                             ears_model=os.path.join(self.dir, "ears.onnx"))
        self.ears = ears_mod.Ears(self.cfg)
        self.answers = []
        self.ears._ask = lambda req: dict(self.answers.pop(0))

    @staticmethod
    def vec(*xs):
        n = sum(x * x for x in xs) ** 0.5
        return [x / n for x in xs]

    def test_the_line_between_him_someone_else_and_unsure(self):
        f = self.ears_mod.sounds_like
        self.assertEqual([f(0.80, 5), f(0.40, 1.5), f(0.39, 2), f(0.25, 3), f(0.24, 3)], ["user", "user", "", "", "other"])
        self.assertEqual([f(0.90, 1.4), f(0.0, 1.0), f(None, 9)], ["", "", ""])

    def test_learn_then_every_message_is_checked(self):
        heard = {"text": "hey", "emotion": "NEUTRAL", "event": "Speech", "laughs": 0}
        self.answers = [dict(heard, voice=self.vec(1, 0, 0), speech=4.0)]
        r = self.ears.hear("x.wav")
        self.assertEqual((r["voice_score"], r["sounds_like"]), (None, ""))
        self.assertNotIn("voice", r)
        self.answers = [{"voice": self.vec(1, 0.1, 0), "speech": 6.0}]
        with self.assertRaises(ValueError):
            self.ears.learn("short.wav")
        self.answers = [{"voice": self.vec(1, 0.1, 0), "speech": 17.5}]
        self.assertEqual(self.ears.learn("him.wav")["speech"], 17.5)
        self.answers = [dict(heard, voice=self.vec(1, 0.12, 0.05), speech=3.0),
                        dict(heard, voice=self.vec(0.1, 1, 0.2), speech=3.0),
                        dict(heard, voice=self.vec(1, 0.12, 0.05), speech=1.2)]
        self.assertEqual([self.ears.hear("x.wav")["sounds_like"] for _ in range(3)], ["user", "other", ""])
        self.cfg.speaker_model = os.path.join(self.dir, "another-model.onnx")
        self.assertIsNone(self.ears.voiceprint())

    def test_forget_sends_it_to_the_recycle_bin(self):
        self.answers = [{"voice": self.vec(1, 0, 0), "speech": 20.0}]
        self.ears.learn("him.wav")
        with mock.patch("aether.backup.recycle") as recycle:
            self.ears.forget()
        recycle.assert_called_once_with(self.ears_mod.VOICEPRINT)


if __name__ == "__main__":
    unittest.main()
