import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aether import imagine as im
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.proc import NO_WINDOW
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory
from aether.tests.test_proc import alive, wait_for


def tiny_png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (120, 60, 200)).save(buf, "PNG")
    return buf.getvalue()


class FakeComfy:

    def __init__(self, finish_after=1):
        self.prompts, self.calls, self.finish_after, self.polls, self.uploads = [], [], finish_after, 0, []
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
                fake.calls.append(self.path)
                if self.path == "/system_stats":
                    return self._json({"system": {}})
                m = re.match(r"/history/(\w+)", self.path)
                if m:
                    fake.polls += 1
                    if fake.polls < fake.finish_after:
                        return self._json({})
                    pid = m.group(1)
                    wf = fake.prompts[-1]
                    if "11" in wf:
                        f = lambda node, ext: {"filename": wf[node]["inputs"]["filename_prefix"] + "_00001_." + ext,  # noqa: E731
                                               "subfolder": "", "type": "output"}
                        outs = {"11": {"images": [f("11", "mp4")], "animated": [True]},
                                **{k: {"images": [f(k, "png")]} for k in ("30", "31", "32")}}
                    else:
                        outs = {"8": {"images": [{"filename": wf["8"]["inputs"]["filename_prefix"] + "_00001_.png",
                                                  "subfolder": "", "type": "output"}]}}
                    return self._json({pid: {"status": {"status_str": "success", "completed": True}, "outputs": outs}})
                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                fake.calls.append(self.path)
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path == "/upload/image":
                    fake.uploads.append(raw)
                    return self._json({"name": "start.png", "subfolder": "", "type": "input"})
                body = json.loads(raw or b"{}")
                if self.path == "/prompt":
                    wf = body["prompt"]
                    fake.prompts.append(wf)
                    os.makedirs(im.OUT_DIR, exist_ok=True)
                    outs = [("11", "mp4"), ("30", "png"), ("31", "png"), ("32", "png")] if "11" in wf else [("8", "png")]
                    for node, ext in outs:
                        with open(os.path.join(im.OUT_DIR, wf[node]["inputs"]["filename_prefix"] + "_00001_." + ext), "wb") as f:
                            f.write(b"not really a video" if ext == "mp4" else tiny_png())
                    return self._json({"prompt_id": "p1"})
                return self._json({})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


STEP = {"step": "make_image", "prompt": "Anime illustration of an adult woman with white hair and ram horns, violet sky",
        "shape": "portrait", "caption": "Me, on a good night"}


class ImagineTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeComfy()
        self.cfg = make_config(make_memory(), image_pause_for=[], comfy_port=self.fake.port)
        self.httpd, self.app = make_server(self.cfg, ScriptedLLM([]), port=0)
        self.img = self.app.imagine
        self.img.state = {"queue": [], "made": {}}
        self.img._save()
        self.events = []
        self.app.broadcast = self.events.append

    def tearDown(self):
        with self.img.lock:
            self.img.state = {"queue": [], "made": {}}
            self.img._save()
        self.httpd.server_close()
        self.fake.close()

    def wait(self, cond, what):
        for _ in range(200):
            if cond():
                return
            time.sleep(0.05)
        self.fail(what)

    def test_recipe_is_the_template(self):
        wf = im.workflow("a castle", "landscape", 7, 25)
        self.assertEqual(wf["4"]["class_type"], "TextEncodeQwenImage21")
        self.assertEqual(wf["4"]["inputs"]["prompt"], "a castle")
        self.assertEqual((wf["5"]["inputs"]["width"], wf["5"]["inputs"]["height"]), (1152, 896))
        self.assertEqual(wf["1"]["inputs"]["unet_name"], "qwen_image_2.1_int8_convrot.safetensors")
        self.assertEqual(wf["6"]["inputs"]["cfg"], 1.0)

    def test_adults_only(self):
        for bad in ("a teenage girl on a beach", "a 16-year-old in a dress", "cute loli with horns", "a schoolgirl uniform portrait"):
            ok, text = self.img.run_step(dict(STEP, prompt=bad + ", detailed anime art"))
            self.assertFalse(ok, bad)
            self.assertIn("adults only", text)
        ok, _ = self.img.run_step(dict(STEP, prompt="a 25-year-old young woman with horns, anime art"))
        self.assertTrue(ok)
        self.assertEqual(len(self.img.state["queue"]), 1)

    def test_limits(self):
        self.assertFalse(self.img.run_step(dict(STEP, prompt="cat"))[0])
        self.img.wake = threading.Event()
        self.cfg.comfy_port = 9
        for _ in range(3):
            self.assertTrue(self.img.run_step(STEP)[0])
        ok, text = self.img.run_step(STEP)
        self.assertFalse(ok)
        self.assertIn("already waiting", text)
        self.img.state = {"queue": [], "made": {im.dt.date.today().isoformat(): self.cfg.image_daily_cap}}
        ok, text = self.img.run_step(STEP)
        self.assertFalse(ok)
        self.assertIn("limit", text)

    def test_step_is_on_her_menu_and_can_be_switched_off(self):
        self.assertIn("make_image", json.dumps(self.app.engine.schema))
        self.cfg.images_enabled = False
        self.app.engine.refresh()
        self.assertNotIn("make_image", json.dumps(self.app.engine.schema))

    def test_she_asks_it_draws_it_arrives_and_she_sees_it(self):
        chat = self.app.new_chat()
        self.app.engine.llm = ScriptedLLM([STEP, {"step": "reply"}, {"say": "It's on its way!"},
                                           {"step": "reply"}, {"verdict": "keep", "say": "Okay, I made you something. The wings!", "new_prompt": ""}])
        self.app.engine.turn("draw me something", place="Aether app")
        conv = self.app.engine.conv
        self.assertEqual(conv.id, chat)
        res = next(e for e in conv.events if e["kind"] == "result" and e.get("of") == "make_image")
        self.assertTrue(res["ok"])
        self.wait(lambda: any(e["kind"] == "made_image" for e in Conversation(self.app.conv_dir, chat).events), "never delivered")
        self.assertEqual(self.fake.prompts[0]["4"]["inputs"]["prompt"], STEP["prompt"])
        self.assertIn("/free", self.fake.calls)
        made = next(e for e in Conversation(self.app.conv_dir, chat).events if e["kind"] == "made_image")
        self.assertTrue(os.path.isfile(made["images"][0]))
        self.assertEqual(made["caption"], "Okay, I made you something. The wings!")
        self.assertEqual(made["title"], "Me, on a good night")
        look = self.app.engine.llm.calls[-1]["messages"]
        self.assertTrue(any(isinstance(m["content"], list) and any(p["type"] == "image_url" for p in m["content"]) for m in look))
        self.assertIn("draw me something", json.dumps(look))
        self.assertEqual(self.app.engine.conv.id, chat)
        self.assertEqual(self.img.state["queue"], [])
        self.assertEqual(self.img.made_today(), 1)
        self.assertTrue(any(e.get("type") == "made_image" for e in self.events))
        self.assertTrue(self.app.meta[chat]["unread"])
        c = Conversation(self.app.conv_dir, chat)
        c.add("user", text="ok that's sick", context="")
        msgs = c.to_messages(20000)
        seen = [m for m in msgs if isinstance(m["content"], list)]
        self.assertTrue(seen)
        self.assertTrue(any(p["type"] == "image_url" for p in seen[-1]["content"]))
        self.assertIn("picture you made", json.dumps(msgs))

    def test_her_own_picture_comes_with_why_she_made_it(self):
        self.assertIn('"why"', json.dumps(self.img.option()))
        folder = os.path.join(im.ATTACH_DIR, "w")
        os.makedirs(folder, exist_ok=True)
        src = os.path.join(folder, "w1.png")
        with open(src, "wb") as f:
            f.write(tiny_png())
        job = {"id": "w1", "chat": "heartbeat", "prompt": "rain on black stone under neon streetlights", "shape": "square",
               "caption": "Neon rain", "why": "I kept thinking about how rain looks on black stone at night",
               "asked": "2026-10-02T15:00:00"}
        self.img._asked_by = lambda job: None
        self.app.engine.llm = ScriptedLLM([{"step": "reply"}, {"verdict": "keep", "new_prompt": "",
                                           "say": "I couldn't stop thinking about rain on black stone. It came out moody."}])
        self.assertEqual(self.img.review(job, src)[0], "keep")
        look = json.dumps(self.app.engine.llm.calls[-1]["messages"])
        self.assertIn("because: \\\"I kept thinking about how rain looks", look)
        self.assertIn("starts with what made you want to make it", look)
        self.img.state["gallery"] = [{"id": "w1", "chat": "heartbeat", "image": "w/w1.png", "title": "Neon rain",
                                      "caption": "moody", "prompt": job["prompt"], "shape": "square", "why": job["why"],
                                      "made": "2026-10-02T15:05:00"}]
        self.assertIn("why you made it: \"I kept thinking", self.img.gallery_step({"step": "gallery", "show": 0})[1])

    def test_she_can_look_through_her_gallery(self):
        chat = self.app.new_chat()
        folder = os.path.join(im.ATTACH_DIR, chat)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "old.png"), "wb") as f:
            f.write(tiny_png())
        self.img.state["gallery"] = [{"id": "a1", "chat": chat, "image": f"{chat}/old.png", "title": "Floating ruins",
                                      "caption": "I love how the sky came out", "prompt": "ruins at dusk, violet sky",
                                      "shape": "square", "made": "2026-09-26T19:10:00"}]
        self.assertIn('"gallery"', json.dumps(self.app.engine.schema))
        self.app.engine.llm = ScriptedLLM([{"step": "gallery", "show": 0}, {"step": "gallery", "show": 1},
                                           {"step": "reply"}, {"say": "Oh, the ruins one. Still my favorite."}])
        self.app.engine.turn("which picture of yours do you like best?", place="Aether app")
        calls = self.app.engine.llm.calls
        self.assertIn("Floating ruins", json.dumps(calls[1]["messages"]))
        saw = lambda msgs: any(isinstance(m["content"], list) and any(p["type"] == "image_url" for p in m["content"])  # noqa: E731
                               for m in msgs)
        self.assertFalse(saw(calls[1]["messages"]))
        self.assertTrue(saw(calls[2]["messages"]))
        self.assertTrue(saw(calls[3]["messages"]))
        c = Conversation(self.app.conv_dir, chat)
        c.add("user", text="nice", context="")
        self.assertFalse(saw(c.to_messages(20000)))
        ok, text = self.img.gallery_step({"step": "gallery", "show": 5})
        self.assertFalse(ok)

    def test_she_redoes_it_once(self):
        self.app.new_chat()
        new = "Anime illustration of an adult woman with long white hair and curled black ram horns with gold tips"
        self.app.engine.llm = ScriptedLLM([STEP, {"step": "reply"}, {"say": "Coming up."},
                                           {"step": "reply"}, {"verdict": "redo", "say": "The horns came out wrong.", "new_prompt": new},
                                           {"step": "reply"}, {"verdict": "keep", "say": "Better. Horns fixed.", "new_prompt": ""}])
        self.app.engine.turn("draw yourself", place="Aether app")
        chat = self.app.engine.conv.id
        self.wait(lambda: any(e["kind"] == "made_image" for e in Conversation(self.app.conv_dir, chat).events), "never delivered")
        self.assertEqual([p["4"]["inputs"]["prompt"] for p in self.fake.prompts], [STEP["prompt"], new])
        made = next(e for e in Conversation(self.app.conv_dir, chat).events if e["kind"] == "made_image")
        self.assertEqual(made["caption"], "Better. Horns fixed.")
        self.assertEqual(made["redone"], "The horns came out wrong.")
        second = self.app.engine.llm.calls[-1]["schema"]
        self.assertEqual(second["properties"]["verdict"]["enum"], ["keep"])

    def test_if_she_cant_look_it_keeps_her_planned_caption(self):
        self.app.new_chat()
        self.app.engine.llm = ScriptedLLM([STEP, {"step": "reply"}, {"say": "On its way."}])
        self.app.engine.turn("draw me something", place="Aether app")
        chat = self.app.engine.conv.id
        self.wait(lambda: any(e["kind"] == "made_image" for e in Conversation(self.app.conv_dir, chat).events), "never delivered")
        made = next(e for e in Conversation(self.app.conv_dir, chat).events if e["kind"] == "made_image")
        self.assertEqual(made["caption"], STEP["caption"])
        self.assertFalse(self.app.engine.busy)

    def test_a_game_starting_pauses_the_picture(self):
        self.fake.finish_after = 10 ** 6
        self.img.wake = threading.Event()
        self.assertTrue(self.img.run_step(STEP)[0])
        job = dict(self.img.state["queue"][0])
        calls = {"n": 0}

        def gaming():
            calls["n"] += 1
            return calls["n"] > 1
        self.img.gaming = gaming
        self.img.draw(job)
        self.assertIn("/interrupt", self.fake.calls)
        self.assertEqual(len(self.img.state["queue"]), 1)
        self.assertIn("gaming", self.img.status)

    VSTEP = {"step": "make_video", "prompt": "The dungeon gate slowly creaks open, blue mist rolls out, camera pushes in",
             "from_picture": 1, "caption": "The gate, opening"}

    def seed_gallery(self, chat):
        folder = os.path.join(im.ATTACH_DIR, chat)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "gate.png"), "wb") as f:
            f.write(tiny_png())
        self.img.state["gallery"] = [{"id": "g1", "chat": chat, "image": f"{chat}/gate.png", "title": "The gate",
                                      "caption": "creepy", "prompt": "a dungeon gate", "shape": "square", "made": "2026-09-27T03:07:00"}]

    def test_video_recipe_is_the_template_with_a_tiled_decode(self):
        wf = im.video_workflow("a gate opening", 7, self.cfg, start_image="start.png")
        types = {v["class_type"] for v in wf.values()}
        self.assertTrue({"Wan22ImageToVideoLatent", "ModelSamplingSD3", "VAEDecodeTiled", "CreateVideo", "SaveVideo",
                         "LoadImage"} <= types)
        self.assertNotIn("VAEDecode", types)
        self.assertEqual(wf["1"]["inputs"]["unet_name"], "wan2.2_ti2v_5B_fp16.safetensors")
        self.assertEqual(wf["2"]["inputs"]["type"], "wan")
        self.assertEqual((wf["7"]["inputs"]["width"], wf["7"]["inputs"]["height"], wf["7"]["inputs"]["length"]), (832, 480, 49))
        self.assertEqual(wf["7"]["inputs"]["start_image"], ["12", 0])
        self.assertEqual(wf["9"]["inputs"]["tile_size"], 256)
        self.assertEqual((wf["8"]["inputs"]["sampler_name"], wf["8"]["inputs"]["cfg"], wf["6"]["inputs"]["shift"]), ("uni_pc", 5.0, 8.0))
        self.assertEqual([wf[k]["inputs"]["batch_index"] for k in ("20", "21", "22")], [0, 24, -1])
        self.assertNotIn("start_image", im.video_workflow("a gate", 7, self.cfg)["7"]["inputs"])

    def test_videos_are_dormant_until_switched_on(self):
        self.assertNotIn("make_video", json.dumps(self.app.engine.schema))
        self.assertNotIn("make_video", self.app.engine.system)
        self.assertFalse(self.img.video_step(self.VSTEP)[0])
        self.cfg.videos_enabled = True
        self.app.engine.refresh()
        self.assertIn("make_video", json.dumps(self.app.engine.schema))
        self.assertIn("make_video", self.app.engine.system)

    def test_a_video_only_when_he_asks(self):
        self.cfg.videos_enabled = True
        self.img.wake = threading.Event()
        self.app.engine._kind = "wake"
        ok, text = self.img.video_step(dict(self.VSTEP, from_picture=0))
        self.assertFalse(ok)
        self.assertIn("only for when {USER} asks", text)
        self.app.engine._kind = "user"
        self.assertTrue(self.img.video_step(dict(self.VSTEP, from_picture=0))[0])
        ok, text = self.img.video_step(dict(self.VSTEP, from_picture=0))
        self.assertFalse(ok)
        self.assertIn("already being made", text)
        self.img.state = {"queue": [], "made": {}, "videos_made": {im.dt.date.today().isoformat(): self.cfg.video_daily_cap}}
        ok, text = self.img.video_step(dict(self.VSTEP, from_picture=0))
        self.assertFalse(ok)
        self.assertIn("limit", text)
        self.assertFalse(self.img.video_step(dict(self.VSTEP, prompt="a 15-year-old dancing in the rain, cinematic"))[0])
        self.assertFalse(self.img.video_step(dict(self.VSTEP, from_picture=9))[0])

    def test_he_asks_for_a_video_it_arrives_and_she_saw_its_frames(self):
        self.cfg.videos_enabled = True
        chat = self.app.new_chat()
        self.seed_gallery(chat)
        self.app.engine.refresh()
        self.app.engine.llm = ScriptedLLM([self.VSTEP, {"step": "reply"}, {"say": "On it. Give it a few minutes."},
                                           {"step": "reply"}, {"verdict": "keep", "say": "The mist actually moves!", "new_prompt": ""}])
        self.app.engine.turn("make that gate picture into a video", place="Aether app")
        self.wait(lambda: any(e["kind"] == "made_video" for e in Conversation(self.app.conv_dir, chat).events), "never delivered")
        self.assertEqual(len(self.fake.uploads), 1)
        wf = self.fake.prompts[0]
        self.assertEqual(wf["12"]["inputs"]["image"], "start.png")
        self.assertEqual(wf["4"]["inputs"]["text"], self.VSTEP["prompt"])
        made = next(e for e in Conversation(self.app.conv_dir, chat).events if e["kind"] == "made_video")
        self.assertTrue(made["video"].endswith(".mp4") and os.path.isfile(made["video"]))
        self.assertTrue(os.path.isfile(made["images"][0]))
        self.assertEqual(made["caption"], "The mist actually moves!")
        look = self.app.engine.llm.calls[-1]["messages"]
        pics = [p for m in look if isinstance(m["content"], list) for p in m["content"] if p["type"] == "image_url"]
        self.assertEqual(len(pics), 3)
        self.assertEqual(self.app.engine.llm.calls[-1]["schema"]["properties"]["verdict"]["enum"], ["keep"])
        self.assertEqual(self.img.videos_today(), 1)
        self.assertEqual(self.img.made_today(), 0)
        g = self.img.gallery()[0]
        self.assertEqual((g["kind"], g["video"].endswith(".mp4")), ("video", True))
        self.assertTrue(any(e.get("type") == "made_video" for e in self.events))
        self.assertIn("(video)", self.img.gallery_step({"step": "gallery", "show": 0})[1])
        c = Conversation(self.app.conv_dir, chat)
        c.add("user", text="dude", context="")
        self.assertIn("video you made", json.dumps(c.to_messages(20000)))

    def test_cancel(self):
        self.img.wake = threading.Event()
        self.cfg.comfy_port = 9
        self.img.run_step(STEP)
        jid = self.img.state["queue"][0]["id"]
        self.img.cancel(jid)
        self.assertEqual(self.img.state["queue"], [])
        with self.assertRaises(ValueError):
            self.img.cancel("nope")


OUT = r"C:\Users\you\.aether\comfy-output"


def comfy(pid, ppid, created, port=8189, out=OUT):
    where = f'"{out}"' if " " in out else out
    return {"pid": pid, "ppid": ppid, "created": created, "name": "python.exe",
            "cmd": rf'"C:\Comfy\ComfyUI\.venv\Scripts\python.exe" -s C:\Comfy\ComfyUI\main.py --listen 127.0.0.1 '
                   rf'--port {port} --disable-auto-launch --output-directory {where}'}


def other(pid, created, name="explorer.exe"):
    return {"pid": pid, "ppid": 4, "created": created, "name": name, "cmd": None}


class LeftoverComfyTests(unittest.TestCase):

    def test_the_2026_09_28_leftover(self):
        procs = [other(7, 1), comfy(100, 50, 20), comfy(101, 100, 21)]
        self.assertEqual(im.leftover_comfy(procs, 8189, OUT), [100])

    def test_a_comfyui_whose_aether_is_running_is_left_alone(self):
        procs = [other(50, 10, "pythonw.exe"), comfy(100, 50, 20), comfy(101, 100, 21)]
        self.assertEqual(im.leftover_comfy(procs, 8189, OUT), [])

    def test_a_reused_pid_isnt_its_aether(self):
        procs = [other(50, 30), comfy(100, 50, 20), comfy(101, 100, 21)]
        self.assertEqual(im.leftover_comfy(procs, 8189, OUT), [100])

    def test_a_lone_real_python_whose_launcher_is_gone(self):
        self.assertEqual(im.leftover_comfy([comfy(101, 100, 21)], 8189, OUT), [101])

    def test_jordans_own_comfyui_and_near_misses_are_never_touched(self):
        procs = [comfy(200, 60, 20, port=8000, out=r"D:\ComfyUI\output"),
                 comfy(201, 60, 20, port=8000),
                 comfy(202, 60, 20, out=r"D:\ComfyUI\output"),
                 comfy(203, 60, 20, port=81890),
                 comfy(204, 60, 20, out=OUT + "2"),
                 other(205, 20, "python.exe")]
        self.assertEqual(im.leftover_comfy(procs, 8189, OUT), [])

    def test_a_folder_with_spaces_and_other_letter_case(self):
        out = r"C:\Users\Some One\.aether\comfy-output"
        self.assertEqual(im.leftover_comfy([comfy(100, 50, 20, out=out.upper())], 8189, out), [100])

    @unittest.skipUnless(os.name == "nt", "Windows programs")
    def test_a_real_leftover_is_stopped_and_a_live_one_is_not(self):
        port =random.randrange(50000, 60000)
        out = os.path.join(tempfile.mkdtemp(prefix="aether-leftover-"), "comfy-output")
        args = [sys.executable, "-c", "import time; time.sleep(120)", "--port", str(port), "--output-directory", out]
        starter = subprocess.run([sys.executable, "-c", "import subprocess as s, sys; print(s.Popen(sys.argv[1:], "
                                  "stdin=s.DEVNULL, stdout=s.DEVNULL, stderr=s.DEVNULL, creationflags=0x08000000).pid)",
                                  *args], capture_output=True, text=True, timeout=30)
        leftover = int(starter.stdout)
        live = subprocess.Popen(args, creationflags=NO_WINDOW)
        try:
            self.assertEqual(im.clear_leftover_comfy(port, out), [leftover])
            self.assertTrue(wait_for(lambda: not alive(leftover), 10))
            self.assertIsNone(live.poll())
        finally:
            live.kill()
            live.wait(10)
            if alive(leftover):
                subprocess.run(["taskkill", "/PID", str(leftover), "/F"], capture_output=True, creationflags=NO_WINDOW)


if __name__ == "__main__":
    unittest.main()
