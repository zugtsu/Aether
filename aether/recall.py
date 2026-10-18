import array
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import urllib.request

from .brainmap import split_memories
from .config import DATA_DIR
from .history import NOT_USER, Conversation, list_conversations, said, stranger


INDEX = os.path.join(DATA_DIR, "recall.json")
VECS = os.path.join(DATA_DIR, "recall.bin")
SCHEMA = """
create table if not exists pieces (id integer primary key, key text unique not null, kind text not null, text text not null,
                                   place text, chat text, ts text, vec blob not null);
create virtual table if not exists pieces_fts using fts5(text, content='pieces', content_rowid='id',
                                                          tokenize='porter unicode61');
"""
VEC_SCHEMA = "create virtual table if not exists pieces_vec using vec0(embedding float[768] distance_metric=cosine)"
VEC_MOST = 4096


def load_vec(db):
    import sqlite_vec
    db.enable_load_extension(True)
    try:
        sqlite_vec.load(db)
    finally:
        db.enable_load_extension(False)


def db_path():
    return os.path.splitext(INDEX)[0] + ".db"


def copy_index(dst_index):
    import shutil
    dst_db = os.path.splitext(dst_index)[0] + ".db"
    if os.path.exists(db_path()):
        src, dst = sqlite3.connect(db_path()), sqlite3.connect(dst_db)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
    for src, dst in ((INDEX, dst_index), (VECS, os.path.splitext(dst_index)[0] + ".bin")):
        if os.path.exists(src):
            shutil.copy2(src, dst)
MODEL_FILE = os.path.join(DATA_DIR, "recall_model.json")
PROBE = "search_document: Aether checks which model made these numbers."
MODEL = "text-embedding-nomic-embed-text-v1.5"
DIMS = 768
HYBRID_K = 4
HYBRID_MAX = 10


PIECE = 600


def chunks(text, size=PIECE, overlap=100):
    if len(text) <= size:
        return [text] if text else []
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind(" ", start + size // 2, end)
            end = cut if cut > 0 else end
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        back = text.rfind(" ", end - overlap, end)
        start = back + 1 if back > start else end
    return out


PART = re.compile(r"\s*(?:[-*•]\s+|\d+[.)]\s+|\*\*[^*\n]{1,80}\*\*)")
HEADING = re.compile(r"\s*#{1,4}\s+")


def sections(text, most=40):
    out, cur, heading, lead = [], None, "", ""

    def clean(s):
        return " ".join(s.replace("**", "").replace("#", "").split())

    def flush():
        body = clean(" ".join(cur or []))
        if len(body) >= 12:
            under = " / ".join(x[:100].rstrip(":") for x in (heading, lead) if x)
            out.extend(chunks((under + ": " if under else "") + body))

    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if HEADING.match(line):
            flush()
            cur, heading, lead = None, clean(s), ""
        elif PART.match(line):
            flush()
            cur = [re.sub(r"^(?:[-*•]|\d+[.)])\s+", "", s)]
        else:
            flush()
            cur, lead = None, clean(s)
    flush()
    return out[:most] if len(out) >= 2 else []


HER = "Her: "


def speakers(text):
    if text.startswith("{USER}: "):
        text = "{USER} said: " + text[len("{USER}: "):]
    elif text.startswith(HER):
        text = "You said: " + text[len(HER):]
    return text.replace("\n" + HER, "\nYou said: ")


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class Recall:
    def __init__(self, cfg, conv_dir, memory):
        self.cfg = cfg
        self.conv_dir = conv_dir
        self.memory = memory
        self.lock = threading.Lock()
        self.meta = []
        self.vecs = array.array("f")
        self.model_ok = True
        self.model_note = ""
        self._model_checked = False
        self.db = None
        self.vec_ok = False
        self.fts_keys = []
        self._load()

    def _open(self):
        os.makedirs(os.path.dirname(db_path()) or ".", exist_ok=True)
        db = sqlite3.connect(db_path(), check_same_thread=False)
        db.executescript(SCHEMA)
        try:
            load_vec(db)
            db.execute(VEC_SCHEMA)
            self.vec_ok = True
        except Exception as e:
            self.vec_ok = False
            from .engine import log
            log(f"recall: sqlite-vec didn't load ({e!r}); search uses the Python loop")
        return db

    @staticmethod
    def _piece(row):
        key, kind, text, place, chat, ts = row
        m = {"key": key, "kind": kind, "text": text, "where": place or "", "ts": ts or ""}
        if chat:
            m["chat"] = chat
        return m

    def _load(self):
        try:
            self.db = self._open()
            if not self.db.execute("select 1 from pieces limit 1").fetchone():
                self._migrate()
            self._vec_sync()
            rows =self.db.execute("select key, kind, text, place, chat, ts, vec from pieces order by id").fetchall()
        except sqlite3.Error:
            return
        vecs = array.array("f")
        vecs.frombytes(b"".join(r[6] for r in rows))
        if len(vecs) == len(rows) * DIMS:
            self.meta, self.vecs = [self._piece(r[:6]) for r in rows], vecs
            self.fts_keys = [m["key"] for m in self.meta]
        else:
            self._clear()

    def _migrate(self):
        try:
            with open(INDEX, encoding="utf-8") as f:
                meta = json.load(f)
            vecs = array.array("f")
            with open(VECS, "rb") as f:
                vecs.frombytes(f.read())
        except (OSError, ValueError):
            return
        if len(vecs) != len(meta) * DIMS:
            return
        self._insert(meta, [vecs[i * DIMS:(i + 1) * DIMS] for i in range(len(meta))])
        self.db.commit()

    def _insert(self, pieces, vecs):
        for p, v in zip(pieces, vecs):
            cur = self.db.execute("insert into pieces(key, kind, text, place, chat, ts, vec) values (?,?,?,?,?,?,?)",
                                  (p["key"], p["kind"], p["text"], p.get("where", ""), p.get("chat"), p.get("ts", ""),
                                   array.array("f", v).tobytes()))
            self.db.execute("insert into pieces_fts(rowid, text) values (?, ?)", (cur.lastrowid, p["text"]))
            if self.vec_ok:
                self.db.execute("insert into pieces_vec(rowid, embedding) values (?, ?)",
                                (cur.lastrowid, array.array("f", v).tobytes()))

    def _delete(self, keys):
        for key in keys:
            row = self.db.execute("select id, text from pieces where key = ?", (key,)).fetchone()
            if row:
                self.db.execute("insert into pieces_fts(pieces_fts, rowid, text) values ('delete', ?, ?)", row)
                self.db.execute("delete from pieces where id = ?", (row[0],))
                if self.vec_ok:
                    self.db.execute("delete from pieces_vec where rowid = ?", (row[0],))

    def _clear(self):
        self.db.execute("delete from pieces")
        self.db.execute("insert into pieces_fts(pieces_fts) values ('delete-all')")
        if self.vec_ok:
            self.db.execute("delete from pieces_vec")
        self.db.commit()

    def _vec_sync(self):
        if not self.vec_ok:
            return
        try:
            self.db.execute("delete from pieces_vec where rowid not in (select id from pieces)")
            self.db.execute("insert into pieces_vec(rowid, embedding) select id, vec from pieces "
                            "where id not in (select rowid from pieces_vec)")
            self.db.commit()
        except sqlite3.Error as e:
            self.db.rollback()
            self.vec_ok = False
            from .engine import log
            log(f"recall: pieces_vec couldn't be filled ({e!r}); search uses the Python loop")

    NAME_MOST = 6

    def _names_table(self):
        from .cue import stem, words
        if getattr(self, "_names", (None, -1))[1] == len(self.meta):
            return self._names[0]
        caps, lower, df = {}, {}, {}
        for m in self.meta:
            for w in words(m["text"]):
                df[w] = df.get(w, 0) + 1
            for x in re.findall(r"(?<=[a-z] )([A-Za-z][a-z]{3,})\b", m["text"]):
                s = stem(x.lower())
                if x[0].isupper():
                    caps[s] = caps.get(s, 0) + 1
                else:
                    lower[s] = lower.get(s, 0) + 1
        table = {w: n for w, n in df.items() if 2 <= n <= self.NAME_MOST and caps.get(w, 0) >= max(1, lower.get(w, 0))}
        self._names = (table, len(self.meta))
        return table

    def names_in(self, text):
        from .cue import stem
        table = self._names_table()
        return sorted({w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if stem(w) in table})

    def linked(self, piece, have=(), most=2):
        have = set(have)
        out, seen_text = [], {self._dup(m["text"]) for m in self.meta if m["key"] in have}
        seen_text.add(self._dup(piece["text"]))
        by_key = {m["key"]: m for m in self.meta}

        def take(m, why):
            if m and m["key"] not in have and self._dup(m["text"]) not in seen_text and len(out) < most:
                seen_text.add(self._dup(m["text"]))
                out.append((m, why))
        names = self.names_in(piece["text"])
        if names:
            for key in self.keyword(" OR ".join(f'"{w}"' for w in names), k=12):
                m = by_key.get(key)
                if m and m["key"] != piece["key"]:
                    take(m, "the same name: " + (", ".join(w for w in names if w in m["text"].lower()) or "a name"))
        mt = re.match(r"chat:(.+):(\d+)(?::[rls]\d+)?$", piece["key"])
        if mt and len(out) < most:
            from .cue import words
            cid, i = mt.group(1), int(mt.group(2))
            turns = sorted({int(x.group(1)) for x in (re.match(rf"chat:{re.escape(cid)}:(\d+)", k) for k in by_key) if x})
            at = turns.index(i) if i in turns else -1
            mine = words(piece["text"])
            for j in ([turns[at + 1]] if 0 <= at < len(turns) - 1 else []) + ([turns[at - 1]] if at > 0 else []):
                m = by_key.get(f"chat:{cid}:{j}") or by_key.get(f"chat:{cid}:{j}:r0")
                if m and words(m["text"]) & mine:
                    take(m, "the same chat, right next to it")
        return out

    @staticmethod
    def _dup(text):
        return " ".join(str(text).lower().split())[:300]

    def close(self):
        with self.lock:
            if self.db is not None:
                try:
                    self.db.close()
                except sqlite3.Error:
                    pass
                self.db = None

    def fts_ready(self, meta):
        return self.db is not None and len(meta) == len(self.fts_keys) and \
            all(m["key"] == k for m, k in zip(meta, self.fts_keys))

    def keyword(self, expr, k=20):
        with self.lock:
            try:
                ids = [r[0] for r in self.db.execute("select rowid from pieces_fts where pieces_fts match ? order by rank "
                                                     "limit ?", (expr, k))]
                if not ids:
                    return []
                keys = dict(self.db.execute(f"select id, key from pieces where id in ({','.join('?' * len(ids))})", ids))
            except sqlite3.Error:
                return []
        return [keys[i] for i in ids if i in keys]

    def embed(self, texts):
        body = {"model": MODEL, "input": texts}
        req = urllib.request.Request(self.cfg.lmstudio_url.rstrip("/") + "/v1/embeddings", json.dumps(body).encode("utf-8"),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)["data"]
        return [_norm(d["embedding"]) for d in sorted(data, key=lambda d: d["index"])]

    def check_model(self):
        v = self.embed([PROBE])[0]
        if len(v) != DIMS:
            self.model_ok = False
            return (f"search is off: {MODEL} gives {len(v)} numbers per text and the search index holds {DIMS}; "
                    "load the model the index was made with, or rebuild the index for this one")
        self.model_ok = True
        try:
            with open(MODEL_FILE, encoding="utf-8") as f:
                old = json.load(f)
        except (OSError, ValueError):
            old = None
        same = bool(old) and old.get("model") == MODEL and len(old.get("probe") or []) == len(v) and \
            sum(a * b for a, b in zip(old["probe"], v)) >= 0.99999
        note = ""
        if old and not same:
            with self.lock:
                had = len(self.meta)
                self.meta, self.vecs, self.fts_keys = [], array.array("f"), []
                self._clear()
            what = (f"{old.get('model')} -> {MODEL}" if old.get("model") != MODEL else
                    f"{MODEL} gives different numbers now: a new file under the same name?")
            note = f"the search model changed ({what}): reading all {had} pieces again"
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(MODEL_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"model": MODEL, "dims": len(v), "probe": v}, f)
        os.replace(MODEL_FILE + ".tmp", MODEL_FILE)
        return note

    def pieces(self):
        out = []
        for cid in list_conversations(self.conv_dir):
            if cid == "heartbeat":
                continue
            c = Conversation(self.conv_dir, cid)
            title = c.title()
            evs = c.events
            for i, e in enumerate(evs):
                if e["kind"] != "user":
                    continue
                words = said(e["text"])
                if words is None:
                    continue
                reply = next((x for x in evs[i + 1:] if x["kind"] in ("reply", "user")), None)
                his = " ".join(words.split())
                hers = " ".join(reply["text"].split()) if reply and reply["kind"] == "reply" else ""
                base = {"kind": "chat", "where": title, "chat": cid, "ts": e["ts"]}
                who = stranger(e)
                tag = f"{who} said {NOT_USER}: " if who else "{USER}: "
                if not self.cfg.recall_full_text or (len(his) <= PIECE and len(hers) <= PIECE):
                    text = tag + his[:PIECE] + ("\n" + HER + hers[:PIECE] if hers else "")
                    out.append({"key": f"chat:{cid}:{i}", "text": text, **base})
                    continue
                for k, part in enumerate(chunks(his)):
                    out.append({"key": f"chat:{cid}:{i}:r{k}", "text": tag + part, **base})
                head = his[:160] + ("…" if len(his) > 160 else "")
                for k, part in enumerate(chunks(hers)):
                    out.append({"key": f"chat:{cid}:{i}:l{k}", "text": f"{tag}{head}\n{HER}{part}", **base})
                for k, part in enumerate(sections(reply["text"]) if hers else []):
                    out.append({"key": f"chat:{cid}:{i}:s{k}", "text": f"{HER}{part}", **base})
        for f in self.memory.files.values():
            if f.rel.startswith("skills/"):
                continue
            for m in split_memories(f.body):
                m = " ".join(m.split())
                day = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})", m) if f.rel == "system/timeline.md" else None
                ts = f"{day.group(1)}T{day.group(2)}:00" if day else ""
                for part in (chunks(m) if self.cfg.recall_full_text else [m[:PIECE]]):
                    h = hashlib.sha1((f.rel + part).encode("utf-8")).hexdigest()[:12]
                    out.append({"key": f"mem:{h}", "kind": "memory", "text": part, "where": f.rel, "ts": ts})
        for label, path in (getattr(self.cfg, "knowledge_sources", None) or {}).items():
            try:
                with open(os.path.expanduser(path), encoding="utf-8") as fh:
                    body = fh.read()
            except OSError:
                continue
            section = ""
            for block in re.split(r"\n\s*\n", body):
                block = block.strip()
                heading = re.match(r"#+\s*(.+)", block)
                if heading:
                    section = heading.group(1).strip()
                    block = block[heading.end():].strip()
                if len(block) < 20:
                    continue
                text = " ".join(((section + ": ") if section else "") .split() + block.split())
                for part in chunks(text):
                    h = hashlib.sha1((label + part).encode("utf-8")).hexdigest()[:12]
                    out.append({"key": f"src:{h}", "kind": "source", "text": part, "where": label, "ts": ""})
        return out

    def update(self, budget=64):
        if not self._model_checked:
            self.model_note = self.check_model()
            self._model_checked = True
        if not self.model_ok:
            return 0
        want = list({p["key"]: p for p in self.pieces()}.values())
        want_text = {p["key"]: p["text"] for p in want}
        with self.lock:
            gone = [m["key"] for m in self.meta if want_text.get(m["key"]) != m["text"]]
            if gone:
                keep = [i for i, m in enumerate(self.meta) if want_text.get(m["key"]) == m["text"]]
                vecs = array.array("f")
                for i in keep:
                    vecs.extend(self.vecs[i * DIMS:(i + 1) * DIMS])
                self.meta = [self.meta[i] for i in keep]
                self.vecs = vecs
                self._delete(gone)
                self.db.commit()
                self.fts_keys = [m["key"] for m in self.meta]
            have = {m["key"] for m in self.meta}
        todo = [p for p in want if p["key"] not in have]
        batch = todo[:budget]
        for i in range(0, len(batch), 32):
            chunk = batch[i:i + 32]
            vecs = self.embed(["search_document: " + p["text"] for p in chunk])
            with self.lock:
                try:
                    self._insert(chunk, vecs)
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                    raise
                for p, v in zip(chunk, vecs):
                    self.meta.append(p)
                    self.vecs.extend(v)
                self.fts_keys = [m["key"] for m in self.meta]
        return len(todo) - len(batch)

    def search(self, query, k=6, min_score=0.5, kinds=None):
        q = self.embed(["search_query: " + str(query)])[0]
        if not self.model_ok or len(q) != DIMS:
            return []
        with self.lock:
            scored = self._nearest(q, k, kinds) if self.vec_ok and self.fts_ready(self.meta) else None
            if scored is None:
                scored = []
                for i, m in enumerate(self.meta):
                    if kinds and m["kind"] not in kinds:
                        continue
                    v = self.vecs[i * DIMS:(i + 1) * DIMS]
                    scored.append((sum(a * b for a, b in zip(q, v)), m))
        scored.sort(key=lambda x: -x[0])
        return [dict(m, score=round(s, 3)) for s, m in scored[:k] if s >= min_score]

    def _nearest(self, q, k, kinds):
        at = {m["key"]: i for i, m in enumerate(self.meta)}

        def score(i):
            return sum(a * b for a, b in zip(q, self.vecs[i * DIMS:(i + 1) * DIMS]))
        blob, ask = array.array("f", q).tobytes(), k + 10
        while True:
            n = min(ask, VEC_MOST)
            try:
                rows = [at.get(key) for (key,) in self.db.execute(
                    "select p.key from pieces_vec v join pieces p on p.id = v.rowid "
                    "where v.embedding match ? and k = ? order by v.distance", (blob, n))]
            except sqlite3.Error:
                return None
            if None in rows:
                return None
            found = sorted(((score(i), i) for i in rows if not kinds or self.meta[i]["kind"] in kinds),
                           key=lambda x: (-x[0], x[1]))
            if len(rows) < n or (len(found) >= k and found[k - 1][0] - score(rows[-1]) > 1e-4):
                return [(s, self.meta[i]) for s, i in found]
            if n >= VEC_MOST:
                return None
            ask *= 4

    def option(self):
        return {"type": "object", "properties": {"step": {"const": "recall"}, "query": {"type": "string"}},
                "required": ["step", "query"], "additionalProperties": False}

    def run_step(self, step, cue=None, his="", conv_id="", now=None):
        try:
            hits = self.search(step["query"], k=6)
        except Exception as e:
            return False, f"Recall isn't available right now ({e})."
        day, day_rows = "", []
        if cue is not None:
            now = now or dt.datetime.now()
            lists = []
            try:
                for text in ([his] if (his or "").strip() else []) + [step["query"]]:
                    lists.append(list(reversed(cue.search(text, conv_id, now, k=HYBRID_K))))
                for text in ([his] if (his or "").strip() else []) + [step["query"]]:
                    day, day_rows = cue.day_lines(text, now)
                    if day_rows:
                        break
            except Exception:
                lists = []
            lists.append(hits)
            merged, seen = [], set()
            for rank in range(max(len(x) for x in lists)):
                for ranked in lists:
                    if rank < len(ranked) and ranked[rank]["key"] not in seen:
                        seen.add(ranked[rank]["key"])
                        merged.append(ranked[rank])
            hits = merged
        once, texts = [], set()
        for h in hits:
            if self._dup(h["text"]) not in texts:
                texts.add(self._dup(h["text"]))
                once.append(h)
        hits = once[:HYBRID_MAX] if cue is not None else once
        if not hits and not day_rows:
            return True, "Nothing in your past chats or memory matches that."
        lines = [f"Your timeline for {day}:"] + day_rows if day_rows else []
        for h in hits:
            lines.append(self._line(h))
        extra = self.hop(hits) if getattr(self.cfg, "recall_links", False) else []
        if extra:
            lines.append("Linked to those (" + "; ".join(sorted({why for _, why in extra})) + "):")
            lines += [self._line(m) for m, _ in extra]
        return True, "\n".join(lines)

    @staticmethod
    def _line(h):
        when = h["ts"][:10] if h.get("ts") else ""
        where = f"chat \"{h['where']}\"" if h["kind"] == "chat" else h["where"]
        return f"- {when + ' ' if when else ''}{where}: {speakers(h['text'])}"

    def hop(self, hits, top=3, most=4):
        extra, have = [], [h["key"] for h in hits]
        for h in hits[:top]:
            for m, why in self.linked(h, have + [m["key"] for m, _ in extra], most=2):
                if len(extra) < most:
                    extra.append((m, why))
        return extra
