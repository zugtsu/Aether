import base64
import hashlib
import json
import os
import queue
import random
import re
import socket
import ssl
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .config import DATA_DIR
from .engine import audit, log
from .proc import NO_WINDOW
from .names import fill

API = "https://discord.com/api/v10"
GATEWAY = "wss://gateway.discord.gg"
INTENTS = (1 << 0) | (1 << 9) | (1 << 12) | (1 << 15)
FATAL = {4004: "the bot token was rejected", 4010: "invalid shard", 4011: "sharding required", 4012: "invalid API version",
         4013: "invalid intents", 4014: "Message Content intent isn't enabled for this bot (Discord developer portal)"}


class WSClosed(Exception):
    def __init__(self, code):
        super().__init__(f"closed {code}")
        self.code = code


class Fatal(Exception):
    pass


class WebSocket:
    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, url, timeout=30):
        u = urllib.parse.urlparse(url)
        host, port = u.hostname, u.port or 443
        path = (u.path or "/") + ("?" + u.query if u.query else "")
        raw = socket.create_connection((host, port), timeout=timeout)
        self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: Aether\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("gateway closed during handshake")
            resp += chunk
        head, self.buf = resp.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise ConnectionError("gateway refused: " + head.split(b"\r\n")[0].decode(errors="replace"))
        want = base64.b64encode(hashlib.sha1((key + self.GUID).encode()).digest()).decode().lower()
        if want not in head.decode(errors="replace").lower():
            raise ConnectionError("gateway handshake didn't verify")
        self.sock.settimeout(None)
        self.lock = threading.Lock()

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WSClosed(1006)
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        msg = b""
        while True:
            b1, b2 = self._read(2)
            fin, op, masked, n = b1 & 0x80, b1 & 0x0F, b2 & 0x80, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if masked else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 0x8:
                raise WSClosed(struct.unpack(">H", data[:2])[0] if len(data) >= 2 else 1005)
            if op == 0x9:
                self._send(0xA, data)
                continue
            if op == 0xA:
                continue
            msg += data
            if fin:
                return msg.decode("utf-8")

    def _send(self, op, data):
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else
                                      bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else
                                      bytes([0x80 | 127]) + struct.pack(">Q", n))
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        with self.lock:
            self.sock.sendall(head + mask + body)

    def send(self, obj):
        self._send(0x1, json.dumps(obj).encode("utf-8"))

    def close(self, code=1000):
        try:
            self._send(0x8, struct.pack(">H", code))
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class Discord:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.ws = None
        self.thread = None
        self.stop_flag = threading.Event()
        self.queue = queue.Queue()
        self.seq = None
        self.session_id = None
        self.resume_url = None
        self.user_id = None
        self.username = ""
        self.connected = False
        self.error = ""
        self.acked = True
        self.dm_channels = {}
        self.channel_names = {}

    def token(self):
        return self.app.vault.get("DISCORD_BOT_TOKEN")

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        if not self.token():
            self.error = "no DISCORD_BOT_TOKEN in the vault (Settings -> Discord -> How to set up a Discord bot)"
            return
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self):
        self.stop_flag.set()
        self.queue.put(None)
        if self.ws:
            self.ws.close()
        self.connected = False

    def status(self):
        return {"enabled": self.cfg.discord_enabled, "connected": self.connected, "bot": self.username,
                "error": self.error, "has_token": bool(self.token())}

    def _run(self):
        backoff = 1
        while not self.stop_flag.is_set():
            try:
                self._session()
                backoff = 1
            except Fatal as e:
                self.error = str(e)
                self.connected = False
                log(f"discord: stopped: {e}")
                return
            except Exception as e:
                self.connected = False
                if self.stop_flag.is_set():
                    return
                self.error = f"reconnecting ({e})"
                log(f"discord: {e!r}; reconnecting in {backoff}s")
                self.stop_flag.wait(backoff)
                backoff = min(60, backoff * 2)

    def _session(self):
        base = self.resume_url if (self.session_id and self.resume_url) else GATEWAY
        ws = self.ws = WebSocket(base.rstrip("/") + "/?v=10&encoding=json")
        try:
            hello = json.loads(ws.recv())
            interval = hello["d"]["heartbeat_interval"] / 1000.0
            beat_stop = threading.Event()
            self.acked = True
            threading.Thread(target=self._heartbeat, args=(ws, interval, beat_stop), daemon=True).start()
            if self.session_id and self.seq is not None:
                ws.send({"op": 6, "d": {"token": self.token(), "session_id": self.session_id, "seq": self.seq}})
            else:
                ws.send({"op": 2, "d": {"token": self.token(), "intents": INTENTS,
                                        "properties": {"os": "windows", "browser": "aether", "device": "aether"}}})
            while not self.stop_flag.is_set():
                p = json.loads(ws.recv())
                if p.get("s") is not None:
                    self.seq = p["s"]
                op = p.get("op")
                if op == 0:
                    self._dispatch(p.get("t"), p.get("d") or {})
                elif op == 1:
                    ws.send({"op": 1, "d": self.seq})
                elif op == 7:
                    raise ConnectionError("Discord asked for a reconnect")
                elif op == 9:
                    if not p.get("d"):
                        self.session_id, self.seq, self.resume_url = None, None, None
                    time.sleep(1 + random.random() * 4)
                    raise ConnectionError("session no longer valid")
                elif op == 11:
                    self.acked = True
        except WSClosed as e:
            if e.code in FATAL:
                raise Fatal(FATAL[e.code])
            if e.code in (4007, 4009):
                self.session_id, self.seq, self.resume_url = None, None, None
            raise ConnectionError(f"gateway closed ({e.code})")
        finally:
            try:
                beat_stop.set()
            except NameError:
                pass
            ws.close(4000)
            self.connected = False

    def _heartbeat(self, ws, interval, stop):
        if stop.wait(interval * random.random()):
            return
        while not stop.is_set():
            if not self.acked:
                ws.close(4000)
                return
            self.acked = False
            try:
                ws.send({"op": 1, "d": self.seq})
            except Exception:
                return
            if stop.wait(interval):
                return

    def _dispatch(self, t, d):
        if t == "READY":
            self.user_id = d["user"]["id"]
            self.username = d["user"].get("username", "")
            self.session_id = d.get("session_id")
            self.resume_url = d.get("resume_gateway_url")
            self.connected, self.error = True, ""
            log(f"discord: connected as {self.username}")
        elif t == "RESUMED":
            self.connected, self.error = True, ""
        elif t == "MESSAGE_CREATE":
            if self.wants(d):
                self.queue.put(d)

    def is_owner(self, uid):
        return str(uid) in [str(x) for x in self.cfg.discord_owner_ids]

    def wants(self, d):
        a = d.get("author") or {}
        if not a or a.get("id") == self.user_id:
            return False
        if a.get("bot") and not self.cfg.discord_allow_bots:
            return False
        if not d.get("guild_id"):
            return self.is_owner(a["id"]) or self.cfg.discord_dm_policy == "open"
        if str(d.get("channel_id")) not in [str(x) for x in self.cfg.discord_channels]:
            return False
        mentioned = any(m.get("id") == self.user_id for m in d.get("mentions") or [])
        replied = ((d.get("referenced_message") or {}).get("author") or {}).get("id") == self.user_id
        return mentioned or replied

    def _worker(self):
        while not self.stop_flag.is_set():
            d = self.queue.get()
            if d is None:
                return
            try:
                self.handle(d)
            except Exception as e:
                log(f"discord: handling a message failed: {e!r}")

    def handle(self, d):
        a = d["author"]
        owner = self.is_owner(a["id"])
        name = a.get("global_name") or a.get("username") or "someone"
        dm = not d.get("guild_id")
        text = re.sub(r"<@!?%s>" % re.escape(self.user_id or "x"), "", d.get("content") or "").strip()
        conv_id = f"discord-{d['channel_id']}"
        if dm:
            title, place = f"Discord DM · {name}", ("Discord DM" if owner else f"Discord DM from {name}")
        else:
            cname = self.channel_name(d["channel_id"])
            title, place = f"Discord #{cname}", f"Discord #{cname}" + ("" if owner else f", {name}")
        images, voice, tone = [], False, ""
        for att in d.get("attachments") or []:
            ctype = att.get("content_type") or ""
            if ctype.startswith("image/") and len(images) < 4 and att.get("size", 0) < 12e6:
                images.append(self.download(att, conv_id))
            elif ctype.startswith("audio/") and att.get("size", 0) < 20e6:
                heard = self.hear(self.download(att, conv_id))
                if heard.get("text"):
                    text = (text + " " + heard["text"]).strip()
                    voice, tone = True, heard.get("tone", "")
        if not text and not images:
            return
        stop_typing = threading.Event()
        threading.Thread(target=self._typing, args=(d["channel_id"], stop_typing), daemon=True).start()
        try:
            reply = self.app.run_turn(conv_id, text or "(picture)", place, images=images, voice=voice, tone=tone,
                                      stranger=not owner, title=title)
        finally:
            stop_typing.set()
        if reply and reply.strip():
            if not owner:
                reply = self.guard(reply, name)
            ref = None if dm else d["id"]
            self.send(d["channel_id"], reply, reply_to=ref)
            if voice and owner:
                try:
                    if self.app.voice.ensure_running():
                        self.send_file(d["channel_id"], "voice.mp3", self.app.voice.synth(reply[:1500]))
                except Exception as e:
                    log(f"discord: voice reply failed: {e!r}")

    def guard(self, reply, who):
        from . import guard
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt_template.md"), encoding="utf-8") as f:
                template = f.read()
        except OSError:
            template = ""
        clean, dropped = guard.stranger_reply(reply, self.app.engine.memory.root, getattr(self.app, "vault", None), [template])
        for s, why in dropped:
            log(f"discord: kept from {who}: {why} | {s[:120]}")
        if dropped:
            audit({"chat": "discord", "place": f"stranger {who}", "step": {"step": "guard"}, "ok": True,
                   "result": f"{len(dropped)} sentence(s) kept private: " + "; ".join(w for _, w in dropped)[:300]})
        return clean

    def _typing(self, channel, stop):
        while not stop.is_set():
            try:
                self.rest("POST", f"/channels/{channel}/typing")
            except Exception:
                pass
            stop.wait(8)

    def channel_name(self, cid):
        if cid not in self.channel_names:
            try:
                self.channel_names[cid] = self.rest("GET", f"/channels/{cid}").get("name") or cid
            except Exception:
                self.channel_names[cid] = cid
        return self.channel_names[cid]

    def download(self, att, conv_id):
        folder = os.path.join(DATA_DIR, "attachments", conv_id)
        os.makedirs(folder, exist_ok=True)
        name = re.sub(r"[^\w.-]", "_", att.get("filename") or "file")[-60:]
        path = os.path.join(folder, time.strftime("%H%M%S-") + name)
        req = urllib.request.Request(att["url"], headers={"User-Agent": "Aether"})
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
            f.write(r.read(25 * 1024 * 1024))
        return path

    def hear(self, path):
        wav = path + ".wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", wav],
                       capture_output=True, timeout=120, creationflags=NO_WINDOW)
        if not os.path.exists(wav):
            return {}
        try:
            return self.app.ears.hear(wav)
        except Exception as e:
            log(f"discord: couldn't hear a voice message: {e!r}")
            return {}

    def rest(self, method, path, body=None, files=None):
        tok = self.token()
        headers = {"Authorization": f"Bot {tok}", "User-Agent": "DiscordBot (https://127.0.0.1, 0.1) Aether"}
        data = None
        if files:
            boundary = uuid.uuid4().hex
            parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json\r\n\r\n'
                     .encode() + json.dumps(body or {}).encode() + b"\r\n"]
            for i, (fname, blob, ctype) in enumerate(files):
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files[{i}]"; filename="{fname}"\r\n'
                             f"Content-Type: {ctype}\r\n\r\n".encode() + blob + b"\r\n")
            data = b"".join(parts) + f"--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        elif method == "POST":
            data = b""
        for _ in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(API + path, data, headers, method=method), timeout=30) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                raw = e.read()
                if e.code == 429:
                    try:
                        wait = float(json.loads(raw).get("retry_after", 1))
                    except ValueError:
                        wait = 1.0
                    time.sleep(wait + 0.2)
                    continue
                raise RuntimeError(f"Discord said {e.code}: {raw[:200].decode(errors='replace')}")
        raise RuntimeError("Discord kept rate-limiting")

    @staticmethod
    def chunks(text, size=1900):
        out, cur, fence = [], "", ""
        for para in text.split("\n"):
            closing = bool(fence) and para.strip().startswith("```")
            pieces = [para[i:i + size - 20] for i in range(0, len(para), size - 20)] or [""]
            for piece in pieces:
                close = "\n```" if fence and not closing else ""
                if cur and len(cur) + 1 + len(piece) + len(close) > size:
                    if closing:
                        out.append(cur + "\n```")
                        cur, piece = "", None
                    else:
                        out.append(cur + close)
                        cur = fence
                if piece is not None:
                    cur = (cur + "\n" + piece) if cur else piece
            if para.strip().startswith("```"):
                fence = "" if fence else para.strip()
        if cur.strip() and cur.strip() != fence:
            out.append(cur)
        return [c for c in out if c.strip()]

    NO_PREVIEWS = 1 << 2

    def send(self, channel, text, reply_to=None):
        text = self.app.vault.scrub(fill(text, self.cfg))
        for i, part in enumerate(self.chunks(text)):
            body = {"content": part, "allowed_mentions": {"parse": []}, "flags": self.NO_PREVIEWS}
            if reply_to and i == 0:
                body["message_reference"] = {"message_id": reply_to, "fail_if_not_exists": False}
            self.rest("POST", f"/channels/{channel}/messages", body)

    def send_file(self, channel, fname, blob, text="", ctype="audio/mpeg"):
        self.rest("POST", f"/channels/{channel}/messages", {"content": text, "allowed_mentions": {"parse": []},
                                                            "flags": self.NO_PREVIEWS}, files=[(fname, blob, ctype)])

    def _owner_dm(self):
        if not (self.connected and self.cfg.discord_mirror and self.cfg.discord_owner_ids):
            return None
        uid = str(self.cfg.discord_owner_ids[0])
        if uid not in self.dm_channels:
            self.dm_channels[uid] = self.rest("POST", "/users/@me/channels", {"recipient_id": uid})["id"]
        return self.dm_channels[uid]

    def dm_owner(self, text):
        try:
            ch = self._owner_dm()
            if not ch:
                return False
            self.send(ch, text)
            return True
        except Exception as e:
            log(f"discord: DM to the user failed: {e!r}")
            return False

    def dm_owner_file(self, fname, blob, text="", ctype="image/png"):
        try:
            ch = self._owner_dm()
            if not ch:
                return False
            self.send_file(ch, fname, blob, self.app.vault.scrub(fill(text, self.cfg))[:1900], ctype)
            return True
        except Exception as e:
            log(f"discord: picture to the user failed: {e!r}")
            return False

