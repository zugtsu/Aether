import os
import re
import subprocess

from .config import DATA_DIR
from .proc import NO_WINDOW

EYES_DIR = os.path.join(DATA_DIR, "eyes")
SLOTS = 3
WARMUP = 1.5
SIZE = "1280x720"
ABOUT_MAX = 80
SKILL_LINE = ("{USER} asks you to look at him or at something he's showing you ('how do I look?', 'what am I holding?', "
              "'can you see me?'): your webcam step shows you a picture from his webcam, right now")
NOT_ASKED = ("Not taken: his message doesn't ask you to look right now. You can't see him at the moment (a picture you "
             "took earlier isn't in front of you anymore): don't describe how he looks; go by what you already said, or "
             "ask if he wants you to look again.")
CLOSED_LINE = ("your eyes (his webcam) are switched OFF in Settings: you can't see him or anything right now. If he asks "
               "you to look or whether you can see him, tell him that, and that he can switch on 'Its eyes' in Settings")
CLOSED_DOC = "# Look (built into Aether)\n\n" + CLOSED_LINE[0].upper() + CLOSED_LINE[1:] + ".\n"
SKILL_DOC = """# Webcam (built into Aether: you use it with your `webcam` step)

{USER}'s webcam is your eyes. Your webcam step takes one picture through it, right now, and shows it to you. Only when he
asks you to look (how he looks, what he's holding or showing you, whether you can see him), and only while he's at
his PC in the app.

## How: one webcam step
- about: what he wants you to look at, in a few words ("him", "what he's holding")

```
{"step": "webcam", "about": "what he's holding"}
```

## Then
The picture is attached to the result: say what you actually see in it, in your own words. If it's dark or blurry,
say so. It's a moment, not a video: you don't see him move, and you can't keep watching.
"""


def device(cfg):
    if getattr(cfg, "eyes_camera", ""):
        return cfg.eyes_camera
    out = subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
                         creationflags=NO_WINDOW)
    m = re.search(r'"([^"]+)" \(video\)', out.stderr + out.stdout)
    return m.group(1) if m else ""


def snapshot(cfg, slot):
    cam = device(cfg)
    if not cam:
        return None, "No camera found: is it plugged in?"
    os.makedirs(EYES_DIR, exist_ok=True)
    path = os.path.join(EYES_DIR, f"look-{slot}.jpg")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "dshow", "-video_size", SIZE,
                        "-i", f"video={cam}", "-t", str(WARMUP), "-update", "1", "-q:v", "3", "-y", path],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                       creationflags=NO_WINDOW)
    if r.returncode != 0 or not os.path.isfile(path):
        if "video_size" in r.stderr or "size" in r.stderr.lower():
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "dshow", "-i", f"video={cam}",
                                "-t", str(WARMUP), "-update", "1", "-q:v", "3", "-y", path],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                               creationflags=NO_WINDOW)
        if r.returncode != 0 or not os.path.isfile(path):
            busy = "in use" in r.stderr.lower() or "could not run graph" in r.stderr.lower()
            return None, ("The camera is busy (another app has it open)." if busy else
                          f"The camera didn't give a picture ({(r.stderr.strip().splitlines() or ['no error'])[-1][:120]}).")
    return path, None


class Eyes:
    def __init__(self, app):
        self.app = app
        self.slot = 0
        self.forget()

    @staticmethod
    def forget():
        try:
            names = os.listdir(EYES_DIR)
        except OSError:
            return
        for name in names:
            if re.fullmatch(r"look-\d+\.jpg", name):
                try:
                    os.remove(os.path.join(EYES_DIR, name))
                except OSError:
                    pass

    def option(self):
        if not getattr(self.app.cfg, "eyes_enabled", False):
            return None
        return {"type": "object", "properties": {"step": {"const": "webcam"},
                                                 "about": {"type": "string", "maxLength": ABOUT_MAX}},
                "required": ["step", "about"], "additionalProperties": False}

    def run_step(self, step):
        eng = self.app.engine
        if not getattr(self.app.cfg, "eyes_enabled", False):
            return False, "Your eyes are switched off in Settings."
        if eng._kind != "user":
            return False, "You look only when {USER} asks you to, while he's here."
        if "discord" in str(eng._place or "").lower():
            return False, ("Not over Discord: the camera is at his PC, and he may not be there. Looking works when he "
                           "talks to you in the app.")
        if not any(a[0] == "webcam" for a in eng._asks):
            return False, NOT_ASKED
        self.slot = self.slot % SLOTS + 1
        path, why = snapshot(self.app.cfg, self.slot)
        if not path:
            return False, why
        about = str(step.get("about") or "").strip()
        return True, (f"You looked through his webcam just now{' at ' + about if about else ''}. The picture is attached "
                      "below: say only what's actually in it. If he isn't in it, or it's too dark to tell, say so: never "
                      "describe him from memory."), [path]
