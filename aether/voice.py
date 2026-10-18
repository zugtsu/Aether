import base64
import http.client
import itertools
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict

from .config import DATA_DIR
from .engine import log, looks_like_code
from .proc import NO_WINDOW, end_tied, spawn_tied

SENT_END = re.compile(r"[.!?…]+[\"')\]]*\s+|\n+")
FENCE = "```"
CODE_BLOCK = re.compile(r"```.*?(?:```|$)", re.S)
RATE = 24000
BREEZE_MODEL = "breeze-stream"
BREEZE_WAIT = 25
BREEZE_LOAD = 150
BREEZE_RETRY = 60
REST_AFTER = 60
BREEZE_SPILL_MB = 400
BREEZE_SLOW = 1.6
BREEZE_SLOW_MIN = 2.0
BREEZE_RELOAD_GAP = 600
BREEZE_OPTIONS = {"guidance_scale": "1", "stream_frames_per_event": "8", "stream_lookahead_margin": "6"}

SOUND = re.compile(r"[(*\[]\s*(laugh(?:s|ing)?|chuckl(?:e|es|ing)|giggl(?:e|es|ing)|sigh(?:s|ing)?|"
                   r"cough(?:s|ing)?|clears? (?:her |my )?throat)\s*[)*\]]", re.I)


def _sound(word):
    w = word.lower()
    if w.startswith(("laugh", "chuckl", "giggl")):
        return "(laugh)"
    if w.startswith("sigh"):
        return "(sigh)"
    if w.startswith("cough"):
        return "(cough)"
    return "(clears throat)"


def clean_for_speech(text, sounds=False):
    t = CODE_BLOCK.sub(" ", text)
    t = "\n".join(ln for ln in t.split("\n") if not looks_like_code(ln))
    t = SOUND.sub(lambda m: f" {_sound(m.group(1))} " if sounds else " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://(?:www\.)?([^/\s]+)\S*", r"\1", t)
    t = re.sub(r"[*_`#>|~]+", "", t)
    t = "".join(ch for ch in t if ord(ch) < 0x2190 or 0x2E80 <= ord(ch) < 0x1F000)
    return re.sub(r"\s+", " ", t).strip()


MOOD_VOICE = {
    "steady": ("Relaxed, warm and conversational, at a natural pace.", ""),
    "playful": ("Playful and teasing, a smirk in the voice.", "a little playful"),
    "happy": ("Happy and bright, warm energy, smiling while she talks.", "a little brighter than usual"),
    "affectionate": ("Soft, warm and affectionate, gentle and a little slower.", "a little softer and warmer"),
    "proud": ("Proud and pleased, confident and warm.", "a little pleased with herself"),
    "curious": ("Curious and interested, lively, leaning in.", "a little curious"),
    "dreamy": ("Dreamy and soft, a little slow and far away.", "a little dreamy"),
    "tired": ("Tired and low-energy, a little dry, but warm.", "a little tired"),
    "annoyed": ("Annoyed and exasperated, sharp and clipped.", "a little short"),
    "sulky": ("Sulky and a little short, reluctant.", "a little sulky"),
    "worried": ("Worried and caring, gentle but concerned.", "a little worried"),
    "missing you": ("Soft and wistful, a little lonely, warm.", "a little wistful"),
}


def direction(mood):
    m = mood or {}
    strong, hint = MOOD_VOICE.get(m.get("name"), MOOD_VOICE["steady"])
    if hint and float(m.get("strength") or 0) < 0.45:
        return f"Relaxed and conversational, {hint}."
    return strong


def gpu_shared_mb(pid):
    ps = (f"(Get-Counter '\\GPU Process Memory(pid_{int(pid)}_*)\\Shared Usage' -ErrorAction Stop).CounterSamples | "
          "Measure-Object CookedValue -Sum | ForEach-Object Sum")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                           text=True, timeout=30, creationflags=NO_WINDOW)
        return float(r.stdout.strip()) / 2 ** 20 if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def to_mp3(wav):
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-f", "mp3", "-q:a", "4", "pipe:1"],
                       input=wav, capture_output=True, timeout=60, creationflags=NO_WINDOW)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("ffmpeg couldn't make an mp3: " + r.stderr.decode("utf-8", "replace")[:200])
    return r.stdout


class Splitter:

    def __init__(self, min_chars=12):
        self.buf = ""
        self.min = min_chars
        self.code = False

    def feed(self, text):
        self.buf += text
        out = []
        while True:
            i = self.buf.find(FENCE)
            if self.code:
                if i < 0:
                    self.buf = self.buf[-2:]
                    return out
                self.buf, self.code = self.buf[i + len(FENCE):], False
                continue
            if i < 0:
                return out + self._sentences()
            head, self.buf = self.buf[:i], self.buf[i + len(FENCE):]
            rest, self.buf = self.buf, head
            out += self._sentences() + self.flush()
            self.buf, self.code = rest, True

    def _sentences(self):
        out = []
        while True:
            m = SENT_END.search(self.buf)
            if not m:
                break
            end = m.end()
            piece = self.buf[:end].strip()
            if len(piece) < self.min and "\n" not in self.buf[:end]:
                m2 = SENT_END.search(self.buf, end)
                if not m2:
                    break
                end = m2.end()
                piece = self.buf[:end].strip()
            self.buf = self.buf[end:]
            if piece:
                out.append(piece)
        return out

    def flush(self):
        s, self.buf = ("" if self.code else self.buf.strip()), ""
        return [s] if s else []


class Clip:

    def __init__(self):
        self.pcm = bytearray()
        self.done = False
        self.cond = threading.Condition()

    def add(self, piece):
        with self.cond:
            self.pcm += piece
            self.cond.notify_all()

    def finish(self):
        with self.cond:
            self.done = True
            self.cond.notify_all()

    def seconds(self):
        return len(self.pcm) / 2 / RATE

    def pieces(self, stuck=60):
        sent = 0
        while True:
            with self.cond:
                if len(self.pcm) == sent and not self.done:
                    self.cond.wait(stuck)
                chunk, done = bytes(self.pcm[sent:]), self.done
            if not chunk and not done:
                return
            sent += len(chunk)
            if chunk:
                yield chunk
            if done:
                with self.cond:
                    if len(self.pcm) == sent:
                        return


class Breeze:

    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.state = "off"
        self.why = ""
        self.retry_at = 0.0
        self.reload_wanted = ""
        self.reloaded_at = 0.0
        self.lock = threading.Lock()
        self.ready = threading.Event()

    @property
    def url(self):
        return self.cfg.breeze_url.rstrip("/")

    def paths(self):
        d = self.cfg.breeze_dir
        return (os.path.join(d, "audiocpp", "audiocpp_server.exe"), os.path.join(d, "models", "breeze-tts-2-q8_0.gguf"),
                os.path.join(d, "voices"))

    def missing(self):
        exe, model, voices = self.paths()
        for p, what in ((exe, "audio.cpp"), (model, "the Breeze model"),
                        (os.path.join(voices, self.cfg.breeze_voice + ".wav"), "her voice file")):
            if not os.path.isfile(p):
                return f"{what} isn't there ({p}); see voice-engine/README.md"
        return ""

    def up(self):
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=1.5) as r:
                return r.status == 200
        except Exception:
            return False

    def start(self):
        with self.lock:
            if self.state in ("starting", "aside"):
                return
            if self.state == "up" and (self.proc is None or self.proc.poll() is None):
                return
            if self.state == "failed" and time.time() < self.retry_at:
                return
            why = self.missing()
            if why:
                self._failed(why)
                return
            self.state, self.why = "starting", ""
            self.ready.clear()
        threading.Thread(target=self._start, daemon=True, name="breeze-start").start()

    def _failed(self, why, wait=BREEZE_RETRY):
        self.state, self.why, self.retry_at = "failed", why, time.time() + wait
        log(f"voice: Breeze: {why}")

    def _start(self):
        try:
            for attempt in (1, 2):
                if not self.up():
                    self._launch()
                    if self.state != "starting":
                        return
                self.whole("Okay.", "Relaxed.")
                spilled = gpu_shared_mb(self.proc.pid) if self.proc is not None else None
                if spilled is None or spilled < BREEZE_SPILL_MB:
                    break
                log(f"voice: Breeze landed partly in regular RAM ({spilled:.0f} MB, too slow to talk smoothly): "
                    + ("loading it again" if attempt == 1 else "text only for now"))
                with self.lock:
                    self._stop_proc()
                if attempt == 2:
                    with self.lock:
                        if self.state == "starting":
                            self._failed(f"not enough free graphics memory when it loaded ({spilled:.0f} MB landed in "
                                         "regular RAM, which is too slow); it tries again in a few minutes", wait=300)
                    return
                time.sleep(5)
            with self.lock:
                if self.state == "starting":
                    self.state = "up"
        except Exception as e:
            with self.lock:
                if self.state == "starting":
                    self._stop_proc()
                    self._failed(str(e)[:300])
        finally:
            self.ready.set()

    def _launch(self):
        exe, model, voices = self.paths()
        port = int(self.url.rsplit(":", 1)[1])
        conf = {"host": "127.0.0.1", "port": port, "backend": "vulkan", "device": int(self.cfg.breeze_device),
                "lazy_load": False, "ui": False, "voice_dir": voices,
                "models": [{"id": BREEZE_MODEL, "family": "breeze_tts", "path": model, "task": "tts",
                            "mode": "streaming", "session_options": {"breeze_tts.reference_cache_slots": "1"},
                            "default_request_options": {"seed": "1", **BREEZE_OPTIONS}}]}
        folder = os.path.join(DATA_DIR, "voice")
        os.makedirs(folder, exist_ok=True)
        os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)
        path = os.path.join(folder, "breeze_server.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conf, f, indent=1)
        with open(os.path.join(DATA_DIR, "logs", "breeze.log"), "ab") as logf:
            p = spawn_tied([exe, "--config", path, "--log"], cwd=os.path.dirname(exe), stdout=logf,
                           stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        with self.lock:
            if self.state != "starting":
                end_tied(p)
                return
            self.proc = p
        t0 = time.time()
        while not self.up():
            if self.state != "starting":
                return
            if p.poll() is not None:
                raise RuntimeError(f"audio.cpp stopped while loading (code {p.returncode}); see ~/.aether/logs/breeze.log")
            if time.time() - t0 > BREEZE_LOAD:
                raise RuntimeError("Breeze took too long to load")
            time.sleep(0.5)
        log(f"voice: Breeze is up ({time.time() - t0:.0f} s)")

    def reload(self):
        why, self.reload_wanted = self.reload_wanted, ""
        if self.state != "up" or time.time() - self.reloaded_at < BREEZE_RELOAD_GAP:
            log(f"voice: Breeze is slow ({why}); not loading it again yet")
            return
        self.reloaded_at = time.time()
        log(f"voice: Breeze is slow ({why}): loading it again")
        self.stop()
        self.start()

    def wait(self, seconds):
        if self.state == "starting":
            self.ready.wait(seconds)
        return self.state == "up"

    def lost(self):
        if self.state == "up" and not self.up():
            with self.lock:
                self._stop_proc()
                self._failed("audio.cpp stopped answering", wait=0)

    def _stop_proc(self):
        p, self.proc = self.proc, None
        if p is not None:
            end_tied(p)

    def stop(self, aside=False):
        with self.lock:
            self._stop_proc()
            self.state = "aside" if aside else "off"
        self.ready.set()

    def _request(self, text, instruction, stream):
        body = {"model": BREEZE_MODEL, "input": text, "voice": self.cfg.breeze_voice, "stream": stream,
                "options": {"instruction": instruction, "seed": "1", **BREEZE_OPTIONS}}
        if stream:
            body.update(stream_format="sse", response_format="pcm")
        req = urllib.request.Request(self.url + "/v1/audio/speech", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=120)

    def stream(self, text, instruction):
        with self._request(text, instruction, True) as r:
            for raw in r:
                line = raw.strip()
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    return
                ev = json.loads(data)
                if ev.get("type") == "speech.audio.delta":
                    yield base64.b64decode(ev.get("audio") or "")
                elif ev.get("type") == "error":
                    err = ev.get("error")
                    raise RuntimeError(str(err.get("message") if isinstance(err, dict) else err)[:200])

    def whole(self, text, instruction):
        with self._request(text, instruction, False) as r:
            return r.read()


class Voice:
    def __init__(self, cfg, broadcast, mood=None):
        self.cfg = cfg
        self.broadcast = broadcast
        self.mood = mood or (lambda: None)
        self.jobs = queue.Queue()
        self.audio = OrderedDict()
        self.gen = 0
        self.ids = itertools.count(1)
        self.splitter = None
        self.chat = ""
        self.proc = None
        self.making = False
        self.slow = 0
        self.noted_at = 0.0
        self.breeze = Breeze(cfg)
        self.lock = threading.Lock()
        self.clips = 0
        self.used_at = 0.0
        threading.Thread(target=self._worker, daemon=True).start()

    def engine(self):
        return "breeze" if self.cfg.voice_engine == "breeze" else "kokoro"

    def wanted(self):
        return self.engine() == "breeze" and self.cfg.speak_replies != "never"

    def warm(self):
        if self.wanted():
            self.breeze.start()
        elif self.breeze.state in ("up", "starting"):
            if self.engine() != "breeze" or (self.quiet() and not self.clips):
                self.breeze.stop()
                log("voice: Breeze unloaded" + ("" if self.engine() != "breeze" else " (Speak her replies: never)"))
            else:
                self._rest_later()

    def _rest_later(self):
        if self.wanted() or self.engine() != "breeze":
            return
        t = threading.Timer(REST_AFTER, self._rest_if_idle)
        t.daemon = True
        t.start()

    def _rest_if_idle(self):
        if (self.wanted() or self.engine() != "breeze" or self.breeze.state != "up" or not self.quiet() or self.clips
                or time.time() - self.used_at < REST_AFTER * 0.9):
            return
        self.breeze.stop()
        log("voice: Breeze unloaded after a clip (Speak her replies: never)")

    def server(self):
        return str(getattr(self.cfg, "tts_url", "") or "").strip().rstrip("/")

    def up(self):
        base = self.server()
        if not base:
            return False
        try:
            with urllib.request.urlopen(base + "/health", timeout=1.5) as r:
                try:
                    return json.load(r).get("model_loaded", True)
                except ValueError:
                    return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            return False

    def ensure_running(self):
        if self.engine() == "breeze":
            self.breeze.start()
            return self.breeze.state in ("up", "starting")
        return self._ensure_kokoro()

    def quiet_why(self):
        if self.engine() != "breeze":
            if not self.server():
                return "no voice server is set yet (Settings -> Voice & Ears)"
            return f"the voice server at {self.server()} isn't answering"
        return {"aside": "the voice is resting while a picture is drawn (it gives ComfyUI its graphics memory)",
                "starting": "the voice is still loading (about 15 seconds)",
                "failed": f"the voice didn't start: {self.breeze.why}"}.get(self.breeze.state, "the voice isn't loaded yet")

    def _ensure_kokoro(self):
        if not self.server():
            return False
        if self.up():
            return True
        if not self.cfg.start_kokoro or self.proc is not None or not self.cfg.kokoro_dir:
            return False
        py = os.path.join(self.cfg.kokoro_dir, ".venv", "Scripts", "python.exe")
        script = os.path.join(self.cfg.kokoro_dir, "server.py")
        if not (os.path.isfile(py) and os.path.isfile(script)):
            return False
        self.proc = subprocess.Popen([py, script], cwd=self.cfg.kokoro_dir, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        for _ in range(60):
            if self.up():
                return True
            time.sleep(0.5)
        return False

    def step_aside(self, wait=20):
        if not self.cfg.breeze_aside_for_pictures or self.breeze.state not in ("up", "starting"):
            return False
        t0 = time.time()
        while (self.making or not self.jobs.empty()) and time.time() - t0 < wait:
            time.sleep(0.25)
        self.breeze.stop(aside=True)
        log("voice: Breeze stepped aside for ComfyUI")
        return True

    def step_back(self):
        with self.breeze.lock:
            if self.breeze.state != "aside":
                return
            self.breeze.state = "off"
        if self.wanted():
            self.breeze.start()

    def status(self):
        return {"engine": self.engine(), "breeze": self.breeze.state, "breeze_why": self.breeze.why}

    def quiet(self):
        return self.splitter is None and not self.making and self.jobs.empty()

    def shutdown(self):
        self.breeze.stop()
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()

    def begin(self, chat):
        with self.lock:
            self.splitter = Splitter()
            self.chat = chat

    def feed(self, text):
        with self.lock:
            if self.splitter is None:
                return
            for s in self.splitter.feed(text):
                self._queue(s)

    def end(self):
        with self.lock:
            if self.splitter is None:
                return
            for s in self.splitter.flush():
                self._queue(s)
            self.splitter = None

    def _queue(self, sentence):
        if clean_for_speech(sentence):
            self.jobs.put((self.gen, next(self.ids), self.chat, sentence))

    def stop(self):
        with self.lock:
            self.gen += 1
            self.splitter = None
        while True:
            try:
                self.jobs.get_nowait()
            except queue.Empty:
                break
        self.broadcast({"type": "audio_stop"})

    def say_now(self, text, chat=""):
        self.begin(chat)
        self.feed(text)
        self.end()

    def _breeze_ready(self):
        if self.engine() != "breeze":
            return False
        self.breeze.start()
        return self.breeze.wait(BREEZE_WAIT)

    def synth(self, text):
        if self.engine() != "breeze":
            return self._kokoro_mp3(clean_for_speech(text))
        with self.lock:
            self.clips += 1
        try:
            if not self._breeze_ready():
                raise RuntimeError(self.quiet_why())
            if not shutil.which("ffmpeg"):
                raise RuntimeError("ffmpeg isn't installed (it turns the voice into an mp3)")
            try:
                return to_mp3(self.breeze.whole(clean_for_speech(text, sounds=True), direction(self.mood())))
            except (urllib.error.URLError, http.client.HTTPException, OSError, subprocess.TimeoutExpired) as e:
                self.breeze.lost()
                raise RuntimeError(f"the voice couldn't make the clip: {e}") from e
        finally:
            with self.lock:
                self.clips -= 1
            self.used_at = time.time()
            self._rest_later()

    def _kokoro_mp3(self, text):
        if not self.server():
            raise RuntimeError("no voice server is set yet (Settings -> Voice & Ears)")
        if not re.match(r"http://(127\.0\.0\.1|localhost|\[::1\]):\d+(/|$)", self.cfg.tts_url.strip()):
            raise RuntimeError("the voice server has to be on this PC (http://127.0.0.1:<port>)")
        body = {"model": getattr(self.cfg, "tts_model", "") or "kokoro", "voice": self.cfg.voice, "input": text,
                "response_format": "mp3", "speed": self.cfg.voice_speed}
        req = urllib.request.Request(self.cfg.tts_url.rstrip("/") + "/v1/audio/speech", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()

    def _keep(self, key, audio):
        self.audio[key] = audio
        while len(self.audio) > 60:
            self.audio.popitem(last=False)

    def _worker(self):
        while True:
            gen, aid, chat, text = self.jobs.get()
            if gen != self.gen:
                continue
            self.making = True
            try:
                if self.engine() != "breeze":
                    self._say_kokoro(gen, aid, chat, text)
                elif self._breeze_ready():
                    self._say_breeze(gen, aid, chat, text)
                else:
                    self._quiet_note()
            except Exception as e:
                log(f"voice: worker: {e!r}")
            finally:
                self.making = False
                self.used_at = time.time()
                if self.breeze.reload_wanted and self.jobs.empty():
                    self.breeze.reload()
                if self.jobs.empty():
                    self._rest_later()

    def _quiet_note(self):
        if self.breeze.state == "aside" or time.time() - self.noted_at < 600:
            return
        self.noted_at = time.time()
        self.broadcast({"type": "audio_error", "text": f"Text only for now: {self.quiet_why()}"})

    def _say_breeze(self, gen, aid, chat, text):
        said = clean_for_speech(text, sounds=True)
        clip, key, told, t0 = Clip(), str(aid), False, time.time()
        try:
            for piece in self.breeze.stream(said, direction(self.mood())):
                if gen != self.gen:
                    return True
                if not piece:
                    continue
                clip.add(piece)
                if not told:
                    self._keep(key, clip)
                    self.broadcast({"type": "audio", "chat": chat, "id": key, "text": said, "stream": True, "rate": RATE})
                    told = True
        except (urllib.error.URLError, http.client.HTTPException, OSError, RuntimeError, ValueError) as e:
            log(f"voice: Breeze stopped on a sentence ({e})" + ("" if told else "; that sentence is text only"))
            self.breeze.lost()
            return told
        finally:
            clip.finish()
        secs = clip.seconds()
        if told and secs >= BREEZE_SLOW_MIN:
            rtf = (time.time() - t0) / secs
            self.slow = self.slow + 1 if rtf > BREEZE_SLOW else 0
            if self.slow >= 2:
                self.slow = 0
                self.breeze.reload_wanted = f"two sentences in a row took {rtf:.1f} s per second of sound"
        return told

    def _say_kokoro(self, gen, aid, chat, text):
        said = clean_for_speech(text)
        if not said:
            return
        try:
            mp3 = self._kokoro_mp3(said)
        except (urllib.error.URLError, OSError, RuntimeError) as e:
            self.broadcast({"type": "audio_error", "text": f"The voice server didn't answer: {e}"})
            return
        if gen != self.gen:
            return
        key = str(aid)
        self._keep(key, mp3)
        self.broadcast({"type": "audio", "chat": chat, "id": key, "text": said})

    def get(self, key):
        return self.audio.get(str(key))

    def options(self, url=None):
        base = str(url if url is not None else self.server()).strip().rstrip("/")
        out = {"ok": False, "models": [], "voices": [], "error": "", "url": base}
        if not base:
            out["error"] = "no voice server is set yet"
            return out
        if not re.match(r"http://(127\.0\.0\.1|localhost|\[::1\]):\d+$", base):
            out["error"] = "the voice server has to be on this PC (http://127.0.0.1:<port>)"
            return out
        for key, path in (("models", "/v1/models"), ("voices", "/v1/audio/voices")):
            try:
                with urllib.request.urlopen(base + path, timeout=3) as r:
                    out[key] = names_in(json.load(r), key)
                out["ok"] = True
            except urllib.error.HTTPError:
                out["ok"] = True
            except (OSError, ValueError) as e:
                out["error"] = out["error"] or f"no answer from {base} ({getattr(e, 'reason', e)})"
        if out["ok"]:
            out["error"] = ""
        return out


def names_in(data, key):
    if isinstance(data, dict):
        data = data.get(key) or data.get("data") or data.get("items") or next(
            (v for v in data.values() if isinstance(v, list)), [])
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict):
            item = item.get("id") or item.get("name") or item.get("voice_id") or item.get("model") or ""
        item = str(item).strip()
        if item and item not in out and len(item) <= 100:
            out.append(item)
    return out[:300]
