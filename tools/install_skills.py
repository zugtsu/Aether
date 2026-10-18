#!/usr/bin/env python3
import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT, "skills")
HOME_DIR = os.environ.get("AETHER_HOME") or os.path.join(os.path.expanduser("~"), ".aether")
try:
    with open(os.path.join(HOME_DIR, "aether.json"), encoding="utf-8") as _f:
        LIVE = json.load(_f).get("memory_dir") or ""
except Exception:
    LIVE = ""
LIVE = os.path.expanduser(LIVE or os.path.join(HOME_DIR, "memory"))
DST = os.path.join(LIVE, "skills")
LOCK_EXT = (".md", ".py")
DATA_EXT = (".json", ".jsonl")
FILE_RIGHTS = "WriteData, AppendData, WriteAttributes, WriteExtendedAttributes, Delete"
DATA_RIGHTS = "Delete"
DIR_RIGHTS = "Delete, DeleteSubdirectoriesAndFiles"

PS_LOCK = r"""
$ErrorActionPreference = 'Stop'
$who = $env:USERNAME
$on = $args[0] -eq 'on'
$files = Get-Content $args[1] | Where-Object { $_ }
$datafiles = Get-Content $args[2] | Where-Object { $_ }
$dirs = Get-Content $args[3] | Where-Object { $_ }
function Apply($path, $rights) {
  $acl = Get-Acl -LiteralPath $path
  $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($who, $rights, 'None', 'None', 'Deny')
  $existing = $acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' -and $_.IdentityReference.Value -like "*\$who" -and -not $_.IsInherited }
  foreach ($e in $existing) { $acl.RemoveAccessRule($e) | Out-Null }
  if ($on) { $acl.AddAccessRule($rule) }
  Set-Acl -LiteralPath $path -AclObject $acl
}
foreach ($f in $files) { Apply $f 'FILE_RIGHTS' }
foreach ($f in $datafiles) { Apply $f 'DATA_RIGHTS' }
foreach ($d in $dirs) { Apply $d 'DIR_RIGHTS' }
""".replace("FILE_RIGHTS", FILE_RIGHTS).replace("DATA_RIGHTS", DATA_RIGHTS).replace("DIR_RIGHTS", DIR_RIGHTS)


def locked_files(exts=LOCK_EXT):
    for root, dirs, files in os.walk(DST):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(exts):
                yield os.path.join(root, f)


def locked_dirs():
    yield DST
    for root, dirs, files in os.walk(DST):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for d in dirs:
            yield os.path.join(root, d)


def is_locked(path):
    r = subprocess.run(["icacls", path], capture_output=True, text=True)
    return "(DENY)" in r.stdout


def lock(on):
    files, data, dirs = list(locked_files()), list(locked_files(DATA_EXT)), list(locked_dirs())
    tmp = os.path.join(os.environ.get("TEMP", "."), "lucy-lock")
    os.makedirs(tmp, exist_ok=True)
    fl, dfl, dl, ps = (os.path.join(tmp, n) for n in ("files.txt", "data.txt", "dirs.txt", "lock.ps1"))
    open(fl, "w", encoding="utf-8").write("\n".join(files))
    open(dfl, "w", encoding="utf-8").write("\n".join(data))
    open(dl, "w", encoding="utf-8").write("\n".join(dirs))
    open(ps, "w", encoding="utf-8").write(PS_LOCK)
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps, "on" if on else "off", fl, dfl, dl], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("lock/unlock failed:\n" + r.stderr)
    return len(files) + len(data) + len(dirs)


def project_skills():
    if not os.path.isdir(SRC):
        return []
    return [s for s in sorted(os.listdir(SRC)) if os.path.isdir(os.path.join(SRC, s)) and not s.startswith(("_", "."))]


def sync():
    changed = []
    for skill in project_skills():
        sdir = os.path.join(SRC, skill)
        if not os.path.isdir(sdir) or skill.startswith("_"):
            continue
        for root, dirs, files in os.walk(sdir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                src = os.path.join(root, f)
                rel = os.path.relpath(src, SRC)
                dst = os.path.join(DST, rel)
                if f.endswith(".json") and os.path.exists(dst):
                    continue
                if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
                changed.append(rel.replace(os.sep, "/"))
    return changed


def git(*args):
    return subprocess.run(["git", "-C", LIVE, *args], capture_output=True, text=True)


def commit(changed):
    git("add", "--", *[f"skills/{c}" for c in changed])
    msg = "skills: install " + ", ".join(sorted({c.split("/")[0] for c in changed}))
    r = git("-c", "user.name=user", "-c", "user.email=user@local", "commit", "-q", "-m", msg)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def status():
    files = list(locked_files()) + list(locked_files(DATA_EXT)) + list(locked_dirs())
    locked = [p for p in files if is_locked(p)]
    print(f"live skills dir: {DST}")
    print(f"{len(locked)}/{len(files)} skill files and folders locked")
    for p in files:
        if not is_locked(p):
            print("  UNLOCKED:", os.path.relpath(p, DST) if p != DST else "skills/")
    diffs = []
    for skill in project_skills():
        sdir = os.path.join(SRC, skill)
        if not os.path.isdir(sdir) or skill.startswith("_"):
            continue
        for root, dirs, fs in os.walk(sdir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in fs:
                if f.endswith(".json"):
                    continue
                src = os.path.join(root, f)
                dst = os.path.join(DST, os.path.relpath(src, SRC))
                if not os.path.exists(dst) or not filecmp.cmp(src, dst, shallow=False):
                    diffs.append(os.path.relpath(src, SRC).replace(os.sep, "/"))
    print("project differs from live:" if diffs else "project and live match", *diffs, sep="\n  " if diffs else "")
    st = git("status", "--short").stdout.strip()
    print("live memory git:", "clean" if not st else "\n  " + st.replace("\n", "\n  "))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--status", action="store_true")
    g.add_argument("--unlock", action="store_true")
    g.add_argument("--lock", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(LIVE):
        sys.exit(f"her memory not found: {LIVE}")
    os.makedirs(DST, exist_ok=True)
    if a.status:
        status()
        return
    if a.unlock:
        print(f"unlocked {lock(False)} files and folders; rerun without flags to sync and relock")
        return
    if a.lock:
        print(f"locked {lock(True)} files and folders")
        return
    lock(False)
    changed = sync()
    if changed:
        ok, msg = commit(changed)
        print(f"synced {len(changed)} file(s):", *changed, sep="\n  ")
        print("committed" if ok else f"commit failed: {msg}")
    else:
        print("nothing to sync")
    print(f"locked {lock(True)} skill files and folders")


if __name__ == "__main__":
    main()
