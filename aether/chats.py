import re

from .history import NOT_USER, STRANGER_PLACE, Conversation, from_user, list_conversations, stranger  # noqa: F401
from .life import HEARTBEAT_CHAT
from .names import USER

MAX_CHARS = 7000
OPTION = {"type": "object",
          "properties": {"step": {"const": "read_chat"}, "which": {"type": "string", "maxLength": 80}},
          "required": ["step", "which"], "additionalProperties": False}
LAST = re.compile(r"^(?:(?:our|the|my)\s+)?(?:last|latest|previous|prior|other|most recent|recent|older|earlier)?"
                  r"(?:\s+(?:one|chat|conversation))?$", re.I)
FILLER = {"the", "chat", "our", "a", "an", "with", "that", "about", "one", "conversation", "called", "named", "where"}


def _words(text):
    return set(re.findall(r"[a-z0-9']+", text.lower())) - FILLER


class ChatReader:
    def __init__(self, app):
        self.app = app

    def option(self):
        return OPTION

    def chats(self):
        current = self.app.engine.conv.id
        out = []
        for cid in list_conversations(self.app.conv_dir):
            if cid in (current, HEARTBEAT_CHAT):
                continue
            c = Conversation(self.app.conv_dir, cid)
            if not c.events:
                continue
            title = (self.app.meta.get(cid) or {}).get("title") or c.title()
            out.append((c.events[-1]["ts"], cid, title, c))
        out.sort(key=lambda ch: ch[0], reverse=True)
        return out

    def pick(self, which):
        chats = self.chats()
        if not chats:
            return None
        w = " ".join(str(which).split()).strip(" \"'.").lower()
        if not w or LAST.match(w):
            return next((ch for ch in chats if any(from_user(e) for e in ch[3].events)), chats[0])
        for ch in chats:
            if w in ch[2].lower():
                return ch
        want = _words(w)
        best = max(chats, key=lambda ch: len(want & _words(ch[2])))
        return best if want & _words(best[2]) else None

    def run_step(self, step):
        ch = self.pick(step.get("which", ""))
        if not ch:
            names = "; ".join(f'"{title}"' for _, _, title, _ in self.chats()[:10])
            return False, (f"No chat matches \"{step.get('which', '')}\". Your other chats with {USER}, newest first: "
                           f"{names or 'none'}. Try again with part of one of those titles, or \"last\".")
        last, _, title, conv = ch
        lines = []
        for e in conv.events:
            when = e.get("ts", "")[5:16].replace("T", " ")
            text = " ".join(str(e.get("text") or "").split())
            if e["kind"] == "user" and stranger(e):
                lines.append(f"[{when}] {stranger(e)} said {NOT_USER}: {text}")
            elif e["kind"] == "user":
                lines.append(f"[{when}] {USER} said: {text}")
            elif e["kind"] == "reply" and text:
                lines.append(f"You said: {text}")
            elif e["kind"] == "wake" and text:
                lines.append(f"[{when}] {text}")
        body = "\n".join(lines)
        if len(body) > MAX_CHARS:
            body = "(the earlier part of this chat isn't shown)\n" + body[-MAX_CHARS:]
        return True, f"Chat \"{title}\" (last active {last[:16].replace('T', ' ')}):\n{body}"
