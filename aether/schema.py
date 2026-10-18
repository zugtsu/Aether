def _obj(props, required=None):
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


S = {"type": "string"}

REPLY_SCHEMA = _obj({"say": S})
NOTICE_SCHEMA = _obj({"noticed": {"type": "string", "maxLength": 200}, "say": S})


def step_schema(memory, skills, allow_tools=True, docs=()):
    options = [_obj({"step": {"const": "reply"}})]
    if not allow_tools:
        return {"anyOf": options}
    addable, editable, readable = memory.addable(), memory.editable(), memory.readable()
    if "notebook" in skills:
        readable = [r for r in readable if not r.startswith("reference/research/")]
    if addable:
        options.append(_obj({"step": {"const": "memory_add"}, "file": {"enum": addable}, "text": S, "reason": S}))
    if editable:
        options.append(_obj({"step": {"const": "memory_replace"}, "file": {"enum": editable}, "old": S, "new": S, "reason": S}))
        options.append(_obj({"step": {"const": "memory_remove"}, "file": {"enum": editable}, "line": S, "reason": S}))
    options.append(_obj({"step": {"const": "memory_create"},
                         "path": {"type": "string", "pattern": "^(reference|notes)/[a-z0-9][a-z0-9_/-]*\\.md$"},
                         "description": S, "text": S, "reason": S}))
    deletable = memory.deletable()
    if deletable:
        options.append(_obj({"step": {"const": "memory_delete"}, "file": {"enum": deletable}, "reason": S}))
    readable = readable + sorted(r for r in memory.files if r.startswith("system/"))
    if readable:
        options.append(_obj({"step": {"const": "read_file"}, "path": {"enum": readable}}))
    if skills or docs:
        options.append(_obj({"step": {"const": "read_skill"}, "skill": {"enum": sorted(set(skills) | set(docs))}}))
        for name in sorted(skills):
            sk = skills[name]
            props = {"step": {"const": "skill"}, "skill": {"const": name}}
            if len(sk.scripts) > 1:
                props["script"] = {"enum": sorted(sk.scripts)}
            if getattr(sk, "commands", None):
                props["command"] = {"enum": sk.commands}
            props["args"] = {"type": "array", "items": S}
            options.append(_obj(props))
    return {"anyOf": options}


def response_format(schema, name):
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}
