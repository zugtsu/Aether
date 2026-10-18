import datetime as dt
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

from .engine import log
from .proc import NO_WINDOW

HER_CONTEXT = 65536
MIN_CONTEXT = 32768
LOAD_TIMEOUT = 300
LMS = os.path.join(os.path.expanduser("~"), ".lmstudio", "bin", "lms.exe")
GIB = 1024 ** 3


class BrainError(Exception):
    pass


def parse_estimate(text):
    m = re.search(r"Estimated GPU Memory:\s*([\d.]+)\s*GiB", re.sub(r"\x1b\[[0-9;]*m", "", text or ""))
    return float(m.group(1)) if m else None


class Brain:
    def __init__(self, app, lms=LMS):
        self.app = app
        self.cfg = app.cfg
        self.lms = lms
        self.lock = threading.Lock()
        self.state = {"phase": "idle"}
        self.previous = None

    def _url(self, path):
        return self.cfg.lmstudio_url.rstrip("/") + path

    def _get(self, path, timeout=5):
        with urllib.request.urlopen(self._url(path), timeout=timeout) as r:
            return json.load(r)

    def _post(self, path, body, timeout=60):
        req = urllib.request.Request(self._url(path), json.dumps(body).encode("utf-8"),
                                     {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise BrainError(f"LM Studio said {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
        except OSError as e:
            raise BrainError(f"Can't reach LM Studio at {self.cfg.lmstudio_url}: {e}")

    def models(self):
        try:
            raw = self._get("/api/v1/models").get("models") or []
        except (OSError, ValueError) as e:
            raise BrainError(f"Can't reach LM Studio at {self.cfg.lmstudio_url}: {e}")
        want = self.current_key()
        out = []
        for m in raw:
            if m.get("type") != "llm":
                continue
            inst = (m.get("loaded_instances") or [None])[0]
            caps = m.get("capabilities") or {}
            out.append({"key": m.get("key"), "name": m.get("display_name") or m.get("key"),
                        "params": m.get("params_string") or "", "quant": (m.get("quantization") or {}).get("name", ""),
                        "size_gb": round((m.get("size_bytes") or 0) / GIB, 2),
                        "max_context": m.get("max_context_length") or 0,
                        "vision": bool(caps.get("vision")), "tools": bool(caps.get("trained_for_tool_use")),
                        "loaded": inst is not None, "instance": inst.get("id") if inst else None,
                        "config": inst.get("config") if inst else None,
                        "current": m.get("key") == want or bool(inst and inst.get("id") == want)})
            out[-1]["refused"], out[-1]["warnings"] = self.problems(out[-1])
        return out

    def current_key(self):
        return str(self.cfg.model).split("/")[-1]

    @staticmethod
    def problems(m):
        if m["max_context"] and m["max_context"] < MIN_CONTEXT:
            return (f"{m['name']} holds at most {m['max_context']:,} tokens: too small (its prompt and a chat "
                    f"need {MIN_CONTEXT:,}+)."), []
        warn = []
        if not m["vision"]:
            warn.append("it can't see pictures: the ones you paste and the ones Aether draws would be text only")
        if not m["tools"]:
            warn.append("it wasn't trained for tool use: steps may come out wrong more often")
        return "", warn

    def estimate(self, key):
        if not os.path.isfile(self.lms):
            return None
        try:
            r = subprocess.run([self.lms, "load", key, "--estimate-only", "-y"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=90, creationflags=NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return parse_estimate(r.stdout)

    def check(self, key, vram=None):
        ms = self.models()
        m = next((x for x in ms if x["key"] == key), None)
        if m is None:
            raise BrainError(f"{key} isn't one of the models LM Studio has downloaded.")
        refused, warnings = self.problems(m)
        needs = self.estimate(key) if not refused else None
        free = None
        if vram and vram.get("total"):
            gemma = sum(p["bytes"] for p in vram.get("parts", []) if p["name"] == "Gemma")
            free = round((vram["total"] - vram["used"] + gemma) / GIB, 2)
        fits = None if needs is None or free is None else needs <= free
        if fits is False:
            warnings.append(f"it needs about {needs:.1f} GB of graphics memory and about {free:.1f} GB would be free: "
                            "it may load partly into regular memory (slow), or not at all")
        return {"model": m, "refused": refused, "warnings": warnings, "needs_gb": needs, "free_gb": free, "fits": fits}

    def busy(self):
        return self.state.get("phase") in ("unloading", "loading", "back")

    def busy_text(self):
        s = self.state
        secs = int(time.time() - s.get("started", time.time()))
        return f"The brain is loading ({s.get('to', '')}, {secs} s so far). Your message can go in a moment."

    def _set(self, **kw):
        self.state = {**self.state, **kw}
        self.app.broadcast({"type": "brain", **self.state})

    def _load(self, key, max_context):
        body = {"model": key, "context_length": min(HER_CONTEXT, max_context or HER_CONTEXT), "flash_attention": True,
                "echo_load_config": True}
        r = self._post("/api/v1/models/load", body, timeout=LOAD_TIMEOUT)
        if r.get("status") != "loaded":
            raise BrainError(f"LM Studio didn't load {key}: {json.dumps(r)[:200]}")
        loaded = next((m for m in self.models() if m["key"] == key and m["loaded"]), None)
        if loaded is None:
            raise BrainError(f"LM Studio says {key} loaded, but it isn't in its list of loaded models.")
        return loaded

    def swap(self, key, wait=120):
        if not self.lock.acquire(blocking=False):
            raise BrainError("A swap is already running.")
        try:
            ms = self.models()
            new = next((m for m in ms if m["key"] == key), None)
            if new is None:
                raise BrainError(f"{key} isn't one of the models LM Studio has downloaded.")
            refused, _ = self.problems(new)
            if refused:
                raise BrainError(refused)
            old = [m for m in ms if m["loaded"]]
            before = next((m for m in ms if m["current"]), old[0] if old else None)
            if before and before["key"] == key and before["loaded"]:
                return before
            app = self.app
            app.life.make_way()
            if not app.gpu.acquire(timeout=wait):
                raise BrainError("Busy with something that won't stop; try again in a minute.")
            try:
                self._set(phase="unloading", to=new["name"], frm=before["name"] if before else "",
                          started=time.time(), error="")
                for m in old:
                    self._post("/api/v1/models/unload", {"instance_id": m["instance"]})
                self._set(phase="loading")
                try:
                    got = self._load(key, new["max_context"])
                except BrainError as e:
                    if before is None:
                        raise
                    log(f"brain: {key} didn't load ({e}); {before['key']} goes back in")
                    self._set(phase="back", error=str(e))
                    self._load(before["key"], before["max_context"])
                    raise BrainError(f"{new['name']} didn't load ({e}). {before['name']} is back in.")
                self.previous = before["key"] if before else None
                app.update_settings({"model": got["instance"] or key})
                took = int(time.time() - self.state["started"])
                self._set(phase="done", took=took, config=got["config"])
                log(f"brain: now {got['key']} ({took} s; {json.dumps(got['config'])[:200]})")
                app.life.log_event("brain swapped", f"{before['name'] if before else 'nothing'} -> {got['name']} "
                                                    f"({took} s): run her test before trusting it")
                return got
            finally:
                app.gpu.release()
        except BrainError as e:
            if self.state.get("phase") in ("unloading", "loading", "back"):
                self._set(phase="failed", error=str(e))
            raise
        finally:
            self.lock.release()

    def status(self):
        try:
            ms, err = self.models(), ""
        except BrainError as e:
            ms, err = [], str(e)
        return {"models": ms, "current": self.current_key(), "previous": self.previous, "state": self.state,
                "lms": os.path.isfile(self.lms), "error": err, "checked": dt.datetime.now().isoformat(timespec="seconds")}
