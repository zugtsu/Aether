TOOLS = [
    {"tool": 'board', "kind": 'skill', "for": 'his projects and his to-dos with no date (the board skill)',
     "asks": [
         {"name": 'board', "what": 'a line on his project board',
          "why": ('his own to-do with no day (10/04: "make a note to buy printer ink" went on HER task list 2/2); '
                  '"remind me" and a day are the calendar\'s'),
          "step": ('{"step": "skill", "skill": "board", "command": "add", "args": ["<section>", "<the line>"]}; to move '
                   'one: "command": "move", "args": ["<words of the line>", "<section>"] (sections: anything he puts "on '
                   'the board" is a project -> active, it starts as new; todo only when he says to-do; later when he says '
                   'later / for later; parked, done; done and remove take only the words)'),
          "trigger": (r"\b(?:put|add|move|mark|take|throw|stick|toss|remove|delete|drop|clear|check|tick|cross)\b[^.?!\n]{0,60}\b(?:on|to|onto|off|from|in|under)\s+(?:my|"
                      r"the|your)\s+(?:project\s+)?(?:board|later list|active list|parked list|to-?do(?:s| list)?)\b|\bmake a note to\b(?![^.?!\n]{0,60}\b(?:today|"
                      r"tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|at \d|on the \d|next week)\b)"),
          "done": {'skill': 'board'},
          "yes": ["add 'clean the gpu fans' to later on my board", 'make a note to buy printer ink', 'add get a new hdmi cable to my to-dos',
                  'Remove the t11 line from my board, that was meant for your task list.',
                  'btw you can check that webcam thing off the todo list and mark it as done'],
          "no": ['the board meeting at work ran long', 'make a note to call mom on saturday', 'check the weather for me',
                 "don’t add things to my board unless I ask you to", "never put stuff on my board on your own"]},
     ],
     "reads": ['list', 'show', 'plan', 'next', 'tick', 'wait'],
     },
    {"tool": 'memory_add', "kind": 'step', "for": 'his facts, and her own notes',
     "asks": [
         {"name": 'fact', "what": 'something about him to keep (his facts)',
          "why": ('not "do you remember my...": a question; "remember I have the barber friday" is a date, so the '
                  'calendar counts'),
          "step": '{"step": "memory_add", "file": "system/human/facts.md", "text": "<the fact>", "reason": "<why>"}',
          "trigger": (r"(?:^|[,.;:!?\n]\s*|\b(?:and|also|please|pls|oh|btw|but)\s+)remember (?:that |this[:,]? )?(?:i\b|"
                      r"i'm\b|i've\b|my\b)|\bkeep in mind (?:that )?(?:i\b|my\b)|\bdon'?t forget (?:that )?(?:i\b|my\b)|"
                      r"\b(?:save|note|write down) that (?:i\b|my\b)"),
          "done": {'step': ['memory_add', 'memory_replace', 'calendar']},
          "yes": ['remember i switched to decaf', 'make a note that i switched to decaf'], "no": ['do you remember my haircut is tuesday?']},
     ],
     },
    {"tool": 'calendar', "kind": 'step', "for": 'anything with a day or a time',
     "asks": [
         {"name": 'calendar', "what": 'a date on the calendar (add, move or cancel)',
          "step": ('{"step": "calendar", "do": "add", "id": "", "what": "<what>", "when": "<his words>", "remind": ""} '
                   '(move: do "change", cancel: do "cancel", with the line\'s id)'),
          "trigger": (r"\bremind me\b|\b(?:put|add|move|cancel|take|remove|delete|reschedule)\b[^.?!\n]{0,60}\b(?:calendar|"
                      r"reminder)s?\b|\bon (?:the|my) calendar\b"),
          "done": {'step': 'calendar'},
          "yes": ['remind me to call the barber friday at 10am', 'take the music plus reminder off the calendar'], "no": []},
     ],
     },
    {"tool": 'journal', "kind": 'step', "for": 'her journal, her private scratchpad',
     "asks": [
         {"name": 'journal', "what": 'an entry in your journal',
          "step": '{"step": "journal", "about": "<a few words>"}',
          "trigger": r"\b(?:write|put|jot)\b[^.?!\n]{0,50}\b(?:in|into) your journal\b|\bjournal (?:about|it|that|this)\b",
          "done": {'step': 'journal'},
          "yes": ['write about tonight in your journal'], "no": ['did you write about that in your journal?']},
     ],
     "reads": ['last'],
     },
    {"tool": 'make_image', "kind": 'step', "for": 'a picture she makes',
     "asks": [
         {"name": 'picture', "what": 'a picture (make_image)',
          "step": '{"step": "make_image", ...}',
          "trigger": r"\bdraw me\b|\b(?:draw|paint|make) (?:me )?(?:a |an )?(?:picture|image|drawing|painting)\b",
          "done": {'step': 'make_image'},
          "yes": ['draw me a dragon over a neon city'], "no": []},
     ],
     },
    {"tool": 'make_music', "kind": 'step', "for": 'a song she makes',
     "asks": [
         {"name": 'track', "what": 'a song (make_music)',
          "step": '{"step": "make_music", "title": "<a few words>", "style": "<your tags>", "length": "medium", "instrumental": false (true: no singing), "caption": "<a line for him>"}',
          "trigger": r"\b(?:make|write|do|create|creating|compose|composing) (?:me |us )?(?:a |an )?(?:new )?(?:\w+ )?(?:track|song|beat|banger|tune|piece|instrumental)\b",
          "done": {'step': 'make_music'},
          "yes": ['make me a trance track', 'write me a song about the rain', 'make us a beat',
                  'hey can you create a song, kind of like the opening of an old cartoon', 'compose me a tune',
                  "how about creating a music piece thats just piano? no lyrics though", 'make me a piano instrumental'],
          "no": ["what's that song called", 'i was listening to drum and bass today', 'that song slaps',
                 'that one is wonderful! what a master piece!', 'you created a banger last night']},
     ],
     },
    {"tool": 'task', "kind": 'step', "for": 'her own work in progress',
     "asks": [
         {"name": 'task', "what": 'your own task list',
          "why": ('a change to it, never a look ("what\'s on your task list?" is in her head already: as an ask it sent '
                  "her to a task step that rewrote t2's next step, live 10/05)"),
          "step": ('{"step": "task", "do": "add" | "next" | "done" | "drop", ...}; a task by its id: "id": "<its id, '
                   'like t4>", one step per task'),
          "trigger": (r"\b(?:put|add|stick|move|take|cross|mark|drop|remove|get)\b[^.?!\n]{0,60}\b(?:on|to|onto|off|from) your (?:own )?task list\b|"
                      r"\byour [^.?!\n]{0,30}\btask\b[^.?!\n]{0,20}\bdone\b|"
                      r"\b(?:drop|finish|close|mark|remove|delete|cancel|clear|done with|move on from|update|move|"
                      r"change|edit|set|bump)\b[^.?!\n]{0,40}\bt\d+\b(?![^.?!\n]*\b(?:board|calendar)\b)|"
                      r"\bt\d+\b[^.?!\n]{0,30}\b(?:is|are) (?:done|finished)\b"),
          "done": {'step': 'task'},
          "yes": ['put learning strudel effects on your task list', 'you can mark your tardigrades task done',
                  'drop t4 through t7, theyre the same as t2', 't2 is done',
                  'Update t11 with that: the capacitive soil sensor is decided, next is the ESP32 buffering.',
                  'Move your task t11 on: next is the ESP32 buffering.'],
          "no": ['whats on your task list right now?', 'whats t2 about?',
                 'Remove the t11 line from my board, that was meant for your task list.']},
     ],
     },
    {"tool": 'shell', "kind": 'step', "for": 'her Workspace, through her command line',
     "asks": [
         {"name": 'workspace', "what": 'a file in your workspace (write_file)',
          "step": '{"step": "write_file", "path": "<the file in your Workspace>", "mode": "add" | "rewrite", "text": "..."}; to change '
                  'a few lines, replace with the old and new text (rewrite is the whole file): {"step": "write_file", '
                  '"path": "...", "mode": "replace", "old": "<the exact lines>", "new": "<the new lines>"}',
          "trigger": r"\b(?:make|create|write|save|put|add|start|jot)\b[^,?!\n]{0,80}\b(?:in|into|to) your workspace\b",
          "done": {'step': ['write_file', 'shell']},
          "yes": ['make a file called ideas.txt in your workspace'], "no": []},
     ],
     },
    {"tool": 'research', "kind": 'skill', "for": 'his Library',
     "asks": [
         {"name": 'library', "what": 'their library, the Drop box (the research skill)',
          "step": ('{"step": "skill", "skill": "research", "command": "search" (what it says about something) | "read" '
                   '(a file by its name) | "list" (what is in it), "args": [...]}'),
          "trigger": (r"\b(?:in|from|through) (?:my|your) (?:library|drop ?box)\b|\bwhat'?s in (?:my|your) (?:library|drop ?box)\b|"
                      r"\b(?:my|your) (?:library|drop ?box)\b[^.!\n]{0,30}\?|"
                      r"\b(?:search|check|read|open|look through|go through|dig through)\b[^.!?\n]{0,30}\b(?:my|your) (?:library|drop ?box)\b|"
                      r"\b(?:find|open|read)\b[^.?!\n]{0,40}\bpdf\b"),
          "done": {'skill': 'research'},
          "yes": ["what's in my library?", "what's in my drop box?", "what's in your library?", "read me page 3 of the router manual pdf",
                  "i put the capacitive soil sensor and ESP32 datasheets and SparkFun's sensor code in your Library. Redo the parts list",
                  "read the capacitive soil sensor datasheet in your library", "search your library for the ESP32 datasheet"],
          "no": ["i went to the library today", "my steam library is huge"]},
         {"name": 'research_save', "what": 'a note in your notebook',
          "why": ("a save to her notebook he asks for; in a chat it's also what puts save_research on her menu at all "
                  '(engine._choose; 10/04: once a search counted as a source she saved after every library question, '
                  '5 of 5, unasked). The notebook as where it goes (not "put more research into gpus"); "make a note '
                  'of this", "jot that down" (10/04 tidy); not a note about him (his facts) and not a to-do (his board '
                  'or calendar)'),
          "step": ('{"step": "save_research"}; a long paste of his first goes in his library as he wrote it: {"step": '
                   '"skill", "skill": "research", "command": "keep", "args": ["<a short title>"]}, then save_research'),
          "trigger": (r"\b(?:save|saving|put|add|keep|jot|note|log|write|stick|file)\b[^.?!\n]{0,40}?\b(?:to|in|into|onto)\s+(?:(?:your|"
                      r"my|the|her)\s+)?(?:research|notebook)\b|\bmake (?:a |some )?notes? (?:of|about|on)\b|\bmake a note(?! (?:that |"
                      r")(?:i\b|i'm\b|i've\b|my\b|to\b))|\b(?:jot|write) (?:this|that|it|these|those) down\b|\btake (?:a )?notes? (?:of|"
                      r"on)\b|\b(?:save|keep|note|jot|log|write)\s+(?:down\s+)?(?:your|the|my)\s+(?:own\s+)?takes?\b(?!\s+(?:short|"
                      r"brief|simple|quick|light|tight|clean|to yourself|under))|\b(?:put|add|stick)\s+your\s+(?:own\s+)?takes?\s+(?:in|"
                      r"into|to)\b"),
          "done": {'step': 'save_research'},
          "yes": ['nice, save that to your research with your take', 'jot that in your notebook', "make a note that the office printer is out of toner"], "no": ['keep your take short', 'put more research into gpus', 'my coworker made a note of it']},
     ],
     "outside": True,
     "reads": ['compare', 'list', 'read', 'search'],
     },
    {"tool": 'notebook', "kind": 'skill', "for": 'her notebook, what she learned', "outside": True,
     "asks": [
         {"name": 'notebook', "what": 'your notebook (the notebook skill)',
          "step": ('{"step": "skill", "skill": "notebook", "command": "topics" (what you have notes on) | "show" (one '
                   'topic), "args": [...]}'),
          "trigger": (r"\b(?:check|read|open|search|look (?:in|at|through)) your notebook\b|\bwhat(?:'?s| is) in your notebook\b|"
                      r"\bwhat (?:have|did) you (?:noted?|learn(?:ed|t)?|write down|written down) (?:about|on)\b|"
                      r"\byour notes on\b"),
          "done": {'skill': 'notebook'},
          "yes": ["what's in your notebook?", 'what have you noted on sourdough starters?', 'what did you learn about the voice stuff?'],
          "no": ['jot that in your notebook', 'what did you learn in school', 'i noted it down']},
     ],
     "reads": ['show', 'topics'],
     },
    {"tool": 'look_back', "kind": 'step', "for": "her memory's history",
     "asks": [
         {"name": 'look_back', "what": "your memory's history (look_back)",
          "why": ('how her own files changed, what they said before, when something first got in (10/04: "how has your '
                  'me.md changed this week?" opened the file as it is now 4 of 4)'),
          "step": '{"step": "look_back", "about": "<the file or the words>"}',
          "trigger": (r"\bhow (?:has|have|did) your\b[^?!\n]{0,30}\bchang|\b[\w-]+\.md\b[^?!\n]{0,30}\bchang|\bwhat did your\b[^?!\n]{0,40}\bsay\b[^?!\n]{0,20}\bbefore\b|"
                      r"\bwhen did (?:you|i|my)\b[^?!\n]{0,40}\bfirst\b[^?!\n]{0,30}\b(?:write|wrote|writ|note|save|learn|"
                      r"put|add|get into|got into|hear|find out)|\bmemory'?s history\b|\bhistory of your\b"),
          "done": {'step': 'look_back'},
          "yes": ['how has your me.md changed this week?'], "no": []},
     ],
     },
    {"tool": 'webcam', "kind": 'step', "for": 'his webcam, when he asks her to look',
     "asks": [
         {"name": 'webcam', "what": 'a look through his webcam (webcam)',
          "step": '{"step": "webcam", "about": "<what he wants you to look at>"}',
          "trigger": (r"\bhow do i look\b(?!\s+(?:up|for|into|through|at)\b)|\bcan you see (?:me|what i'?m)\b|"
                      r"\b(?:look|take a look|peek|glance) at (?:me|what i'?m)\b|\bwhat am i (?:holding|wearing|showing you|doing)\b|"
                      r"\b(?:through|with|on|into|in|at|check) (?:the|my|your) (?:web)?cam(?:era)?\b"),
          "done": {'step': 'webcam'},
          "yes": ['how do i look tonight?', 'hey can you see me?', 'what am i holding right now?',
                  'take a look through the webcam', 'look into my webcam, can you see me?', 'can you see what im holding?',
                  'look at what im holding', 'all set, go ahead and take a look at me on the webcam!',
                  'look at the camera real quick', 'check the webcam'],
          "no": ['how do i look up the bus times', 'look at this picture i sent you', 'i got a webcam earlier',
                 'oh so thats how i look, cool', 'i know you wanted eyes, so now you have em!',
                 'look at this article about gemma', 'can you see this?', 'look over here',
                 'look at this screenshot of my high score lol',
                 'i just dropped my drafted plan for the greenhouse into your library, feel free to look at it and give me your opinion']},
     ],
     },
    {"tool": 'read_chat', "kind": 'step', "for": 'one of their chats',
     "asks": [
         {"name": 'chat', "what": 'one of your chats (read_chat)',
          "step": '{"step": "read_chat", "which": "last"}',
          "trigger": r"\b(?:check|read|look at|open|go through) (?:our|the) (?:last|other|previous) chat\b",
          "done": {'step': 'read_chat'},
          "yes": ['go check our last chat'], "no": []},
     ],
     },
]


def asks():
    rows = []
    for t in TOOLS:
        for a in t.get("asks", []):
            rows.append((a["name"], a["what"], a["step"], a["trigger"], _done(a["done"]), t["tool"]))
    return rows


def _done(rule):
    key, want = next(iter(rule.items()))
    want = want if isinstance(want, list) else [want]
    if key == "skill":
        return lambda s: s.get("step") == "skill" and s.get("skill") in want
    return lambda s: s.get(key) in want


def outside_skills():
    return [t["tool"] for t in TOOLS if t.get("outside")]


def lookup_commands():
    return {t["tool"]: list(t["reads"]) for t in TOOLS if "reads" in t}


def ask_first():
    return {t["tool"]: list(t["ask_first"]) for t in TOOLS if "ask_first" in t}
