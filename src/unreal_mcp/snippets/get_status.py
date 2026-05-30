"""Snippet builder for get_status - the deferred-ready check.

'Ready' means: the editor answered AND a real map/world is loaded (not the empty
'Untitled' placeholder you get before a level finishes opening).
"""

from unreal_mcp.snippets import wrap


def build() -> str:
    body = (
        "w = _world()\n"
        "name = w.get_name() if w else None\n"
        "ready = bool(w) and name not in (None, '', 'Untitled')\n"
        "n = len(_eas().get_all_level_actors()) if ready else 0\n"
        "_emit({'ready': ready, 'world': name, 'actor_count': n})\n"
    )
    return wrap(body)
