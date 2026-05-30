"""Snippet builder for open_level - load a different map into the editor.

R3 caveat (baked into the tool docstring too): after this, get_level_actors reflects the NEWLY loaded
in-editor world. To verify a SAVE persisted to disk, use restart_editor (a full process restart) -
re-opening the same level in-session can serve a stale cached version. That's a hard-won lesson.
"""

import json

from unreal_mcp.snippets import wrap


def build(level_path: str) -> str:
    body = (
        f"path = {json.dumps(level_path)}\n"
        "ok = _les().load_level(path)\n"
        "w = _world()\n"
        "_emit({'opened': bool(ok), 'requested': path, 'world': (w.get_name() if w else None)})\n"
    )
    return wrap(body)
