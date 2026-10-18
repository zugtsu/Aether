import json
import os
import re
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aether import imagine as im
from aether import songs
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def lyrics(sections=6, lines=3, words=4):
    names = ["verse", "chorus", "verse", "chorus", "bridge", "chorus", "verse", "chorus", "outro", "chorus"]
    return "\n".join(f"[{names[i]}]\n" + "\n".join(" ".join(["la"] * words) for _ in range(lines)) for i in range(sections))


GOOD = lyrics(7, 4)
STEP = {"step": "make_music", "title": "Glass Hours", "style": "dark synthwave, melancholic, 90 bpm, breathy voice",
        "length": "medium", "caption": "Something for your drive home."}


class FakeComfy:
    def __init__(self, error=""):
        self.prompts, self.error = [], error
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, obj):
                data = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/system_stats":
                    return self._json({"system": {}})
                m = re.match(r"/history/(\w+)", self.path)
                if m:
                    wf = fake.prompts[-1]
                    if fake.error:
                        return self._json({m.group(1): {"status": {"status_str": "error", "messages": [
                            ["execution_error", {"exception_message": fake.error}]]}, "outputs": {}}})
                    f = {"filename": wf["7"]["inputs"]["filename_prefix"] + "_00001_.mp3", "subfolder": "", "type": "output"}
                    return self._json({m.group(1): {"status": {"status_str": "success", "completed": True},
                                                    "outputs": {"7": {"audio": [f]}}}})
                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if self.path == "/prompt":
                    wf = body["prompt"]
                    fake.prompts.append(wf)
                    os.makedirs(im.OUT_DIR, exist_ok=True)
                    with open(os.path.join(im.OUT_DIR, wf["7"]["inputs"]["filename_prefix"] + "_00001_.mp3"), "wb") as f:
                        f.write(b"ID3 not really a song")
                    return self._json({"prompt_id": "p1"})
                return self._json({})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class SongPartsTests(unittest.TestCase):
    def test_the_workflow_is_the_blueprint(self):
        wf = songs.music_workflow("synthwave, female vocal", GOOD, 180, 7, prefix="aether-song-x")
        self.assertEqual([wf[k]["class_type"] for k in sorted(wf)],
                         ["CheckpointLoaderSimple", "YuE2GenerateMusic", "ConditioningZeroOut", "EmptyYuE2LatentAudio",
                          "KSampler", "VAEDecodeAudio", "SaveAudioMP3"])
        music, ks = wf["2"]["inputs"], wf["5"]["inputs"]
        self.assertEqual((music["clip"], music["mode"], music["abc"], music["max_duration"]), (["1", 1], "full", "", 180.0))
        self.assertEqual((ks["positive"], ks["negative"], ks["latent_image"]), (["2", 0], ["3", 0], ["4", 0]))
        self.assertEqual((ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]), (32, 1.0, "dpm_2", "sgm_uniform"))
        self.assertEqual(wf["4"]["inputs"]["seconds"], ["2", 1])
        self.assertEqual(wf["6"]["inputs"]["vae"], ["1", 2])
        self.assertEqual(wf["7"]["inputs"]["quality"], "128k")
        self.assertEqual(wf["1"]["inputs"]["ckpt_name"], "yue2_3b_int8_convrot.safetensors")

    def test_female_vocal_on_every_style_line_once(self):
        self.assertEqual(songs.style_line("dark dnb, 172bpm"), "dark dnb, 172bpm, female vocal")
        self.assertEqual(songs.style_line("Soft Female Vocal, lofi"), "Soft Female Vocal, lofi")
        self.assertEqual(songs.style_line(""), "female vocal")

    def test_an_instrumental_has_no_voice_and_no_words(self):
        line = songs.style_line("solo piano, breathy female vocal, melancholic, sung softly", instrumental=True)
        self.assertEqual(line, "solo piano, melancholic, instrumental, no vocals")
        self.assertNotIn("female vocal", songs.style_line("lofi beats", instrumental=True))
        self.assertEqual(songs.style_line("trap beat, rising synths, rap verses, heavy 808", instrumental=True),
                         "trap beat, rising synths, heavy 808, instrumental, no vocals")
        self.assertEqual(songs.style_line("Soft, ethereal piano with very light ambient synth pads and deep reverb. No vocals.",
                                          instrumental=True),
                         "Soft, ethereal piano with very light ambient synth pads and deep reverb, instrumental, no vocals")
        self.assertEqual(songs.style_line("calm piano without singing; slow", instrumental=True),
                         "calm piano, slow, instrumental, no vocals")
        bare = songs.instrumental_lyrics("short")
        self.assertEqual(bare, "[intro]\n\n[verse]\n\n[chorus]\n\n[verse]\n\n[chorus]\n\n[outro]")
        self.assertEqual(songs.seconds_for(bare, "short"), 150)

    def test_the_length_table(self):
        self.assertEqual({k: v[0] for k, v in songs.LENGTHS.items()}, {"short": 150, "medium": 210, "long": 300})
        for k, shape in songs.SHAPES.items():
            self.assertTrue(shape.endswith("outro"), k)
        self.assertEqual(songs.DOWN, {"long": "medium", "medium": "short"})

    def test_the_time_comes_from_her_lyrics(self):
        self.assertEqual(songs.seconds_for(lyrics(9, 4), "medium"), 259)
        self.assertEqual(songs.seconds_for(lyrics(4, 3), "medium"), 210)
        self.assertEqual(songs.seconds_for(lyrics(10, 8), "long"), 330)
        self.assertEqual(songs.seconds_for(lyrics(10, 8), "short"), 210)

    def test_the_lyrics_check(self):
        self.assertEqual(songs.check_lyrics(GOOD, "medium"), "")
        self.assertEqual(songs.check_lyrics(lyrics(5, 4), "short"), "")
        self.assertEqual(songs.check_lyrics(lyrics(9, 5), "long"), "")
        self.assertIn("brackets", songs.check_lyrics("just some words\nand more words", "medium"))
        self.assertIn("sections", songs.check_lyrics(lyrics(2), "medium"))
        self.assertIn("8 lines", songs.check_lyrics(lyrics(6, 9), "medium"))
        self.assertIn("words", songs.check_lyrics(lyrics(7, 6, 12), "medium"))
        self.assertIn("sung lines", songs.check_lyrics(lyrics(8, 7), "medium"))

    def test_the_app_plays_a_song(self):
        with open(os.path.join(PROJECT, "aether", "ui", "app.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn('e.kind === "made_song"', js)
        self.assertIn("<audio", js)
        self.assertNotIn("Open in Strudel", js)


class SongJobTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeComfy()
        self.cfg = make_config(make_memory(), image_pause_for=[], comfy_port=self.fake.port)
        self.httpd, self.app = make_server(self.cfg, ScriptedLLM([]), port=0)
        self.img = self.app.imagine
        self.img.state = {"queue": [], "made": {}}
        self.img._save()
        self.events = []
        self.app.broadcast = self.events.append
        self.app.engine._kind = "user"

    def tearDown(self):
        with self.img.lock:
            self.img.state = {"queue": [], "made": {}}
            self.img._save()
        self.httpd.server_close()
        self.fake.close()

    def step(self, *answers, **changes):
        self.app.engine.llm = ScriptedLLM([{"lyrics": a} for a in answers])
        return self.img.song_step(dict(STEP, **changes))

    def test_it_is_on_her_menu_with_its_page(self):
        self.assertIn("make_music", json.dumps(self.app.engine.schema))
        self.assertIn("make_music", self.app.engine._docs())

    def test_lyrics_come_back_once_and_then_it_queues(self):
        ok, text = self.step("no sections here", GOOD)
        self.assertTrue(ok, text)
        job = self.img.state["queue"][0]
        self.assertEqual((job["kind"], job["length"], job["lyrics"]), ("song", "medium", GOOD))
        self.assertTrue(job["prompt"].endswith("female vocal"))
        ok, text = self.step("still bad", "bad again")
        self.assertFalse(ok)

    def test_an_instrumental_skips_the_lyrics(self):
        ok, text = self.step(instrumental=True, style="solo piano, minimalist, soft reverb, slow")
        self.assertTrue(ok, text)
        self.assertIn("an instrumental, no singing", text)
        job = self.img.state["queue"][0]
        self.assertTrue(job["instrumental"])
        self.assertTrue(job["prompt"].endswith("instrumental, no vocals"))
        self.assertNotIn("female vocal", job["prompt"])
        self.assertTrue(all(ln.startswith("[") for ln in job["lyrics"].split("\n") if ln))
        self.assertEqual(self.app.engine.llm.calls, [])
        self.assertIn('"instrumental"', json.dumps(self.app.engine.schema))

    def test_two_misses_are_not_queued(self):
        ok, text = self.step("no sections", "still none")
        self.assertFalse(ok)
        self.assertIn("didn't fit", text)
        self.assertEqual(self.img.state["queue"], [])

    def test_his_cap_and_her_own_time_cap(self):
        day = time.strftime("%Y-%m-%d")
        self.img.state["songs_made"] = {day: {"asked": 10}}
        ok, text = self.step(GOOD)
        self.assertFalse(ok)
        self.assertIn("10 songs", text)
        self.app.engine._kind = "wake"
        ok, text = self.step(GOOD)
        self.assertTrue(ok, text)
        self.assertTrue(self.img.state["queue"][0]["own"])
        self.img.state["queue"] = []
        self.img.state["songs_made"] = {day: {"asked": 0, "own": 1}}
        ok, text = self.step(GOOD)
        self.assertFalse(ok)
        self.assertIn("own time", text)

    def test_out_of_memory_tries_the_next_length_down_once(self):
        self.img.state["queue"] = [{"id": "s1", "kind": "song", "length": "long", "tries": 1}]
        self.assertTrue(self.img._song_shorter(dict(self.img.state["queue"][0])))
        self.assertEqual(self.img.state["queue"][0]["length"], "medium")
        self.assertFalse(self.img._song_shorter(dict(self.img.state["queue"][0])))
        self.assertFalse(self.img._song_shorter({"id": "s2", "length": "short"}))

    def test_she_writes_it_it_renders_and_it_arrives(self):
        self.app.new_chat()
        ok, text = self.step(GOOD)
        self.assertTrue(ok, text)
        self.img.wake.set()
        for _ in range(300):
            if any(e.get("type") == "made_song" for e in self.events):
                break
            time.sleep(0.05)
        self.assertEqual(self.img.state["queue"], [])
        sent = [e for e in self.events if e.get("type") == "made_song"]
        self.assertEqual(len(sent), 1)
        self.assertTrue(sent[0]["audio"].endswith(".mp3"))
        ev = [e for e in self.app.engine.conv.events if e["kind"] == "made_song"][0]
        self.assertEqual((ev["title"], ev["caption"]), ("Glass Hours", "Something for your drive home."))
        self.assertTrue(os.path.isfile(ev["audio"]))
        rec = songs.records()[-1]
        self.assertEqual((rec["title"], rec["length"], rec["lyrics"]), ("Glass Hours", "medium", GOOD))
        self.assertEqual(self.fake.prompts[-1]["2"]["inputs"]["max_duration"], 210.0)
        made = self.img.state["songs_made"][time.strftime("%Y-%m-%d")]
        self.assertEqual(made, {"asked": 1})


if __name__ == "__main__":
    unittest.main()
