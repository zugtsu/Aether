import os
import subprocess
import tempfile
import zipfile

from .config import DATA_DIR, HOME
from .proc import NO_WINDOW

KEEP_FOLDERS = ("conversations", "attachments")
KEEP_FILES = ("aether.json", "life.json", "schedules.json", "vault.dat", "model_scores.json")


def backup_dir(cfg):
    return os.path.abspath(os.path.expanduser(getattr(cfg, "backup_dir", "") or os.path.join(HOME, "Desktop", "Aether Backups")))


def make(cfg, memory_root, data_dir=DATA_DIR):
    out_dir = backup_dir(cfg)
    os.makedirs(out_dir, exist_ok=True)
    name = "aether-backup.zip"
    path = os.path.join(out_dir, name)
    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, "memory.bundle")
        r = subprocess.run(["git", "-C", memory_root, "bundle", "create", bundle, "--all"], capture_output=True, text=True,
                           timeout=300, creationflags=NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError("git couldn't bundle the memory: " + r.stderr.strip()[:200])
        with zipfile.ZipFile(path + ".part", "w", zipfile.ZIP_DEFLATED) as z:
            z.write(bundle, "memory.bundle")
            for f in KEEP_FILES:
                p = os.path.join(data_dir, f)
                if os.path.isfile(p):
                    z.write(p, f"aether/{f}")
            for folder in KEEP_FOLDERS:
                base = os.path.join(data_dir, folder)
                for dirpath, _dirs, files in os.walk(base):
                    for f in files:
                        p = os.path.join(dirpath, f)
                        z.write(p, "aether/" + os.path.relpath(p, data_dir).replace("\\", "/"))
            z.writestr("RESTORE.txt",
                       "Aether backup\n\n"
                       "Aether data: copy the aether folder to %USERPROFILE%\\.aether\n"
                       "Memory:      git clone memory.bundle %USERPROFILE%\\.aether\\memory\n"
                       "The vault (vault.dat) only opens on the same Windows account it was made on.\n")
    os.replace(path + ".part", path)
    return path


def rotate(cfg, keep=7):
    folder = backup_dir(cfg)
    zips = sorted((f for f in os.listdir(folder) if f.startswith("aether-") and f.endswith(".zip")), reverse=True)
    old = [os.path.join(folder, f) for f in zips[keep:]]
    for p in old:
        recycle(p)
    return old


def recycle(path):
    ps = ("Add-Type -AssemblyName Microsoft.VisualBasic; "
          "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($env:AETHER_RECYCLE, 'OnlyErrorDialogs', 'SendToRecycleBin')")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, timeout=60,
                   env=dict(os.environ, AETHER_RECYCLE=path), creationflags=NO_WINDOW)
