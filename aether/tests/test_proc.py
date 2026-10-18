import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from aether.proc import NO_WINDOW, end_tied, spawn_tied

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAKE_COMFY = """
import os, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
with open(sys.argv[1] + ".tmp", "w") as f:
    f.write(f"{os.getpid()} {child.pid}")
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
time.sleep(120)
"""

FAKE_AETHER = """
import sys, time
sys.path.insert(0, sys.argv[1])
from aether.proc import spawn_tied
p = spawn_tied(sys.argv[2:], creationflags=0x08000000)
print(f"{'tied' if p.job else 'untied: ' + p.tie_error} {p.pid}", flush=True)
time.sleep(120)
"""


def alive(pid):
    import ctypes
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(0x00100000 | 0x1000, False, pid)
    if not h:
        return False
    try:
        return k32.WaitForSingleObject(ctypes.c_void_p(h), 0) == 0x102
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def wait_for(cond, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return cond()


@unittest.skipUnless(os.name == "nt", "Windows jobs")
class TiedTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="aether-tied-")
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", os.path.join(self.dir, "venv")], check=True,
                       capture_output=True)
        self.venv_python = os.path.join(self.dir, "venv", "Scripts", "python.exe")
        self.pidfile = os.path.join(self.dir, "pids")
        self.started = []

    def tearDown(self):
        for pid in self.started:
            if alive(pid):
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
        shutil.rmtree(self.dir, ignore_errors=True)

    def comfy_family(self, launcher_pid):
        self.assertTrue(wait_for(lambda: os.path.exists(self.pidfile)), "the fake ComfyUI never ran")
        with open(self.pidfile) as f:
            real, child = map(int, f.read().split())
        family = [launcher_pid, real, child]
        self.started += family
        self.assertNotEqual(launcher_pid, real, "the venv's python.exe should be a launcher with its own child")
        self.assertTrue(all(alive(p) for p in family))
        return family

    def test_a_hard_killed_aether_takes_its_comfyui_along(self):
        aether = subprocess.Popen([sys.executable, "-c", FAKE_AETHER, PROJECT, self.venv_python, "-c", FAKE_COMFY,
                                   self.pidfile], stdout=subprocess.PIPE, text=True, creationflags=NO_WINDOW)
        self.started.append(aether.pid)
        said = aether.stdout.readline().split()
        self.assertEqual(said[0], "tied", said)
        family = self.comfy_family(int(said[1]))
        subprocess.run(["taskkill", "/PID", str(aether.pid), "/F"], capture_output=True, creationflags=NO_WINDOW)
        aether.wait(10)
        aether.stdout.close()
        self.assertTrue(wait_for(lambda: not any(alive(p) for p in family), 10),
                        f"still running after Aether was killed: {[p for p in family if alive(p)]}")

    def test_stopping_it_stops_the_whole_family(self):
        p = spawn_tied([self.venv_python, "-c", FAKE_COMFY, self.pidfile], creationflags=NO_WINDOW)
        self.assertIsNotNone(p.job, p.tie_error)
        family = self.comfy_family(p.pid)
        self.assertTrue(end_tied(p))
        self.assertTrue(wait_for(lambda: not any(alive(q) for q in family), 10))
        self.assertFalse(end_tied(p))


@unittest.skipUnless(os.name == "nt", "Windows jobs")
class EarsTiedTests(unittest.TestCase):

    def test_her_ears_stop_with_the_real_python_they_started(self):
        from aether.config import Config
        from aether.ears import Ears
        from aether.proc import processes
        ears = Ears(Config())
        if not ears.available():
            self.skipTest("SenseVoice isn't installed here")
        ears._start()
        launcher = ears.proc.pid
        self.assertIsNotNone(ears.proc.job, ears.proc.tie_error)
        family = [launcher] + [p["pid"] for p in processes() if p["ppid"] == launcher]
        try:
            self.assertTrue(all(alive(p) for p in family))
            ears.shutdown()
            self.assertTrue(wait_for(lambda: not any(alive(p) for p in family), 10),
                            f"still running after her ears stopped: {[p for p in family if alive(p)]}")
        finally:
            for pid in family:
                if alive(pid):
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
        print(f"(her ears: {len(family)} program(s), all stopped)", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
