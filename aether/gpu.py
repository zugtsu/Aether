import ctypes
import re
import sys

GB = 1024 ** 3
NAMED = (("Gemma", ("llama-server.exe",)), ("voice", ("audiocpp_server.exe",)),
         ("the Aether window", ("electron.exe",)))
INSTANCE = re.compile(r"pid_(\d+)_(luid_\w+?_phys_\d+)", re.I)
_card = None


def summary(adapters, procs, programs, total=0, card="", pictures=()):
    if not adapters:
        return None
    luid = max(adapters, key=adapters.get)
    used = adapters[luid]
    kids = {}
    for pid, (_, parent) in programs.items():
        kids.setdefault(parent, []).append(pid)
    comfy, todo = set(), [p for p in pictures if p]
    while todo:
        p = todo.pop()
        if p not in comfy:
            comfy.add(p)
            todo += kids.get(p, [])
    parts = {}
    for (pid, where), n in procs.items():
        if where != luid or n <= 0:
            continue
        exe = programs.get(pid, ("", 0))[0].lower()
        label = "pictures" if pid in comfy else next((lab for lab, exes in NAMED if exe in exes), None)
        if label:
            parts[label] = parts.get(label, 0) + n
    known = sum(parts.values())
    ordered = sorted(parts.items(), key=lambda kv: -kv[1])
    if used > known:
        ordered.append(("everything else", used - known))
    return {"used": used, "total": total, "card": card, "parts": [{"name": k, "bytes": v} for k, v in ordered]}


def usage(pictures=()):
    if sys.platform != "win32":
        return None
    try:
        adapters = {}
        for name, n in _counter(r"\GPU Adapter Memory(*)\Dedicated Usage"):
            adapters[name] = adapters.get(name, 0) + n
        procs = {}
        for name, n in _counter(r"\GPU Process Memory(*)\Dedicated Usage"):
            m = INSTANCE.match(name)
            if m:
                key = (int(m.group(1)), m.group(2))
                procs[key] = procs.get(key, 0) + n
        card, total = _card_info()
        return summary(adapters, procs, _programs(), total, card, pictures)
    except OSError:
        return None


class _Value(ctypes.Structure):
    _fields_ = [("CStatus", ctypes.c_ulong), ("largeValue", ctypes.c_longlong)]


class _Item(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", _Value)]


def _counter(path):
    pdh = ctypes.WinDLL("pdh")
    query, counter = ctypes.c_void_p(), ctypes.c_void_p()
    if pdh.PdhOpenQueryW(None, None, ctypes.byref(query)):
        raise OSError("PdhOpenQuery failed")
    try:
        if pdh.PdhAddEnglishCounterW(query, path, None, ctypes.byref(counter)):
            raise OSError(f"no counter {path}")
        pdh.PdhCollectQueryData(query)
        size, count = ctypes.c_ulong(0), ctypes.c_ulong(0)
        pdh.PdhGetFormattedCounterArrayW(counter, 0x400, ctypes.byref(size), ctypes.byref(count), None)
        if not size.value:
            return []
        buf = ctypes.create_string_buffer(size.value)
        if pdh.PdhGetFormattedCounterArrayW(counter, 0x400, ctypes.byref(size), ctypes.byref(count), buf):
            raise OSError("PdhGetFormattedCounterArray failed")
        items = ctypes.cast(buf, ctypes.POINTER(_Item))
        return [(items[i].szName, items[i].FmtValue.largeValue) for i in range(count.value) if items[i].FmtValue.CStatus in (0, 1)]
    finally:
        pdh.PdhCloseQuery(query)


class _Entry(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong), ("th32ProcessID", ctypes.c_ulong),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong),
                ("szExeFile", ctypes.c_wchar * 260)]


def _programs():
    k32 = ctypes.WinDLL("kernel32")
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    if not snap or snap == ctypes.c_void_p(-1).value:
        return {}
    out, e = {}, _Entry()
    e.dwSize = ctypes.sizeof(_Entry)
    try:
        ok = k32.Process32FirstW(ctypes.c_void_p(snap), ctypes.byref(e))
        while ok:
            out[e.th32ProcessID] = (e.szExeFile, e.th32ParentProcessID)
            ok = k32.Process32NextW(ctypes.c_void_p(snap), ctypes.byref(e))
    finally:
        k32.CloseHandle(ctypes.c_void_p(snap))
    return out


def _card_info():
    global _card
    if _card is None:
        import winreg
        best = ("", 0)
        cls = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls) as root:
                for i in range(64):
                    try:
                        sub = winreg.EnumKey(root, i)
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(root, sub) as k:
                            size = winreg.QueryValueEx(k, "HardwareInformation.qwMemorySize")[0]
                            desc = winreg.QueryValueEx(k, "DriverDesc")[0]
                    except OSError:
                        continue
                    if isinstance(size, int) and size > best[1]:
                        best = (str(desc), size)
        except OSError:
            pass
        _card = best
    return _card


if __name__ == "__main__":
    u = usage()
    if not u:
        print("can't read the graphics counters here")
    else:
        print(f"{u['card'] or 'graphics card'}: {u['used'] / GB:.1f} of {u['total'] / GB:.1f} GB in use")
        for p in u["parts"]:
            print(f"  {p['name']:<18} {p['bytes'] / GB:5.1f} GB")
