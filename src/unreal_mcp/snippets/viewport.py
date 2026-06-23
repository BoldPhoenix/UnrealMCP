"""Snippet builders for viewport / selection tools - drive and inspect the LIVE editor viewport and
actor selection (harvested from UE5.8 EditorAppToolset; built on the same Editor Subsystems our 'eyes'
already use). These MOVE the real editor viewport camera / change selection - distinct from 'eyes'
(a transient off-screen render) and from set_camera (a CineCameraActor's depth-of-field dial).

Each builder returns wrap(body); the shared PREAMBLE supplies _ues/_eas/_les, _world, _emit, _find_actor.
Bodies are try/except so an API-signature mismatch returns {'error': ...} instead of crashing the bridge.

VERIFY-on-metal: set_level_viewport_camera_info (the camera SETTER) is the one call not already exercised
by eyes.py; flagged inline. The getter + selection + bounds calls are all proven in eyes.py.
"""

import json

from unreal_mcp.snippets import wrap

# Inline helper compiled into snippets that summarize actors.
_BRIEF = (
    "def _brief(a):\n"
    "    t = a.get_actor_transform(); L = t.translation; R = t.rotation.rotator()\n"
    "    return {'name': a.get_name(), 'label': a.get_actor_label(), 'class': a.get_class().get_name(),\n"
    "            'location': [L.x, L.y, L.z], 'rotation': [R.pitch, R.yaw, R.roll]}\n"
)


def build_get_viewport_camera() -> str:
    """Read the live editor perspective-viewport camera pose."""
    body = (
        "try:\n"
        "    ci = _ues().get_level_viewport_camera_info()\n"
        "    loc, rot = ci[-2], ci[-1]\n"
        "    _emit({'location': [loc.x, loc.y, loc.z], 'rotation': [rot.pitch, rot.yaw, rot.roll]})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_set_viewport_camera(location, rotation=None, look_at=None) -> str:
    """Move the editor viewport camera to a pose (give rotation OR look_at; default keeps current rot)."""
    lx, ly, lz = [float(v) for v in location]
    cam = "    loc = unreal.Vector(%r, %r, %r)\n" % (lx, ly, lz)
    if look_at is not None:
        tx, ty, tz = [float(v) for v in look_at]
        cam += "    rot = unreal.MathLibrary.find_look_at_rotation(loc, unreal.Vector(%r, %r, %r))\n" % (tx, ty, tz)
    elif rotation is not None:
        rp, ry, rr = [float(v) for v in rotation]
        cam += "    rot = unreal.Rotator(pitch=%r, yaw=%r, roll=%r)\n" % (rp, ry, rr)
    else:
        cam += "    rot = _ues().get_level_viewport_camera_info()[-1]\n"
    body = (
        "try:\n"
        + cam
        + "    _ues().set_level_viewport_camera_info(loc, rot)\n"   # verified live on UE5.8 (2026-06-22)
        + "    _emit({'set': True, 'location': [loc.x, loc.y, loc.z], 'rotation': [rot.pitch, rot.yaw, rot.roll]})\n"
        + "except Exception as e:\n"
        + "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_get_selected() -> str:
    """List the currently-selected level actors (name, label, class, transform)."""
    body = (
        _BRIEF
        + "try:\n"
        + "    sel = _eas().get_selected_level_actors()\n"
        + "    _emit({'count': len(sel), 'actors': [_brief(a) for a in sel]})\n"
        + "except Exception as e:\n"
        + "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_select(idents, additive=False) -> str:
    """Select level actors by label or name. additive=False replaces the current selection."""
    body = (
        "try:\n"
        + "    idents = " + json.dumps(list(idents)) + "\n"
        + "    found = []; missing = []\n"
        + "    for i in idents:\n"
        + "        a = _find_actor(i)\n"
        + "        found.append(a) if a is not None else missing.append(i)\n"
        + "    base = _eas().get_selected_level_actors() if " + ("True" if additive else "False") + " else []\n"
        + "    _eas().set_selected_level_actors(base + found)\n"
        + "    _emit({'selected': [a.get_actor_label() for a in found], 'missing': missing})\n"
        + "except Exception as e:\n"
        + "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_focus_viewport(idents, distance=None) -> str:
    """Drive the REAL editor viewport camera to frame the given actors (combined collision bounds).

    Like eyes_focus, but it moves the actual viewport (so the user sees it) instead of an off-screen
    render. distance defaults to 2.5x the framed radius.
    """
    dist_expr = ("%r" % float(distance)) if distance is not None else "radius * 2.5"
    body = (
        "try:\n"
        + "    idents = " + json.dumps(list(idents)) + "\n"
        + "    found = [a for a in (_find_actor(i) for i in idents) if a is not None]\n"
        + "    if not found:\n"
        + "        _emit({'error': 'no actors found', 'idents': idents})\n"
        + "    else:\n"
        + "        mn = [1e18, 1e18, 1e18]; mx = [-1e18, -1e18, -1e18]\n"
        + "        for a in found:\n"
        + "            o, e = a.get_actor_bounds(True)\n"
        + "            for k, c, ex in ((0, o.x, e.x), (1, o.y, e.y), (2, o.z, e.z)):\n"
        + "                mn[k] = min(mn[k], c - ex); mx[k] = max(mx[k], c + ex)\n"
        + "        origin = unreal.Vector((mn[0]+mx[0])/2.0, (mn[1]+mx[1])/2.0, (mn[2]+mx[2])/2.0)\n"
        + "        radius = min(max((mx[0]-mn[0])/2.0, (mx[1]-mn[1])/2.0, (mx[2]-mn[2])/2.0, 40.0), 100000.0)\n"
        + "        dist = " + dist_expr + "\n"
        + "        cam_loc = unreal.Vector(origin.x + dist*0.651, origin.y + dist*0.651, origin.z + dist*0.39)\n"
        + "        cam_rot = unreal.MathLibrary.find_look_at_rotation(cam_loc, origin)\n"
        + "        _ues().set_level_viewport_camera_info(cam_loc, cam_rot)\n"   # verified live on UE5.8 (2026-06-22)
        + "        _emit({'focused': [a.get_actor_label() for a in found],\n"
        + "               'camera_loc': [cam_loc.x, cam_loc.y, cam_loc.z]})\n"
        + "except Exception as e:\n"
        + "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)
