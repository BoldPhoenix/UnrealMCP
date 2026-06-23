"""The MCP server itself.

`mcp` is the FastMCP instance - the high-level SDK object that handles the ENTIRE MCP
protocol for us: the initialize handshake, capability negotiation, tools/list, tools/call
dispatch, and the stdio JSON-RPC framing. We never touch that wire by hand; we just attach
tools to it with @mcp.tool decorators in later increments.

Right now it has no tools yet - that's increment 3 onward (run_console_command first).
"""

import json
import os
import re
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from unreal_mcp import config
from unreal_mcp.editor_client import client
from unreal_mcp.snippets import (
    asset_ops as _asset,
    asset_search as _asset_search,
    cinematic as _cine,
    delete_actors as _delete_actors,
    eyes as _eyes,
    film as _film,
    get_level_actors as _get_level_actors,
    get_status as _get_status,
    move_actor as _move,
    open_level as _open_level,
    run_console_command as _console,
    save_level as _save_level,
    set_property as _set_property,
    spawn_actor as _spawn_actor,
    viewport as _viewport,
)

# The editor's on-disk log (for get_output_log) - derived from the configured project + uproject name.
_LOG_PATH = os.path.join(config.UNREAL_PROJECT_DIR, "Saved", "Logs",
                         os.path.splitext(os.path.basename(config.UNREAL_UPROJECT))[0] + ".log")

# The name Claude Code displays for this server. Matches the key in .mcp.json.
mcp = FastMCP("unrealmcp")


@mcp.tool()
def run_console_command(command: str) -> dict:
    """Run an Unreal editor console command (e.g. "stat fps", "stat unit", "r.ScreenPercentage 80").

    Executes inside the live editor on the current world. Returns {"ran": <command>} on success,
    or {"error": "editor not ready"} when no map/world is loaded yet.
    """
    return client.run_snippet(_console.build(command))


@mcp.tool()
def get_status() -> dict:
    """Report whether the editor is reachable and ready (a real map/world is loaded).

    Returns {"ready": bool, "world": <name>, "actor_count": int}. This is the 'deferred-ready'
    check - confirm the editor is up and a map is loaded before issuing other tools.
    """
    return client.run_snippet(_get_status.build())


@mcp.tool()
def get_level_actors() -> dict:
    """List the actors in the current level (name, label, class, transform).

    NOTE: reflects the editor's IN-MEMORY world, not what's saved on disk. Tagged
    "source": "editor-memory" as a reminder - disk truth is the .umap file / git.
    """
    return client.run_snippet(_get_level_actors.build())


@mcp.tool()
def spawn_actor(
    class_path: str,
    location: list[float] = [0.0, 0.0, 0.0],
    rotation: list[float] = [0.0, 0.0, 0.0],
    label: str | None = None,
) -> dict:
    """Spawn an actor of the given class at a transform, then persist it (Modify + dirty).

    class_path examples: "/Script/Engine.StaticMeshActor", "/Script/Engine.PointLight", or a
    Blueprint class path like "/Game/Blueprints/BP_Thing.BP_Thing_C".
    location = [x, y, z]; rotation = [pitch, yaw, roll]; label = optional friendly name.
    Returns {"spawned": <name>, "label": <label>} or {"error": ...}.
    """
    return client.run_snippet(_spawn_actor.build(class_path, location, rotation, label))


@mcp.tool()
def set_property(actor: str, property: str, value: Any) -> dict:
    """Set a property on an actor (found by label or name), then persist it.

    property "location"/"rotation"/"scale" expect a [x, y, z] list (rotation = [pitch, yaw, roll]).
    Any other property name is applied via set_editor_property(value).
    Returns {"set": <property>, "actor": <name>} or {"error": ...}.
    """
    return client.run_snippet(_set_property.build(actor, property, value))


@mcp.tool()
def delete_actors(actors: list[str]) -> dict:
    """Delete actors by label or name, then persist.

    Returns {"deleted": [<names>], "requested": [<idents>]} or {"error": ...}.
    """
    return client.run_snippet(_delete_actors.build(actors))


@mcp.tool()
def save_level() -> dict:
    """Save the current level to its .umap on disk (R1: a world is written as .umap, never .uasset).

    Routes through the level-save API only. Returns {"saved": bool, "package": "/Game/Maps/..."}.
    """
    return client.run_snippet(_save_level.build())


@mcp.tool()
def open_level(level_path: str) -> dict:
    """Open (load) a level into the editor, e.g. "/Game/Maps/Apartment".

    After this, reads reflect the newly-loaded in-editor world. To verify a SAVE persisted to disk,
    use restart_editor (full process restart) - re-opening the same map in-session can show stale cache.
    """
    return client.run_snippet(_open_level.build(level_path))


@mcp.tool()
def asset_search(path: str = "/Game", class_name: str | None = None, limit: int = 100) -> dict:
    """Search the Asset Registry under `path` (recursive), optionally filtered by class
    (e.g. "World", "Material", "StaticMesh"). Returns up to `limit` {name, package, class} entries."""
    return client.run_snippet(_asset_search.build(path, class_name, limit))


@mcp.tool()
def get_output_log(lines: int = 200) -> dict:
    """Read the tail of the editor's on-disk output log (honest disk read, not an in-editor query)."""
    return {"log_path": _LOG_PATH, "lines": lines, "text": client.read_text_tail(_LOG_PATH, lines)}


# --- structured logs (harvested from UE5.8 LogsToolset; implemented over our on-disk tail + console) ---
@mcp.tool()
def log_search(pattern: str, regex: bool = False, lines: int = 3000, limit: int = 100) -> dict:
    """Filter the editor's on-disk log for lines matching `pattern` (instead of dumping the whole tail).

    regex=False = case-insensitive substring match; regex=True = `pattern` is a Python regex. Scans the
    last `lines` lines, returns up to `limit` matches (newest last) + total match count. Use when chasing
    a specific category/error, e.g. "LogModelContextProtocol", "Warning:", "BuckCharacter".
    """
    text = client.read_text_tail(_LOG_PATH, lines)
    rows = text.splitlines() if isinstance(text, str) else []
    try:
        rx = re.compile(pattern if regex else re.escape(pattern), re.IGNORECASE)
    except re.error as e:
        return {"error": f"bad regex: {e}", "pattern": pattern}
    hits = [r for r in rows if rx.search(r)]
    return {"pattern": pattern, "regex": regex, "scanned_lines": len(rows),
            "match_count": len(hits), "matches": hits[-limit:], "log_path": _LOG_PATH}


@mcp.tool()
def log_categories(lines: int = 5000) -> dict:
    """List the Unreal log CATEGORIES seen in the recent on-disk log, with hit counts (sorted by frequency).

    Scans the last `lines` lines for `LogXxx:` tokens - the menu of category names to feed to log_search
    or set_log_verbosity.
    """
    text = client.read_text_tail(_LOG_PATH, lines)
    rows = text.splitlines() if isinstance(text, str) else []
    counts: dict[str, int] = {}
    for r in rows:
        m = re.search(r"\b(Log[A-Za-z0-9_]+):", r)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return {"scanned_lines": len(rows), "category_count": len(ordered),
            "categories": [{"category": c, "hits": n} for c, n in ordered]}


@mcp.tool()
def set_log_verbosity(category: str, level: str = "Log") -> dict:
    """Set a log category's verbosity live via the `Log <category> <level>` console command.

    level = Off | Error | Warning | Display | Log | Verbose | VeryVerbose | Default (restore). e.g.
    set_log_verbosity("LogBlueprintUserMessages", "Verbose") before reproducing a bug, then "Default"
    after. Needs a loaded editor world. Returns {"ran": "Log ..."} or {"error": "editor not ready"}.
    """
    return client.run_snippet(_console.build(f"Log {category} {level}"))


@mcp.tool()
def restart_editor(wait_ready_seconds: float = 0.0) -> dict:
    """Cleanly quit the editor and relaunch it - the headline lifecycle feature, in one call.

    Sends a CLEAN quit (never force-kill), waits for the process to fully exit (so we don't relaunch
    into a project lock), then relaunches the editor DETACHED. Returns as soon as relaunch is issued
    ({"relaunched": true, "ready": false}) - call get_status to confirm when the map has loaded.
    Pass wait_ready_seconds > 0 to block and poll readiness up to that cap.
    """
    import time as _t
    client.request_quit()
    exited = client.wait_for_exit(timeout=90.0)
    if not exited:
        return {"quit_requested": True, "old_editor_exited": False, "relaunched": False,
                "error": "editor did not exit within 90s (a save prompt may be open). Resolve it, then retry."}
    client.relaunch_editor()
    result = {"quit_requested": True, "old_editor_exited": True, "relaunched": True, "ready": False}
    if wait_ready_seconds and wait_ready_seconds > 0:
        deadline = _t.time() + float(wait_ready_seconds)
        while _t.time() < deadline:
            try:
                st = client.run_snippet(_get_status.build())
                if isinstance(st, dict) and st.get("ready"):
                    result["ready"] = True
                    result["world"] = st.get("world")
                    break
            except Exception:
                pass
            _t.sleep(5.0)
    if not result["ready"]:
        result["note"] = "editor relaunching; call get_status to confirm when the map has loaded."
    return result


@mcp.tool()
def asset_save(asset_path: str) -> dict:
    """Save a Content-Browser asset (.uasset) to disk, e.g. "/Game/Textures/Apartment/M_Black".

    REFUSES Worlds/levels (R1 guard) - use save_level for those. Returns {"saved": bool, "asset": path}.
    """
    return client.run_snippet(_asset.build_save(asset_path))


@mcp.tool()
def asset_edit(op: str, src: str, dst: str | None = None,
               prop: str | None = None, value: Any = None) -> dict:
    """Content-Browser asset CRUD. op = exists | duplicate | rename | delete | set_property.

    duplicate/rename need `dst`; set_property needs `prop` + `value` (refuses Worlds). `src`/`dst` are
    asset paths like "/Game/Path/Asset".
    """
    return client.run_snippet(_asset.build_edit(op, src, dst, prop, value))


@mcp.tool()
def asset_dependencies(package: str, include_soft: bool = False) -> dict:
    """List what an asset depends on (Asset Registry). `package` e.g. "/Game/Maps/Apartment"."""
    return client.run_snippet(_asset.build_dependencies(package, include_soft))


@mcp.tool()
def asset_referencers(package: str, include_soft: bool = False) -> dict:
    """List what references an asset (Asset Registry) - impact analysis before a delete/rename."""
    return client.run_snippet(_asset.build_referencers(package, include_soft))


@mcp.tool()
def material_instance(name: str, package_path: str, parent: str,
                      scalars: dict | None = None, vectors: dict | None = None) -> dict:
    """Create a MaterialInstanceConstant under `package_path` with `parent` material, setting scalar
    params {name: float} and vector params {name: [r,g,b,a]}. Saves it. For look-dev.
    """
    return client.run_snippet(_asset.build_material_instance(name, package_path, parent, scalars, vectors))


@mcp.tool()
def asset_import(source_file: str, destination_path: str = "/Game",
                 replace_existing: bool = True, save: bool = True) -> dict:
    """Import a source file from disk (FBX / OBJ / glTF / texture / etc.) into the project as asset(s).

    source_file = absolute disk path (e.g. a Blender or 3D-gen export); destination_path = a content
    path like "/Game/Meshes". Uses UE's default factory per file extension; advanced import settings
    (skeletal vs static, LODs, material import) go via execute_python. Returns {"imported": [paths], ...}.
    """
    return client.run_snippet(_asset.build_import(source_file, destination_path, replace_existing, save))


@mcp.tool()
def move_actor(actor: str, location: list[float] | None = None, rotation: list[float] | None = None,
               scale: list[float] | None = None, relative: bool = False) -> dict:
    """Move/rotate/scale an actor (by label or name). relative=False sets absolute; relative=True adds
    world offsets / rotation and multiplies scale. location [x,y,z], rotation [pitch,yaw,roll]. Persists.
    """
    return client.run_snippet(_move.build(actor, location, rotation, scale, relative))


@mcp.tool()
def execute_python(code: str) -> dict:
    """Run arbitrary Python inside the editor - the escape hatch / power tool.

    Executes `code` on the game thread via Remote Execution and returns the raw result:
    {"success": bool, "result": <repr of last value>, "output": [log lines]}. Use this for one-off
    operations not yet covered by a dedicated tool - anything the code prints shows up in "output".
    This is what lets us add new behavior WITHOUT a new tool + reconnect.
    """
    return client.run_python(code)


# --- eyes: fresh, on-demand visual capture (returns a PNG Image the model can actually see) ---
_EYES_MAX_BYTES = 3_500_000
_EYES_NOTE = (
    "Live on-demand clean scene render of the in-editor world from the stamped camera/time. "
    "NOT disk truth and NOT proof of saved state. Never delete or 'fix' an actor based on this "
    "image alone - confirm with get_level_actors first."
)


def _eyes_result(snippet: str):
    """Run an eyes snippet, read the PNG it wrote, and return [Image, metadata-json]."""
    meta = client.run_snippet(snippet)
    if not isinstance(meta, dict) or "error" in meta:
        return [json.dumps(meta)]
    png_path = meta.pop("png_path", None)
    if not png_path:
        return [json.dumps({"error": "no image path returned", "raw": meta})]
    png = client.read_binary(png_path, delete_after=True)
    if len(png) > _EYES_MAX_BYTES:
        return [json.dumps({"error": "image too large; request a smaller width/height",
                            "bytes": len(png), "meta": meta})]
    meta["note"] = _EYES_NOTE
    return [Image(data=png, format="png"), json.dumps(meta)]


@mcp.tool()
def eyes_focus(actor: str, distance: float | None = None, fov: float = 90.0,
               width: int = 1280, height: int = 720):
    """See a named actor: a fresh, on-demand render auto-framed on the actor's bounds.

    Returns a PNG image + metadata (actor_count, camera, capture time). LIVE render of the in-editor
    world, NOT disk truth - never base a destructive action on it; confirm with get_level_actors.
    """
    return _eyes_result(_eyes.build_focus(actor, distance, fov, width, height))


@mcp.tool()
def eyes_look(camera_location: list[float], look_at: list[float] | None = None,
              camera_rotation: list[float] | None = None, fov: float = 90.0,
              width: int = 1280, height: int = 720):
    """See from a steerable virtual camera. Give camera_location [x,y,z] and EITHER look_at [x,y,z]
    (auto-aims at it) OR camera_rotation [pitch,yaw,roll]. Fresh on-demand render; NOT disk truth.
    """
    return _eyes_result(_eyes.build_look(camera_location, camera_rotation, look_at, fov, width, height))


@mcp.tool()
def eyes_mirror(fov: float = 90.0, width: int = 1280, height: int = 720):
    """See roughly what you're looking at: render from the live editor viewport camera.

    Clean render (no gizmos/selection/grid overlays). Fresh on-demand; NOT disk truth.
    """
    return _eyes_result(_eyes.build_mirror(fov, width, height))


@mcp.tool()
def eyes_overview(width: int = 1280, height: int = 1280, padding: float = 1.2):
    """Top-down ORTHOGRAPHIC map view of the whole level (ceilings/roof temporarily hidden so the
    interior is visible). Fresh on-demand render; NOT disk truth. Returns a PNG image + metadata.
    """
    return _eyes_result(_eyes.build_overview(width, height, padding))


# --- viewport / selection: drive + inspect the LIVE editor viewport (harvested from UE5.8 EditorAppToolset) ---
@mcp.tool()
def get_viewport_camera() -> dict:
    """Read the live editor perspective-viewport camera pose -> {"location":[x,y,z], "rotation":[pitch,yaw,roll]}.

    The REAL viewport camera (what's on screen), distinct from eyes_* (off-screen renders) and from
    set_camera (a CineCameraActor's lens/DoF).
    """
    return client.run_snippet(_viewport.build_get_viewport_camera())


@mcp.tool()
def set_viewport_camera(location: list[float], rotation: list[float] | None = None,
                        look_at: list[float] | None = None) -> dict:
    """Move the editor viewport camera. location [x,y,z] + EITHER rotation [pitch,yaw,roll] OR look_at
    [x,y,z] (auto-aims); omit both to keep current rotation. Pair with eyes_mirror to SEE the result.
    (Moves the live viewport - the camera visibly jumps.)
    """
    return client.run_snippet(_viewport.build_set_viewport_camera(location, rotation, look_at))


@mcp.tool()
def get_selected_actors() -> dict:
    """List actors currently selected in the editor -> {"count", "actors":[{name,label,class,location,rotation}]}."""
    return client.run_snippet(_viewport.build_get_selected())


@mcp.tool()
def select_actors(actors: list[str], additive: bool = False) -> dict:
    """Select level actors by label or name. additive=False replaces the selection, True adds.
    Returns {"selected":[labels], "missing":[idents not found]}.
    """
    return client.run_snippet(_viewport.build_select(actors, additive))


@mcp.tool()
def focus_viewport(actors: list[str], distance: float | None = None) -> dict:
    """Drive the REAL editor viewport camera to frame the given actors (by label/name) from their combined
    bounds. distance defaults to 2.5x the framed radius. 'Go look at X' in the editor, then eyes_mirror.
    """
    return client.run_snippet(_viewport.build_focus_viewport(actors, distance))


# --- cinematic core (validated live): author a camera move -> render via Movie Render Queue -> poll ---
@mcp.tool()
def sequence_create_camera_move(name: str, poses: list[dict],
                                package_path: str = "/Game/Cinematics",
                                camera_label: str = "FlythroughCam",
                                fps: int = 30, length_seconds: float | None = None) -> dict:
    """Author a keyframed camera move as a LevelSequence on an existing CineCameraActor (default the
    FlythroughCam), then save it. Feed the returned sequence_path to render_sequence.

    poses: list of {time_s: float, location: [x,y,z], rotation: [pitch,yaw,roll] (optional),
    look_at: [x,y,z] (optional - aims the camera at that point at each key)}.
    """
    return client.run_snippet(_cine.build_camera_move(name, package_path, camera_label, fps, poses, length_seconds))


@mcp.tool()
def render_sequence(sequence_path: str, map_path: str, output_dir: str,
                    resolution: list[int] = [1920, 1080], fmt: str = "png",
                    still: bool = False, still_frame: int = 0,
                    aa_spatial_samples: int = 8, crf: int = 20) -> dict:
    """Render a LevelSequence via Movie Render Queue (ASYNC - returns immediately; poll with render_status).

    sequence_path "/Game/Cinematics/SEQ.SEQ"; map_path "/Game/Maps/Apartment.Apartment" (explicit, for
    deterministic possessable binding); output_dir = absolute disk path. fmt = "png" | "exr" | "mp4".
    still=True renders one supersampled frame (book illustration). Returns {output_dir,
    expected_frame_count, file_glob, started}.
    """
    return client.run_snippet(_cine.build_render(sequence_path, map_path, output_dir, resolution,
                                                 fmt, still, still_frame, aa_spatial_samples, crf))


@mcp.tool()
def render_status(output_dir: str, expected_frame_count: int, file_glob: str = "*.png", preview: bool = False):
    """Poll an in-progress render. done = editor-not-rendering AND files_written >= expected (so a
    still-finalizing video never reads as done). preview=True returns the latest finished PNG as an Image.
    """
    import glob
    st = client.run_snippet(_cine.build_render_status_probe())
    is_rendering = bool(st.get("is_rendering")) if isinstance(st, dict) else True
    files = glob.glob(os.path.join(output_dir, file_glob))
    done = (not is_rendering) and len(files) >= int(expected_frame_count)
    result = {"is_rendering": is_rendering, "files_written": len(files),
              "expected": int(expected_frame_count), "done": done, "output_dir": output_dir}
    if preview and done and files and file_glob.lower().endswith("png"):
        png = client.read_binary(sorted(files)[-1])  # a deliverable - do NOT delete
        return [Image(data=png, format="png"), json.dumps(result)]
    return result


@mcp.tool()
def set_camera(camera: str = "FlythroughCam", aperture: float | None = None,
               focal_length: float | None = None, focus_method: str | None = None,
               focus_distance: float | None = None, save: bool = True) -> dict:
    """Set lens / depth-of-field on a CineCameraActor (the crisp-vs-blurry dial).

    aperture = f-stop (HIGH like f/16-22 = deep/crisp, LOW like f/2.8 = shallow/blurry).
    focal_length = mm (zoom). focus_method = "disable" (DoF OFF, tack-sharp everywhere) | "manual" |
    "tracking". focus_distance = unreal units (for manual focus on a subject). save=True persists to the
    .umap so it survives a reload. Returns the resulting settings.
    """
    return client.run_snippet(_cine.build_set_camera(camera, aperture, focal_length, focus_method, focus_distance, save))


# --- film authoring (Sequencer): create shots/master, animate, play anim, cut, audio, fades, visibility ---
@mcp.tool()
def create_sequence(name: str, package_path: str = "/Game/Cinematics", fps: int = 30,
                    length_seconds: float = 10.0) -> dict:
    """Create an empty LevelSequence (a shot, or a master) at package_path with frame rate set in the
    correct order. Build shots/master first, then add cameras/anim/audio to them across calls.
    """
    return client.run_snippet(_film.build_create_sequence(name, package_path, fps, length_seconds))


@mcp.tool()
def animate_actor(sequence_path: str, actor: str, poses: list[dict]) -> dict:
    """Keyframe an actor's transform in a sequence - the staging workhorse (characters, props, lights,
    even cameras). poses: [{time_s, location:[x,y,z]?, rotation:[pitch,yaw,roll]?, look_at:[x,y,z]?,
    scale:[x,y,z]?}]. Anim plays in-place; this drives WHERE it travels.
    """
    return client.run_snippet(_film.build_animate_actor(sequence_path, actor, poses))


@mcp.tool()
def play_animation(sequence_path: str, actor: str, anim_path: str, start_s: float = 0.0,
                   play_rate: float = 1.0, loop_to_s: float | None = None) -> dict:
    """Play a skeletal AnimSequence on a character in a sequence (makes characters ACT, not just move).
    anim_path "/Game/.../SomeAnim". Defaults to the anim's length; loop_to_s stretches/loops to a time.
    """
    return client.run_snippet(_film.build_play_animation(sequence_path, actor, anim_path, start_s, play_rate, loop_to_s))


@mcp.tool()
def add_camera_cut(sequence_path: str, cuts: list[dict]) -> dict:
    """Add camera-cut sections that switch between cameras over time (multi-angle editing within a shot).
    cuts: [{camera, start_s, end_s}]. Pair with animate_actor on each camera for its move.
    """
    return client.run_snippet(_film.build_add_camera_cut(sequence_path, cuts))


@mcp.tool()
def add_audio(sequence_path: str, clips: list[dict]) -> dict:
    """Add an audio track with clips (dialogue / music / sfx). clips: [{sound: "/Game/.../Sound",
    start_s, end_s, start_offset_s?, looping?}]. Call again to stack tracks for a mix bed.
    """
    return client.run_snippet(_film.build_add_audio(sequence_path, clips))


@mcp.tool()
def add_fade(sequence_path: str, fades: list[dict], color: list[float] | None = None) -> dict:
    """Add/key a fade track. fades: [{time_s, value}] where value 0.0=clear -> 1.0=fully faded to color
    (default black). Fade in: (0,1)->(1,0); fade out at the tail: (end-1,0)->(end,1).
    """
    return client.run_snippet(_film.build_add_fade(sequence_path, fades, color))


@mcp.tool()
def set_actor_visibility_track(sequence_path: str, actor: str, keys: list[dict]) -> dict:
    """Key an actor's visibility over time (entrances/exits). keys: [{time_s, visible: bool}] - the tool
    inverts to the engine's bHidden channel for you, so `visible` reads naturally.
    """
    return client.run_snippet(_film.build_set_visibility(sequence_path, actor, keys))


@mcp.tool()
def add_shot(master_path: str, child_path: str, start_s: float, duration_s: float, row: int = 0) -> dict:
    """Append a child shot LevelSequence onto a MASTER's cinematic shot track at start_s (the multi-shot
    film backbone). Render the master with render_sequence. Keep master + shots at the SAME fps.
    """
    return client.run_snippet(_film.build_add_shot(master_path, child_path, start_s, duration_s, row))


@mcp.tool()
def sequence_inspect(sequence_path: str) -> dict:
    """Read back a sequence's structure (bindings, child component bindings, tracks, section ranges, fps,
    length) - the get_level_actors for Sequencer. Use before re-binding to keep authoring idempotent.
    """
    return client.run_snippet(_film.build_sequence_inspect(sequence_path))


def main() -> None:
    """Run the server over stdio (transport is implicit when an MCP client launches us)."""
    mcp.run()
