"""Snippet builder for set_property.

Finds an actor by label or name, then sets a property inside an undo transaction and runs
the R2 persistence pattern. 'location'/'rotation'/'scale' use the dedicated actor setters
(which fire the proper editor change notifications); anything else goes through
set_editor_property, which behaves like editing the field in the Details panel.

The value is shipped in as JSON and re-parsed inside the editor, so any JSON-serializable
value (number, string, bool, list) survives the trip safely.
"""

import json

from unreal_mcp.snippets import wrap


def build(ident, prop, value) -> str:
    body = (
        f"ident = {json.dumps(ident)}\n"
        f"prop = {json.dumps(prop)}\n"
        f"value = json.loads({json.dumps(json.dumps(value))})\n"
        "w = _world()\n"
        "if w is None:\n"
        "    _emit({'error': 'editor not ready'})\n"
        "else:\n"
        "    target = next((a for a in _eas().get_all_level_actors()\n"
        "                   if a.get_actor_label() == ident or a.get_name() == ident), None)\n"
        "    if target is None:\n"
        "        _emit({'error': 'actor not found', 'ident': ident})\n"
        "    else:\n"
        "        with unreal.ScopedEditorTransaction('UMCP set_property'):\n"
        "            target.modify(True)\n"
        "            if prop == 'location':\n"
        "                target.set_actor_location(unreal.Vector(value[0], value[1], value[2]), False, False)\n"
        "            elif prop == 'rotation':\n"
        "                target.set_actor_rotation(unreal.Rotator(pitch=value[0], yaw=value[1], roll=value[2]), False)\n"
        "            elif prop == 'scale':\n"
        "                target.set_actor_scale3d(unreal.Vector(value[0], value[1], value[2]))\n"
        "            else:\n"
        "                target.set_editor_property(prop, value)\n"
        "        _persist(w)\n"
        "        _emit({'set': prop, 'actor': target.get_name()})\n"
    )
    return wrap(body)
