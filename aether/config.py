import json
import os
import threading
from dataclasses import dataclass, field, asdict

HOME = os.path.expanduser("~")
DATA_DIR = os.environ.get("AETHER_HOME") or os.path.join(HOME, ".aether")
CONFIG_FILE = os.path.join(DATA_DIR, "aether.json")
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _agent_id():
    try:
        with open(os.path.join(PROJECT, "agent.json"), encoding="utf-8") as f:
            return json.load(f).get("agent_id") or ""
    except Exception:
        return ""


def real_memory_dir(agent_id):
    return os.path.join(HOME, ".letta", "lc-local-backend", "memfs", agent_id, "memory")


def _table():
    from . import tool_table
    return tool_table


@dataclass
class Config:
    lmstudio_url: str = "http://127.0.0.1:1234"
    model: str = "unsloth/gemma-4-12b-it-qat"
    temperature_talk: float = 1.0
    temperature_tools: float = 0.2
    temperature_retry: float = 0.8
    builtin_skills: list = field(default_factory=lambda: ["journal"])
    top_p: float = 0.95
    top_k: int = 64
    reply_max_tokens: int = 700
    step_max_tokens: int = 1500
    request_timeout: int = 300

    agent_id: str = field(default_factory=_agent_id)
    memory_dir: str = os.path.join(DATA_DIR, "memory")
    allow_real_memory: bool = False
    protected: dict = field(default_factory=lambda: {
        "system/projects.md": "board",
        "system/journal.md": "journal",
        "reference/lessons.md": "Aether's nightly reflection",
        "life/": "Aether (dreams and heartbeat)",
        "reference/facts-history.md": "Aether (the record of changed facts)",
        "reference/lessons-archive.md": "Aether's nightly reflection (every lesson you've learned)",
        "reference/music/": "Aether ({USER}'s ratings of your tracks)",
        "reference/lessons-history.md": "Aether's nightly reflection (lessons that left your rulebook)",
        "reference/journal/": "Aether (her older journal entries, moved by the nightly roll-over)",
        "system/timeline.md": "Aether's Keeper (what happened, written nightly)",
        "system/threads.md": "Aether's Keeper (unfinished things)",
        "reference/stances.md": "Aether's Keeper (her takes, from what she said)",
        "reference/research/": "your save_research step and the research skill",
        "system/calendar.md": "your calendar step ({USER} edits it on his Calendar page)",
        "system/working.md": "your task step",
    })
    add_only: list = field(default_factory=list)
    edit_only: list = field(default_factory=lambda: ["system/human.md"])
    keep_history: dict = field(default_factory=lambda: {"system/human/facts.md": "reference/facts-history.md"})
    dedupe_similarity: float = 0.92

    max_steps: int = 11
    history_chars: int = 48000
    read_ahead: bool = True
    archive_after_days: int = 7

    skill_timeout: int = 90
    skill_output_chars: int = 6000
    ask_first: dict = field(default_factory=lambda: _table().ask_first())
    outside_skills: list = field(default_factory=lambda: _table().outside_skills())
    lookup_commands: dict = field(default_factory=lambda: _table().lookup_commands())

    port: int = 8850
    display_name: str = "Companion"
    user_name: str = "User"
    full_name: str = "Your local AI companion"
    tagline: str = "A local AI companion."
    library_dir: str = os.path.join(HOME, "Desktop", "Aether Drop Box")
    space_intensity: float = 0.55
    show_work: bool = True
    brain_style: str = "tree"

    tts_url: str = ""
    tts_model: str = ""
    voice: str = ""
    voice_speed: float = 1.0
    speak_replies: str = "when_i_talk"
    start_kokoro: bool = False
    kokoro_dir: str = ""
    voice_engine: str = "kokoro"
    breeze_dir: str = os.path.join(PROJECT, "voice-engine")
    breeze_url: str = "http://127.0.0.1:8881"
    breeze_voice: str = "voice"
    breeze_device: int = 0
    breeze_aside_for_pictures: bool = True
    hear_tone: bool = True
    theme: str = "astral"
    mic_device: str = ""
    ears_python: str = os.path.join(PROJECT, ".venv", "Scripts", "python.exe")
    ears_model: str = os.path.join(PROJECT, "models", "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17", "model.int8.onnx")
    speaker_model: str = os.path.join(PROJECT, "models", "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx")

    mood_enabled: bool = True
    mood_half_life_hours: float = 1.5
    heartbeat_enabled: bool = True
    heartbeat_minutes: int = 60
    heartbeat_idle_minutes: int = 5
    message_idle_minutes: int = 30
    quiet_start: str = "23:00"
    quiet_end: str = "07:00"
    sleep_work: bool = True
    sleep_work_minutes: int = 90
    own_thinking: bool = True
    own_history_chars: int = 12000
    reach_out_cap: int = 6
    reach_out_to: str = "latest"
    reach_out_chat: str = ""
    wakeups_enabled: bool = True
    wakeup_max: int = 3
    dreams_enabled: bool = True
    dream_time: str = "03:00"
    reflect_enabled: bool = True
    lesson_trial_days: int = 14
    lesson_hints: bool = True
    examples_enabled: bool = False
    examples_min: float = 0.75
    examples_collect: bool = True
    journal_keep_days: int = 21
    journal_max_chars: int = 30000
    facts_keep_days: int = 30

    images_enabled: bool = True
    image_daily_cap: int = 12
    image_steps: int = 25
    image_review: bool = True
    image_pause_for: list = field(default_factory=list)
    comfy_port: int = 8189
    comfy_dir: str = ""
    comfy_idle_minutes: int = 10
    comfy_launch: bool = True

    videos_enabled: bool = False
    video_daily_cap: int = 2
    songs_enabled: bool = True
    song_daily_cap: int = 10
    song_own_daily_cap: int = 1
    video_width: int = 832
    video_height: int = 480
    video_length: int = 49
    video_steps: int = 20
    video_fps: int = 24

    permission_levels: dict = field(default_factory=lambda: {"app": 0, "discord": 0, "avatar": 0, "own": 0})
    workspace_dir: str = os.path.join(HOME, "AetherWorkspace")
    shell_timeout: int = 60

    discord_enabled: bool = False
    discord_owner_ids: list = field(default_factory=list)
    discord_channels: list = field(default_factory=list)
    discord_dm_policy: str = "allowlist"
    discord_allow_bots: bool = False
    discord_mirror: bool = True

    avatar_model: str = os.path.join(PROJECT, "live2d-models", "my-avatar", "my-avatar.model3.json")
    avatar_enabled: bool = True
    avatar: str = ""

    backups_enabled: bool = False
    backup_dir: str = ""
    calendar_enabled: bool = True
    recall_enabled: bool = True
    eyes_enabled: bool = False
    eyes_camera: str = ""
    recall_links: bool = True
    recall_hybrid: bool = True
    recall_full_text: bool = False
    cue_enabled: bool = False
    cue_max: int = 4
    cue_rare: float = 0.02
    cue_weight: float = 3.9
    cue_min: float = 0.6
    cue_word_min: float = 0.65
    prompt_journal_days: int = 0
    prompt_journal_chars: int = 0
    prompt_recap: bool = False
    nudge_enabled: bool = False
    keeper_verify: bool = True
    keeper_enabled: bool = False
    keeper_lately: bool = True
    keeper_board_check: bool = False
    prompt_timeline_days: int = 0
    prompt_timeline_chars: int = 0
    knowledge_sources: dict = field(default_factory=dict)
    cue_notice: bool = False

    @property
    def memory_path(self):
        return os.path.abspath(os.path.expanduser(self.memory_dir))

    def is_real_memory(self):
        if not self.agent_id:
            return False
        real = os.path.normcase(os.path.abspath(real_memory_dir(self.agent_id)))
        return os.path.normcase(self.memory_path) == real

    def memory_mode(self):
        if self.is_real_memory():
            return "REAL memory"
        home = os.path.normcase(os.path.abspath(os.path.join(DATA_DIR, "memory")))
        return "home" if os.path.normcase(self.memory_path) == home else "test copy"

    def check_safe(self):
        if self.is_real_memory() and not self.allow_real_memory:
            raise SystemExit(
                "Aether is pointed at a protected memory folder, and allow_real_memory is off.\n"
                "Point memory_dir at another folder (python -m aether new-memory makes one).")


GROW_ONLY = {"outside_skills"}
FROM_CODE = ("ask_first", "lookup_commands", "protected")
_save_lock = threading.Lock()


def _saved(cfg):
    data = asdict(cfg)
    for k in FROM_CODE:
        data.pop(k, None)
    return data


def save(cfg, path=CONFIG_FILE):
    with _save_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_saved(cfg), f, indent=2)
        os.replace(tmp, path)


def load(path=CONFIG_FILE, write_defaults=True):
    cfg = Config()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        known = set(asdict(cfg)) - set(FROM_CODE)
        for k, v in data.items():
            if k in known:
                default = getattr(cfg, k)
                if isinstance(default, dict) and isinstance(v, dict):
                    v = {**default, **v}
                elif k in GROW_ONLY and isinstance(v, list):
                    v = list(dict.fromkeys(list(default) + v))
                setattr(cfg, k, v)
    elif write_defaults:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_saved(cfg), f, indent=2)
    return cfg
