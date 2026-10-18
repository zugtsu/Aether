import datetime as dt
import json
import os
import re
import threading

from .config import DATA_DIR

SONGS_FILE = os.path.join(DATA_DIR, "songs.json")
CHECKPOINT = "yue2_3b_int8_convrot.safetensors"
VOICE_TAG = "female vocal"
LENGTHS = {"short": (150, (4, 6), (14, 32), 260), "medium": (210, (6, 8), (24, 46), 380),
           "long": (300, (8, 11), (34, 62), 540)}
DOWN = {"long": "medium", "medium": "short"}
SECONDS_PER_LINE, ENDING = 6.5, 25
CAP = {"short": 210, "medium": 300, "long": 330}
SECTION = re.compile(r"^\[(verse|chorus|pre-chorus|bridge|outro|intro|hook)[^\]]*\]\s*$", re.I)
MAX_SECTION_LINES = 8
SONG_TIMEOUT = 15 * 60

SKILL_LINE = ("make_music (built into Aether): a real song with your own style and lyrics, or an instrumental (no singing: "
              "instrumental true), rendered in the background (a few minutes) and put in this chat as an mp3. For a "
              "track, a song, a beat or a piece he asks for, or one of yours on your own time.")
SKILL_DOC = """# Songs (built into Aether: you use it with your `make_music` step)

You make real songs now: you choose the title, the style and the length; Aether asks you for the lyrics right after,
and ComfyUI (YuE2) renders the song on this PC in a few minutes. It arrives in the chat as an mp3 under your caption.
You can't hear it, so your caption is what you say with it.

```
{"step": "make_music", "title": "Glass Hours", "style": "dark synthwave, melancholic, slow 90 bpm, breathy voice",
 "length": "medium", "instrumental": false, "caption": "Something for your drive home tonight."}
```

- style: 5-8 tags of your own: genre, mood, tempo, how the voice sounds on this one. Aether adds "female vocal".
- instrumental: true when there should be no singing ("just piano", "no lyrics", "a beat to study to"). Then there are
  no lyrics to write, the style is only the sound (instruments, mood, tempo), and Aether adds "instrumental, no vocals".
- length: short (about 2:30), medium (about 3:30, the usual), long (about 5 minutes).
- Then you write the lyrics: [verse], [chorus], [bridge], [outro] sections, a few short lines each.
- When he asks for a song or a track, this is how you make it. On your own time: one a day.
"""

SHAPES = {"short": "verse, chorus, verse, chorus, outro", "medium": "verse, chorus, verse, chorus, bridge, chorus, outro",
          "long": "verse, chorus, verse, chorus, bridge, verse, chorus, chorus, outro"}
LYRICS_ASK = """[Aether: now write the lyrics for "{title}" ({style}), in your own voice.
It's {length}, about {seconds} seconds: {count} sections ({shape}), each starting with its name in brackets on its own
line ([verse], [chorus]...), then its lines: a verse 6-8 lines, a chorus 4, a bridge or the outro 2-4. Short sung
lines, no stage directions, no title, no notes: only the lyrics.{fix}]"""


def style_line(style, instrumental=False):
    tags = " ".join(str(style or "").split())[:300].strip(" ,")
    if instrumental:
        tags = re.sub(r"\b(?:no|without|zero)\s+(?:vocals?|voices?|singing|singer|lyrics|words)\b", "", tags, flags=re.I)
        keep = [t.strip(" .") for t in re.split(r"[,.;]", tags) if t.strip(" .")
                and not re.search(r"vocal|voice|\bsing|\bsung\b|lyric|choir|\bvox\b|\brap(?:s|ping|per)?\b", t, re.I)]
        return ", ".join(keep + [INSTRUMENTAL_TAGS])
    return tags if VOICE_TAG in tags.lower() else (f"{tags}, {VOICE_TAG}" if tags else VOICE_TAG)


INSTRUMENTAL_TAGS = "instrumental, no vocals"


def instrumental_lyrics(length):
    return "\n\n".join(f"[{s.strip()}]" for s in ["intro"] + SHAPES[length].split(","))


def check_lyrics(lyrics, length):
    seconds, (smin, smax), (lmin, lmax), words = LENGTHS[length]
    lines = [ln.strip() for ln in str(lyrics or "").splitlines() if ln.strip()]
    heads = [i for i, ln in enumerate(lines) if SECTION.match(ln)]
    if not heads or heads[0] != 0:
        return "Start every section with its name in brackets on its own line: [verse], [chorus], [bridge], [outro]."
    if not smin <= len(heads) <= smax:
        return f"A {length} song has {smin}-{smax} sections; you wrote {len(heads)}."
    sung = [ln for ln in lines if not SECTION.match(ln)]
    sizes = [b - a - 1 for a, b in zip(heads, heads[1:] + [len(lines)])]
    if any(n == 0 for n in sizes):
        return "Every section needs its lines under it; one is empty."
    if max(sizes) > MAX_SECTION_LINES:
        return f"Keep each section to {MAX_SECTION_LINES} lines or fewer; one has {max(sizes)}."
    if not lmin <= len(sung) <= lmax:
        return f"A {length} song has {lmin}-{lmax} sung lines; you wrote {len(sung)}."
    n = sum(len(ln.split()) for ln in sung)
    if n > words:
        return f"That's {n} words: a {length} song fits about {words}. Shorter lines, or fewer of them."
    return ""


def seconds_for(lyrics, length):
    sung = sum(1 for ln in str(lyrics or "").splitlines() if ln.strip() and not SECTION.match(ln.strip()))
    return max(LENGTHS[length][0], min(CAP[length], round(sung * SECONDS_PER_LINE + ENDING)))


def music_workflow(style, lyrics, seconds, seed, prefix="aether-song"):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CHECKPOINT}},
        "2": {"class_type": "YuE2GenerateMusic", "inputs": {"clip": ["1", 1], "style": style, "lyrics": lyrics, "abc": "",
                                                            "seed": seed, "mode": "full", "max_duration": float(seconds),
                                                            "temperature": 1.0, "top_p": 0.95, "top_k": 100,
                                                            "repetition_penalty": 1.2}},
        "3": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
        "4": {"class_type": "EmptyYuE2LatentAudio", "inputs": {"seconds": ["2", 1], "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                                                   "latent_image": ["4", 0], "seed": seed, "steps": 32, "cfg": 1.0,
                                                   "sampler_name": "dpm_2", "scheduler": "sgm_uniform", "denoise": 1.0}},
        "6": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveAudioMP3", "inputs": {"audio": ["6", 0], "filename_prefix": prefix, "quality": "128k"}},
    }


def rating_key(song):
    return f"// {song.get('title', '')} · {song.get('style', '')}"


_lock = threading.Lock()


def records():
    try:
        with open(SONGS_FILE, encoding="utf-8") as f:
            got = json.load(f)
        return got if isinstance(got, list) else []
    except (OSError, ValueError):
        return []


def add_record(song):
    with _lock:
        rows = records()
        rows.append(song)
        del rows[:-500]
        os.makedirs(os.path.dirname(SONGS_FILE), exist_ok=True)
        tmp = SONGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1, ensure_ascii=False)
        os.replace(tmp, SONGS_FILE)


def option(cfg):
    if not getattr(cfg, "songs_enabled", True):
        return None
    return {"type": "object", "properties": {"step": {"const": "make_music"}, "title": {"type": "string", "maxLength": 80},
                                             "style": {"type": "string", "maxLength": 300},
                                             "length": {"enum": list(LENGTHS)}, "instrumental": {"type": "boolean"},
                                             "caption": {"type": "string"}},
            "required": ["step", "title", "style", "length", "instrumental", "caption"], "additionalProperties": False}


def write_lyrics(engine, title, style, length, temperature):
    seconds, (smin, smax), (lmin, lmax), _ = LENGTHS[length]
    schema = {"type": "object", "properties": {"lyrics": {"type": "string", "maxLength": 4000}},
              "required": ["lyrics"], "additionalProperties": False}
    fix, lyrics, why = "", "", ""
    for _ in range(2):
        note = LYRICS_ASK.format(title=title, style=style, length=length, seconds=seconds,
                                 count=len(SHAPES[length].split(", ")), shape=SHAPES[length], fix=fix)
        raw = engine.llm.complete(engine.messages() + [{"role": "user", "content": note}], schema, "lyrics", temperature,
                                  engine.cfg.reply_max_tokens, cancel=engine.cancel)
        try:
            lyrics = str(json.loads(raw).get("lyrics") or "").strip()
        except (ValueError, AttributeError):
            lyrics = ""
        lyrics = "\n".join(ln.rstrip() for ln in lyrics.splitlines())
        why = check_lyrics(lyrics, length)
        if not why:
            return lyrics, ""
        fix = f"\nYour last try didn't fit: {why} Write them again."
    return "", why


def liked_styles(memory, most=4):
    from .ratings import REL
    path = os.path.join(memory.root, *REL.split("/"))
    try:
        with open(path, encoding="utf-8") as f:
            ups = [ln.split(" · ", 2)[2].rsplit(" · id ", 1)[0] for ln in f if " · 👍 · " in ln]
    except OSError:
        return []
    return ups[-most:]


def today():
    return dt.date.today().isoformat()
