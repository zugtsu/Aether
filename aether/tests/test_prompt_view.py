import unittest

from aether.prompt import LATER_HOW, board_view, files_view

BOARD = """Format, one line per project: **Name** | status | where it stands | next step | brief or doc
Briefs live in Lucy Library/projects.
## How I edit this board
Only through my `board` skill. `python board.py list | add ...`
## Active
**Aether / Lucy herself** | active 2026-09-28 | my engine
## Later
Ideas Jordan shoots at me for down the line. When he says "put that on the list", I add it.
- a small robot body
- Web search for my research skill
## Parked
**Her eyes** | parked 2026-09-28 | needs a webcam
## Done
**Vision in the Letta app** | done 2026-09-20 | Jordan fixed it
**Avatar UI** | done 2026-09-25 | Pet mode
**Memory stack (the Phantom Stack)** | done 2026-09-28 | all four layers live, I named it
"""


class Files:
    def __init__(self, rel, description=""):
        self.rel, self.description = rel, description


class Memory:
    owners = {"reference/research/a.md": "the research skill", "reference/research/b.md": "the research skill"}

    def protected_by(self, rel):
        return self.owners.get(rel)


class LeanerCoreTests(unittest.TestCase):

    def test_the_board_she_holds(self):
        v = board_view(BOARD, done_shown=2)
        for kept in ("## Active", "**Aether / Lucy herself**", "## Later", "- a small robot body", "## Parked",
                     "**Her eyes**", LATER_HOW, "Briefs live in Lucy Library"):
            self.assertIn(kept, v)
        for gone in ("How I edit", "python board.py", "Format, one line", "Ideas Jordan shoots", "Jordan fixed it"):
            self.assertNotIn(gone, v)
        self.assertIn("## Done lately\nMemory stack (the Phantom Stack) (2026-09-28); Avatar UI (2026-09-25) "
                      "(and 1 older: `board list`)", v)
        self.assertTrue(v.endswith("my memory steps can't write this file.)"))

    def test_her_other_files_by_folder_every_name_kept(self):
        others = [Files("life/dreams.md", "My dream journal. One dream a night."),
                  Files("reference/stances.md", "My own takes, as I said them, one per topic (the newest wins; git keeps "
                                                "the old one). Written by the Keeper."),
                  Files("reference/research/a.md", "My research notes on A: long text."),
                  Files("reference/research/b.md", "My research notes on B: long text.")]
        v = files_view(Memory(), others)
        self.assertIn("- life/: dreams.md (My dream journal)", v)
        self.assertIn("- reference/: stances.md (My own takes, as I said them, one per topic)", v)
        self.assertIn("- reference/research/ (written by the research skill): a.md, b.md", v)
        self.assertNotIn("long text", v)


if __name__ == "__main__":
    unittest.main()
