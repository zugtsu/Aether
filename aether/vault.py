import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import threading

from .config import DATA_DIR

VAULT_FILE = os.path.join(DATA_DIR, "vault.dat")
NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,40}$")


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def protect(data: bytes) -> bytes:
    src, _keep = _blob(data)
    out = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), "Aether vault", None, None, None, 0x1, ctypes.byref(out)):
        raise OSError("Windows couldn't lock the vault")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def unprotect(data: bytes) -> bytes:
    src, _keep = _blob(data)
    out = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)):
        raise OSError("this vault belongs to a different Windows account or PC")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


class Vault:
    def __init__(self, path=VAULT_FILE):
        self.path = path
        self.lock = threading.Lock()
        self._items = None

    def _load(self):
        if self._items is None:
            if os.path.exists(self.path):
                with open(self.path, "rb") as f:
                    self._items = json.loads(unprotect(f.read()).decode("utf-8"))
            else:
                self._items = {}
        return self._items

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(protect(json.dumps(self._items).encode("utf-8")))
        os.replace(tmp, self.path)

    def names(self):
        with self.lock:
            return [{"name": k, "skills": v.get("skills", []), "hint": f"{len(v['value'])} characters", "note": v.get("note", "")}
                    for k, v in sorted(self._load().items())]

    def set(self, name, value, skills=(), note=""):
        name = str(name).strip().upper()
        if not NAME.match(name):
            raise ValueError("names look like DISCORD_BOT_TOKEN (capitals, digits, underscores)")
        value = str(value)
        if len(value) < 4:
            raise ValueError("that value is too short to be a secret")
        with self.lock:
            self._load()[name] = {"value": value, "skills": sorted({str(s) for s in skills if s}), "note": str(note)[:120]}
            self._save()

    def allow(self, name, skills):
        with self.lock:
            item = self._load().get(name)
            if not item:
                raise ValueError("no such secret")
            item["skills"] = sorted({str(s) for s in skills if s})
            self._save()

    def remove(self, name):
        with self.lock:
            if self._load().pop(name, None) is None:
                raise ValueError("no such secret")
            self._save()

    def get(self, name):
        with self.lock:
            item = self._load().get(name)
            return item["value"] if item else None

    def env_for(self, skill):
        with self.lock:
            return {f"AETHER_SECRET_{k}": v["value"] for k, v in self._load().items()
                    if skill in v.get("skills", []) or "*" in v.get("skills", [])}

    def scrub(self, text):
        if not text:
            return text
        try:
            with self.lock:
                values = [v["value"] for v in self._load().values() if len(v["value"]) >= 6]
        except OSError:
            return text
        for v in sorted(values, key=len, reverse=True):
            text = text.replace(v, "••••")
        return text

