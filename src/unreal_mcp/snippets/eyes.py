"""Snippet builders for the 'eyes' tools - fresh, on-demand scene captures.

Anti-stale BY CONSTRUCTION: each call creates a brand-new render target, drops a TRANSIENT
SceneCapture2D, calls capture_scene() (which renders immediately, on demand - NOT the editor
viewport's throttled redraw, the thing that caused the original stale-frame disaster), exports a
PNG, and destroys the capture actor in a finally block. Nothing is cached, nothing is saved, and the
editor viewport's back buffer is never read. The snippet prints the PNG path; the bridge reads the
bytes off disk and deletes the file.

Every snippet is wrapped in try/except so a UE5.7 API-signature mismatch returns a clean
{'error': ...} instead of crashing the bridge.
"""

import json

from unreal_mcp.snippets import wrap


# Shared capture body. __CAMLINES__ (8-space indented) must define cam_loc + cam_rot, or leave them
# None (e.g. actor-not-found) to skip the capture cleanly. __W__/__H__/__FOV__/__MODE__ are filled in.
_TEMPLATE = """import os, uuid, datetime
def _proj_saved():
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
try:
    w = _world()
    if w is None:
        _emit({'error': 'editor not ready'})
    else:
        W = __W__; H = __H__; FOV = __FOV__; MODE = __MODE__
        cam_loc = None; cam_rot = None
__CAMLINES__
        if cam_loc is not None:
            out_dir = os.path.join(_proj_saved(), 'UMCP_Eyes')
            os.makedirs(out_dir, exist_ok=True)
            out_name = 'eyes_' + uuid.uuid4().hex
            rt = unreal.RenderingLibrary.create_render_target2d(w, W, H, unreal.TextureRenderTargetFormat.RTF_RGBA8)
            cap = _eas().spawn_actor_from_class(unreal.SceneCapture2D, cam_loc, cam_rot, transient=True)
            try:
                comp = cap.get_component_by_class(unreal.SceneCaptureComponent2D)
                comp.set_editor_property('capture_every_frame', False)
                comp.set_editor_property('capture_on_movement', False)
                comp.set_editor_property('texture_target', rt)
                comp.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
                comp.set_editor_property('fov_angle', FOV)
                comp.set_world_location_and_rotation(cam_loc, cam_rot, False, False)
                comp.capture_scene()
                unreal.RenderingLibrary.export_render_target(w, rt, out_dir, out_name + '.png')
            finally:
                _eas().destroy_actor(cap)
            _emit({'png_path': os.path.join(out_dir, out_name + '.png'), 'mode': MODE,
                   'camera_loc': [cam_loc.x, cam_loc.y, cam_loc.z],
                   'camera_rot': [cam_rot.pitch, cam_rot.yaw, cam_rot.roll],
                   'fov': FOV, 'width': W, 'height': H, 'world': w.get_name(),
                   'actor_count': len(_eas().get_all_level_actors()),
                   'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
except Exception as e:
    _emit({'error': repr(e)})
"""


def _compose(cam_lines: str, width: int, height: int, fov: float, mode: str) -> str:
    body = (_TEMPLATE
            .replace("__W__", str(int(width)))
            .replace("__H__", str(int(height)))
            .replace("__FOV__", repr(float(fov)))
            .replace("__MODE__", repr(mode))
            .replace("__CAMLINES__", cam_lines))
    return wrap(body)


def build_mirror(fov: float = 90.0, width: int = 1280, height: int = 720) -> str:
    """Render from the live editor perspective-viewport camera (what the user is looking at)."""
    cam = (
        "        ci = _ues().get_level_viewport_camera_info()\n"
        "        cam_loc, cam_rot = ci[-2], ci[-1]\n"
    )
    return _compose(cam, width, height, fov, "mirror")


def build_look(camera_location, camera_rotation=None, look_at=None,
               fov: float = 90.0, width: int = 1280, height: int = 720) -> str:
    """Steerable camera: explicit location, plus EITHER a look_at target (auto-aim) or a rotation."""
    lx, ly, lz = [float(v) for v in camera_location]
    cam = "        cam_loc = unreal.Vector(%r, %r, %r)\n" % (lx, ly, lz)
    if look_at is not None:
        tx, ty, tz = [float(v) for v in look_at]
        cam += ("        cam_rot = unreal.MathLibrary.find_look_at_rotation("
                "cam_loc, unreal.Vector(%r, %r, %r))\n" % (tx, ty, tz))
    elif camera_rotation is not None:
        rp, ry, rr = [float(v) for v in camera_rotation]
        cam += "        cam_rot = unreal.Rotator(pitch=%r, yaw=%r, roll=%r)\n" % (rp, ry, rr)
    else:
        cam += "        cam_rot = unreal.Rotator(pitch=0.0, yaw=0.0, roll=0.0)\n"
    return _compose(cam, width, height, fov, "look")


def build_focus(ident, distance=None, fov: float = 90.0, width: int = 1280, height: int = 720) -> str:
    """Frame a named actor (by label or name). Auto-distances from its COLLISION bounds (tighter than
    full bounds for characters - full bounds can be bloated by perception/collision volumes), with a
    fallback to full bounds and a clamp so an oversized box can't fling the camera into orbit. cam
    stays None if the actor isn't found."""
    dist_expr = ("%r" % float(distance)) if distance is not None else "radius * 2.5"
    cam = (
        "        ident = %s\n" % json.dumps(ident)
        + "        target = next((a for a in _eas().get_all_level_actors()\n"
        + "                       if a.get_actor_label() == ident or a.get_name() == ident), None)\n"
        + "        if target is None:\n"
        + "            _emit({'error': 'actor not found', 'ident': ident})\n"
        + "        else:\n"
        + "            origin, extent = target.get_actor_bounds(True)\n"
        + "            radius = max(extent.x, extent.y, extent.z)\n"
        + "            if radius < 10.0:\n"
        + "                origin, extent = target.get_actor_bounds(False)\n"
        + "                radius = max(extent.x, extent.y, extent.z)\n"
        + "            radius = min(max(radius, 40.0), 300.0)\n"
        + "            dist = %s\n" % dist_expr
        + "            cam_loc = unreal.Vector(origin.x + dist*0.651, origin.y + dist*0.651, origin.z + dist*0.39)\n"
        + "            cam_rot = unreal.MathLibrary.find_look_at_rotation(cam_loc, origin)\n"
    )
    return _compose(cam, width, height, fov, "focus")


# Top-down orthographic map view. Bespoke (not via _compose): it hides ceilings, sizes an ortho
# camera to the whole scene, and restores visibility in a finally. Tokens: __PAD__/__W__/__H__.
_OVERVIEW_TEMPLATE = """import os, uuid, datetime
def _proj_saved():
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
try:
    w = _world()
    if w is None:
        _emit({'error': 'editor not ready'})
    else:
        actors = _eas().get_all_level_actors()
        hidden = []
        for a in actors:
            nm = (a.get_actor_label() + ' ' + a.get_name()).lower()
            if 'ceiling' in nm or 'roof' in nm:
                try:
                    a.set_is_temporarily_hidden_in_editor(True); hidden.append(a)
                except Exception:
                    pass
        cap = None
        try:
            xs = []; ys = []; zs = []
            for a in actors:
                p = a.get_actor_location(); xs.append(p.x); ys.append(p.y); zs.append(p.z)
            cx = (min(xs) + max(xs)) / 2.0; cy = (min(ys) + max(ys)) / 2.0
            span = max(max(xs) - min(xs), max(ys) - min(ys))
            ortho_w = span * __PAD__ + 200.0
            cam_loc = unreal.Vector(cx, cy, max(zs) + 1500.0)
            cam_rot = unreal.Rotator(pitch=-90.0, yaw=0.0, roll=0.0)
            out_dir = os.path.join(_proj_saved(), 'UMCP_Eyes'); os.makedirs(out_dir, exist_ok=True)
            out_name = 'eyes_' + uuid.uuid4().hex
            rt = unreal.RenderingLibrary.create_render_target2d(w, __W__, __H__, unreal.TextureRenderTargetFormat.RTF_RGBA8)
            cap = _eas().spawn_actor_from_class(unreal.SceneCapture2D, cam_loc, cam_rot, transient=True)
            comp = cap.get_component_by_class(unreal.SceneCaptureComponent2D)
            comp.set_editor_property('capture_every_frame', False)
            comp.set_editor_property('capture_on_movement', False)
            comp.set_editor_property('texture_target', rt)
            comp.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
            comp.set_editor_property('projection_type', unreal.CameraProjectionMode.ORTHOGRAPHIC)
            comp.set_editor_property('ortho_width', ortho_w)
            comp.set_world_location_and_rotation(cam_loc, cam_rot, False, False)
            comp.capture_scene()
            unreal.RenderingLibrary.export_render_target(w, rt, out_dir, out_name + '.png')
            _emit({'png_path': os.path.join(out_dir, out_name + '.png'), 'mode': 'overview',
                   'camera_loc': [cam_loc.x, cam_loc.y, cam_loc.z], 'ortho_width': ortho_w,
                   'hidden_ceiling_actors': [a.get_actor_label() for a in hidden],
                   'width': __W__, 'height': __H__, 'world': w.get_name(),
                   'actor_count': len(actors),
                   'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
        finally:
            if cap is not None:
                _eas().destroy_actor(cap)
            for a in hidden:
                try:
                    a.set_is_temporarily_hidden_in_editor(False)
                except Exception:
                    pass
except Exception as e:
    _emit({'error': repr(e)})
"""


def build_overview(width: int = 1280, height: int = 1280, padding: float = 1.2) -> str:
    """Top-down ORTHOGRAPHIC map view of the whole level. Temporarily hides ceiling/roof actors (by
    name) so the interior shows, captures straight down with an ortho camera sized to the scene, then
    restores visibility in a finally. Fresh/anti-stale; transient capture actor; never saves."""
    body = (_OVERVIEW_TEMPLATE
            .replace("__PAD__", repr(float(padding)))
            .replace("__W__", str(int(width)))
            .replace("__H__", str(int(height))))
    return wrap(body)
