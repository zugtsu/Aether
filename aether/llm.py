import json
import threading
import urllib.error
import urllib.request

from .names import fill
from .schema import response_format


class Cancelled(Exception):
    pass


class LLMError(Exception):
    pass


class LMStudio:
    def __init__(self, cfg):
        self.cfg = cfg
        self.url = cfg.lmstudio_url.rstrip("/") + "/v1/chat/completions"
        self.last_usage = {}
        self.think = set()
        self.think_room = 2500
        self.last_reasoning = ""

    def complete(self, messages, schema, name, temperature, max_tokens, on_text=None, cancel=None):
        messages = fill(messages, self.cfg)
        body = {
            "model": self.cfg.model, "messages": messages, "stream": True,
            "temperature": temperature, "top_p": self.cfg.top_p, "top_k": self.cfg.top_k,
            "max_tokens": max_tokens, "response_format": response_format(schema, name),
            "stream_options": {"include_usage": True},
        }
        if "all" in self.think or name in self.think:
            body["reasoning_effort"] = "high"
            body["max_tokens"] = max_tokens + self.think_room
        else:
            body["reasoning_effort"] = "none"
        self.last_reasoning = ""
        thought = []
        req = urllib.request.Request(self.url, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=self.cfg.request_timeout)
        except urllib.error.HTTPError as e:
            raise LLMError(f"LM Studio said {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
        except OSError as e:
            raise LLMError(f"Can't reach LM Studio at {self.cfg.lmstudio_url}: {e}")
        done = threading.Event()
        if cancel is not None:
            def watch():
                while not done.is_set():
                    if cancel.wait(0.1):
                        try:
                            resp.close()
                        except Exception:
                            pass
                        return
            threading.Thread(target=watch, daemon=True).start()
        out = []
        got_usage = False
        try:
            for raw in resp:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                ev = json.loads(data)
                if ev.get("error"):
                    err = ev["error"]
                    raise LLMError("LM Studio: " + str(err.get("message") if isinstance(err, dict) else err))
                if ev.get("usage"):
                    self.last_usage = ev["usage"]
                    got_usage = True
                for ch in ev.get("choices") or []:
                    thought.append((ch.get("delta") or {}).get("reasoning_content") or "")
                    piece = (ch.get("delta") or {}).get("content") or ""
                    if piece:
                        out.append(piece)
                        if on_text:
                            on_text(piece)
        except (OSError, ValueError, AttributeError):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            raise
        finally:
            done.set()
            self.last_reasoning = "".join(thought)
            try:
                resp.close()
            except Exception:
                pass
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if not got_usage:
            chars, pics = 0, 0
            for m in messages:
                c = m.get("content")
                if isinstance(c, str):
                    chars += len(c)
                else:
                    for part in c or []:
                        if part.get("type") == "text":
                            chars += len(part.get("text", ""))
                        else:
                            pics += 1
            self.last_usage = {"prompt_tokens": chars // 4 + pics * 256, "estimated": True}
        return "".join(out)

    def read_ahead(self, messages):
        body = {"model": self.cfg.model, "messages": fill(messages, self.cfg), "stream": False, "max_tokens": 1,
                "temperature": 0}
        req = urllib.request.Request(self.url, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.request_timeout) as r:
                r.read()
        except urllib.error.HTTPError as e:
            raise LLMError(f"LM Studio said {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
        except OSError as e:
            raise LLMError(f"Can't reach LM Studio at {self.cfg.lmstudio_url}: {e}")

    def models(self):
        with urllib.request.urlopen(self.cfg.lmstudio_url.rstrip("/") + "/api/v0/models", timeout=5) as r:
            return json.load(r).get("data", [])


class ScriptedLLM:

    def __init__(self, answers, chunk=7):
        self.answers = list(answers)
        self.calls = []
        self.read_aheads = []
        self.chunk = chunk
        self.last_usage = {}

    def read_ahead(self, messages):
        self.read_aheads.append(messages)

    def complete(self, messages, schema, name, temperature, max_tokens, on_text=None, cancel=None):
        self.calls.append({"messages": messages, "schema": schema, "name": name, "temperature": temperature})
        if not self.answers:
            raise LLMError("ScriptedLLM ran out of answers")
        a = self.answers.pop(0)
        if callable(a):
            a = a(messages, cancel)
        text = a if isinstance(a, str) else json.dumps(a)
        for i in range(0, len(text), self.chunk):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if on_text:
                on_text(text[i:i + self.chunk])
        return text
