import json
import os
import subprocess
import sys

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_SUSPENDED = 0x00000004


def python_exe():
    exe = sys.executable
    if os.path.basename(exe).lower() == "pythonw.exe":
        twin = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(twin):
            return twin
    return exe


_win = None


def _winapi():
    global _win
    if _win is None:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC_LIMIT(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED_LIMIT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.SetInformationJobObject.restype = wintypes.BOOL
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.AssignProcessToJobObject.restype = wintypes.BOOL
        k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.TerminateJobObject.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        ntdll = ctypes.WinDLL("ntdll")
        ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
        ntdll.NtResumeProcess.restype = ctypes.c_long
        _win = (ctypes, k32, ntdll, EXTENDED_LIMIT)
    return _win


class Job:

    def __init__(self):
        ctypes, k32, _, EXTENDED_LIMIT = _winapi()
        self.handle = k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = 0x2000
        if not k32.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            err = ctypes.WinError(ctypes.get_last_error())
            self.end()
            raise err

    def add(self, popen):
        ctypes, k32, _, _ = _winapi()
        if not k32.AssignProcessToJobObject(self.handle, int(popen._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def end(self):
        h, self.handle = self.handle, None
        if h:
            _, k32, _, _ = _winapi()
            k32.TerminateJobObject(h, 1)
            k32.CloseHandle(h)


def spawn_tied(args, **kw):
    if os.name != "nt":
        p = subprocess.Popen(args, **kw)
        p.job, p.tie_error = None, "not Windows"
        return p
    kw["creationflags"] = kw.get("creationflags", 0) | CREATE_SUSPENDED
    p = subprocess.Popen(args, **kw)
    p.job, p.tie_error = None, ""
    try:
        job = Job()
        try:
            job.add(p)
            p.job = job
        except OSError:
            job.end()
            raise
    except OSError as e:
        p.tie_error = str(e)
    _, _, ntdll, _ = _winapi()
    if ntdll.NtResumeProcess(int(p._handle)) != 0:
        if p.job:
            p.job.end()
        else:
            p.kill()
        p.wait(10)
        raise OSError(f"couldn't start {os.path.basename(str(args[0]))} (it wouldn't come out of pause)")
    return p


def end_tied(p, wait=10):
    running = p.poll() is None
    job = getattr(p, "job", None)
    if job:
        job.end()
    elif running:
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
    if running:
        try:
            p.wait(wait)
        except subprocess.TimeoutExpired:
            pass
    return running


def processes():
    ps = ("[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "
          "ConvertTo-Json -Compress -InputObject @(Get-CimInstance Win32_Process | ForEach-Object { [pscustomobject]@{ "
          "pid = $_.ProcessId; ppid = $_.ParentProcessId; name = $_.Name; "
          "created = $(if ($_.CreationDate) { $_.CreationDate.ToFileTimeUtc() } else { 0 }); "
          "cmd = $(if ($_.Name -like 'python*') { $_.CommandLine } else { $null }) } })")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                       timeout=60, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise OSError("couldn't list programs: " + r.stderr.decode("utf-8", "replace").strip()[:300])
    got = json.loads(r.stdout.decode("utf-8-sig", "replace") or "[]")
    return got if isinstance(got, list) else [got]
