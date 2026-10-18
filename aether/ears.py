import datetime as dt
import json
import os
import subprocess
import threading

from .config import DATA_DIR
from .proc import end_tied, spawn_tied

VOICEPRINT = os.path.join(DATA_DIR, "voice", "voiceprint.json")
VOICE_YES, VOICE_NO, VOICE_MIN = 0.40, 0.25, 1.5
VOICE_LEARN_MIN = 10.0

EVENT_TAGS = {"Laughter": "laughing", "Cry": "crying"}
EMOTION_TAGS = {"HAPPY": "sounds happy", "SAD": "sounds sad", "ANGRY": "sounds angry",
                "FEARFUL": "sounds scared", "SURPRISED": "sounds surprised", "DISGUSTED": "sounds disgusted"}


def tone_of(result):
    if result.get("laughs", 0) >= 1:
        return "laughing"
    ev = EVENT_TAGS.get(result.get("event", ""))
    if ev:
        return ev
    return EMOTION_TAGS.get(result.get("emotion", "").upper(), "")


def sounds_like(score, speech):
    if score is None or speech < VOICE_MIN:
        return ""
    return "user" if score >= VOICE_YES else "other" if score < VOICE_NO else ""


class Ears:
    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.lock = threading.Lock()

    def available(self):
        return os.path.isfile(self.cfg.ears_python) and os.path.isfile(self.cfg.ears_model)

    def _start(self):
        tokens = os.path.join(os.path.dirname(self.cfg.ears_model), "tokens.txt")
        worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ears_worker.py")
        speaker = self.cfg.speaker_model if os.path.isfile(self.cfg.speaker_model or "") else ""
        self.proc = spawn_tied([self.cfg.ears_python, worker, self.cfg.ears_model, tokens, speaker],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding="utf-8", bufsize=1,
                               creationflags=0x08000000 if os.name == "nt" else 0)
        ready = self.proc.stdout.readline()
        if '"ready"' not in ready:
            end_tied(self.proc)
            self.proc = None
            raise RuntimeError("the ears helper didn't start")

    def _ask(self, req):
        if not self.available():
            raise RuntimeError("SenseVoice isn't installed where Aether expects it (ears_python / ears_model)")
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            self.proc.stdin.write(json.dumps(req) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        if not line:
            self.proc = None
            raise RuntimeError("the ears helper stopped")
        r = json.loads(line)
        if "error" in r:
            raise RuntimeError(r["error"])
        return r

    def hear(self, wav_path):
        r = self._ask({"wav": wav_path})
        r["tone"] = tone_of(r) if self.cfg.hear_tone else ""
        vec, mine = r.pop("voice", None), self.voiceprint()
        score = round(sum(a * b for a, b in zip(vec, mine["vector"])), 3) if vec and mine else None
        r["voice_score"] = score
        r["sounds_like"] = sounds_like(score, r.get("speech", 0))
        return r

    def voiceprint(self):
        try:
            with open(VOICEPRINT, encoding="utf-8") as f:
                p = json.load(f)
        except (OSError, ValueError):
            return None
        return p if p.get("model") == os.path.basename(self.cfg.speaker_model or "") and p.get("vector") else None

    def learn(self, wav_path):
        r = self._ask({"embed": wav_path})
        if r.get("speech", 0) < VOICE_LEARN_MIN:
            raise ValueError(f"Only {r.get('speech', 0):.0f} s of talking came through; talk for about 20 s.")
        p = {"vector": r["voice"], "model": os.path.basename(self.cfg.speaker_model), "speech": r["speech"],
             "made": dt.datetime.now().isoformat(timespec="seconds")}
        os.makedirs(os.path.dirname(VOICEPRINT), exist_ok=True)
        tmp = VOICEPRINT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(p, f)
        os.replace(tmp, VOICEPRINT)
        return {"speech": p["speech"], "made": p["made"]}

    def forget(self):
        if os.path.exists(VOICEPRINT):
            from .backup import recycle
            recycle(VOICEPRINT)

    def shutdown(self):
        if self.proc is not None:
            end_tied(self.proc)
            self.proc = None
