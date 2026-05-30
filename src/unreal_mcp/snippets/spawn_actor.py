"""Snippet builder for spawn_actor.

Spawns an actor of the given class at a transform, inside an undo transaction, then runs
the R2 persistence pattern (actor.modify + world.modify + mark_package_dirty) so the new
actor will actually serialize when the level is saved.
"""

import json

from unreal_mcp.snippets import wrap


def build(class_path, location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), label=None) -> str:
    loc = [float(v) for v in location]
    rot = [float(v) for v in rotation]
    body = (
        f"cls_path = {json.dumps(class_path)}\n"
        f"loc = unreal.Vector(x={loc[0]}, y={loc[1]}, z={loc[2]})\n"
        f"rot = unreal.Rotator(pitch={rot[0]}, yaw={rot[1]}, roll={rot[2]})\n"
        f"label = {json.dumps(label)}\n"
        "w = _world()\n"
        "if w is None:\n"
        "    _emit({'error': 'editor not ready'})\n"
        "else:\n"
        "    cls = unreal.load_class(None, cls_path) or unreal.load_object(None, cls_path)\n"
        "    if cls is None:\n"
        "        _emit({'error': 'class not found', 'class': cls_path})\n"
        "    else:\n"
        "        with unreal.ScopedEditorTransaction('UMCP spawn_actor'):\n"
        "            actor = _eas().spawn_actor_from_class(cls, loc, rot)\n"
        "            actor.modify(True)\n"
        "            if label:\n"
        "                actor.set_actor_label(label)\n"
        "        _persist(w)\n"
        "        _emit({'spawned': actor.get_name(), 'label': actor.get_actor_label()})\n"
    )
    return wrap(body)
