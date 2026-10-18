import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

PROTOCOL = "2025-06-18"
CLIENT = {"name": "aether", "version": "1"}


class McpError(Exception):
    pass


class McpServer:

    def __init__(self, command, args=(), env=None, cwd=None, timeout=60):
        exe = shutil.which(command) or command
        if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
            raise McpError(f"{command} is a batch file ({os.path.basename(exe)}); point it at the program itself")
        self.timeout = timeout
        self.next_id = 0
        self.lines = queue.Queue()
        self.stderr = []
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
        try:
            self.proc = subprocess.Popen([exe, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, cwd=cwd, env=env, **kw)
        except OSError as e:
            raise McpError(f"couldn't start {command}: {e}") from None
        threading.Thread(target=self._pump, args=(self.proc.stdout, self.lines), daemon=True).start()
        threading.Thread(target=self._drain, daemon=True).start()
        try:
            self.info = self._request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": CLIENT})
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except McpError:
            self.close()
            raise

    @staticmethod
    def _pump(stream, q):
        for raw in iter(stream.readline, b""):
            q.put(raw)
        q.put(None)

    def _drain(self):
        for raw in iter(self.proc.stderr.readline, b""):
            self.stderr.append(raw.decode("utf-8", "replace").rstrip())
            del self.stderr[:-20]

    def _send(self, msg):
        try:
            self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
            self.proc.stdin.flush()
        except OSError:
            raise McpError("the server closed" + self._why()) from None

    def _why(self):
        return (": " + " | ".join(self.stderr[-3:])) if self.stderr else ""

    def _request(self, method, params):
        self.next_id += 1
        rid = self.next_id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        end = time.time() + self.timeout
        while True:
            left = end - time.time()
            if left <= 0:
                raise McpError(f"no answer to {method} in {self.timeout} s")
            try:
                raw = self.lines.get(timeout=left)
            except queue.Empty:
                continue
            if raw is None:
                raise McpError("the server stopped" + self._why())
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if "method" in msg and "id" in msg:
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": {}} if msg["method"] == "ping" else
                           {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "not supported"}})
                continue
            if msg.get("id") != rid:
                continue
            if "error" in msg:
                err = msg["error"] or {}
                raise McpError(f"{method}: {err.get('message', err)}")
            return msg.get("result") or {}

    def tools(self):
        out, cursor = [], None
        for _ in range(20):
            r = self._request("tools/list", {"cursor": cursor} if cursor else {})
            out += [t for t in r.get("tools") or [] if isinstance(t, dict) and t.get("name")]
            cursor = r.get("nextCursor")
            if not cursor:
                break
        return out

    def call(self, name, arguments):
        r = self._request("tools/call", {"name": name, "arguments": arguments})
        parts = []
        for c in r.get("content") or []:
            if c.get("type") == "text":
                parts.append(str(c.get("text", "")))
            elif c.get("type") == "resource" and isinstance(c.get("resource"), dict) and "text" in c["resource"]:
                parts.append(str(c["resource"]["text"]))
            else:
                parts.append(f"[{c.get('type', 'something')} not shown]")
        if not parts and r.get("structuredContent") is not None:
            parts.append(json.dumps(r["structuredContent"], ensure_ascii=False))
        return not r.get("isError"), "\n".join(parts).strip() or "(no output)"

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(3)
        for pipe in (self.proc.stdout, self.proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def parse_args(schema, pairs):
    props = (schema or {}).get("properties") or {}
    out = {}
    for p in pairs:
        if "=" not in p:
            return {}, f"'{p}' isn't name=value (this tool takes: {', '.join(props) or 'nothing'})"
        k, v = p.split("=", 1)
        k, v = k.strip(), v.strip()
        if props and k not in props:
            return {}, f"no '{k}' here (this tool takes: {', '.join(props)})"
        kind = (props.get(k) or {}).get("type")
        try:
            if kind == "integer":
                v = int(v)
            elif kind == "number":
                v = float(v)
            elif kind == "boolean":
                v = v.lower() in ("true", "yes", "1", "on")
            elif kind in ("array", "object"):
                v = json.loads(v)
        except ValueError:
            return {}, f"'{k}' should be a {kind}"
        out[k] = v
    missing = [k for k in (schema or {}).get("required") or [] if k not in out]
    if missing:
        return {}, f"missing: {', '.join(missing)}"
    return out, ""


def main(server, tools, argv):
    if not argv or argv[0] not in tools:
        print(f"error: name a tool first: {', '.join(tools)}")
        return 2
    name, schema = argv[0], tools[argv[0]]
    arguments, problem = parse_args(schema, argv[1:])
    if problem:
        print(f"error: {problem}")
        return 2
    try:
        with McpServer(server["command"], server.get("args") or [], cwd=os.path.dirname(os.path.abspath(sys.argv[0])),
                       timeout=int(server.get("timeout") or 60)) as s:
            ok, text = s.call(name, arguments)
    except McpError as e:
        print(f"error: {e}")
        return 1
    print(text)
    return 0 if ok else 1
