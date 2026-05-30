"""Snippet builder for move_actor - transform an actor, with a RELATIVE mode set_property lacks.

Absolute mode mirrors set_property's setters; relative mode adds world offsets / rotation and multiplies
scale. Inside an undo transaction + R2 persist, like the other mutators.
"""

import json

from unreal_mcp.snippets import wrap


def build(ident, location=None, rotation=None, scale=None, relative=False) -> str:
    body = (
        f"ident = {json.dumps(ident)}\n"
        f"loc = {json.dumps(location)}\n"
        f"rot = {json.dumps(rotation)}\n"
        f"scl = {json.dumps(scale)}\n"
        f"relative = {bool(relative)!r}\n"
        "w = _world()\n"
        "if w is None:\n"
        "    _emit({'error': 'editor not ready'})\n"
        "else:\n"
        "    target = next((a for a in _eas().get_all_level_actors()\n"
        "                   if a.get_actor_label() == ident or a.get_name() == ident), None)\n"
        "    if target is None:\n"
        "        _emit({'error': 'actor not found', 'ident': ident})\n"
        "    else:\n"
        "        with unreal.ScopedEditorTransaction('UMCP move_actor'):\n"
        "            target.modify(True)\n"
        "            if relative:\n"
        "                if loc: target.add_actor_world_offset(unreal.Vector(loc[0], loc[1], loc[2]), False, False)\n"
        "                if rot: target.add_actor_world_rotation(unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]), False, False)\n"
        "                if scl:\n"
        "                    s = target.get_actor_scale3d()\n"
        "                    target.set_actor_scale3d(unreal.Vector(s.x*scl[0], s.y*scl[1], s.z*scl[2]))\n"
        "            else:\n"
        "                if loc: target.set_actor_location(unreal.Vector(loc[0], loc[1], loc[2]), False, False)\n"
        "                if rot: target.set_actor_rotation(unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]), False)\n"
        "                if scl: target.set_actor_scale3d(unreal.Vector(scl[0], scl[1], scl[2]))\n"
        "        _persist(w)\n"
        "        _emit({'moved': target.get_name(), 'relative': relative})\n"
    )
    return wrap(body)
