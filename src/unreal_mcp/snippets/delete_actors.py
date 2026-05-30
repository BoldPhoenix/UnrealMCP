"""Snippet builder for delete_actors.

Deletes actors matched by label or name (inside an undo transaction), then runs the R2
persistence pattern so the deletion sticks on the next save.
"""

import json

from unreal_mcp.snippets import wrap


def build(idents) -> str:
    body = (
        f"wanted = set(json.loads({json.dumps(json.dumps(list(idents)))}))\n"
        "w = _world()\n"
        "if w is None:\n"
        "    _emit({'error': 'editor not ready'})\n"
        "else:\n"
        "    victims = [a for a in _eas().get_all_level_actors()\n"
        "               if a.get_actor_label() in wanted or a.get_name() in wanted]\n"
        "    deleted = [a.get_name() for a in victims]\n"
        "    with unreal.ScopedEditorTransaction('UMCP delete_actors'):\n"
        "        for a in victims:\n"
        "            a.modify(True)\n"
        "        _eas().destroy_actors(victims)\n"
        "    _persist(w)\n"
        "    _emit({'deleted': deleted, 'requested': sorted(wanted)})\n"
    )
    return wrap(body)
