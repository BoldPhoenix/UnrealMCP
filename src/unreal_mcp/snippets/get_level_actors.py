"""Snippet builder for get_level_actors - an honest, editor-memory read of the level.

The result is tagged source='editor-memory' on purpose: it reflects the live in-editor
world, NOT what's saved to the .umap on disk. Disk truth = the file / git.
"""

from unreal_mcp.snippets import wrap


def build() -> str:
    body = (
        "w = _world()\n"
        "if w is None:\n"
        "    _emit({'error': 'editor not ready'})\n"
        "else:\n"
        "    out = []\n"
        "    for a in _eas().get_all_level_actors():\n"
        "        loc = a.get_actor_location(); rot = a.get_actor_rotation(); scl = a.get_actor_scale3d()\n"
        "        out.append({\n"
        "            'name': a.get_name(),\n"
        "            'label': a.get_actor_label(),\n"
        "            'class': a.get_class().get_name(),\n"
        "            'location': [loc.x, loc.y, loc.z],\n"
        "            'rotation': [rot.pitch, rot.yaw, rot.roll],\n"
        "            'scale': [scl.x, scl.y, scl.z],\n"
        "        })\n"
        "    _emit({'source': 'editor-memory', 'count': len(out), 'actors': out})\n"
    )
    return wrap(body)
