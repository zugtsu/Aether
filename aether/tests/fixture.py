import os
import subprocess
import tempfile

from aether.config import Config

FILES = {
    "system/persona.md": "---\ndescription: Who I am.\nread_only: true\n---\n**Name:** Testy\nI tease Jordan.\n",
    "system/human.md": "---\ndescription: My read of Jordan.\n---\nJordan likes anime.\n",
    "system/human/facts.md": "---\ndescription: Facts, append-only.\n---\n- 2026-09-14: Is self-taught.\n",
    "system/projects.md": "---\ndescription: Project board.\n---\n**Aether** | building\n",
    "system/journal.md": "---\ndescription: My journal.\n---\n- 2026-09-25: A good day.\n",
    "system/rules.md": "---\ndescription: Rules. Set by Jordan.\nread_only: true\n---\nJordan is my person.\n",
    "reference/almanac/frost.md": "---\ndescription: Frost notes.\n---\nFrost dates.\n",
    "reference/garden.md": "---\ndescription: Garden notes.\n---\nGarden layout.\n",
    "skills/echo/SKILL.md": "---\nname: echo\ndescription: Says back what you give it.\n---\nRun:\n```\n{\"step\": \"skill\", \"skill\": \"echo\", \"args\": [\"hello\"]}\n```\n",
    "skills/echo/scripts/echo.py": "import os, sys\nprint('ARGS=' + '|'.join(sys.argv[1:]))\nprint('MEM=' + os.environ.get('MEMORY_DIR', ''))\n",
    "skills/fail/SKILL.md": "---\nname: fail\ndescription: Always fails.\n---\n```\n{\"step\": \"skill\", \"skill\": \"fail\", \"args\": [\"go\"]}\n```\n",
    "skills/fail/scripts/fail.py": "import sys\nprint('broken on purpose')\nsys.exit(3)\n",
    "skills/slow/SKILL.md": "---\nname: slow\ndescription: Takes a long time.\n---\n{\"step\": \"skill\", \"skill\": \"slow\", \"args\": []}\n",
    "skills/slow/scripts/slow.py": "import time\ntime.sleep(30)\nprint('done')\n",
    "skills/nofront/SKILL.md": "# No frontmatter\n`python x.py`\n",
    "skills/nofront/scripts/x.py": "print(1)\n",
    "skills/noscript/SKILL.md": "---\nname: noscript\ndescription: Instructions only.\n---\nUse pdftoppm.\n",
    "skills/badpy/SKILL.md": "---\nname: badpy\ndescription: Broken script.\n---\n`python bad.py`\n",
    "skills/badpy/scripts/bad.py": "def (:\n",
    "skills/plants/SKILL.md": "---\nname: plants\ndescription: Watering schedule.\n---\n{\"step\": \"skill\", \"skill\": \"plants\", \"command\": \"next\", \"args\": []}\n{\"step\": \"skill\", \"skill\": \"plants\", \"command\": \"skip\", \"args\": [\"<date>\"]}\n",
    "skills/plants/scripts/plants.py": "import sys\nCOMMANDS = ('next', 'skip')\nprint('plants ' + ' '.join(sys.argv[1:]))\n",
}


def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=t@t", "-C", root, *args],
                          capture_output=True, text=True, check=True).stdout


def make_memory():
    root = tempfile.mkdtemp(prefix="aether-mem-")
    for rel, text in FILES.items():
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root


def make_config(root, **kw):
    kw.setdefault("comfy_launch", False)
    kw.setdefault("voice_engine", "kokoro")
    kw.setdefault("start_kokoro", False)
    kw.setdefault("archive_after_days", 0)
    kw.setdefault("library_dir", tempfile.mkdtemp(prefix="lib-"))
    kw.setdefault("workspace_dir", tempfile.mkdtemp(prefix="ws-"))
    from aether import tool_table
    kw.setdefault("ask_first", {**tool_table.ask_first(), "plants": ["skip"]})
    kw.setdefault("lookup_commands", {**tool_table.lookup_commands(), "plants": ["next"]})
    return Config(memory_dir=root, agent_id="agent-test", **kw)
