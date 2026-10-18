import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aether.brain import Brain, BrainError, parse_estimate
from aether.llm import ScriptedLLM
from aether.server import make_server
from aether.tests.fixture import make_config, make_memory

GEMMA = {"type": "llm", "key": "gemma-4-12b-it-qat", "display_name": "Gemma 4 12B", "params_string": "12B",
         "quantization": {"name": "Q4_K_XL"}, "size_bytes": 6925879040, "max_context_length": 262144,
         "capabilities": {"vision": True, "trained_for_tool_use": True}}
BIG = {"type": "llm", "key": "qwen-30b-a3b", "display_name": "Qwen 30B A3B", "params_string": "30B",
       "quantization": {"name": "Q4_K_M"}, "size_bytes": 18 * 1024 ** 3, "max_context_length": 131072,
       "capabilities": {"vision": False, "trained_for_tool_use": True}}
SMALL = {"type": "llm", "key": "whiterabbitneo-13b", "display_name": "Whiterabbitneo 13B", "params_string": "13B",
         "quantization": {"name": "Q4_K_S"}, "size_bytes": 7414445181, "max_context_length": 16384,
         "capabilities": {"vision": False, "trained_for_tool_use": False}}
NOMIC = {"type": "embedding", "key": "text-embedding-nomic-embed-text-v1.5", "max_context_length": 2048}


class FakeLMStudio:

    def __init__(self):
        self.models = [dict(GEMMA), dict(BIG), dict(SMALL), dict(NOMIC)]
        self.loaded = {"gemma-4-12b-it-qat": {"context_length": 65536, "flash_attention": True},
                       "text-embedding-nomic-embed-text-v1.5": {"context_length": 2048}}
        self.calls, self.fail_load = [], set()
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                out = [dict(m, loaded_instances=[{"id": m["key"], "config": fake.loaded[m["key"]]}]
                            if m["key"] in fake.loaded else []) for m in fake.models]
                self._send(200, {"models": out})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.calls.append((self.path, body))
                if self.path.endswith("/unload"):
                    fake.loaded.pop(body["instance_id"], None)
                    return self._send(200, {"instance_id": body["instance_id"]})
                if body["model"] in fake.fail_load:
                    return self._send(500, {"error": "out of memory"})
                fake.loaded[body["model"]] = {"context_length": body.get("context_length"),
                                              "flash_attention": body.get("flash_attention")}
                self._send(200, {"type": "llm", "instance_id": body["model"], "status": "loaded", "load_time_seconds": 1})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.lm = FakeLMStudio()
        cfg = make_config(make_memory(), lmstudio_url=self.lm.url, model="unsloth/gemma-4-12b-it-qat")
        self.httpd, self.app = make_server(cfg, ScriptedLLM([]), port=0)
        self.brain = self.app.brains
        self.brain.lms = "no-lms-here.exe"

    def tearDown(self):
        self.httpd.server_close()
        self.lm.close()

    def test_the_list_is_his_chat_models_with_hers_marked(self):
        ms = {m["key"]: m for m in self.brain.models()}
        self.assertEqual(set(ms), {"gemma-4-12b-it-qat", "qwen-30b-a3b", "whiterabbitneo-13b"})
        self.assertTrue(ms["gemma-4-12b-it-qat"]["current"] and ms["gemma-4-12b-it-qat"]["loaded"])
        self.assertFalse(ms["qwen-30b-a3b"]["loaded"])
        self.assertEqual(ms["gemma-4-12b-it-qat"]["config"]["context_length"], 65536)
        self.assertIn("too small (", ms["whiterabbitneo-13b"]["refused"])
        self.assertEqual((ms["gemma-4-12b-it-qat"]["refused"], ms["gemma-4-12b-it-qat"]["warnings"]), ("", []))

    def test_too_small_is_refused_and_missing_powers_are_warned(self):
        refused, _ = Brain.problems(next(m for m in self.brain.models() if m["key"] == "whiterabbitneo-13b"))
        self.assertIn("16,384 tokens: too small (", refused)
        refused, warn = Brain.problems(next(m for m in self.brain.models() if m["key"] == "qwen-30b-a3b"))
        self.assertEqual(refused, "")
        self.assertTrue(any("can't see pictures" in w for w in warn))
        self.assertEqual(Brain.problems(next(m for m in self.brain.models() if m["current"])), ("", []))
        with self.assertRaises(BrainError):
            self.brain.swap("whiterabbitneo-13b")
        self.assertEqual(self.lm.calls, [])
        with self.assertRaises(ValueError):
            self.app.start_brain_swap("whiterabbitneo-13b")
        c = self.brain.check("qwen-30b-a3b", {"total": 20 * 1024 ** 3, "used": 12 * 1024 ** 3,
                                              "parts": [{"name": "Gemma", "bytes": 7 * 1024 ** 3}]})
        self.assertEqual(c["free_gb"], 15.0)

    def test_a_swap_unloads_her_brain_loads_the_new_one_and_keeps_the_way_back(self):
        got = self.brain.swap("qwen-30b-a3b")
        self.assertEqual(got["key"], "qwen-30b-a3b")
        paths = [p for p, _ in self.lm.calls]
        self.assertEqual(paths, ["/api/v1/models/unload", "/api/v1/models/load"])
        self.assertIn("text-embedding-nomic-embed-text-v1.5", self.lm.loaded)
        load = self.lm.calls[1][1]
        self.assertEqual((load["context_length"], load["flash_attention"]), (65536, True))
        self.assertEqual(self.app.cfg.model, "qwen-30b-a3b")
        self.assertEqual(self.brain.previous, "gemma-4-12b-it-qat")
        self.assertEqual(self.brain.state["phase"], "done")
        self.assertFalse(self.app.gpu.locked())
        self.assertEqual(self.app.life.state["life_log"][-1]["what"], "brain swapped")
        self.brain.swap("gemma-4-12b-it-qat")
        self.assertEqual(self.app.cfg.model, "gemma-4-12b-it-qat")
        self.assertEqual(set(self.lm.loaded), {"gemma-4-12b-it-qat", "text-embedding-nomic-embed-text-v1.5"})

    def test_a_brain_that_wont_load_puts_the_old_one_back(self):
        self.lm.fail_load.add("qwen-30b-a3b")
        with self.assertRaises(BrainError) as e:
            self.brain.swap("qwen-30b-a3b")
        self.assertIn("Gemma 4 12B is back in", str(e.exception))
        self.assertIn("gemma-4-12b-it-qat", self.lm.loaded)
        self.assertEqual(self.app.cfg.model, "unsloth/gemma-4-12b-it-qat")
        self.assertEqual(self.brain.state["phase"], "failed")
        self.assertFalse(self.app.gpu.locked())

    def test_his_message_during_a_swap_is_told_why_and_a_busy_model_waits(self):
        self.brain.state = {"phase": "loading", "to": "Qwen 30B A3B", "started": 0}
        with self.assertRaises(RuntimeError) as e:
            self.app._claim_model()
        self.assertIn("The brain is loading", str(e.exception))
        self.brain.state = {"phase": "idle"}
        self.app.gpu.acquire()
        try:
            with self.assertRaises(BrainError):
                self.brain.swap("qwen-30b-a3b", wait=0.1)
        finally:
            self.app.gpu.release()
        self.assertEqual(self.lm.calls, [])

    def test_the_fit_estimate_is_read_from_lms(self):
        self.assertEqual(parse_estimate("Model: x\n\x1b[1mEstimated GPU Memory:\x1b[0m   6.45 GiB\nConfidence: LOW"), 6.45)
        self.assertIsNone(parse_estimate("Error: no such model"))
        self.assertIsNone(self.brain.estimate("qwen-30b-a3b"))
