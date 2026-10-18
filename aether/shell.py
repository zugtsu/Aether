import json
import os
import re
import subprocess
import threading

from .proc import NO_WINDOW

LEVELS = {0: "skills only", 1: "look around", 2: "her workspace", 3: "full command line"}

READ_ONLY = {
    "get-childitem", "dir", "ls", "gci", "get-content", "type", "cat", "gc", "get-item", "gi", "get-itemproperty",
    "get-location", "pwd", "gl", "test-path", "resolve-path", "split-path", "join-path", "get-filehash",
    "select-string", "sls", "findstr", "measure-object", "measure", "select-object", "select", "where-object", "where",
    "?", "sort-object", "sort", "group-object", "format-table", "ft", "format-list", "fl", "out-string", "foreach-object",
    "%", "foreach", "get-process", "ps", "gps", "tasklist", "get-service", "gsv", "get-psdrive", "gdr", "get-volume",
    "get-disk", "get-computerinfo", "systeminfo", "hostname", "whoami", "get-date", "date", "get-command", "gcm",
    "get-help", "get-netipaddress", "ipconfig", "get-ciminstance", "gcim", "get-wmiobject", "gwmi", "get-uptime",
    "get-host", "get-culture", "get-timezone", "write-output", "echo", "write-host", "tree", "where.exe",
    "get-hotfix", "get-counter", "get-eventlog", "get-winevent", "convertto-json", "convertfrom-json", "get-unique",
    "compare-object", "diff", "get-member", "gm", "nvidia-smi", "python", "py", "node", "git",
}
GIT_READ = re.compile(r"^\s*git\s+(?:(?:status|log|diff|show|rev-parse|ls-files|blame)\b|remote\s+-v\s*$|branch(?:\s+(?:-a|-r|-v|"
                      r"-vv|--all|--remotes|--list|--verbose|--show-current|--merged|--no-merged))*\s*$)", re.I)
GIT_WRITES = re.compile(r"--output\b", re.I)
PY_READ = re.compile(r"^\s*(python|py|node)\s+(--version|-V)\s*$", re.I)
SECRETS = re.compile(r"(?:^|[\\/\s'\"])\.aether-skills(?:[\\/'\"\s]|$)|vault\.dat\b", re.I)
PY_INLINE = re.compile(r"\s(?:-[cmep]|--eval|--print)(?:\s|$)", re.I)

ALWAYS_ASK = {
    "remove-item", "rm", "del", "erase", "rd", "rmdir", "ri", "clear-content", "clc", "clear-item", "clear-recyclebin",
    "format-volume", "format", "diskpart", "cipher", "winget", "choco", "scoop", "msiexec", "install-module",
    "install-package", "uninstall-package", "npm", "pip", "pipx", "set-itemproperty", "sp", "new-itemproperty",
    "remove-itemproperty", "reg", "regedit", "bcdedit", "set-service", "stop-service", "start-service",
    "restart-service", "new-service", "sc", "sc.exe", "stop-computer", "restart-computer", "shutdown", "logoff",
    "netsh", "set-netipaddress", "new-netfirewallrule", "set-netfirewallprofile", "set-executionpolicy",
    "set-mppreference", "add-mppreference", "takeown", "icacls", "schtasks", "register-scheduledtask",
    "unregister-scheduledtask", "stop-process", "kill", "taskkill", "send-mailmessage", "invoke-webrequest", "iwr",
    "invoke-restmethod", "irm", "curl", "wget", "start-bitstransfer", "set-acl", "new-localuser", "add-localgroupmember",
    "robocopy",
}
NET_CONFIG = re.compile(r"^(?:set|new|remove|add|enable|disable|rename|reset|restart|register|unregister|clear)-"
                        r"(?:net|dnsclient|vpnconnection)", re.I)
NET_FILES = re.compile(r"drivers[\\/]+etc(?:[\\/]|$)", re.I)
OPAQUE = {
    "invoke-expression", "iex", "invoke-command", "icm", "start-process", "saps", "start", "start-job", "sajb",
    "invoke-item", "ii", "cmd", "powershell", "pwsh", "powershell_ise", "wsl", "bash", "wscript", "cscript", "mshta",
    "rundll32", "regsvr32", "add-type", "import-module", "ipmo", "set-alias", "sal", "new-alias", "nal",
    "invoke-cimmethod", "invoke-wmimethod", "enable-psremoting", "enter-pssession", "new-pssession",
}
SAFE_METHODS = {
    "tostring", "toupper", "tolower", "toupperinvariant", "tolowerinvariant", "trim", "trimstart", "trimend", "split",
    "replace", "substring", "contains", "startswith", "endswith", "indexof", "lastindexof", "padleft", "padright",
    "gettype", "equals", "compareto", "adddays", "addhours", "addminutes", "addseconds", "addmonths", "addyears",
    "toshortdatestring", "tolongdatestring", "toshorttimestring", "tolongtimestring", "getfiles", "getdirectories",
    "round", "floor", "ceiling", "abs", "max", "min", "pow", "sqrt", "join", "format", "isnullorempty",
    "isnullorwhitespace", "parse", "tryparse", "tobase64string", "frombase64string", "toint32", "todouble",
}
SAFE_TYPES = {"math", "string", "datetime", "timespan", "convert", "char", "int", "int32", "int64", "double", "decimal"}
SAFE_PROPS = {"name", "fullname", "basename", "extension", "length", "lastwritetime", "creationtime", "count", "path",
              "id", "processname", "mode", "directoryname", "value", "key"}
FOREACH = {"foreach-object", "%", "foreach"}
PLAIN = {"ScriptBlockAst", "NamedBlockAst", "PipelineAst", "CommandAst", "CommandParameterAst", "CommandExpressionAst",
         "StringConstantExpressionAst", "ExpandableStringExpressionAst", "ConstantExpressionAst", "ArrayLiteralAst",
         "FileRedirectionAst", "MergingRedirectionAst", "VariableExpressionAst"}
PLAIN_VARS = {"true", "false", "null"}
REGISTRY = re.compile(r"\b(HKLM|HKCU|HKCR|HKU|HKCC|Registry|WSMan|Cert|Alias|Function)::?", re.I)
ABS_PATH = re.compile(r"""(?:(?<![\w])[A-Za-z]:[\\/]|\\\\|(?<![\w.])~[\\/]|\$env:|\$home\b)""", re.I)
QUOTED_PATH = re.compile(r"""(["'])([A-Za-z]:[\\/][^"'\n]*)\1""")
BARE_PATH = re.compile(r"""[A-Za-z]:[\\/][^\s'"|;]*""")
VALUE_PATH = re.compile(r"""[A-Za-z]:[\\/][^"'|;\n]*""")
ROOTED = re.compile(r"[\\/](?![\\/])")
DRIVE_RELATIVE = re.compile(r"[A-Za-z]:(?![\\/])")


def _drive_paths(command):
    found = [m.group(2) for m in QUOTED_PATH.finditer(command)]
    rest = QUOTED_PATH.sub(" ", command)
    found += BARE_PATH.findall(rest)
    return found, BARE_PATH.sub(" ", rest)


def _inside(path, ws):
    p = os.path.normcase(os.path.abspath(path))
    return p == ws or p.startswith(ws.rstrip("\\/") + os.sep)


_L = "System.Management.Automation.Language."
_PARSE = ("$e=$null; $t=$null; $ast=[" + _L + "Parser]::ParseInput($env:AETHER_CMD,[ref]$t,[ref]$e); "
          "$all=@($ast.FindAll({$true}, $true)); "
          "$c=@($all | Where-Object { $_ -is [" + _L + "CommandAst] } | ForEach-Object { @{name=$_.GetCommandName(); "
          "text=$_.Extent.Text; args=@($_.CommandElements | Select-Object -Skip 1 | Where-Object { $_ -is [" + _L +
          "StringConstantExpressionAst] } | ForEach-Object { $_.Value })} }); "
          "$m=@($all | Where-Object { $_ -is [" + _L + "InvokeMemberExpressionAst] } | ForEach-Object { @{static=$_.Static; "
          "type=$(if ($_.Expression -is [" + _L + "TypeExpressionAst]) { $_.Expression.TypeName.FullName } else { '' }); "
          "name=$(if ($_.Member -is [" + _L + "StringConstantExpressionAst]) { $_.Member.Value } else { $null })} }); "
          "$w=@($all | Where-Object { ($_ -is [" + _L + "AssignmentStatementAst] -and $_.Left -isnot [" + _L +
          "VariableExpressionAst] -and $_.Left -isnot [" + _L + "ConvertExpressionAst]) -or ($_ -is [" + _L +
          "UnaryExpressionAst] -and \"$($_.TokenKind)\" -match 'PlusPlus|MinusMinus' -and $_.Child -isnot [" + _L +
          "VariableExpressionAst]) }).Count; "
          "$s=@($all | Where-Object { $_ -is [" + _L + "StringConstantExpressionAst] -or $_ -is [" + _L +
          "ExpandableStringExpressionAst] } | ForEach-Object { $_.Value }); "
          "$v=@($all | Where-Object { $_ -is [" + _L + "VariableExpressionAst] } | ForEach-Object { $_.VariablePath.UserPath }); "
          "$k=@($all | ForEach-Object { $_.GetType().Name } | Sort-Object -Unique); "
          "$r=@($all | Where-Object { $_ -is [" + _L + "FileRedirectionAst] }).Count; "
          "@{commands=$c; redirects=$r; methods=$m; member_writes=$w; strings=$s; variables=$v; kinds=$k; "
          "errors=@($e | ForEach-Object { $_.Message })} | ConvertTo-Json -Compress -Depth 5")


def _list(x):
    return [] if x is None else x if isinstance(x, list) else [x]


WRAPPED = re.compile(r"^\s*(?:powershell|pwsh)(?:\.exe)?\s+(?:-(?:NoProfile|NonInteractive|NoLogo|nop|noni)\s+|"
                     r"-(?:ExecutionPolicy|ep)\s+\w+\s+)*-(?:Command|c)\s+(?P<q>[\"'])(?P<inner>.*)(?P=q)\s*$", re.I | re.S)


def unwrap(command):
    m = WRAPPED.match(command or "")
    if not m or m.group("q") in m.group("inner") or not m.group("inner").strip():
        return command
    return m.group("inner").strip()


def analyze(command):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PARSE], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=20, env=dict(os.environ, AETHER_CMD=command),
                       creationflags=NO_WINDOW)
    try:
        d = json.loads(r.stdout.strip() or "{}")
    except ValueError:
        d = {}
    if not isinstance(d, dict) or "commands" not in d:
        return {"commands": [], "redirects": 0, "methods": [], "member_writes": 0, "strings": [], "variables": [],
                "kinds": [], "errors": ["couldn't read the command"]}
    cmds = [{"name": c.get("name") or None, "text": str(c.get("text") or ""), "args": [str(a) for a in _list(c.get("args"))]}
            for c in _list(d.get("commands")) if isinstance(c, dict)]
    methods = [{"static": bool(m.get("static")), "type": str(m.get("type") or ""), "name": m.get("name") or None}
               for m in _list(d.get("methods")) if isinstance(m, dict)]
    return {"commands": cmds, "redirects": int(d.get("redirects") or 0), "methods": methods,
            "member_writes": int(d.get("member_writes") or 0), "strings": [str(s) for s in _list(d.get("strings"))],
            "variables": [str(v) for v in _list(d.get("variables"))], "kinds": [str(k) for k in _list(d.get("kinds"))],
            "errors": [str(e) for e in _list(d.get("errors"))]}


def _base(name):
    return os.path.basename(str(name)).lower()


def _unsafe_methods(info):
    bad = []
    for m in info["methods"]:
        name = (m["name"] or "").lower()
        typ = m["type"].lower().removeprefix("system.")
        if not name or name not in SAFE_METHODS or (m["static"] and typ not in SAFE_TYPES):
            bad.append(f"[{m['type']}]::{m['name']}" if m["static"] else f".{m['name'] or '(picked at run time)'}()")
    for c in info["commands"]:
        if _base(c["name"] or "") in FOREACH:
            bad += [f".{a}" for a in c["args"] if a.lower() not in SAFE_METHODS | SAFE_PROPS]
    return bad


_EDGE_BEFORE, _EDGE_AFTER = " \t\r\n\"'`(:,;=", " \t\r\n\"'`),;"


def _climbs(text):
    for m in re.finditer(r"\.{2,}", text):
        a, b = m.start(), m.end()
        before, after = text[a - 1:a], text[b:b + 1]
        sep_b, sep_a = before in ("\\", "/"), after in ("\\", "/")
        edge_b, edge_a = before == "" or before in _EDGE_BEFORE, after == "" or after in _EDGE_AFTER
        if b - a == 2 and (sep_b or edge_b) and (sep_a or edge_a):
            return True
        if (sep_b and (sep_a or edge_a)) or (sep_a and (sep_b or edge_b)):
            return True
    return False


def _outside(command, info, ws):
    paths, rest = _drive_paths(command)
    if [p for p in paths if not _inside(p, ws)] or _climbs(command) or ABS_PATH.search(rest):
        return True
    for s in info["strings"]:
        v = s.strip()
        found = [m.group(0).strip() for m in VALUE_PATH.finditer(v)]
        if ([p for p in found if not _inside(p, ws)] or _climbs(v) or ABS_PATH.search(VALUE_PATH.sub(" ", v))
                or ROOTED.match(v) or DRIVE_RELATIVE.match(v) or v == "~"):
            return True
    return False


NOTE_READS = {"get-content", "gc", "cat", "type", "get-childitem", "gci", "dir", "ls", "test-path", "select-string", "sls",
              "get-item", "gi", "measure-object", "measure", "select-object", "select", "sort-object", "sort",
              "where-object", "where", "?", "format-list", "fl", "format-table", "ft", "out-string", "get-date", "date",
              "write-output", "echo"}
NOTE_ADDS = {"add-content", "ac", "new-item", "ni", "out-file"}
OVERWRITES = re.compile(r"(?:^|\s)-(?:force|f)\b", re.I)
APPENDS = re.compile(r"(?:^|\s)-(?:append|noclobber)\b", re.I)


def notes_only(level, command, info, workspace):
    if level < 2 or info["errors"] or not info["commands"] or info["redirects"] or info["methods"] or info["member_writes"]:
        return False
    if sorted(set(info["kinds"]) - PLAIN) or [v for v in info["variables"] if v.lower() not in PLAIN_VARS]:
        return False
    for c in info["commands"]:
        name = _base(c["name"] or "")
        if name in NOTE_READS:
            continue
        if name not in NOTE_ADDS or OVERWRITES.search(c["text"]):
            return False
        if name == "out-file" and not APPENDS.search(c["text"]):
            return False
    return not _outside(command, info, os.path.normcase(os.path.abspath(workspace)))


EDIT_CMDS = {"get-content", "gc", "cat", "type", "set-content", "add-content", "ac", "out-file", "foreach-object", "%",
             "where-object", "where", "?", "select-string", "sls", "sort-object", "sort", "select-object", "select"}
FILE_CMDS = {"get-content", "gc", "cat", "type", "set-content", "add-content", "ac", "out-file"}
EDIT_KINDS = {"ParenExpressionAst", "BinaryExpressionAst", "UnaryExpressionAst", "IfStatementAst", "StatementBlockAst",
              "ScriptBlockExpressionAst"}
PATH_PARAM = re.compile(r"^-(?:path|literalpath|filepath|pspath|lp)$", re.I)


def _plain_path(text):
    toks = re.findall(r"""'[^']*'|"[^"]*"|\S+""", text)[1:]
    for i, t in enumerate(toks):
        if PATH_PARAM.match(t.rstrip(":")) and i + 1 < len(toks):
            tok = toks[i + 1]
            break
    else:
        if not toks or toks[0].startswith("-"):
            return None
        tok = toks[0]
    if tok.startswith("'"):
        return tok.strip("'")
    if tok.startswith('"'):
        return None if re.search(r"[$`]", tok) else tok.strip('"')
    return None if re.search(r"[$`(){}@;|]", tok) else tok


def text_edit_only(info):
    if set(info["kinds"]) - PLAIN - EDIT_KINDS:
        return False
    if [v for v in info["variables"] if v.lower() not in PLAIN_VARS | {"_", "psitem"}]:
        return False
    for c in info["commands"]:
        name = _base(c["name"] or "")
        if name not in EDIT_CMDS:
            return False
        if name in FOREACH and c.get("args"):
            return False
        if name in FILE_CMDS and _plain_path(c["text"]) is None:
            return False
    return True


def decide(level, command, info, workspace):
    if level <= 0:
        return "deny", "your permission level here is 0 (skills only): no command line"
    if info["errors"]:
        return "deny", "PowerShell can't read that command: " + "; ".join(info["errors"])[:200]
    if SECRETS.search(command) or any(SECRETS.search(s) for s in info["strings"]):
        return "deny", "that's where {USER}'s keys are kept: no command reads them"
    if any(c["name"] is None for c in info["commands"]):
        return "ask", "runs a command picked at run time, so it can't be checked (always asks)"
    names = [_base(c["name"]) for c in info["commands"]]
    risky = sorted({n for n in names if n in ALWAYS_ASK | OPAQUE or n.removesuffix(".exe") in ALWAYS_ASK | OPAQUE
                    or NET_CONFIG.match(n)})
    if risky:
        return "ask", f"uses {', '.join(risky)} (always asks)"
    inline = [c for c in info["commands"] if _base(c["name"]).removesuffix(".exe") in ("python", "py", "node")
              and PY_INLINE.search(c["text"])]
    if inline:
        return "ask", "runs code written into the command, so it can't be checked (always asks)"
    unsafe = _unsafe_methods(info)
    if unsafe:
        return "ask", f"calls .NET directly ({', '.join(unsafe[:3])}), so it can't be checked (always asks)"
    if info["member_writes"]:
        return "ask", "changes a property of something (always asks)"
    if REGISTRY.search(command) and not all(n in READ_ONLY for n in names):
        return "ask", "changes the registry or system settings (always asks)"
    if (NET_FILES.search(command) or any(NET_FILES.search(s) for s in info["strings"])) \
            and not all(n in READ_ONLY for n in names):
        return "ask", "changes the hosts file, a network setting (always asks)"
    looks_only = (not info["redirects"] and all(n in READ_ONLY for n in names)
                  and all(GIT_READ.match(c["text"]) and not GIT_WRITES.search(c["text"])
                          for c in info["commands"] if _base(c["name"]) == "git")
                  and all(PY_READ.match(c["text"]) for c in info["commands"]
                          if _base(c["name"]) in ("python", "py", "node")))
    if level == 1:
        return ("run", "looks only") if looks_only else ("deny", "level 1 is look-around only: that command changes or runs things")
    if level == 2:
        if looks_only:
            return "run", "looks only"
        if any(_base(c["name"]).removesuffix(".exe") == "git" for c in info["commands"]):
            return "ask", "a git command that isn't one of the read-only ones (always asks)"
        built = sorted(set(info["kinds"]) - PLAIN) or [v for v in info["variables"] if v.lower() not in PLAIN_VARS]
        if built and not text_edit_only(info):
            return "ask", "builds part of the command at run time, so where it reaches can't be checked"
        if _outside(command, info, os.path.normcase(os.path.abspath(workspace))):
            return "ask", "reaches outside her workspace"
        return "run", "inside her workspace"
    return "run", "full command line"


DELETERS = {"remove-item", "rm", "del", "erase", "rd", "rmdir", "ri"}
ONE_DELETE = ("Not deleted: a delete runs on its own, one Remove-Item with the paths written out plainly (one per "
              "Remove-Item), nothing else in the line. What it deletes goes to the Recycle Bin.")


def delete_targets(info, cwd, workspace):
    cmds = info.get("commands") or []
    if not any(c.get("name") and _base(c["name"]).removesuffix(".exe") in DELETERS for c in cmds):
        return None
    c = cmds[0]
    if (len(cmds) != 1 or not c.get("args") or info.get("variables") or info.get("methods") or info.get("redirects")
            or re.search(r"\s-(?:include|exclude|filter)\b", c.get("text", ""), re.I)):
        return None, ONE_DELETE
    import glob
    paths = []
    for a in c["args"]:
        p = os.path.expandvars(os.path.expanduser(a.strip().strip('"').strip("'")))
        p = os.path.abspath(p if os.path.isabs(p) else os.path.join(cwd, p))
        found = glob.glob(p) if any(ch in p for ch in "*?[") else ([p] if os.path.exists(p) else [])
        if not found:
            return None, f"Not deleted: there's nothing at {a}."
        paths += [os.path.abspath(f) for f in found]
    ws = os.path.normcase(os.path.abspath(os.path.expanduser(workspace or ""))).rstrip("\\/")
    for p in paths:
        q = os.path.normcase(p).rstrip("\\/")
        if q == ws or ws.startswith(q + os.sep) or os.path.dirname(q) == q:
            return None, (f"Not deleted: {p} is your whole Workspace, or a folder it's in. That's never deleted; to "
                          "clear something out, name the files or folders inside it.")
    return list(dict.fromkeys(paths)), None


def recycle(paths):
    script = ("Add-Type -AssemblyName Microsoft.VisualBasic; $fs = [Microsoft.VisualBasic.FileIO.FileSystem]; "
              "foreach ($p in ($env:AETHER_PATHS | ConvertFrom-Json)) { if (Test-Path -LiteralPath $p -PathType Container) "
              "{ $fs::DeleteDirectory($p, 'OnlyErrorDialogs', 'SendToRecycleBin') } else "
              "{ $fs::DeleteFile($p, 'OnlyErrorDialogs', 'SendToRecycleBin') } }")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, env=dict(os.environ, AETHER_PATHS=json.dumps(paths)),
                       creationflags=NO_WINDOW)
    left = [p for p in paths if os.path.exists(p)]
    if r.returncode != 0 or left:
        return False, ("Not all of it went to the Recycle Bin: " + (", ".join(left) or (r.stderr.strip()[:200] or "unknown error")))
    return True, "Sent to the Recycle Bin (he can put it back from there): " + "; ".join(paths)


def run(command, cwd, timeout=60, max_chars=8000, cancel=None, on_output=None):
    os.makedirs(cwd, exist_ok=True)
    proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command],
                            cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=NO_WINDOW)
    chunks = []

    def pump():
        for line in iter(proc.stdout.readline, b""):
            text = line.decode("utf-8", "replace")
            chunks.append(text)
            if on_output:
                on_output(text)
    t = threading.Thread(target=pump, daemon=True)
    t.start()
    waited = 0.0
    try:
        while True:
            try:
                proc.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                waited += 0.2
                if (cancel is not None and cancel.is_set()) or waited >= timeout:
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
                    proc.wait(5)
                    t.join(2)
                    return (130 if cancel is not None and cancel.is_set() else 124), \
                        "".join(chunks)[-max_chars:] + ("\n[stopped]" if cancel is not None and cancel.is_set() else f"\n[timed out after {timeout}s]")
        t.join(3)
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
    out = "".join(chunks).rstrip()
    if len(out) > max_chars:
        out = out[:max_chars] + f"\n... ({len(out) - max_chars} more characters cut)"
    return proc.returncode, out or "(no output)"
