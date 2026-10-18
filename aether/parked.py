import os
import re

PARKED_LINE = re.compile(r"^\*\*(.+?)\*\*", re.M)
WORD = re.compile(r"[a-z]{6,}")
GENERIC = {"research", "script", "scripts", "system", "systems", "notes", "draft", "drafts", "design", "project",
           "projects", "summary", "overview", "requirements", "readme", "version", "versions", "update", "updates",
           "status", "report", "reports", "ideas", "planning", "outline", "general", "section", "sections", "details",
           "options", "review", "reviews", "testing", "process", "current", "initial", "future"}


def parked_projects(board_text):
    text = str(board_text or "").replace("\r\n", "\n")
    m = re.search(r"(?ms)^## Parked\s*$(.*?)(?=^## |\Z)", text)
    if not m:
        return set()
    return {re.sub(r"\s+", "-", n.strip().lower()) for n in PARKED_LINE.findall(m.group(1))}


def words_for(slug, workspace_dir):
    stems = [slug]
    folder = os.path.join(str(workspace_dir or ""), slug)
    try:
        stems += [os.path.splitext(f)[0] for f in os.listdir(folder)]
    except OSError:
        pass
    return {w for s in stems for w in WORD.findall(s.lower().replace("-", " ").replace("_", " "))} - GENERIC


def parked_words(board_text, workspace_dir):
    return {slug: words_for(slug, workspace_dir) for slug in parked_projects(board_text)}


def which_parked(text, words_by_slug):
    low = str(text or "").lower()
    mine = set(WORD.findall(low.replace("-", " ").replace("_", " ")))
    for slug, words in sorted(words_by_slug.items()):
        if slug in low.replace(" ", "-") or (mine & words):
            return slug
    return ""
