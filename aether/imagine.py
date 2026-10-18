import atexit
import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid

from . import songs as songs_mod
from .config import DATA_DIR
from .engine import log
from .proc import NO_WINDOW, end_tied, processes, spawn_tied
from .names import USER

STATE_FILE = os.path.join(DATA_DIR, "images.json")
OUT_DIR = os.path.join(DATA_DIR, "comfy-output")
COMFY_LOG = os.path.join(DATA_DIR, "logs", "comfyui.log")
ATTACH_DIR = os.path.join(DATA_DIR, "attachments")
SHAPES = {"square": (1024, 1024), "portrait": (896, 1152), "landscape": (1152, 896)}
MODEL = {"unet": "qwen_image_2.1_int8_convrot.safetensors", "clip": "qwen3vl_8b_int8_convrot.safetensors",
         "vae": "qwen_image_2.1_vae_bf16.safetensors"}
QUEUE_MAX = 3
REVIEW_WAIT = 10 * 60
STUDIO_DIR = os.path.join(DATA_DIR, "studio")
MAX_TRIES = 3
DRAW_TIMEOUT = 30 * 60
VIDEO_MODEL = {"unet": "wan2.2_ti2v_5B_fp16.safetensors", "clip": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
               "vae": "wan2.2_vae.safetensors"}
VIDEO_TIMEOUT = 120 * 60
VIDEO_NEGATIVE = ("色调艳丽，过曝，静态，细节模糊不清"
                  "，字幕，风格，作品，画作，画面，静止"
                  "，整体发灰，最差质量，低质量，JPEG压缩"
                  "残留，丑陋的，残缺的，多余的手指，画"
                  "得不好的手部，画得不好的脸部，畸形的"
                  "，毁容的，形态畸形的肢体，手指融合，"
                  "静止不动的画面，杂乱的背景，三条腿，"
                  "背景人很多，倒着走")
NOT_ADULT = re.compile(
    r"\b(child|children|childlike|kid|kids|kiddo|minor|minors|underage|under-age|teen|teens|teenage|teenager|"
    r"preteen|pre-teen|tween|loli|lolis|lolicon|shota|shotacon|toddler|infant|baby girl|baby boy|schoolgirl|"
    r"schoolboy|school girl|school boy|little girl|little boy|young girl|young boy|elementary school|middle school|"
    r"(?:[1-9]|1[0-7])[- ]?(?:years?|yrs?)[- ]?old)\b", re.I)


def workflow(prompt, shape, seed, steps, prefix="aether"):
    w, h = SHAPES[shape]
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": MODEL["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": MODEL["clip"], "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": MODEL["vae"]}},
        "4": {"class_type": "TextEncodeQwenImage21",
              "inputs": {"clip": ["2", 0], "prompt": prompt, "negative_prompt": "", "resolution": 1024}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["4", 0], "negative": ["4", 1],
                                                   "latent_image": ["5", 0], "seed": seed, "steps": steps, "cfg": 1.0,
                                                   "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}},
    }


def video_workflow(prompt, seed, cfg, start_image=None, prefix="aether-video"):
    n = max(1, int(cfg.video_length))
    latent = {"vae": ["3", 0], "width": int(cfg.video_width), "height": int(cfg.video_height), "length": n, "batch_size": 1}
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": VIDEO_MODEL["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": VIDEO_MODEL["clip"], "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VIDEO_MODEL["vae"]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": VIDEO_NEGATIVE}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": latent},
        "8": {"class_type": "KSampler", "inputs": {"model": ["6", 0], "positive": ["4", 0], "negative": ["5", 0],
                                                   "latent_image": ["7", 0], "seed": seed, "steps": int(cfg.video_steps),
                                                   "cfg": 5.0, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["8", 0], "vae": ["3", 0], "tile_size": 256,
                                                         "overlap": 64, "temporal_size": 32, "temporal_overlap": 8}},
        "10": {"class_type": "CreateVideo", "inputs": {"images": ["9", 0], "fps": float(cfg.video_fps)}},
        "11": {"class_type": "SaveVideo", "inputs": {"video": ["10", 0], "filename_prefix": prefix, "format": "mp4"}},
    }
    for i, at in enumerate((0, n // 2, -1)):
        wf[f"2{i}"] = {"class_type": "ImageFromBatch", "inputs": {"image": ["9", 0], "batch_index": at, "length": 1}}
        wf[f"3{i}"] = {"class_type": "SaveImage", "inputs": {"images": [f"2{i}", 0], "filename_prefix": f"{prefix}-still{i}"}}
    if start_image:
        wf["12"] = {"class_type": "LoadImage", "inputs": {"image": start_image}}
        latent["start_image"] = ["12", 0]
    return wf


def find_comfy(cfg):
    appdata = os.environ.get("APPDATA", "")
    places = []
    if cfg.comfy_dir:
        places.append((cfg.comfy_dir, None))
    try:
        with open(os.path.join(appdata, "Comfy Desktop", "installations.json"), encoding="utf-8") as f:
            for inst in json.load(f):
                if inst.get("sourceId") != "cloud" and inst.get("installPath"):
                    places.append((inst["installPath"], inst.get("id")))
    except (OSError, ValueError, TypeError):
        pass
    for path, iid in places:
        code = os.path.join(path, "ComfyUI")
        py = os.path.join(code, ".venv", "Scripts", "python.exe")
        if os.path.isfile(py) and os.path.isfile(os.path.join(code, "main.py")):
            yml = os.path.join(appdata, "Comfy Desktop", "instance-model-paths", f"{iid}.yaml") if iid else ""
            return py, code, (yml if yml and os.path.isfile(yml) else None)
    return None


def leftover_comfy(procs, port, out_dir=None):
    out_dir = os.path.normcase(os.path.abspath(out_dir or OUT_DIR))
    port_at = re.compile(rf'--port[\s=]+"?{int(port)}(?!\d)')
    dir_at = re.compile(r'--output-directory[\s=]+"?' + re.escape(out_dir) + r'\\?(?=["\s]|$)')
    ours = {}
    for p in procs:
        cmd = os.path.normcase(p.get("cmd") or "")
        if port_at.search(cmd) and dir_at.search(cmd):
            ours[p["pid"]] = p
    started = {p["pid"]: p.get("created") or 0 for p in procs}
    tops = []
    for pid, p in ours.items():
        parent = p.get("ppid")
        if parent in ours:
            continue
        if parent in started and started[parent] <= (p.get("created") or 0):
            continue
        tops.append(pid)
    return sorted(tops)


def clear_leftover_comfy(port, out_dir=None):
    tops = leftover_comfy(processes(), port, out_dir)
    for pid in tops:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30, creationflags=NO_WINDOW)
    return tops


class Imagine:
    def __init__(self, app, start=True):
        self.app, self.cfg = app, app.cfg
        self.lock = threading.Lock()
        self.state = self._load()
        self.proc = None
        self.proc_lock = threading.Lock()
        self.status = ""
        self.last_work = time.time()
        self._games = (0.0, False)
        self.wake = threading.Event()
        atexit.register(self.stop_comfy)
        if start:
            threading.Thread(target=self._loop, daemon=True, name="imagine").start()

    def _load(self):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                s = json.load(f)
            if isinstance(s, dict) and isinstance(s.get("queue"), list):
                s.setdefault("made", {})
                s.setdefault("gallery", [])
                return s
        except (OSError, ValueError):
            pass
        return {"queue": [], "made": {}, "gallery": []}

    def _save(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=1)
        os.replace(tmp, STATE_FILE)

    def made_today(self):
        return int(self.state["made"].get(dt.date.today().isoformat(), 0))

    def info(self):
        with self.lock:
            q = list(self.state["queue"])
        return {"waiting": len(q), "status": self.status, "made_today": self.made_today(),
                "cap": self.cfg.image_daily_cap, "videos_today": self.videos_today(), "video_cap": self.cfg.video_daily_cap,
                "queue": [{"id": j["id"], "caption": j["caption"], "asked": j["asked"], "kind": j.get("kind", "picture")}
                          for j in q]}

    def gallery(self):
        with self.lock:
            return list(reversed(self.state.get("gallery") or []))

    def cancel(self, job_id):
        with self.lock:
            q = self.state["queue"]
            keep = [j for j in q if j["id"] != job_id]
            if len(keep) == len(q):
                raise ValueError("no such picture waiting")
            drawing = bool(q) and q[0]["id"] == job_id and self.status == "drawing"
            self.state["queue"] = keep
            self._save()
        if drawing:
            self._post("/interrupt", {})
        return True

    def option(self):
        if not self.cfg.images_enabled:
            return None
        return {"type": "object", "properties": {"step": {"const": "make_image"}, "why": {"type": "string", "maxLength": 200},
                                                 "prompt": {"type": "string"}, "shape": {"enum": list(SHAPES)},
                                                 "caption": {"type": "string"}},
                "required": ["step", "why", "prompt", "shape", "caption"], "additionalProperties": False}

    def run_step(self, step):
        if not self.cfg.images_enabled:
            return False, "Pictures are turned off in Settings."
        prompt = " ".join(str(step.get("prompt") or "").split())[:1500]
        caption = " ".join(str(step.get("caption") or "").split())[:200]
        why = " ".join(str(step.get("why") or "").split())[:200]
        shape = step.get("shape") if step.get("shape") in SHAPES else "square"
        if len(prompt) < 12:
            return False, "That prompt is too short: describe what to show and the style."
        if NOT_ADULT.search(prompt + " " + caption):
            return False, ("Not drawn: adults only. Nothing that reads as a child or a teenager, ever. "
                           "Tell {USER} you won't draw that.")
        conv = self.app.engine.conv
        with self.lock:
            q = self.state["queue"]
            if len(q) >= QUEUE_MAX:
                return False, f"{len(q)} pictures are already waiting. Let those finish first."
            if self.made_today() + sum(j.get("kind") not in ("video", "song") for j in q) >= self.cfg.image_daily_cap:
                return False, f"That's today's limit ({self.cfg.image_daily_cap} pictures). Tell {USER}; tomorrow you can again."
            q.append({"id": uuid.uuid4().hex[:8], "chat": conv.id, "prompt": prompt, "shape": shape, "caption": caption,
                      "why": why, "asked": dt.datetime.now().isoformat(timespec="seconds"), "seed": random.randrange(2 ** 48),
                      "tries": 0})
            self._save()
            n = len(q)
        self.wake.set()
        when = ("{USER} is gaming right now, so it waits until he's done" if self.gaming()
                else "about 3 minutes" + (f", after the {n - 1} before it" if n > 1 else ""))
        return True, (f"Queued. Aether is drawing it in the background ({when}) and will put it in this chat with "
                      "your caption. You haven't seen it yet: just tell him it's on its way.")

    def videos_today(self):
        return int((self.state.get("videos_made") or {}).get(dt.date.today().isoformat(), 0))

    def video_option(self):
        if not self.cfg.videos_enabled:
            return None
        return {"type": "object", "properties": {"step": {"const": "make_video"}, "prompt": {"type": "string"},
                                                 "from_picture": {"type": "integer"}, "caption": {"type": "string"}},
                "required": ["step", "prompt", "from_picture", "caption"], "additionalProperties": False}

    def video_step(self, step):
        if not self.cfg.videos_enabled:
            return False, "Videos are turned off in Settings."
        if self.app.engine._kind != "user":
            return False, "Videos are only for when {USER} asks for one in his message, so not now. Don't retry."
        prompt = " ".join(str(step.get("prompt") or "").split())[:1500]
        caption = " ".join(str(step.get("caption") or "").split())[:200]
        if len(prompt) < 12:
            return False, "That prompt is too short: describe the scene, what moves, and how the camera moves."
        if NOT_ADULT.search(prompt + " " + caption):
            return False, "Not made: adults only. Nothing that reads as a child or a teenager, ever. Tell {USER} you won't make that."
        start = None
        try:
            pic = int(step.get("from_picture") or 0)
        except (TypeError, ValueError):
            pic = 0
        if pic > 0:
            items = self.gallery()
            if pic > len(items):
                return False, f"There's no picture {pic} in your gallery; you have {len(items)}. Use 0 to start from nothing."
            start = os.path.join(ATTACH_DIR, *items[pic - 1]["image"].split("/"))
            if not os.path.isfile(start):
                return False, f"Picture {pic} is missing from disk. Use 0 to start from nothing."
        with self.lock:
            q = self.state["queue"]
            if any(j.get("kind") == "video" for j in q):
                return False, "A video is already being made. One at a time: tell {USER} this one waits."
            if len(q) >= QUEUE_MAX:
                return False, f"{len(q)} things are already waiting to be made. Let those finish first."
            if self.videos_today() >= self.cfg.video_daily_cap:
                return False, f"That's today's limit ({self.cfg.video_daily_cap} videos). Tell {USER}; tomorrow you can again."
            q.append({"id": uuid.uuid4().hex[:8], "kind": "video", "chat": self.app.engine.conv.id, "prompt": prompt,
                      "shape": "video", "caption": caption, "from_image": start,
                      "asked": dt.datetime.now().isoformat(timespec="seconds"), "seed": random.randrange(2 ** 48), "tries": 0})
            self._save()
        self.wake.set()
        when = "{USER} is gaming right now, so it waits until he's done" if self.gaming() else "a video takes a while, about 10 minutes or more"
        return True, (f"Queued. Aether is making the video in the background ({when}) and will put it in this chat with "
                      "your caption. You haven't seen it yet: just tell him it's on its way.")

    def songs_today(self, own):
        made = (self.state.get("songs_made") or {}).get(dt.date.today().isoformat(), {})
        key = "own" if own else "asked"
        with self.lock:
            queued = sum(1 for j in self.state["queue"] if j.get("kind") == "song" and bool(j.get("own")) == own)
        return int(made.get(key, 0)) + queued

    def song_option(self):
        return songs_mod.option(self.cfg)

    def song_step(self, step):
        if not getattr(self.cfg, "songs_enabled", True):
            return False, "Songs are turned off in Settings."
        own = self.app.engine._kind != "user"
        cap = self.cfg.song_own_daily_cap if own else self.cfg.song_daily_cap
        if self.songs_today(own) >= cap:
            return False, (f"That's today's limit ({cap} song{'s' if cap != 1 else ''}"
                           + (" on your own time" if own else "") + "). Tomorrow you can again.")
        title = " ".join(str(step.get("title") or "").split())[:80]
        caption = " ".join(str(step.get("caption") or "").split())[:300]
        length = step.get("length") if step.get("length") in songs_mod.LENGTHS else "medium"
        instrumental = step.get("instrumental") is True
        style = songs_mod.style_line(step.get("style"), instrumental)
        fixed = songs_mod.INSTRUMENTAL_TAGS if instrumental else songs_mod.VOICE_TAG
        if len(title) < 2 or len(style) < len(fixed) + 8:
            return False, ("Give the piece a title and a style of your own (instruments, mood, tempo)." if instrumental else
                           "Give the song a title and a style of your own (genre, mood, tempo, how the voice sounds).")
        with self.lock:
            if any(j.get("kind") == "song" for j in self.state["queue"]):
                return False, "A song is already being made. One at a time: tell {USER} this one waits."
            if len(self.state["queue"]) >= QUEUE_MAX:
                return False, f"{len(self.state['queue'])} things are already waiting to be made. Let those finish first."
        if instrumental:
            lyrics = songs_mod.instrumental_lyrics(length)
        else:
            self.app.engine.hooks.on_status("writing the lyrics")
            lyrics, why = songs_mod.write_lyrics(self.app.engine, title, style, length, self.cfg.temperature_talk)
            if not lyrics:
                return False, f"Not queued: the lyrics didn't fit the length twice ({why}). Try again, or a shorter length."
        with self.lock:
            self.state["queue"].append({"id": uuid.uuid4().hex[:8], "kind": "song", "chat": self.app.engine.conv.id,
                                        "prompt": style, "title": title, "lyrics": lyrics, "length": length,
                                        "shape": "song", "caption": caption, "own": own,
                                        **({"instrumental": True} if instrumental else {}),
                                        "asked": dt.datetime.now().isoformat(timespec="seconds"),
                                        "seed": random.randrange(2 ** 48), "tries": 0})
            self._save()
        self.wake.set()
        when = "{USER} is gaming right now, so it waits until he's done" if self.gaming() else "a few minutes"
        made = "an instrumental, no singing" if instrumental else "lyrics written"
        return True, (f"Queued: \"{title}\", {made}. Aether is making it in the background ({when}) and "
                      "will put it in this chat with your caption. You haven't heard it: just tell him it's on its way.")

    def _upload(self, path):
        boundary = uuid.uuid4().hex
        with open(path, "rb") as f:
            data = f.read()
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{os.path.basename(path)}\"\r\n"
                "Content-Type: image/png\r\n\r\n").encode() + data + \
               (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
                f"--{boundary}--\r\n").encode()
        req = urllib.request.Request(self.base + "/upload/image", body,
                                     {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            got = json.loads(r.read() or b"{}")
        name = got.get("name")
        if not name:
            raise RuntimeError("ComfyUI didn't take the starting picture")
        return f"{got['subfolder']}/{name}" if got.get("subfolder") else name

    def gallery_option(self):
        if not (self.cfg.images_enabled or self.state.get("gallery")):
            return None
        return {"type": "object", "properties": {"step": {"const": "gallery"}, "show": {"type": "integer"}},
                "required": ["step", "show"], "additionalProperties": False}

    def gallery_step(self, step):
        items = self.gallery()
        if not items:
            return False, "You haven't made any pictures yet."
        try:
            n = int(step.get("show") or 0)
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            lines = [f"{i}. {g['made'][:16].replace('T', ' ')}{' · (video)' if g.get('kind') == 'video' else ''}"
                     f" · \"{g.get('title') or g.get('caption', '')}\""
                     + (f" · you said: \"{g['caption']}\"" if g.get("title") and g.get("caption") != g.get("title") else "")
                     + (f" · why you made it: \"{g['why']}\"" if g.get("why") else "")
                     + f" · prompt: {g['prompt'][:140]}" for i, g in enumerate(items[:30], 1)]
            more = f"\n({len(items) - 30} older ones not listed.)" if len(items) > 30 else ""
            return True, (f"Your gallery ({len(items)} pictures, newest first). To really see one, take this step "
                          "again with its number.\n" + "\n".join(lines) + more)
        if n > len(items):
            return False, f"There's no picture {n}; you have {len(items)}."
        g = items[n - 1]
        path = os.path.join(ATTACH_DIR, *g["image"].split("/"))
        if not os.path.isfile(path):
            return False, f"Picture {n} is missing from disk."
        what = f"Video {n} (you can't watch it; its first frame is attached below)" if g.get("kind") == "video" else \
            f"Picture {n}, attached below so you can see it"
        return True, (f"{what}: \"{g.get('title') or g.get('caption', '')}\", "
                      f"made {g['made'][:16].replace('T', ' ')}. What you said about it: \"{g.get('caption', '')}\". "
                      f"Your prompt: {g['prompt']}"), [path]

    def gaming(self):
        names = {str(n).lower() for n in self.cfg.image_pause_for}
        if not names:
            return False
        t, val = self._games
        if time.time() - t < 20:
            return val
        try:
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=20,
                                 creationflags=NO_WINDOW).stdout
            running = {line.split('","')[0].strip('"').lower() for line in out.splitlines() if line.strip()}
            val = bool(names & running)
        except Exception:
            val = False
        self._games = (time.time(), val)
        return val

    @property
    def base(self):
        return f"http://127.0.0.1:{self.cfg.comfy_port}"

    def _get(self, path, timeout=10):
        with urllib.request.urlopen(self.base + path, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")

    def _post(self, path, body, timeout=30):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"ComfyUI said {e.code}: {e.read()[:300].decode(errors='replace')}")
        except (urllib.error.URLError, OSError):
            return None

    def comfy_up(self):
        try:
            self._get("/system_stats", timeout=3)
            return True
        except Exception:
            return False

    def ensure_comfy(self):
        if self.comfy_up():
            return True
        if not self.cfg.comfy_launch:
            raise RuntimeError("ComfyUI isn't running (starting it is switched off)")
        found = find_comfy(self.cfg)
        if not found:
            raise RuntimeError("ComfyUI isn't installed (Comfy Desktop not found)")
        py, code, yml = found
        os.makedirs(OUT_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(COMFY_LOG), exist_ok=True)
        args = [py, "-s", os.path.join(code, "main.py"), "--listen", "127.0.0.1", "--port", str(self.cfg.comfy_port),
                "--disable-auto-launch", "--output-directory", OUT_DIR]
        if yml:
            args += ["--extra-model-paths-config", yml]
        self.status = "starting ComfyUI"
        with open(COMFY_LOG, "ab") as logf:
            self.proc = spawn_tied(args, cwd=code, stdout=logf, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        if not self.proc.job:
            log(f"imagine: ComfyUI isn't tied to Aether ({self.proc.tie_error}); only a normal quit stops it")
        for _ in range(180):
            if self.comfy_up():
                log("imagine: ComfyUI is up")
                return True
            if self.proc.poll() is not None:
                break
            time.sleep(1)
        self.stop_comfy()
        raise RuntimeError(f"ComfyUI didn't start (see {COMFY_LOG})")

    def stop_comfy(self):
        with self.proc_lock:
            p, self.proc = self.proc, None
        if p and end_tied(p):
            log("imagine: stopped ComfyUI")

    def _loop(self):
        if self.cfg.comfy_launch:
            try:
                gone = clear_leftover_comfy(self.cfg.comfy_port)
                if gone:
                    log(f"imagine: stopped a ComfyUI an earlier Aether left running (pid {', '.join(map(str, gone))})")
            except Exception as e:
                log(f"imagine: couldn't look for a leftover ComfyUI: {e!r}")
        while True:
            self.wake.wait(15)
            self.wake.clear()
            try:
                self.tick()
            except Exception as e:
                log(f"imagine: {e!r}")

    def tick(self):
        with self.lock:
            job = dict(self.state["queue"][0]) if self.state["queue"] else None
        if not job:
            self.status = ""
            if self.proc and time.time() - self.last_work > self.cfg.comfy_idle_minutes * 60:
                self.stop_comfy()
            return
        if self.gaming():
            self.status = "waiting: {USER} is gaming"
            return
        self.draw(job)

    def _fail(self, job, why):
        log(f"imagine: {job['id']} failed: {why}")
        with self.lock:
            q = self.state["queue"]
            live = next((j for j in q if j["id"] == job["id"]), None)
            if not live:
                return
            live["tries"] = live.get("tries", 0) + 1
            if live["tries"] < MAX_TRIES:
                self._save()
                return
            q.remove(live)
            self._save()
        what = {"video": "video", "song": "song"}.get(job.get("kind"), "picture")
        self.app.broadcast({"type": "note", "text": f"{self.cfg.display_name}'s {what} didn't work out: {why}"})

    @staticmethod
    def _out_path(f):
        return os.path.join(OUT_DIR, f.get("subfolder") or "", f["filename"])

    def draw(self, job):
        voice = getattr(self.app, "voice", None)
        aside = voice.step_aside() if voice else False
        try:
            return self._draw(job)
        finally:
            if aside:
                voice.step_back()

    def _draw(self, job):
        video, song = job.get("kind") == "video", job.get("kind") == "song"
        self.status = "making a video" if video else "making a song" if song else "drawing"
        self.last_work = time.time()
        try:
            self.ensure_comfy()
            if song:
                wf = songs_mod.music_workflow(job["prompt"], job["lyrics"], songs_mod.seconds_for(job["lyrics"], job["length"]),
                                              job["seed"], prefix=f"aether-song-{job['id']}")
            elif video:
                start = self._upload(job["from_image"]) if job.get("from_image") else None
                wf = video_workflow(job["prompt"], job["seed"], self.cfg, start, prefix=f"aether-video-{job['id']}")
            else:
                wf = workflow(job["prompt"], job["shape"], job["seed"], self.cfg.image_steps, prefix=f"aether-{job['id']}")
            r = self._post("/prompt", {"prompt": wf, "client_id": "aether"})
        except (RuntimeError, OSError) as e:
            return self._fail(job, str(e))
        if not r or not r.get("prompt_id"):
            return self._fail(job, f"ComfyUI didn't take the picture: {r}")
        pid = r["prompt_id"]
        t0 = time.time()
        while True:
            time.sleep(2)
            with self.lock:
                still = any(j["id"] == job["id"] for j in self.state["queue"])
            if not still:
                self._post("/interrupt", {})
                self.status = ""
                return
            if self.gaming():
                self._post("/interrupt", {})
                self.status = "waiting: {USER} is gaming"
                log(f"imagine: {job['id']} paused, {USER} is gaming")
                return
            if time.time() - t0 > (VIDEO_TIMEOUT if video else songs_mod.SONG_TIMEOUT if song else DRAW_TIMEOUT):
                self._post("/interrupt", {})
                return self._fail(job, "it took too long")
            try:
                hist = self._get(f"/history/{pid}")
            except Exception:
                if not self.comfy_up():
                    return self._fail(job, "ComfyUI stopped")
                continue
            h = hist.get(pid)
            if not h:
                continue
            st = h.get("status") or {}
            if st.get("status_str") == "error":
                msgs = [m[1].get("exception_message", "") for m in st.get("messages") or [] if m and m[0] == "execution_error"]
                why = (msgs[0] if msgs else "ComfyUI error")[:200]
                if song and re.search(r"out of memory|\bOOM\b|allocat", why, re.I) and self._song_shorter(job):
                    return
                return self._fail(job, why)
            outs = h.get("outputs") or {}
            where = self._out_path
            if song:
                aud = (outs.get("7") or {}).get("audio") or []
                if not aud:
                    if st.get("completed"):
                        return self._fail(job, "no song came out")
                    continue
                src, stills = where(aud[0]), []
                break
            if video:
                vid = (outs.get("11") or {}).get("images") or []
                if not vid:
                    if st.get("completed"):
                        return self._fail(job, "no video came out")
                    continue
                src = where(vid[0])
                stills = [where(outs[k]["images"][0]) for k in ("30", "31", "32") if (outs.get(k) or {}).get("images")]
                break
            files = [im for out in outs.values() for im in out.get("images") or []]
            if not files:
                if st.get("completed"):
                    return self._fail(job, "no picture came out")
                continue
            src, stills = where(files[0]), []
            break
        self._post("/free", {"unload_models": True, "free_memory": True})
        if getattr(self.app, "voice", None):
            self.app.voice.step_back()
        self.last_work = time.time()
        if not os.path.isfile(src):
            return self._fail(job, f"the {'video' if video else 'song' if song else 'picture'} file is missing")
        if song:
            return self._deliver_song(job, src)
        stills = [p for p in stills if os.path.isfile(p)]
        verdict = self.review(job, src, stills)
        if verdict[0] == "redo":
            return self._redo(job, verdict[1], verdict[2])
        self.deliver(job, src, verdict[1], stills)

    def _asked_by(self, job):
        from .life import HEARTBEAT_CHAT
        if job["chat"] == HEARTBEAT_CHAT:
            return ""
        try:
            conv = self.app.conv(job["chat"])
        except ValueError:
            return ""
        said = [e for e in conv.events if e["kind"] == "user" and e.get("ts", "") <= job["asked"]]
        return " ".join((said[-1].get("text") or "").split())[:300] if said else ""

    def review(self, job, src, stills=None):
        app = self.app
        planned = ("keep", job["caption"])
        video = job.get("kind") == "video"
        if not self.cfg.image_review or (video and not stills):
            return planned
        t0 = time.time()
        while app.engine.busy or not app.gpu.acquire(blocking=False):
            if time.time() - t0 > REVIEW_WAIT:
                log(f"imagine: {job['id']} not reviewed, she stayed busy")
                return planned
            time.sleep(2)
        from .history import Conversation
        conv = Conversation(STUDIO_DIR, f"studio-{job['id']}" + ("-redo" if job.get("redo_of") else ""))
        asked = self._asked_by(job)
        second = bool(job.get("redo_of")) or video
        if video:
            text = ("[Aether: the video you made is done. You can't watch video, so three frames from it are attached: "
                    "the start, the middle and the end. Look at them closely before anything else. This is private, just "
                    "you and your video; {USER} only sees what you put in \"say\", right above it.\n"
                    + (f"What {USER} said when you started it: \"{asked}\"\n" if asked else "")
                    + f"Your prompt: \"{job['prompt']}\"\nThe caption you planned: \"{job['caption']}\"\n"
                    "It goes to him now. In \"say\", give it to him in your own words, reacting to how it actually turned "
                    "out from what you can see (a sentence or two). Leave new_prompt empty.]")
        else:
            text = None
        text = text or ("[Aether: the picture you made is done. It's attached: look at it closely before anything else. "
                "This is private, just you and your picture; {USER} only sees what you put in \"say\", right above it.\n"
                + (f"What {USER} said when you started it: \"{asked}\"\n" if asked else "You made this one on your own"
                   + (f", because: \"{job['why']}\"" if job.get("why") else "") + ".\n")
                + f"Your prompt: \"{job['prompt']}\"\nThe caption you planned: \"{job['caption']}\"\n"
                + ("" if asked else "Since it's yours, \"say\" starts with what made you want to make it, in your own "
                   "words, like telling a friend, then how it turned out.\n")
                + ("This is your redo, so it goes to him now. In \"say\", give it to him in your own words, reacting to how it "
                   "actually turned out (a sentence or two). Leave new_prompt empty.]" if second else
                   "Decide:\n- keep: it's what you wanted, or close enough. In \"say\", give it to him in your own words, reacting "
                   "to how it actually turned out (a sentence or two). Leave new_prompt empty.\n"
                   "- redo: something important is clearly wrong (not just 'could be better'). In \"say\", one short line on "
                   "what's wrong; in new_prompt, a better prompt that fixes it. You get one redo. Adults only.]"))
        final = {"type": "object", "properties": {"verdict": {"enum": ["keep"] if second else ["keep", "redo"]},
                                                  "say": {"type": "string"}, "new_prompt": {"type": "string"}},
                 "required": ["verdict", "say", "new_prompt"], "additionalProperties": False}
        eng = app.engine
        keep_conv = eng.conv
        fin = {}
        try:
            eng.conv = conv
            app.speaking = False
            eng.busy = True
            self.status = "looking it over"
            eng.turn(text, place="her studio (private, {USER} isn't here)", kind="wake", final_schema=final,
                     tools=False, images=stills if video else [src])
            fin = eng.last_final or {}
        except Exception as e:
            log(f"imagine: {job['id']} review failed: {e!r}")
        finally:
            eng.conv = keep_conv
            eng.busy = False
            app.gpu.release()
            app.broadcast({"type": "done", "chat": conv.id, "text": ""})
        say = " ".join(str(fin.get("say") or "").split())[:600]
        if fin.get("verdict") == "redo" and not second:
            new = " ".join(str(fin.get("new_prompt") or "").split())[:1500]
            if len(new) >= 12 and not NOT_ADULT.search(new):
                return ("redo", new, say)
        return ("keep", say or job["caption"])

    def _redo(self, job, new_prompt, why):
        with self.lock:
            q = self.state["queue"]
            for i, j in enumerate(q):
                if j["id"] == job["id"]:
                    q[i] = dict(j, prompt=new_prompt, seed=random.randrange(2 ** 48), redo_of=job["prompt"],
                                redo_why=why, tries=0)
                    break
            self._save()
        log(f"imagine: {job['id']} she's redoing it: {why}")
        self.status = "redrawing"
        self.wake.set()

    def deliver(self, job, src, say=None, stills=None):
        app = self.app
        say = say or job["caption"]
        if job.get("kind") == "video":
            return self._deliver_video(job, src, say, stills or [])
        for _ in range(240):
            if not app.engine.busy:
                break
            time.sleep(0.5)
        from .life import HEARTBEAT_CHAT
        conv = None
        if job["chat"] != HEARTBEAT_CHAT:
            try:
                conv = app.conv(job["chat"])
            except ValueError:
                conv = None
        if conv is None:
            conv = app.life.reach_target()[0]
        folder = os.path.join(ATTACH_DIR, conv.id)
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, dt.datetime.now().strftime("%H%M%S-") + f"aether-picture-{job['id']}.png")
        shutil.copyfile(src, dst)
        conv.add("made_image", images=[dst], caption=say, title=job["caption"], prompt=job["prompt"], shape=job["shape"],
                 **({"redone": job["redo_why"]} if job.get("redo_of") else {}))
        with self.lock:
            self.state["queue"] = [j for j in self.state["queue"] if j["id"] != job["id"]]
            day = dt.date.today().isoformat()
            self.state["made"] = {day: self.made_today() + 1}
            g = self.state.setdefault("gallery", [])
            g.append({"id": job["id"], "chat": conv.id, "image": os.path.relpath(dst, ATTACH_DIR).replace("\\", "/"),
                      "title": job["caption"], "caption": say, "prompt": job["prompt"], "shape": job["shape"],
                      **({"why": job["why"]} if job.get("why") else {}),
                      "made": dt.datetime.now().isoformat(timespec="seconds")})
            del g[:-500]
            self._save()
        app.meta.setdefault(conv.id, {})["unread"] = True
        app._save_meta()
        app.broadcast({"type": "made_image", "chat": conv.id, "caption": say, "title": job["caption"], "images": [app._rel(dst)]})
        log(f"imagine: {job['id']} delivered to {conv.id}")
        dc = getattr(app, "discord", None)
        awake = app.life.awake(dt.datetime.now())
        if dc and self.cfg.discord_enabled and awake:
            try:
                with open(dst, "rb") as f:
                    dc.dm_owner_file(os.path.basename(dst), f.read(), say, "image/png")
            except Exception as e:
                log(f"imagine: Discord copy failed: {e!r}")
        if awake and self.cfg.speak_replies == "always" and app.voice.ensure_running():
            app.voice.say_now(say, conv.id)
        self.status = ""

    def _song_shorter(self, job):
        down = songs_mod.DOWN.get(job.get("length"))
        if not down or job.get("shortened"):
            return False
        with self.lock:
            for j in self.state["queue"]:
                if j["id"] == job["id"]:
                    j.update(length=down, shortened=job["length"], tries=0, seed=random.randrange(2 ** 48))
            self._save()
        log(f"imagine: song {job['id']} out of memory at {job['length']}, trying {down}")
        self.wake.set()
        return True

    def _deliver_song(self, job, src):
        app = self.app
        say = job["caption"] or job["title"]
        for _ in range(240):
            if not app.engine.busy:
                break
            time.sleep(0.5)
        from .life import HEARTBEAT_CHAT
        conv = None
        if job["chat"] != HEARTBEAT_CHAT:
            try:
                conv = app.conv(job["chat"])
            except ValueError:
                conv = None
        if conv is None:
            conv = app.life.reach_target()[0]
        folder = os.path.join(ATTACH_DIR, conv.id)
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, dt.datetime.now().strftime("%H%M%S-") + f"aether-song-{job['id']}.mp3")
        shutil.copyfile(src, dst)
        rel = os.path.relpath(dst, ATTACH_DIR).replace("\\", "/")
        conv.add("made_song", audio=dst, caption=say, title=job["title"], style=job["prompt"], lyrics=job["lyrics"],
                 length=job["length"])
        songs_mod.add_record({"id": job["id"], "title": job["title"], "style": job["prompt"], "lyrics": job["lyrics"],
                              "length": job["length"], "seed": job["seed"], "file": rel, "chat": conv.id,
                              "caption": say, "asked": "own time" if job.get("own") else job["asked"],
                              **({"instrumental": True} if job.get("instrumental") else {}),
                              "when": dt.datetime.now().isoformat(timespec="seconds")})
        with self.lock:
            self.state["queue"] = [j for j in self.state["queue"] if j["id"] != job["id"]]
            day = dt.date.today().isoformat()
            made = (self.state.get("songs_made") or {}).get(day, {})
            key = "own" if job.get("own") else "asked"
            self.state["songs_made"] = {day: {**made, key: int(made.get(key, 0)) + 1}}
            self._save()
        app.meta.setdefault(conv.id, {})["unread"] = True
        app._save_meta()
        app.broadcast({"type": "made_song", "chat": conv.id, "caption": say, "title": job["title"],
                       "style": job["prompt"], "audio": app._rel(dst)})
        log(f"imagine: song {job['id']} delivered to {conv.id}")
        dc = getattr(app, "discord", None)
        awake = app.life.awake(dt.datetime.now())
        if dc and self.cfg.discord_enabled and awake and os.path.getsize(dst) < 8 * 1024 * 1024:
            try:
                with open(dst, "rb") as f:
                    dc.dm_owner_file(os.path.basename(dst), f.read(), say, "audio/mpeg")
            except Exception as e:
                log(f"imagine: Discord copy failed: {e!r}")
        if awake and self.cfg.speak_replies == "always" and app.voice.ensure_running():
            app.voice.say_now(say, conv.id)
        self.status = ""

    def _deliver_video(self, job, src, say, stills):
        app = self.app
        for _ in range(240):
            if not app.engine.busy:
                break
            time.sleep(0.5)
        try:
            conv = app.conv(job["chat"])
        except ValueError:
            conv = app.life.reach_target()[0]
        folder = os.path.join(ATTACH_DIR, conv.id)
        os.makedirs(folder, exist_ok=True)
        stamp = dt.datetime.now().strftime("%H%M%S-")
        dst = os.path.join(folder, stamp + f"aether-video-{job['id']}.mp4")
        shutil.copyfile(src, dst)
        poster = None
        if stills:
            poster = os.path.join(folder, stamp + f"aether-video-{job['id']}.png")
            shutil.copyfile(stills[0], poster)
        conv.add("made_video", video=dst, images=[poster] if poster else [], caption=say, title=job["caption"],
                 prompt=job["prompt"], **({"from_picture": job["from_image"]} if job.get("from_image") else {}))
        with self.lock:
            self.state["queue"] = [j for j in self.state["queue"] if j["id"] != job["id"]]
            self.state["videos_made"] = {dt.date.today().isoformat(): self.videos_today() + 1}
            if poster:
                g = self.state.setdefault("gallery", [])
                g.append({"id": job["id"], "kind": "video", "chat": conv.id,
                          "image": os.path.relpath(poster, ATTACH_DIR).replace("\\", "/"),
                          "video": os.path.relpath(dst, ATTACH_DIR).replace("\\", "/"),
                          "title": job["caption"], "caption": say, "prompt": job["prompt"], "shape": "video",
                          "made": dt.datetime.now().isoformat(timespec="seconds")})
                del g[:-500]
            self._save()
        app.meta.setdefault(conv.id, {})["unread"] = True
        app._save_meta()
        app.broadcast({"type": "made_video", "chat": conv.id, "caption": say, "title": job["caption"],
                       "video": app._rel(dst), "images": [app._rel(poster)] if poster else []})
        log(f"imagine: video {job['id']} delivered to {conv.id}")
        dc = getattr(app, "discord", None)
        size = os.path.getsize(dst)
        awake = app.life.awake(dt.datetime.now())
        if dc and self.cfg.discord_enabled and awake and size < 8 * 1024 * 1024:
            try:
                with open(dst, "rb") as f:
                    dc.dm_owner_file(os.path.basename(dst), f.read(), say, "video/mp4")
            except Exception as e:
                log(f"imagine: Discord copy failed: {e!r}")
        if awake and self.cfg.speak_replies == "always" and app.voice.ensure_running():
            app.voice.say_now(say, conv.id)
        self.status = ""
