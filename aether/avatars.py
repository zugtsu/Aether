import json
import os
import re
import shutil
import zipfile

ORB = "orb"
LOGO_ORB = "logo-orb"
BUILT_IN = (ORB, LOGO_ORB)
MAX_BYTES = 300 * 1024 * 1024
SETTINGS = "aether-avatar.json"
FRAMING = {"zoom": 1.0, "y": 0.0}
MOOD_WORDS = {
    "playful": ["playful", "wink", "tease", "smirk", "grin", "happy", "smile", "star"],
    "happy": ["happy", "joy", "smile", "glad", "laugh", "star"],
    "affectionate": ["love", "blush", "heart", "shy", "affection"],
    "proud": ["proud", "smug", "confident", "smirk", "grin"],
    "curious": ["curious", "surprise", "wonder", "question", "think"],
    "dreamy": ["dreamy", "dream", "relax", "calm", "sleepy"],
    "tired": ["tired", "sleepy", "sluggish", "sigh", "bored"],
    "annoyed": ["annoyed", "angry", "anger", "mad", "irritated"],
    "sulky": ["sulk", "pout", "disgust", "sad"],
    "worried": ["worried", "worry", "nervous", "anxious", "sad", "cry"],
    "missing you": ["lonely", "miss", "sad", "cry"],
}
NAME_OK = re.compile(r"^[\w .()-]{1,60}$")


class AvatarError(Exception):
    pass


def find_model(folder):
    for root, dirs, files in os.walk(folder):
        if os.path.relpath(root, folder).count(os.sep) > 3:
            dirs[:] = []
            continue
        for f in sorted(files):
            if f.lower().endswith(".model3.json"):
                return os.path.join(root, f)
    return None


def _read(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def missing_files(model_path):
    d = _read(model_path)
    refs = d.get("FileReferences") or {}
    base = os.path.dirname(model_path)
    names = [refs.get("Moc"), refs.get("Physics"), refs.get("Pose"), refs.get("DisplayInfo"), refs.get("UserData")]
    names += list(refs.get("Textures") or [])
    names += [e.get("File") for e in refs.get("Expressions") or [] if isinstance(e, dict)]
    for group in (refs.get("Motions") or {}).values():
        names += [m.get("File") for m in group or [] if isinstance(m, dict)]
    return [n for n in names if n and not os.path.isfile(os.path.join(base, n))]


def mood_map(expression_names):
    low = [(n, n.lower()) for n in expression_names]
    out = {"steady": None}
    for mood, words in MOOD_WORDS.items():
        out[mood] = next((n for w in words for n, lo in low if w in lo), None)
    return out


def inspect(model_path):
    if not model_path or not os.path.isfile(model_path):
        raise AvatarError("no model file there")
    d = _read(model_path)
    refs = d.get("FileReferences") or {}
    exprs = [e.get("Name") for e in refs.get("Expressions") or [] if isinstance(e, dict) and e.get("Name")]
    groups = {g.get("Name"): g.get("Ids") or [] for g in d.get("Groups") or [] if isinstance(g, dict)}
    mouth = (groups.get("LipSync") or ["ParamMouthOpenY"])[0]
    framing = dict(FRAMING)
    moods = mood_map(exprs)
    try:
        saved = _read(os.path.join(os.path.dirname(model_path), SETTINGS))
        framing.update({k: float(saved[k]) for k in FRAMING if isinstance(saved.get(k), (int, float))})
        for mood, e in (saved.get("moods") or {}).items():
            if mood in moods and (e is None or e in exprs):
                moods[mood] = e
    except (OSError, ValueError, AttributeError):
        pass
    warn = []
    if not exprs:
        warn.append("no expressions: the face won't change with the mood")
    if "LipSync" not in groups:
        warn.append("no LipSync group: the mouth uses ParamMouthOpenY, which this model may not have")
    gone = missing_files(model_path)
    if gone:
        warn.append("missing files: " + ", ".join(gone[:5]))
    return {"file": os.path.basename(model_path), "expressions": exprs, "moods": moods, "mouth": mouth,
            "blink": bool(groups.get("EyeBlink")), "framing": framing, "warnings": warn}


def _settings(model_path):
    try:
        cur = _read(os.path.join(os.path.dirname(model_path), SETTINGS))
        return cur if isinstance(cur, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_settings(model_path, cur):
    with open(os.path.join(os.path.dirname(model_path), SETTINGS), "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=1)
    return cur


def save_framing(model_path, zoom, y):
    cur = _settings(model_path)
    cur.update(zoom=max(0.3, min(3.0, float(zoom))), y=max(-1.0, min(1.0, float(y))))
    return _write_settings(model_path, cur)


def save_mood(model_path, mood, expression):
    if mood not in MOOD_WORDS and mood != "steady":
        raise AvatarError(f"no mood called {mood}")
    if expression is not None and expression not in inspect(model_path)["expressions"]:
        raise AvatarError(f"the model has no expression called {expression}")
    cur = _settings(model_path)
    cur.setdefault("moods", {})[mood] = expression
    return _write_settings(model_path, cur)


def listing(root):
    out = []
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        if name.startswith("."):
            continue
        folder = os.path.join(root, name)
        model = find_model(folder) if os.path.isdir(folder) else None
        if not model:
            continue
        try:
            info = inspect(model)
            out.append({"name": name, "file": info["file"], "ok": not any(w.startswith("missing") for w in info["warnings"]),
                        "warnings": info["warnings"]})
        except (AvatarError, OSError, ValueError) as e:
            out.append({"name": name, "file": os.path.basename(model), "ok": False, "warnings": [str(e)[:120]]})
    return out


def model_of(root, name):
    if not name or not NAME_OK.match(name) or name in (".", ".."):
        return None
    folder = os.path.join(root, name)
    if os.path.dirname(os.path.abspath(folder)) != os.path.abspath(root) or not os.path.isdir(folder):
        return None
    return find_model(folder)


def add(src, root, name=None):
    src = os.path.abspath(os.path.expanduser(str(src or "").strip().strip('"')))
    if not os.path.exists(src):
        raise AvatarError("nothing at that path")
    name = (name or os.path.splitext(os.path.basename(src.rstrip("\\/")))[0]).strip()
    if not NAME_OK.match(name) or name in (".", ".."):
        raise AvatarError("pick a simple name (letters, numbers, spaces, - . _ ( ))")
    if name.lower() in BUILT_IN:
        raise AvatarError(f"\"{name}\" is a built-in avatar's name: pick another")
    dest = os.path.join(root, name)
    if os.path.exists(dest):
        raise AvatarError(f"there's already an avatar called {name}")
    os.makedirs(root, exist_ok=True)
    if os.path.isdir(src):
        total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(src) for f in fs)
        if total > MAX_BYTES:
            raise AvatarError(f"too big ({total // 2**20} MB; the limit is {MAX_BYTES // 2**20} MB)")
        shutil.copytree(src, dest)
    elif zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            infos = z.infolist()
            if sum(i.file_size for i in infos) > MAX_BYTES:
                raise AvatarError(f"too big unpacked (the limit is {MAX_BYTES // 2**20} MB)")
            base = os.path.abspath(dest)
            for i in infos:
                target = os.path.abspath(os.path.join(base, i.filename))
                if not (target == base or target.startswith(base + os.sep)):
                    raise AvatarError(f"the zip has a path that points outside its folder: {i.filename}")
            z.extractall(dest)
    else:
        raise AvatarError("pick a folder or a .zip")
    model = find_model(dest)
    if not model:
        _put_aside(dest)
        raise AvatarError("no .model3.json in it (only Live2D Cubism 3/4 models; Cubism 2 isn't supported)")
    gone = missing_files(model)
    if gone:
        _put_aside(dest)
        raise AvatarError("the model needs files that aren't there: " + ", ".join(gone[:5]))
    info = inspect(model)
    info["name"] = name
    return info


def _put_aside(folder):
    aside = os.path.join(os.path.dirname(folder), ".refused")
    os.makedirs(aside, exist_ok=True)
    target = os.path.join(aside, os.path.basename(folder))
    n = 1
    while os.path.exists(target):
        n += 1
        target = os.path.join(aside, f"{os.path.basename(folder)}-{n}")
    shutil.move(folder, target)
