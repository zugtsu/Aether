# Skills

One skill ships with Aether: the **board** (its project list and to-dos), already in its starter memory
(`starter-memory/skills/board/`). Everything else is a skill you add.

A skill is a folder here:

```
skills/
  <name>/
    SKILL.md          frontmatter with name + description, then how to use it
    scripts/<name>.py the script its step runs (plain Python; arguments come from its step)
```

`SKILL.md` starts like this, and shows its step exactly as it sends it:

```
---
name: <name>
description: <one line: what it's for; it picks skills by this line>
---
{"step": "skill", "skill": "<name>", "command": "<command>", "args": ["..."]}
```

A skill only goes live if its frontmatter has `name` and `description`, it has at least one `scripts/*.py` that
compiles, and its page shows how to call it (see `aether/skills.py`).

A skill that needs an API key reads it from `AETHER_SECRET_<NAME>`, once you've saved it in **Settings -> Vault** and
allowed that skill (the main README's **Secrets and API keys** has the rest).

Then copy your skills into its memory:

```
python tools\install_skills.py
```
