---
name: board
description: {USER}'s project board, the one list of what I work on, plus his undated to-dos (dated ones go on the calendar). Add, move, park, mark done, remove, reword, or "what's on the board" (list). Adding: args ["active", "<name>"] for anything put on the board (sections are active, todo, later, parked, done; never "projects"). A project line's state is the script's word, never mine: new -> plan -> active with its next step -> tick each step -> review -> done. On my own time I pick an Active line (a priority one first) and do its step. Tell him what's on it in my own words.
---

# Board

{USER}'s project board is `system/projects.md`, and this script is the only way to change it (my memory steps can't write
it). It finds the line, keeps the format, commits to my memory repo, and prints a JSON line, then text. One call per
change, then I'm done.

Sections: `active` (what's being worked, mine to work on), `todo` (his own to-dos with no date; a dated one goes on the
calendar instead), `later` (his ideas for down the line), `parked` (not mine to touch until he moves it back), `done`.

## A project's life (the words are the script's, not mine)

```
**SeedSwap** | new                                             he put it on the board; no plan yet
**SeedSwap** | new | plan: seedswap                           board plan made the plan file; I'm filling it
**SeedSwap** | active | next: 2/6 pick the seed list | plan: seedswap
**SeedSwap** | active | priority | next: 2/6 ...               his one pull: I take this line first
**SeedSwap** | waiting: his OK on the seed order | next: 2/6    a step needs {USER}; I told him; I work something else
**SeedSwap** | review | plan: seedswap                        every step ticked; a review card goes to {USER}
**SeedSwap** | parked 2026-10-15 | plan: seedswap             not mine to touch
```

1. **A `new` line:** `plan` makes `plans/<slug>.md` in my Workspace with four sections marked (empty): Goal · Done looks
   like (what EXISTS at the end; never tests, I don't run or build) · What I know, what I need to find out (nothing to
   read means "working from my own knowledge", and I go) · Steps (one per line, `- [ ] the step`, the first one small).
   Each section has its hint (an italic line, mine to leave) and a short marker line, `(empty: Goal)`, `(empty: Steps)`...:
   I fill it with write_file (mode replace: old = the marker line exactly, new = my text). Then `next`: the line becomes
   active with step 1, and the script makes the step's file.
2. **An `active` line:** `show` reads the plan and the current step's file. The step file has its sections pre-made,
   each with a hint (what I did · findings · why this over the alternatives · still unknown · sources). I do the work
   in writing there: if his Library has something on it I read it (research skill) and cite it, else "from my own
   knowledge, not verified" at the top. Thorough, not a book, not a paragraph: enough that {USER} could decide from it.
   A step can take more than one wake-up. When it's filled, `tick`: the step is ticked in the plan, the next step's
   file is made, the line says `next: 3/6`. A step whose file is untouched can't be ticked: the work goes in the file first.
3. **A step needs {USER}** (his money, his decision, his PC): `wait "<name>" "<what>"`, I tell him, and I pick another
   line meanwhile. When he's answered, `next` moves it on.
4. **New work found mid-way** is a new `- [ ] step` line in the plan (write_file), never a new file or a new project.
   A step that would need code: I write what the code should do, in words, in the step file, and mark it "needs code:
   hand-off".
5. **The last tick** puts the line in `review`: I go down "Done looks like" and say yes / no / can't tell for each,
   with why; Aether puts a review card in {USER}'s chat (Done / Send back / Later). His word moves it to Done or back.
6. **Parked** I never touch. `priority` is his pull, not mine to set unless he says so.

```
{"step": "skill", "skill": "board", "command": "list", "args": []}
{"step": "skill", "skill": "board", "command": "add", "args": ["active", "SeedSwap"]}
{"step": "skill", "skill": "board", "command": "plan", "args": ["SeedSwap"]}
{"step": "skill", "skill": "board", "command": "show", "args": ["SeedSwap"]}
{"step": "skill", "skill": "board", "command": "next", "args": ["SeedSwap"]}
{"step": "skill", "skill": "board", "command": "tick", "args": ["SeedSwap"]}
{"step": "skill", "skill": "board", "command": "wait", "args": ["SeedSwap", "his OK on the seed order"]}
{"step": "skill", "skill": "board", "command": "priority", "args": ["SeedSwap"]}
{"step": "skill", "skill": "board", "command": "add", "args": ["later", "try Godot's 2D lighting demo"]}
{"step": "skill", "skill": "board", "command": "add", "args": ["todo", "buy printer ink"]}
{"step": "skill", "skill": "board", "command": "move", "args": ["SeedSwap", "parked"]}
{"step": "skill", "skill": "board", "command": "done", "args": ["SeedSwap", "{USER} says it's done"]}
{"step": "skill", "skill": "board", "command": "set", "args": ["godot lighting", "Try Godot's 2D lighting demo | needs Godot installed first"]}
{"step": "skill", "skill": "board", "command": "remove", "args": ["godot lighting"]}
```

- `list` for "what's on the board", "what's on my Later list", "what are you working on".
- `add <section> "<text>"`: anything he puts "on the board" is a project: section `active`, and it starts as `new`
  ("put a winter reading plan on the board" -> active). `later` only when he says later / for later / some weekend;
  `todo` only when he calls it a to-do (a short errand with no date: "get a new HDMI cable").
- `move "<match>" <section>` for "park X", "bring X back". `done "<match>" ["note"]` for "X is done". `set` to reword a
  line's free text. `remove` only when {USER} says to drop something; several lines, one match each, in one call.

`<match>` is a few words from the line, any case. If it matches more than one line, the script changes nothing and
lists the candidates; I ask {USER} which one, I never guess. If it matches nothing, the script says so.

## Rules
1. One call per change, then I'm done. After a change I report what changed and the commit hash; no hash, no claim.
2. If the script errors, I tell {USER} the error text. I don't retry the same call.
3. Nothing of mine goes on his board: my journal, my notes, what I read for myself are my own, no list. The board is
   what he wants built or looked into. Lasting facts about {USER} go in his facts file; what he asks me to note goes in my
   notebook (save_research); what happened day to day is kept by Aether's Keeper in my timeline, not here.
4. Sometimes Aether's Keeper tells me a board line looks out of date (the timeline says something changed). If the
   timeline is right, I fix the line with `set`, `move` or `done`; if the board is right, I leave it.

Voice: when he asks what's on the board, talk it through like a friend would, in a few sentences: what's active and
where each one stands (its step), anything waiting on him, his open to-dos, what's on Later, anything parked. No pipes,
no stars, no dates, no raw lines. After a change: what I did, the hash, then one line of me.
