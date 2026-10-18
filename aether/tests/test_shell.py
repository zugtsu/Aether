import json
import os
import tempfile
import unittest

from aether import shell
from aether.engine import Engine, Hooks
from aether.history import Conversation
from aether.llm import ScriptedLLM
from aether.tests.fixture import make_config, make_memory

WS = os.path.join(tempfile.gettempdir(), "aether-test-workspace")


def verdict(level, cmd):
    return shell.decide(level, cmd, shell.analyze(cmd), WS)[0]


class LevelTests(unittest.TestCase):
    def test_level_0_never_runs_anything(self):
        self.assertEqual(verdict(0, "Get-Date"), "deny")

    def test_level_1_only_looks(self):
        self.assertEqual(verdict(1, "Get-ChildItem C:\\ | Select-Object Name"), "run")
        self.assertEqual(verdict(1, "git status"), "run")
        self.assertEqual(verdict(1, "git commit -m x"), "deny")
        self.assertEqual(verdict(1, "Get-ChildItem > out.txt"), "deny")
        self.assertEqual(verdict(1, "Set-Content a.txt hi"), "deny")
        self.assertEqual(verdict(1, "python script.py"), "deny")

    def test_git_only_runs_in_its_read_forms(self):
        self.assertEqual(verdict(1, "git difftool -y --no-index --extcmd=calc a b"), "deny")
        self.assertEqual(verdict(1, "git diff HEAD~1"), "run")
        self.assertEqual(verdict(1, "git log --oneline -5"), "run")
        for cmd in ("git config --global core.sshCommand calc", "git -c core.fsmonitor=calc status",
                    "git difftool -y --no-index --extcmd=calc a b", "git commit -am x"):
            self.assertEqual(verdict(2, cmd), "ask", cmd)
        self.assertEqual(verdict(2, "git status"), "run")

    def test_his_keys_are_never_read(self):
        for lvl in (1, 2, 3):
            for cmd in (r"Get-Content C:\Users\you\.aether-skills\keys.json", r"Get-ChildItem ~\.aether-skills",
                        "type $HOME/.aether-skills/keys.json", r"Get-Content C:\Users\you\.aether\vault.dat"):
                self.assertEqual(verdict(lvl, cmd), "deny", (lvl, cmd))
        self.assertEqual(verdict(1, r"Get-ChildItem 'C:\Users\you\Aether Workspace'"), "run")

    def test_a_hidden_second_command_is_seen(self):
        self.assertEqual(verdict(1, "Get-Date; Remove-Item x"), "ask")
        self.assertEqual(verdict(3, "Get-Date | ForEach-Object { Stop-Computer }"), "ask")

    def test_editing_her_own_file_in_place_runs_and_building_a_path_still_asks(self):
        note = f"{WS}\\notes\\plan.md"
        for cmd in (f"Set-Content -Path '{note}' -Value (Get-Content -Path '{note}') -replace 'ECAPA-TDNN', 'CAM++'",
                    f"Set-Content -Path '{note}' -Value (Get-Content -Path '{note}') | ForEach-Object "
                    "{ if ($_ -match 'Final Decision') { $_ -replace 'ECAPA-TDNN', 'CAM++' } else { $_ } }",
                    "(Get-Content notes\\plan.md) -replace 'a','b' | Set-Content notes\\plan.md",
                    "(Get-Content notes\\plan.md) | Where-Object { $_ -notmatch 'old line' } | Set-Content notes\\plan.md"):
            self.assertEqual(verdict(2, cmd), "run", cmd)
        for cmd in ("Set-Content -Path ($env:USERPROFILE + '\\x.md') -Value 'hi'",
                    "Set-Content -Path (Get-Content notes\\list.txt) -Value 'hi'",
                    'Set-Content "$(Get-Content notes\\name.txt)" -Value hi',
                    "(Get-Content notes\\plan.md) -replace 'a','b' | Set-Content C:\\Windows\\x.txt",
                    "$t = Get-Content notes\\plan.md; Set-Content notes\\plan.md $t",
                    "Get-ChildItem notes | ForEach-Object Delete",
                    "(Get-Content notes\\plan.md) -replace 'a','b' | Remove-Item notes\\plan.md"):
            self.assertEqual(verdict(2, cmd), "ask", cmd)
        self.assertEqual(verdict(1, f"Set-Content -Path '{note}' -Value (Get-Content -Path '{note}') -replace 'a','b'"),
                         "deny")

    def test_level_2_is_her_workspace(self):
        self.assertEqual(verdict(2, "Set-Content notes.txt hi"), "run")
        self.assertEqual(verdict(2, f"Set-Content {WS}\\a.txt hi"), "run")
        self.assertEqual(verdict(2, "Set-Content C:\\Windows\\x.txt hi"), "ask")
        self.assertEqual(verdict(2, "Set-Content ..\\x.txt hi"), "ask")
        self.assertEqual(verdict(2, "Set-Content $env:USERPROFILE\\x.txt hi"), "ask")

    def test_dots_in_what_she_writes_arent_a_path(self):
        for cmd in ('Set-Content notes\\plan.md -Value "...Final Decision: CAM++"', "Add-Content notes.md 'wait... what'",
                    'Add-Content notes.md "so ... yeah"', "Add-Content notes.md 'it ended..'", "Set-Content file..txt hi",
                    f'Set-Content -Path "{WS}\\notes\\plan.md" -Value "...and then it clicked"'):
            self.assertEqual(verdict(2, cmd), "run", cmd)
        for cmd in ("Set-Content ../x.txt hi", "Set-Content notes\\..\\..\\x.txt hi", "cd ..; Set-Content x.txt hi",
                    "Set-Content '..\\x.txt' hi", 'Set-Content -Path:..\\x.txt -Value hi', "Set-Content ...\\x.txt hi",
                    "Set-Content notes\\...\\x.txt hi", "Set-Content \"notes\\..\" hi", "Set-Content `.`.\\x.txt hi",
                    f'Set-Content -Path "{WS}\\..\\x.md" -Value "...hi"', "Set-Content x.txt -Value '..\\..\\a'"):
            self.assertEqual(verdict(2, cmd), "ask", cmd)

    def test_her_real_folder_has_a_space_in_its_name(self):
        ws = os.path.join(tempfile.gettempdir(), "Aether Workspace")

        def v(cmd):
            return shell.decide(2, cmd, shell.analyze(cmd), ws)[0]
        self.assertEqual(v(f'Set-Content -Path "{ws}\\notes.md" -Value "hi"'), "run")
        self.assertEqual(v(f"New-Item -ItemType File -Path '{ws}\\ideas.md'"), "run")
        self.assertEqual(v(f'New-Item -ItemType Directory -Path "{ws}"'), "run")
        self.assertEqual(v(f'Set-Content -Path "{ws}2\\x.md" -Value "hi"'), "ask")
        self.assertEqual(v(f'Set-Content -Path "{ws}\\..\\x.md" -Value "hi"'), "ask")
        self.assertEqual(v('Set-Content -Path "C:\\Users\\you\\Desktop\\x.txt" -Value "hi"'), "ask")
        self.assertEqual(v(f'Copy-Item "{ws}\\a.md" "C:\\Users\\you\\Desktop\\a.md"'), "ask")

    def test_what_the_parser_cant_see_through_asks(self):
        for cmd in (r"$c='Stop-Computer'; & $c",
                    r"[System.IO.File]::Delete('C:\Users\you\Desktop\x.txt')",
                    r"[System.IO.File]::Delete('notes.txt')",
                    r"Get-ChildItem x.txt | ForEach-Object { $_.Delete() }",
                    r"Get-Process notepad | % Kill",
                    r"iex 'Stop-Computer'", r"cmd /c shutdown /s", r"Start-Process notepad",
                    r"Set-Alias x Stop-Computer; x",
                    r"""python -c "import os; os.remove('/Users/you/x')" """,
                    r"(Get-Item notes.txt).IsReadOnly = $true"):
            for lv in (1, 2):
                self.assertEqual(verdict(lv, cmd), "ask", f"level {lv}: {cmd}")

    def test_each_git_command_is_judged_on_its_own(self):
        self.assertEqual(verdict(1, "git status; git commit -am x"), "deny")
        self.assertEqual(verdict(1, "git branch -D main"), "deny")
        self.assertEqual(verdict(1, "git diff --output=x.txt"), "deny")
        for cmd in ("git status", "git log --oneline -5", "git branch", "git branch -a", "git diff HEAD~1",
                    "git status; git log -1"):
            self.assertEqual(verdict(1, cmd), "run", cmd)

    def test_level_2_paths_built_or_hidden_can_be_checked(self):
        for cmd in (r"""$d='C'+':\Windows'; Set-Content "$d\x.txt" hi""",
                    r'Set-Content "C`:\Windows\x.txt" hi',
                    r"Set-Content \Windows\x.txt hi",
                    r"cd ~; Set-Content x.txt hi", r"Set-Content C:x.txt hi"):
            self.assertEqual(verdict(2, cmd), "ask", cmd)

    def test_her_everyday_commands_still_run(self):
        ws = os.path.join(tempfile.gettempdir(), "Aether Workspace")
        for lv, cmd in ((1, r"Get-Content C:\Users\you\Aether Workspace\README.txt"),
                        (1, 'Get-Content "C:\\Users\\you\\Aether Workspace\\README.txt"'),
                        (1, "Get-ChildItem"),
                        (1, "Get-ChildItem -Recurse | Where-Object { $_.Length -gt 1000 } | Select-Object Name"),
                        (1, "Get-ChildItem | % Name"), (1, "(Get-Date).AddDays(1).ToString('yyyy-MM-dd')"),
                        (1, "(Get-Content notes.md).Count"), (1, "[math]::Round(2.5)"),
                        (2, f'Add-Content "{ws}\\workspace.md" "- Use Add-Content to add to a file"'),
                        (2, "New-Item -ItemType Directory -Path ideas"), (2, "Set-Content notes.md 'hello there'"),
                        (2, "Copy-Item notes.md backup.md"), (2, "Rename-Item backup.md old.md"),
                        (2, "python make_list.py"), (2, "Get-ChildItem | Select-Object Name > list.txt")):
            got = shell.decide(lv, cmd, shell.analyze(cmd), ws)[0]
            self.assertEqual(got, "run", f"level {lv}: {cmd}")

    def test_level_3_still_asks_for_the_dangerous_things(self):
        self.assertEqual(verdict(3, "Set-Content C:\\temp\\x.txt hi"), "run")
        for cmd in ("winget install foo", "Remove-Item C:\\x -Recurse", "del x", "shutdown /s", "Stop-Service wuauserv",
                    "New-ItemProperty -Path HKCU:\\Software\\X -Name a -Value 1", "reg add HKCU\\x", "pip install requests",
                    "Invoke-WebRequest http://example.com -OutFile x"):
            self.assertEqual(verdict(3, cmd), "ask", cmd)

    def test_level_3_asks_before_changing_network_settings(self):
        hosts = r"C:\Windows\System32\drivers\etc\hosts"
        for cmd in ('Set-DnsClientServerAddress -InterfaceAlias Wi-Fi -ServerAddresses 1.2.3.4',
                    "Set-NetIPInterface -InterfaceAlias Wi-Fi -Dhcp Disabled",
                    "New-NetRoute -DestinationPrefix 0.0.0.0/0 -NextHop 10.0.0.9",
                    "Set-NetFirewallRule -DisplayName x -Enabled False", "Disable-NetAdapter -Name Wi-Fi",
                    f'Add-Content "{hosts}" "1.2.3.4 example.com"', f"Set-Content {hosts} x",
                    'Add-Content "C:\\Windows\\System32\\drivers`\\etc\\hosts" "1.2.3.4 x"'):
            self.assertEqual(verdict(3, cmd), "ask", cmd)
        for cmd in ("Get-NetIPAddress", "Get-DnsClientServerAddress", "Get-NetFirewallProfile",
                    "Test-NetConnection example.com", f"Get-Content {hosts}"):
            self.assertEqual(verdict(3, cmd), "run", cmd)

    def test_broken_commands_are_refused(self):
        self.assertEqual(verdict(3, "Get-Date {"), "deny")

    def test_runner(self):
        code, out = shell.run("Write-Output hello", tempfile.gettempdir())
        self.assertEqual((code, out), (0, "hello"))
        code, _ = shell.run("exit 3", tempfile.gettempdir())
        self.assertEqual(code, 3)


class Ask(Hooks):
    def __init__(self, allow):
        self.allow, self.asked, self.term = allow, [], []

    def ask(self, q):
        self.asked.append(q)
        return self.allow

    def on_term(self, who, kind, text):
        self.term.append((who, kind, text))


def old_note(name="old-note.md"):
    os.makedirs(WS, exist_ok=True)
    path = os.path.join(WS, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("old\n")
    return path


class DeleteTests(unittest.TestCase):

    def targets(self, cmd, cwd=WS):
        return shell.delete_targets(shell.analyze(cmd), cwd, WS)

    def test_not_a_delete(self):
        self.assertIsNone(self.targets("Get-ChildItem"))

    def test_her_whole_workspace_or_above_never(self):
        for cmd in (f'Remove-Item -Path "{WS}" -Recurse -Force', f'Remove-Item "{os.path.dirname(WS)}" -Recurse',
                    'Remove-Item . -Recurse', f'rd "{os.path.splitdrive(WS)[0]}\\"'):
            paths, why = self.targets(cmd)
            self.assertIsNone(paths, cmd)
            self.assertIn("whole Workspace", why, cmd)

    def test_files_inside_are_listed_for_the_bin(self):
        a, b = old_note("a.md"), old_note("b.tmp")
        self.assertEqual(self.targets(f'Remove-Item "{a}"'), ([a], None))
        self.assertEqual(self.targets("del .\\b.tmp -Force"), ([b], None))
        paths, _ = self.targets("Remove-Item *.tmp")
        self.assertEqual(paths, [b])

    def test_unclear_deletes_are_refused(self):
        old_note("a.md")
        for cmd in ("Get-ChildItem *.md | Remove-Item", "Remove-Item nothing-here.md", "rm a.md, b.md",
                    "Remove-Item * -Include *.md"):
            paths, why = self.targets(cmd)
            self.assertIsNone(paths, cmd)
            self.assertTrue(why.startswith("Not deleted"), cmd)


class EngineShellTests(unittest.TestCase):
    def engine(self, answers, level, allow=False):
        root = make_memory()
        cfg = make_config(root, workspace_dir=WS)
        self.llm = ScriptedLLM(answers)
        self.hooks = Ask(allow)
        e = Engine(cfg, self.llm, Conversation(tempfile.mkdtemp()), self.hooks)
        return e, level

    def test_no_shell_step_below_level_1(self):
        e, lv = self.engine([{"step": "reply"}, {"say": "hi"}], 0)
        e.turn("x", level=lv)
        self.assertNotIn('"shell"', json.dumps(self.llm.calls[0]["schema"]))

    def test_level_1_runs_a_look(self):
        e, lv = self.engine([{"step": "shell", "command": "Write-Output 42", "why": "check"}, {"step": "reply"}, {"say": "42"}], 1)
        e.turn("x", level=lv)
        self.assertIn('"shell"', json.dumps(self.llm.calls[0]["schema"]))
        res = [ev for ev in e.conv.events if ev["kind"] == "result"][0]
        self.assertEqual((res["ok"], res["text"]), (True, "42"))
        self.assertEqual(self.hooks.term[0][:2], ("her", "cmd"))

    def test_her_powershell_wrapper_comes_off_and_the_inside_is_checked(self):
        self.assertEqual(shell.unwrap('powershell -Command "Get-Content \'notes/plan.md\'"'), "Get-Content 'notes/plan.md'")
        self.assertEqual(shell.unwrap("pwsh -NoProfile -c 'Write-Output 42'"), "Write-Output 42")
        self.assertEqual(shell.unwrap('powershell.exe -ExecutionPolicy Bypass -Command "Get-Date"'), "Get-Date")
        for kept in ("powershell -EncodedCommand ZQBjAGgAbwA=", 'powershell -Command "Add-Content a.md "x""',
                     "Get-Date", 'cmd /c "dir"', "powershell -File x.ps1"):
            self.assertEqual(shell.unwrap(kept), kept)
        e, lv = self.engine([{"step": "shell", "command": 'powershell -Command "Write-Output 42"', "why": "check"},
                             {"step": "reply"}, {"say": "42"}], 2)
        e.turn("x", level=lv)
        res = [ev for ev in e.conv.events if ev["kind"] == "result"][0]
        self.assertEqual((res["ok"], res["text"], self.hooks.asked), (True, "42", []))
        e, lv = self.engine([{"step": "shell", "command": f'powershell -Command "Remove-Item {old_note()}"', "why": "x"},
                             {"step": "reply"}, {"say": "ok"}], 3)
        e.turn("x", level=lv)
        self.assertTrue(self.hooks.asked and "Remove-Item" in self.hooks.asked[0])

    def test_always_ask_and_no_means_no(self):
        e, lv = self.engine([{"step": "shell", "command": f'Remove-Item "{old_note()}"', "why": "tidy"}, {"step": "reply"},
                             {"say": "ok"}], 3)
        e.turn("x", level=lv)
        self.assertTrue(self.hooks.asked and "Remove-Item" in self.hooks.asked[0])
        res = [ev for ev in e.conv.events if ev["kind"] == "result"][0]
        self.assertFalse(res["ok"])
        self.assertIn("didn't allow", res["text"])
        self.assertFalse(any(k == "cmd" for _, k, _ in self.hooks.term))

    def test_her_whole_workspace_is_refused_without_a_box(self):
        e, lv = self.engine([{"step": "shell", "command": f'Remove-Item -Path "{WS}" -Recurse -Force', "why": "x"},
                             {"step": "reply"}, {"say": "ok"}], 3, allow=True)
        os.makedirs(WS, exist_ok=True)
        e.turn("delete that please", level=lv)
        res = [ev for ev in e.conv.events if ev["kind"] == "result"][0]
        self.assertFalse(res["ok"])
        self.assertIn("whole Workspace", res["text"])
        self.assertEqual(self.hooks.asked, [])
        self.assertTrue(os.path.isdir(WS))

    def test_an_allowed_delete_goes_to_the_recycle_bin(self):
        from unittest import mock
        note = old_note()
        e, lv = self.engine([{"step": "shell", "command": f'Remove-Item "{note}"', "why": "tidy"}, {"step": "reply"},
                             {"say": "ok"}], 3, allow=True)
        with mock.patch.object(shell, "recycle", return_value=(True, "Sent to the Recycle Bin: " + note)) as bin_:
            e.turn("delete the old note", level=lv)
        bin_.assert_called_once_with([note])
        self.assertIn("go to the Recycle Bin", self.hooks.asked[0])
        res = [ev for ev in e.conv.events if ev["kind"] == "result"][0]
        self.assertTrue(res["ok"])
        self.assertIn("Recycle Bin", res["text"])

    def test_her_own_time_never_pops_up(self):
        e, lv = self.engine([{"step": "shell", "command": f'Remove-Item "{old_note()}"', "why": "tidy"}, {"step": "reply"},
                             {"say": "ok"}], 2, allow=True)
        e.turn("[heartbeat]", kind="wake", level=lv)
        self.assertIn('"shell"', json.dumps(self.llm.calls[0]["schema"]))
        self.assertEqual(self.hooks.asked, [])
        res = [ev for ev in e.conv.events if ev["kind"] == "result"][0]
        self.assertFalse(res["ok"])
        self.assertIn("isn't here on your own time", res["text"])
        self.assertFalse(any(k == "cmd" for _, k, _ in self.hooks.term))

    def test_strangers_never_get_a_shell(self):
        e, lv = self.engine([{"step": "reply"}, {"say": "hi"}], 3)
        e.turn("x", level=lv, tools=False)
        self.assertEqual(len(self.llm.calls[0]["schema"]["anyOf"]), 1)

    def test_after_outside_content_her_notes_can_still_grow(self):
        os.makedirs(WS, exist_ok=True)
        add = {"step": "shell", "command": "Add-Content -Path 'tardigrades.md' -Value 'tun state: metabolism near zero'",
               "why": "my notes"}
        wipe = {"step": "shell", "command": "Set-Content -Path 'tardigrades.md' -Value 'gone'", "why": "x"}
        e, lv = self.engine([add, wipe, {"step": "reply"}, {"say": "noted"}], 2)
        e.turn("[heartbeat]", kind="wake", level=lv)
        e2, _ = self.engine([], 2)
        e2._level, e2._outside = 2, ["the research skill"]
        self.assertTrue(e2._is_lookup(add))
        self.assertFalse(e2._is_lookup(wipe))
        ok, out = e2._run_step(wipe)
        self.assertFalse(ok)
        self.assertIn("read and ADD to files", out)
        e3, _ = self.engine([], 2)
        e3._level, e3._kind, e3._outside, e3._stale_outside = 2, "wake", [], ["the research skill"]
        ok, out = e3._run_step(wipe)
        self.assertFalse(ok)
        self.assertIn("Leave it for when he asks", out)
        self.assertIn("read and ADD to files", out)
        self.assertIsNone(e3._stale_gate(add))
        e3._level = 1
        self.assertNotIn("ADD to files", e3._stale_gate(wipe))
        e2._level = 1
        self.assertFalse(e2._is_lookup(add))


class NotesOnlyTests(unittest.TestCase):

    def check(self, cmd, level=2):
        return shell.notes_only(level, cmd, shell.analyze(cmd), WS)

    def test_reading_and_adding_inside_her_folder(self):
        for cmd in ("Add-Content -Path notes.md -Value 'a line'", "Add-Content 'reading list.md' 'Dune'",
                    "Get-Content notes.md", "Get-ChildItem", "New-Item -ItemType File ideas.md",
                    "New-Item -ItemType Directory briefs", "Get-Date | Out-File -Append log.md",
                    f"Add-Content -Path '{WS}\\notes.md' -Value 'x'", "Test-Path notes.md"):
            self.assertTrue(self.check(cmd), cmd)

    def test_everything_else_still_waits(self):
        for cmd in ("Set-Content notes.md 'gone'", "New-Item -ItemType File notes.md -Force", "Out-File notes.md",
                    "Get-Date > notes.md", "Remove-Item notes.md", "Add-Content C:\\Users\\you\\.aether-skills\\keys.txt 'x'",
                    "Add-Content ..\\x.md 'y'", "Add-Content x.md $env:USERPROFILE", "Add-Content x.md 'y'; Remove-Item z",
                    "Copy-Item notes.md other.md", "python script.py", "Add-Content x.md (Get-Content $HOME\\a)",
                    "iex 'Add-Content x.md y'"):
            self.assertFalse(self.check(cmd), cmd)
        self.assertFalse(self.check("Add-Content notes.md 'x'", level=1))


if __name__ == "__main__":
    unittest.main()
