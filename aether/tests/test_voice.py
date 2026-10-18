import base64
import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from aether import voice as voice_mod
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory
from aether.voice import Clip, Voice, clean_for_speech, direction

PIECES = [b"\x01\x00" * 800, b"\x02\x00" * 800, b"\x03\x00" * 400]


class FakeAudio:

    def __init__(self):
        self.bodies, self.kokoro, self.breeze_error = [], [], False
        me = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/health":
                    return self._send(200, b'{"model_loaded": true}', "application/json")
                self._send(404, b"", "text/plain")

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if body.get("model") == "kokoro":
                    me.kokoro.append(body["input"])
                    return self._send(200, b"ID3kokoro:" + body["input"].encode(), "audio/mpeg")
                me.bodies.append(body)
                if not body.get("stream"):
                    return self._send(200, b"RIFFwav:" + body["input"].encode(), "audio/wav")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                if me.breeze_error:
                    self.wfile.write(b'data: {"type":"error","error":{"message":"model busy"}}\n\n')
                    return
                try:
                    for p in PIECES:
                        ev = {"type": "speech.audio.delta", "audio": base64.b64encode(p).decode()}
                        self.wfile.write(b"data: " + json.dumps(ev).encode() + b"\n\n")
                        self.wfile.flush()
                    self.wfile.write(b'data: {"type":"speech.audio.done"}\n\ndata: [DONE]\n\n')
                except ConnectionError:
                    pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def engine_dir(with_model=True):
    d = tempfile.mkdtemp()
    for rel in ("audiocpp/audiocpp_server.exe", "voices/voice.wav") + (("models/breeze-tts-2-q8_0.gguf",) if with_model else ()):
        os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
        open(os.path.join(d, rel), "wb").close()
    return d


def wait_for(cond, secs=10):
    t0 = time.time()
    while time.time() - t0 < secs:
        if cond():
            return True
        time.sleep(0.02)
    return False


class SpeechTextTests(unittest.TestCase):
    def test_a_laugh_or_sigh_she_wrote(self):
        text = "Oh (laughs) no. *sighs* Fine [chuckles], and (clears throat) okay."
        self.assertEqual(clean_for_speech(text, sounds=True), "Oh (laugh) no. (sigh) Fine (laugh) , and (clears throat) okay.")
        self.assertEqual(clean_for_speech(text), "Oh no. Fine , and okay.")
        self.assertEqual(clean_for_speech("(I laughed at that)", sounds=True), "(I laughed at that)")

    def test_the_old_cleaning_still_holds(self):
        self.assertEqual(clean_for_speech("**Look** at https://www.example.com/x?y=1 ♥ 😈 — ok…", sounds=True),
                         "Look at example.com — ok…")

    def test_her_mood_is_the_direction(self):
        self.assertIn("Relaxed", direction(None))
        self.assertIn("Relaxed", direction({"name": "no such mood", "strength": 1}))
        self.assertIn("teasing", direction({"name": "playful", "strength": 0.9}))
        weak = direction({"name": "playful", "strength": 0.2})
        self.assertTrue(weak.startswith("Relaxed and conversational") and "playful" in weak, weak)
        self.assertEqual(set(voice_mod.MOOD_VOICE), set(__import__("aether.life", fromlist=["MOODS"]).MOODS))


class ClipTests(unittest.TestCase):
    def test_a_reader_gets_pieces_as_they_arrive(self):
        c, got = Clip(), []
        c.add(b"ab")
        reader = threading.Thread(target=lambda: got.extend(c.pieces()))
        reader.start()
        time.sleep(0.05)
        c.add(b"cd")
        time.sleep(0.05)
        c.add(b"ef")
        c.finish()
        reader.join(5)
        self.assertEqual(b"".join(got), b"abcdef")
        self.assertGreaterEqual(len(got), 2)
        self.assertEqual(b"".join(c.pieces()), b"abcdef")

    def test_a_stuck_sentence_ends_the_stream(self):
        c = Clip()
        c.add(b"ab")
        self.assertEqual(list(c.pieces(stuck=0.1)), [b"ab"])


class VoiceServerTests(unittest.TestCase):

    def setUp(self):
        seen = self.seen = []

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.end_headers()
                self.wfile.write(b"ID3-fake-mp3")

            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def log_message(self, *a):
                pass
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.serving = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.cfg = make_config(make_memory(), voice_engine="kokoro", start_kokoro=False, voice="alloy",
                               tts_url=f"http://127.0.0.1:{self.srv.server_address[1]}", tts_model="tts-1")
        self.v = Voice(self.cfg, lambda e: None, mood=lambda: {"name": "steady", "strength": 0.5})

    def tearDown(self):
        self.stop()

    def stop(self):
        if self.serving:
            self.serving = False
            self.srv.shutdown()
            self.srv.server_close()

    def test_its_model_and_voice_go_to_the_server(self):
        self.assertTrue(self.v.up())
        self.assertEqual(self.v._kokoro_mp3("hi there"), b"ID3-fake-mp3")
        self.assertEqual((self.seen[0]["model"], self.seen[0]["voice"], self.seen[0]["input"]), ("tts-1", "alloy", "hi there"))

    def test_down_and_off_this_pc(self):
        self.stop()
        self.assertFalse(self.v.up())
        self.cfg.tts_url = "http://example.com:80"
        with self.assertRaises(RuntimeError):
            self.v._kokoro_mp3("hi")
        self.assertEqual(self.seen, [])


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeAudio()
        self.events = []
        self.cfg = make_config(make_memory(), voice_engine="breeze", breeze_url=self.fake.url, tts_url=self.fake.url,
                               breeze_dir=engine_dir(), start_kokoro=False)
        self.mood = {"name": "playful", "strength": 0.9}
        self.v = Voice(self.cfg, self.events.append, mood=lambda: self.mood)

    def tearDown(self):
        self.fake.close()

    def audio(self):
        return [e for e in self.events if e["type"] == "audio"]

    def test_she_speaks_in_her_own_voice_streamed(self):
        self.v.warm()
        self.assertTrue(wait_for(lambda: self.v.breeze.state == "up"))
        self.assertEqual(self.fake.bodies[0]["input"], "Okay.")
        self.v.say_now("Well, look who's back. (laughs) Took you long enough!")
        self.assertTrue(wait_for(lambda: len(self.audio()) == 2 and all(self.v.get(e["id"]).done for e in self.audio())))
        ev = self.audio()[1]
        self.assertTrue(ev["stream"])
        self.assertEqual(ev["rate"], 24000)
        self.assertEqual(bytes(self.v.get(ev["id"]).pcm), b"".join(PIECES))
        said = self.fake.bodies[2]
        self.assertEqual(said["input"], "(laugh) Took you long enough!")
        self.assertEqual(said["voice"], "voice")
        self.assertIn("teasing", said["options"]["instruction"])
        self.assertEqual(said["options"]["guidance_scale"], "1")
        self.assertEqual(self.fake.kokoro, [])

    def test_a_sentence_breeze_couldnt_make_stays_text(self):
        self.v.warm()
        self.assertTrue(wait_for(lambda: self.v.breeze.state == "up"))
        self.fake.breeze_error = True
        self.v.say_now("This one goes wrong somewhere.")
        self.assertTrue(wait_for(lambda: len(self.fake.bodies) == 2 and not self.v.making))
        self.assertEqual((self.audio(), self.fake.kokoro), ([], []))
        self.assertEqual(self.v.breeze.state, "up")

    def test_missing_files_mean_text_only_and_he_is_told_once(self):
        self.cfg.breeze_dir = engine_dir(with_model=False)
        self.assertFalse(self.v.ensure_running())
        self.assertEqual(self.v.breeze.state, "failed")
        self.assertIn("Breeze model", self.v.breeze.why)
        self.v.say_now("Hello there, nobody hears this. Or this one either.")
        self.assertTrue(wait_for(lambda: self.v.jobs.empty() and not self.v.making))
        notes = [e for e in self.events if e["type"] == "audio_error"]
        self.assertEqual(len(notes), 1)
        self.assertIn("Text only for now: the voice didn't start", notes[0]["text"])
        self.assertEqual((self.audio(), self.fake.kokoro), ([], []))

    def test_kokoro_as_her_voice_leaves_breeze_alone(self):
        self.cfg.voice_engine = "kokoro"
        self.v.warm()
        self.v.say_now("Just Kokoro today.")
        self.assertTrue(wait_for(lambda: self.fake.kokoro == ["Just Kokoro today."]))
        self.assertEqual((self.v.breeze.state, self.fake.bodies), ("off", []))

    def test_breeze_steps_aside_for_pictures_and_comes_back(self):
        self.v.warm()
        self.assertTrue(wait_for(lambda: self.v.breeze.state == "up"))
        self.assertTrue(self.v.step_aside())
        self.assertEqual(self.v.breeze.state, "aside")
        self.assertFalse(self.v.ensure_running())
        self.assertIn("resting while a picture is drawn", self.v.quiet_why())
        self.v.say_now("Drawing something for you.")
        self.assertTrue(wait_for(lambda: self.v.jobs.empty() and not self.v.making))
        self.assertEqual((self.audio(), self.fake.kokoro), ([], []))
        self.assertEqual([e for e in self.events if e["type"] == "audio_error"], [])
        self.v.step_back()
        self.assertTrue(wait_for(lambda: self.v.breeze.state == "up"))
        self.cfg.breeze_aside_for_pictures = False
        self.assertFalse(self.v.step_aside())
        self.assertEqual(self.v.breeze.state, "up")

    def test_never_lets_her_voice_go_and_always_loads_it(self):
        self.cfg.speak_replies = "never"
        self.v.warm()
        self.assertEqual((self.v.breeze.state, self.fake.bodies), ("off", []))
        self.cfg.speak_replies = "always"
        self.v.warm()
        self.assertTrue(wait_for(lambda: self.v.breeze.state == "up"))
        self.cfg.speak_replies = "never"
        self.v.warm()
        self.assertEqual(self.v.breeze.state, "off")
        self.cfg.speak_replies = "when_i_talk"
        self.v.warm()
        self.assertTrue(wait_for(lambda: self.v.breeze.state == "up"))
        self.v.warm()
        self.assertEqual(self.v.breeze.state, "up")

    def test_on_never_a_clip_borrows_her_voice_then_lets_it_go(self):
        self.cfg.speak_replies = "never"
        mp3 = mock.patch.object(voice_mod, "to_mp3", side_effect=lambda wav: b"MP3")
        with mock.patch.object(voice_mod, "REST_AFTER", 0.3), mock.patch.object(voice_mod.shutil, "which",
                                                                                 return_value="ffmpeg"), mp3:
            self.assertEqual(self.v.synth("A clip for Discord."), b"MP3")
            self.assertEqual(self.v.breeze.state, "up")
            self.assertTrue(wait_for(lambda: self.v.breeze.state == "off", 3))
            self.v.say_now("The play button.")
            self.assertTrue(wait_for(lambda: len(self.audio()) == 1))
            self.assertTrue(wait_for(lambda: self.v.breeze.state == "off", 3))
            self.cfg.speak_replies = "always"
            self.v.synth("Another clip.")
            time.sleep(0.6)
            self.assertEqual(self.v.breeze.state, "up")
            self.cfg.speak_replies = "never"
            self.assertTrue(self.v.step_aside())
            self.v.step_back()
            self.assertEqual(self.v.breeze.state, "off")

    def test_stop_drops_whats_queued(self):
        self.v.warm()
        self.assertTrue(wait_for(lambda: self.v.breeze.state == "up"))
        with mock.patch.object(self.v, "_breeze_ready", side_effect=lambda: time.sleep(0.3) or True):
            self.v.say_now("First sentence here. Second sentence here. Third sentence here.")
            time.sleep(0.1)
            self.v.stop()
            time.sleep(1)
        self.assertLessEqual(len(self.audio()), 1)
        self.assertIn({"type": "audio_stop"}, self.events)

    def _spill_run(self, shared_mb):
        b, launches = self.v.breeze, []

        class FakeProc:
            pid, job = 4242, None

            def poll(self):
                return 0

        def launch():
            launches.append(1)
            b.proc = FakeProc()
        with mock.patch.object(b, "up", return_value=False), mock.patch.object(b, "_launch", side_effect=launch), \
                mock.patch.object(voice_mod, "gpu_shared_mb", side_effect=shared_mb), \
                mock.patch.object(voice_mod.time, "sleep"):
            b.start()
            self.assertTrue(wait_for(lambda: b.ready.is_set()))
        return b, launches

    def test_a_breeze_that_landed_in_regular_ram_loads_again(self):
        b, launches = self._spill_run([1024.0, 20.0])
        self.assertEqual((b.state, len(launches)), ("up", 2))

    def test_still_in_regular_ram_after_a_second_try_means_kokoro_for_now(self):
        b, launches = self._spill_run([1024.0, 900.0])
        self.assertEqual((b.state, len(launches)), ("failed", 2))
        self.assertIn("graphics memory", b.why)
        self.assertGreater(b.retry_at - time.time(), 200)
        self.v.say_now("This one stays text for now.")
        self.assertTrue(wait_for(lambda: [e for e in self.events if e["type"] == "audio_error"]))
        self.assertIn("graphics memory", self.events[-1]["text"])
        self.assertEqual(self.fake.kokoro, [])

    def test_too_slow_twice_in_a_row_loads_breeze_again_when_shes_quiet(self):
        self.v.warm()
        self.assertTrue(wait_for(lambda: self.v.breeze.state == "up"))
        with mock.patch.object(voice_mod, "BREEZE_SLOW", -1), mock.patch.object(voice_mod, "BREEZE_SLOW_MIN", 0), \
                mock.patch.object(self.v.breeze, "reload") as reload:
            self.v.say_now("First slow sentence here.")
            self.assertTrue(wait_for(lambda: len(self.audio()) == 1 and not self.v.making))
            reload.assert_not_called()
            self.v.say_now("Second slow sentence here.")
            self.assertTrue(wait_for(lambda: reload.called))
        self.assertIn("two sentences in a row", self.v.breeze.reload_wanted)

    def test_reload_waits_between_tries(self):
        self.v.warm()
        self.assertTrue(wait_for(lambda: self.v.breeze.state == "up"))
        b = self.v.breeze
        b.reload_wanted = "slow"
        b.reload()
        self.assertTrue(wait_for(lambda: b.state == "up"))
        first = b.reloaded_at
        b.reload_wanted = "slow again"
        b.reload()
        self.assertEqual((b.reloaded_at, b.state, b.reload_wanted), (first, "up", ""))

    def test_whole_clips_for_discord_and_the_game(self):
        self.v.warm()
        self.assertTrue(wait_for(lambda: self.v.breeze.state == "up"))
        with mock.patch.object(voice_mod.shutil, "which", return_value="ffmpeg"), \
                mock.patch.object(voice_mod, "to_mp3", side_effect=lambda wav: b"MP3<" + wav + b">"):
            self.assertEqual(self.v.synth("*sighs* Fine."), b"MP3<RIFFwav:(sigh) Fine.>")
        with mock.patch.object(voice_mod.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "ffmpeg"):
                self.v.synth("*sighs* Fine.")
        self.v.step_aside()
        with self.assertRaisesRegex(RuntimeError, "resting while a picture is drawn"):
            self.v.synth("Not now.")
        self.assertEqual(self.fake.kokoro, [])
        self.cfg.voice_engine = "kokoro"
        self.assertEqual(self.v.synth("*sighs* Fine."), b"ID3kokoro:Fine.")


class AudioRouteTests(unittest.TestCase):
    def test_the_page_gets_her_voice_while_its_made(self):
        httpd, app = make_server(make_config(make_memory()), ScriptedLLM([]), port=0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            port = httpd.server_address[1]
            clip = Clip()
            app.voice.audio["7"] = clip
            clip.add(b"\x01\x00" * 10)

            def later():
                time.sleep(0.2)
                clip.add(b"\x02\x00" * 10)
                clip.finish()
            threading.Thread(target=later, daemon=True).start()
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("GET", f"/api/audio?t={app.token}&id=7", headers={"Host": f"127.0.0.1:{port}"})
            r = c.getresponse()
            self.assertEqual((r.status, r.getheader("Content-Type")), (200, "application/octet-stream"))
            self.assertEqual(r.read(), b"\x01\x00" * 10 + b"\x02\x00" * 10)
            c.close()
            app.voice.audio["8"] = b"ID3old"
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("GET", f"/api/audio?t={app.token}&id=8", headers={"Host": f"127.0.0.1:{port}"})
            r = c.getresponse()
            self.assertEqual((r.getheader("Content-Type"), r.read()), ("audio/mpeg", b"ID3old"))
            c.close()
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_switching_her_voice_in_settings(self):
        fake = FakeAudio()
        httpd, app = make_server(make_config(make_memory(), breeze_url=fake.url, breeze_dir=engine_dir()), ScriptedLLM([]), port=0)
        try:
            with self.assertRaises(ValueError):
                app.update_settings({"voice_engine": "siri"})
            app.update_settings({"voice_engine": "breeze"})
            self.assertTrue(wait_for(lambda: app.voice.breeze.state == "up"))
            self.assertEqual(app.services()["voice"]["breeze"], "up")
            app.update_settings({"voice_engine": "kokoro"})
            self.assertEqual(app.voice.breeze.state, "off")
            app.update_settings({"voice_engine": "breeze", "speak_replies": "always"})
            self.assertTrue(wait_for(lambda: app.voice.breeze.state == "up"))
            app.update_settings({"speak_replies": "never"})
            self.assertEqual(app.voice.breeze.state, "off")
            app.update_settings({"speak_replies": "when_i_talk"})
            self.assertTrue(wait_for(lambda: app.voice.breeze.state == "up"))
        finally:
            fake.close()
            httpd.server_close()


class PromptTests(unittest.TestCase):
    def test_she_is_told_her_voice_can_laugh_only_with_breeze(self):
        from aether import prompt
        from aether.memory import Memory
        cfg = make_config(make_memory())
        mem = Memory(cfg.memory_path, cfg)
        self.assertNotIn("(laugh)", prompt.build(mem, {}, cfg))
        self.assertNotIn("{VOICE_SOUNDS}", prompt.build(mem, {}, cfg))
        cfg.voice_engine = "breeze"
        self.assertIn("write (laugh) or (sigh)", prompt.build(mem, {}, cfg))


if __name__ == "__main__":
    unittest.main()
