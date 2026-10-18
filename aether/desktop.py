import ctypes
import json
import os
import subprocess
import sys
import urllib.request

from .config import DATA_DIR, PROJECT
from .proc import NO_WINDOW

ICON = os.path.join(DATA_DIR, "aether.ico")


def popup(text, title="Aether"):
    try:
        ctypes.windll.user32.MessageBoxW(None, str(text), title, 0x40)
    except Exception:
        print(text)


def running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ui/app.js", timeout=1.5) as r:
            return b"aether-token" in r.read(4096)
    except Exception:
        return False


def make_icon(picture):
    from PIL import Image
    os.makedirs(os.path.dirname(ICON), exist_ok=True)
    im = Image.open(picture).convert("RGBA")
    side = min(im.size)
    left, top = (im.width - side) // 2, max(0, (im.height - side) // 4)
    im = im.crop((left, top, left + side, top + side))
    im.save(ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ICON


APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop")
ELECTRON = os.path.join(APP_DIR, "node_modules", "electron", "dist", "electron.exe")
LOGO_ICO = os.path.join(APP_DIR, "logo.ico")


def app_icon(cfg):
    if os.path.isfile(LOGO_ICO):
        return LOGO_ICO
    pic = os.path.join(cfg.memory_path, "profile.png")
    return make_icon(pic) if os.path.exists(pic) else os.path.join(os.path.dirname(sys.executable), "pythonw.exe")


def create_shortcut(cfg, name="Aether"):
    icon = app_icon(cfg)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    lnk = os.path.join(desktop, f"{name}.lnk")
    if os.path.isfile(ELECTRON):
        with open(os.path.join(APP_DIR, "launch.json"), "w", encoding="utf-8") as f:
            json.dump({"pythonw": pythonw, "project": PROJECT, "port": cfg.port, "icon": icon}, f, indent=1)
        target, args, workdir = ELECTRON, f'"{APP_DIR}"', APP_DIR
    else:
        target, args, workdir = pythonw, "-m aether app --quit-when-closed", PROJECT
    spec = json.dumps({"lnk": lnk, "target": target, "args": args,
                       "dir": workdir, "icon": icon, "desc": "Aether - your local AI companion"})
    ps = ("$s = ConvertFrom-Json $env:AETHER_LNK; $w = New-Object -ComObject WScript.Shell; "
          "$l = $w.CreateShortcut($s.lnk); $l.TargetPath = $s.target; $l.Arguments = $s.args; "
          "$l.WorkingDirectory = $s.dir; $l.IconLocation = $s.icon; $l.Description = $s.desc; $l.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True,
                       env=dict(os.environ, AETHER_LNK=spec), timeout=30, creationflags=NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(lnk):
        raise RuntimeError("couldn't make the shortcut: " + (r.stderr.strip() or "unknown error"))
    return lnk
