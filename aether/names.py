USER = "{USER}"
DEFAULT = "User"
GIT_USER = "user"
GIT_USER_EMAIL = "user@local"
OLD_USER_NAMES = ("jordan",)


def is_user_author(author):
    return str(author or "").strip().lower() in (GIT_USER,) + OLD_USER_NAMES


def user_name(cfg=None):
    name = " ".join(str(getattr(cfg, "user_name", "") or "").split())
    return name or DEFAULT


def fill(obj, cfg=None):
    name = user_name(cfg)
    if isinstance(obj, str):
        return obj.replace(USER, name) if USER in obj else obj
    if isinstance(obj, list):
        return [fill(x, cfg) for x in obj]
    if isinstance(obj, tuple):
        return tuple(fill(x, cfg) for x in obj)
    if isinstance(obj, dict):
        return {k: fill(v, cfg) for k, v in obj.items()}
    return obj
