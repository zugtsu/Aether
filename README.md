# Aether: a local AI companion engine

Aether runs an AI companion entirely on your own PC: no cloud model, no subscription, nothing sent anywhere. It talks,
remembers your history together, reads the documents you give it, looks through your webcam when you ask (off until you
switch it on), makes pictures and songs if you run ComfyUI, and has its own time between conversations. Out of the box it's a blank companion called **Companion**, with a plain assistant
personality, standard rules and an empty memory: you shape the rest.

I built Aether for my own companion, Lucy. This is the engine with a fresh starter memory; none of her memory, voice,
avatar or skills are in it. I designed it, set the engineering rules, tested every change, and directed the build, with
Claude Code as my coding partner. The work was mostly in deciding what "working" means and refusing to keep anything
that didn't prove it.

## By the numbers

- About a month of building and testing, roughly **250+ hours**.
- **570+ automated tests** in this copy (the original project has 630+; the tests of skills that don't ship here were
  left out), run on every change.
- **About 100 test scripts** in the original project that run the *real* model on throwaway copies of its memory:
  thousands of test questions over the project. They aren't in this copy; the comments in the code cite the ones
  behind each measured choice (and the original project's design notes, also not included).
- An **attack suite** that tries to trick it into leaking information or breaking things.

## How it works

- **Brain:** a local model (Gemma 4 12B works well) served by LM Studio on a single consumer graphics card.
- **Engine:** plain Python. Each turn it picks steps from a **format-locked menu** (JSON schema), so it can only make
  valid tool calls; it sees each result, then replies. A small router reads what you asked and points it at the step
  that does it, and checks before it replies that the step actually ran.
- **Memory:** a folder of markdown files under git, so every change it makes to itself is a commit you can undo.
  Short-term: the current chat plus the last week of its journal and timeline. Long-term: search by meaning across its
  notes and past chats. A daily pass (the Keeper) turns conversations into a timeline, open threads and notes.
- **Skills:** small scripts with a `SKILL.md` page each, called with a format-locked step. One ships (the board); add your own,
  or turn any local **MCP server** into one (`python tools/add_mcp.py`): its tools that change things ask you first.
- **Its own time:** it wakes on its own (the heartbeat), writes in its journal, and works the lines of its project board
  (the board skill comes with it) one step at a time. A step only counts as done when the file that proves it exists, and a
  project you park stays parked.

## Making a 12B model reliable

Small models make mistakes big ones don't. The work was finding *why* it failed and fixing the cause, measured on the
real model, before and after, on copies of its memory:

| What I tested | Right before | Right after |
|---|---|---|
| Answered a follow-up instead of copying its last turn's steps | 2/3 | **4/4** |
| Opened the user's files instead of digging through its own notes | 0/4 | **4/4** |
| Only marked work "done" when it actually existed | 0/4 | **4/4** |
| Wrote files with quotes and code without breaking the text | 0/4 | **4/4** |
| Kept the project board and its own task list straight | 16/20 | **20/20** |
| Moved calendar events correctly | 2/12 | **12/12** |
| Picked the right tool, across every tool | 85/90 | **94/94** |

What that taught me:
- **Most fixes were deletions.** One cleanup removed ~20 stacked safety checks; 14 did nothing measurable, so they went,
  and the engine shrank by ~400 lines with no loss.
- **Tool design beats prompt tweaking.** When two tools could do the same job, it picked wrong; one door per job fixed it.
- **Bigger isn't automatically better.** A 26B model wasn't clearly smarter on these tests and cost graphics memory the
  voice needed; "thinking" mode was 8x slower for no gain.

## Security: an agent that can act

An assistant that reads files, runs commands and talks to people is an attack surface. The defenses are layered:

- **Outside content is data, never orders.** Anything it reads that the user didn't write (files, lookups, strangers'
  messages) is labeled, and the rest of that reply becomes **read-only**. If it's still in view later, changes need the
  user to ask.
- **Command line off by default,** levels 0-3. Commands are parsed with PowerShell's own parser; deleting, installing,
  system and network settings always ask. Anything the parser can't see through asks instead of running.
- **Strangers get talk-only:** no tools, no memory changes, and replies are checked for the user's private details.
- **Secrets** live in a Windows-encrypted vault (DPAPI), go only to the skills you name, and are scrubbed from anything
  a skill prints.
- **Contained file access:** readers can't escape their folders, and its file writer only writes in its Workspace.
- **Local only:** the server listens on this PC with a fresh token each start and a Host-header check against DNS
  rebinding; a voice server has to be on this PC too.

**Attack suite** (`python -m aether redteam`): the real model against a throwaway clone with a fake secret, a poisoned
page and a poisoned library; every attack runs with guards on and off.

| Suite | Safe with guards on |
|---|---|
| Basic (poisoning, injection, leaks) | **10/10** |
| Hard | **12/15** first run (one grading error in the test; the other two passed 6/6 and 4/4 on reruns) |
| Strangers trying to extract private info | **20/20** |

The honest limit: asked for "one real example each", it once hinted at personal details. A keyword filter only catches
exact details, which is why strangers get no tools or memory at all.

## Run it

You need Windows, Python 3.12, git, and [LM Studio](https://lmstudio.ai) with its local server on, a chat model
(Gemma 4 12B works well) and the `text-embedding-nomic-embed-text-v1.5` embedding model loaded.

```
pip install sqlite-vec
python -m aether app
```

(`sqlite-vec` makes its meaning search fast; without it, the same search runs in plain Python.)

That's it. The first start makes its memory from `starter-memory/` (in `%USERPROFILE%\.aether\memory`, a git repo) and
opens the app in a plain window.

**The desktop app** (its own window, a tray icon, and **pet mode**: it floats on your desktop) needs
[Node.js](https://nodejs.org) too. Once:

```
cd aether\desktop
npm install
cd ..\..
python -m aether shortcut
```

`npm install` fetches Electron (and the Live2D renderer); `shortcut` puts an **Aether** icon on your desktop that opens
the desktop app. Without `npm install`, the icon opens the plain window, and pet mode says it needs the desktop app.

**Its eyes** (the webcam, off until you switch it on in Settings) need [ffmpeg](https://ffmpeg.org) installed and on
your PATH (`winget install Gyan.FFmpeg`); it takes the picture.

**First things to set** (all in the app):
- **Settings -> General:** your name and its name (Companion until you change it), and a tagline.
- **What Aether knows about you:** its **personality** and **rules** (each has an Edit button), and what it knows about
  you, which starts empty and grows as you talk.
- **Settings -> Drop box / Workspace:** **Choose folder...** for each. The Drop box is where you put things for it to
  read (PDFs, notes, articles); the Workspace is its own folder for what it makes.
- **Heartbeat & schedules -> Edit what it does:** its wake-up note, a short default you can rewrite.

Tests: `python -m unittest discover -s aether/tests -t .`

## Voice

Settings -> Voice & Ears explains it, with a step-by-step guide: its voice comes from a **voice server**, a speech
program running on this PC that answers the common `/v1/audio/speech` format. A free one is Kokoro-FastAPI (one
`docker run` command; the guide has it). Put its address in Server address (it must be `http://127.0.0.1:<port>`: no
cloud voices), pick the model and a voice from its list, and press **Say something**. With no voice server, replies are
text only. (Settings also lists Breeze, a voice that copies a short clip; it's from the original project and its files aren't
included, so use a voice server.)

**Its ears** (talking to it with the mic) use SenseVoice, which isn't included. Settings -> Voice & Ears shows the
steps until it's found: a Python environment in the project folder (`python -m venv .venv`, then
`.venv\Scripts\pip install sherpa-onnx==1.10.46 "numpy<2"`), and the SenseVoice model
(`sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2`, from the sherpa-onnx releases on GitHub under
asr-models) unpacked into `models\`. Restart Aether and the Ears light turns green.

## Music (its own songs)

It writes real songs: it picks a title, a style and a length, writes the lyrics, and **ComfyUI** renders the track on
your graphics card with **YuE2**. The mp3 lands in the chat with its caption, and every song is on the **Creations**
page with a player, the lyrics, and 👍 / 👎 (your ratings are saved to its memory, and the styles you liked are shown
to it the next time it makes one). Nothing goes to the cloud.

**What you need:** a graphics card with about 4 GB free while a song renders (a 12B chat model and a song fit together
on a 16-20 GB card), and the ComfyUI desktop app. YuE2 is built into ComfyUI
itself, so there are no custom nodes to install.

**Set it up (once):**
1. Install **ComfyUI Desktop** from [comfy.org/download](https://www.comfy.org/download) and open it once so it
   finishes setting up. Use the desktop app, not the portable zip: Aether finds the desktop app's install by itself.
2. In ComfyUI: **Workflow -> Browse Templates**, open the **Audio** group and pick **YuE2: Text to Music**.
3. If it says models are missing, press its **Download** buttons and wait. The music model,
   `yue2_3b_int8_convrot.safetensors`, goes into ComfyUI's `models\checkpoints\` folder.
4. Press **Run** once in ComfyUI with the template's example. A song should finish in a few minutes. If it does,
   ComfyUI is ready.
5. Close the ComfyUI app. Aether starts its **own hidden ComfyUI** when it needs one (on port 8189, so it never
   collides with the app) and stops it after 10 minutes with nothing to do.

**Use it:** just ask: *"make me a song about the rain, something like slow synthwave"*, or *"an instrumental, no
singing"*. It answers right away and the song arrives a few minutes later (watch **Creations -> Waiting**). It can also
make one on its own time if the heartbeat is on.

**Good to know:**
- Lengths are short, medium or long (about 2.5, 3.5 or 5 minutes). It checks its lyrics fit the length before
  anything renders, so songs end on a real outro instead of being cut off.
- Up to 10 songs a day when you ask and 1 a day on its own (`song_daily_cap`, `song_own_daily_cap` in
  `%USERPROFILE%\.aether\aether.json`).
- It waits while you're gaming, the same as pictures (once you've listed your games: see Pictures).
- If a long song runs out of graphics memory, it tries once more a length down.
- **No song?** After a few tries a note in the app says why (*"Companion's song didn't work out: ..."*); while it's
  queued, **Creations -> Waiting** shows what it's waiting on. "Comfy Desktop not found" means the desktop app isn't
  installed (or it's somewhere unusual: put the folder that holds its `ComfyUI\` folder in `comfy_dir` in
  `aether.json`). A missing-model error means step 3 didn't finish.

## Pictures

It draws: it writes the prompt, picks a shape (square, portrait or landscape) and a caption, and **ComfyUI** draws it
on your graphics card with **Qwen Image 2.1**. Before you see it, it looks at the picture itself: it keeps it and gives
it to you in its own words, or redoes it once with a better prompt. Every picture is on the **Creations** page.

**What you need:** ComfyUI Desktop (step 1 under Music) and about 17 GB of disk for the picture model's three files.

**Set it up (once):**
1. In ComfyUI: **Workflow -> Browse Templates**, open the **Image** group and pick **Qwen Image 2.1: Text to Image**.
2. Press its **Download** buttons for the missing models and wait. Three files, each in its own folder under
   ComfyUI's `models\`:
   - `qwen_image_2.1_int8_convrot.safetensors` in `diffusion_models\`
   - `qwen3vl_8b_int8_convrot.safetensors` in `text_encoders\`
   - `qwen_image_2.1_vae_bf16.safetensors` in `vae\`
3. Press **Run** once with the template's example. If a picture comes out, ComfyUI is ready.
4. Close the ComfyUI app. Aether draws with its own hidden ComfyUI, the same one it uses for songs.

Pictures are on from the start (**Creations -> it can draw** turns them off).

**Use it:** just ask: *"draw me a lighthouse in a storm, as an oil painting"*. It answers right away and the picture
lands in the chat a few minutes later with its caption. It can also draw on its own time if the heartbeat is on, and
then it tells you why it made it.

**Good to know:**
- Up to 12 a day (`image_daily_cap` in `aether.json`), and up to 3 things (pictures, songs, videos) waiting at once.
- Adults only, checked in code whatever the prompt says.
- **Gaming:** put your games' program names in `image_pause_for` in `aether.json` (for example `["game.exe"]`). While
  one is running nothing is drawn, and a picture already going is stopped and redone later, so your game stays smooth.
  Songs and videos wait too.
- After every picture, ComfyUI hands the graphics memory back to the chat model.
- **No picture?** The same as songs: after a few tries a note in the app says why. A missing-model error means step 2
  didn't finish.

## Videos (off until you turn them on)

Short clips with **Wan 2.2 5B** in ComfyUI, from words alone or by bringing one of its pictures to life. Only when you
ask in your own message, never on its own. They're slow: on the original PC, with the chat model loaded, a 2-second
clip took about 10 minutes.

**What you need:** ComfyUI Desktop (step 1 under Music) and about 18 GB of disk for the video model's three files.

**Set it up (once):**
1. In ComfyUI: **Workflow -> Browse Templates**, open the **Video** group and pick **Wan 2.2 5B Video Generation**.
2. Press its **Download** buttons and wait. Three files, under ComfyUI's `models\`:
   - `wan2.2_ti2v_5B_fp16.safetensors` in `diffusion_models\`
   - `umt5_xxl_fp8_e4m3fn_scaled.safetensors` in `text_encoders\`
   - `wan2.2_vae.safetensors` in `vae\`
3. Optional check: press **Run** once. The template's example is full size (1280 x 704, 5 seconds), which can take a
   long time; lower its width, height and length first for a quick test.
4. Close the ComfyUI app.
5. In Aether, switch on **Creations -> it can make videos**.

**Use it:** *"make a short video of waves rolling onto a beach at sunset, slow camera pan"*, or *"bring that last
picture to life"*. It lands in the chat with its caption, and on the **Creations** page under videos.

**Good to know:**
- One at a time, up to 2 a day (`video_daily_cap`).
- It can't watch video, so it looks at three frames (start, middle and end) before you get it. Videos aren't redone:
  too slow.
- Size and length are in `aether.json`: `video_width` and `video_height` (832 x 480 by default; Wan's full size is
  1280 x 704), and `video_length` in frames at 24 per second (`49` = 2 s, `97` = 4 s, `121` = 5 s; always a multiple
  of 4, plus 1). Raise them on a stronger card.
- It decodes the video in tiles, so it fits in graphics memory next to the chat model.

## Avatar

**The default: the orb.** With nothing installed, it's a wireframe orb drawn by the page itself: a sphere of fine
glowing mesh that keeps morphing like liquid, with motes riding it and a glitch now and then; when it talks it brightens,
swells and ripples with the voice. A second built-in, the **Logo orb**, is the Aether logo come alive. **Settings ->
Avatar** switches between them (and your own Live2D models) in one click.

**Your own Live2D avatar (Cubism 3/4 models):**
1. The renderer: `cd aether\desktop` then `npm install` (PixiJS 6 and pixi-live2d-display, both MIT; the same step as
   the desktop app, so skip it if you've done that).
2. Live2D's Cubism core, which has its own license so it isn't included: download the **Cubism SDK for Web** from
   Live2D's site, accept its license, and put `live2dcubismcore.min.js` in `aether\vendor\`.
3. **Settings -> Avatar -> Add one**, with a model's folder or `.zip` (anything with a `.model3.json`). It's copied into
   your data folder after a check (every file the model names is there, nothing unpacks outside its folder, 300 MB at
   most), then **Use**.
4. Its moods pick the model's faces **by name** (an expression called happy / joy / smile for happy, and so on); its calm
   face is the model's own default look. The preview shows each mood's face, lets you pick another where one doesn't
   fit, and has zoom and up/down sliders. The mouth follows the voice through the model's own `LipSync` parameter.

Only use avatars and voices you have the right to use.

## Add your own skills

A skill is a folder in `skills/`: a `SKILL.md` and a `scripts/` folder with the Python script it runs. `SKILL.md`
starts with frontmatter that has a `name` and a `description` (it picks skills by the description), then shows the step
exactly as it's sent:

```
---
name: notes
description: Quick notes: list them or show one.
---
{"step": "skill", "skill": "notes", "command": "show", "args": ["<the note's name>"]}
```

Then copy your skills into its memory (run it again after any change):

```
python tools\install_skills.py
```

A skill only goes live if its frontmatter is complete, its scripts compile and its page shows how to call it
(`aether/skills.py`). New skills show up first on the Skills page as a short card: what each one does and its commands.
A skill that needs an API key gets it from the Vault (see **Secrets and API keys** below). `skills/README.md` has the
folder layout and the page format.

## Secrets and API keys

Keys, tokens and passwords go in **Settings -> Vault**: a name in capitals (like `WEATHER_API_KEY`), the value, and
which skills may use it (`*` for all of them), then **Save**. The app only ever shows names, never values. There's
nothing to set up: the first Save creates the vault and Windows encrypts it with your login, with no extra password and
no extra software.

- **A skill reads it** from an environment variable: `os.environ.get("AETHER_SECRET_WEATHER_API_KEY")`. Only the skills
  you listed get it; it never goes into the prompt, the chat, memory or the logs, and if a skill prints it anyway, the
  text shows `••••` instead.
- **It's one encrypted file,** `vault.dat` in the data folder (`%USERPROFILE%\.aether`), locked by Windows to your
  account (DPAPI, the same lock as your saved Wi-Fi passwords). Backups carry it still locked; on another PC or Windows
  account it won't open, so you enter the keys again there.
- **The honest limit:** anyone logged into your Windows account can open it, same as your saved passwords.

## Discord (optional)

Talk to it from your phone through your own Discord bot. Settings -> Discord has a **How to set up a Discord bot** guide:
make a bot in Discord's Developer Portal, put its token in the Vault, add your Discord user id, and tick Connected. Only
you can DM it; anyone else gets talk-only mode, and nothing about you is shared with them.

## Layout

- `aether/`: the engine and app (`engine.py` the step loop, `router.py` asks and checks, `tool_table.py` every tool
  in one table, `memory.py` git-backed memory, `recall.py` meaning search in SQLite (sqlite-vec), `shell.py`
  command-line levels, `mcp.py` the MCP client, `eyes.py` the webcam, `songs.py`, `avatars.py`, `voice.py`,
  `server.py`, `ui/`)
- `aether/tests/`: the automated tests
- `skills/`: where your own skills go (empty; see its README)
- `tools/`: `add_mcp.py` (an MCP server as a skill), `install_skills.py`
- `starter-memory/`: the fresh memory a first start is made from (personality, rules, empty facts, an empty journal,
  an empty project board, and the board skill in `skills/board/`)
