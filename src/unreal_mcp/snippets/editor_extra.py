"""Snippet builders for "editor extra" tools - PIE control, content-browser navigation/selection,
asset-editor opening, console-variable search, and viewport world<->screen projection. Harvested from
UE5.8's EditorAppToolset (EditorToolset plugin) and re-expressed over the Python editor bindings our
stdio server already drives.

Each builder returns wrap(body); the shared PREAMBLE supplies _eas/_ues/_les, _world, _emit, _find_actor.
Bodies are try/except at 0-indent so an API-signature mismatch returns {'error': ...} instead of crashing
the bridge. The C++ surface uses GEditor / FContentBrowserModule / IConsoleManager directly - several of
those have no 1:1 Python binding, so the riskier calls carry a trailing  # VERIFY:  comment naming the
exact uncertainty and (where possible) a console-command fallback.

PIE semantics (from EditorAppToolset.cpp, verified by reading the source 2026-06-22):
  * "is PIE running"  ==  GEditor->PlayWorld != nullptr   ->  _ues().get_game_world() is not None
    (scene.py's own _is_pie() uses exactly this game-world check - PROVEN pattern).
  * StartPIE  ->  GEditor->RequestPlaySession(...)  ;  StopPIE  ->  GEditor->RequestEndPlayMap().
    The clean Python wrappers for those are LevelEditorSubsystem.editor_play_simulate() /
    editor_request_end_play() - flagged VERIFY (binding name not stub-confirmed on this box).
    Both are inherently ASYNC in the engine (the C++ tool returns an async result + watcher); we issue
    the request and report it as started/stopping, then the caller polls is_pie_running.
"""

import json

from unreal_mcp.snippets import wrap


# ---------------------------------------------------------------------------------------------------
# PIE (Play In Editor)
# ---------------------------------------------------------------------------------------------------

def build_is_pie_running() -> str:
    """Report whether a PIE / Simulate session is currently active.

    Mirrors EditorAppToolset::IsPIERunning (GEditor->PlayWorld != nullptr). The Python-side equivalent
    is UnrealEditorSubsystem.get_game_world() - non-None exactly while a play world exists (this is the
    same check scene.py uses for _is_pie(), so it is the proven path).
    """
    body = (
        "try:\n"
        "    gw = _ues().get_game_world()\n"   # PROVEN: scene.py _is_pie() uses get_game_world() is not None
        "    running = gw is not None\n"
        "    _emit({'pie_running': running, 'world': (gw.get_name() if running else None)})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_start_pie(simulate=False) -> str:
    """Start a PIE (simulate=False) or Simulate-In-Editor (simulate=True) session.

    Async in the engine; we request the session and report started=True, then the caller polls
    is_pie_running. Refuses if a session is already active (matches the C++ guard on GEditor->PlayWorld).
    """
    sim = "True" if simulate else "False"
    body = (
        "try:\n"
        "    if _ues().get_game_world() is not None:\n"
        "        _emit({'error': 'a play session is already running'})\n"
        "    else:\n"
        "        _les().editor_play_simulate()\n"   # VERIFY: LevelEditorSubsystem.editor_play_simulate() - C++ uses GEditor->RequestPlaySession; no clean console verb for "play". simulate-vs-PIE distinction (" + sim + ") may not be honored by this binding.
        "        _emit({'started': True, 'simulate': " + sim + ", 'async': True, 'note': 'poll is_pie_running to confirm'})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e), 'hint': 'editor_play_simulate binding unverified; see VERIFY note'})\n"
    )
    return wrap(body)


def build_stop_pie() -> str:
    """Stop the active PIE / Simulate session (async; poll is_pie_running to confirm it ended).

    Mirrors EditorAppToolset::StopPIE -> GEditor->RequestEndPlayMap(). Refuses if nothing is running.
    """
    body = (
        "try:\n"
        "    if _ues().get_game_world() is None:\n"
        "        _emit({'error': 'no play session is currently running'})\n"
        "    else:\n"
        "        _les().editor_request_end_play()\n"   # VERIFY: LevelEditorSubsystem.editor_request_end_play() - C++ uses GEditor->RequestEndPlayMap().
        "        _emit({'stopping': True, 'async': True, 'note': 'poll is_pie_running to confirm'})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e), 'hint': 'editor_request_end_play binding unverified; see VERIFY note'})\n"
    )
    return wrap(body)


# ---------------------------------------------------------------------------------------------------
# Content browser navigation + selection
# ---------------------------------------------------------------------------------------------------

def build_get_content_browser_path() -> str:
    """Read the content browser's current folder path (e.g. "/Game/Props").

    C++ reads FContentBrowserModule::GetCurrentPath(). No clean Python binding for the *current* path,
    so this is best-effort: we report the folders of the currently-selected assets as a proxy, and the
    raw selected-asset list, since that's what Python can actually see.
    """
    body = (
        "try:\n"
        "    sel = unreal.EditorUtilityLibrary.get_selected_asset_data()\n"   # VERIFY: EditorUtilityLibrary.get_selected_asset_data() returns AssetData list
        "    paths = []\n"
        "    for d in sel:\n"
        "        pn = str(d.package_name)\n"
        "        paths.append(pn.rsplit('/', 1)[0] if '/' in pn else pn)\n"
        "    folders = sorted(set(paths))\n"
        "    _emit({'best_effort': True, 'selected_folders': folders,\n"
        "           'current_path': (folders[0] if folders else None),\n"
        "           'note': 'no Python binding for FContentBrowserModule.GetCurrentPath; derived from selection'})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_set_content_browser_path(path) -> str:
    """Navigate the content browser to (and select) a folder path, e.g. "/Game/Props".

    C++ calls FContentBrowserModule::SetSelectedPaths({Path}). The Python proxy is
    EditorAssetLibrary.sync_browser_to_objects on the folder, which scrolls/expands the browser to it.
    """
    body = (
        "try:\n"
        "    p = " + json.dumps(str(path)) + "\n"
        "    unreal.EditorAssetLibrary.sync_browser_to_objects([p])\n"   # VERIFY: sync to a FOLDER path scrolls the browser there (proven for asset paths; folder behavior best-effort vs C++ SetSelectedPaths)
        "    _emit({'navigated': p, 'best_effort': True,\n"
        "           'note': 'used sync_browser_to_objects; C++ uses FContentBrowserModule.SetSelectedPaths'})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_get_selected_assets() -> str:
    """List the assets currently selected in the content browser (package paths + class).

    Mirrors EditorAppToolset::GetSelectedAssets (FContentBrowserModule::GetAllSelectedAssets).
    Python path: EditorUtilityLibrary.get_selected_asset_data().
    """
    body = (
        "try:\n"
        "    data = unreal.EditorUtilityLibrary.get_selected_asset_data()\n"   # VERIFY: EditorUtilityLibrary.get_selected_asset_data()
        "    out = []\n"
        "    for d in data:\n"
        "        out.append({'package': str(d.package_name),\n"
        "                    'name': str(d.asset_name),\n"
        "                    'class': str(getattr(d, 'asset_class_path', getattr(d, 'asset_class', '')))})\n"
        "    _emit({'count': len(out), 'assets': out})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_select_assets(paths) -> str:
    """Select assets in the content browser by package path (e.g. ["/Game/Props/WD49"]).

    Mirrors EditorAppToolset::SelectAssets -> UEditorAssetLibrary::SyncBrowserToObjects.
    Python path: EditorAssetLibrary.sync_browser_to_objects([...]) (selects + scrolls into view).
    """
    body = (
        "try:\n"
        "    paths = " + json.dumps([str(p) for p in paths]) + "\n"
        "    unreal.EditorAssetLibrary.sync_browser_to_objects(paths)\n"   # PROVEN-ish: SyncBrowserToObjects is exactly what the C++ SelectAssets calls
        "    _emit({'selected': paths})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_open_editor_for_asset(asset_path) -> str:
    """Open the appropriate asset editor for an asset (e.g. open a Material in the Material Editor).

    Mirrors EditorAppToolset::OpenEditorForAsset -> UAssetEditorSubsystem::OpenEditorForAsset.
    Python path: AssetEditorSubsystem.open_editor_for_asset(load_asset(path)).
    """
    body = (
        "try:\n"
        "    p = " + json.dumps(str(asset_path)) + "\n"
        "    asset = unreal.load_asset(p)\n"
        "    if asset is None:\n"
        "        _emit({'error': 'asset not found', 'asset': p})\n"
        "    else:\n"
        "        aes = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)\n"   # VERIFY: get_editor_subsystem(unreal.AssetEditorSubsystem) - the C++ uses GEditor->GetEditorSubsystem<UAssetEditorSubsystem>()
        "        opened = aes.open_editor_for_asset(asset)\n"
        "        _emit({'opened': bool(opened) if opened is not None else True, 'asset': p})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


# ---------------------------------------------------------------------------------------------------
# Console variable search
# ---------------------------------------------------------------------------------------------------

def build_search_cvars(substring, limit=200) -> str:
    """Find console variables whose name contains `substring`; return name + value + help for each.

    Mirrors EditorAppToolset::SearchCVars, which walks IConsoleManager::ForEachConsoleObjectThatContains.
    There is no direct Python binding for that iterator, so we drive the editor's own  DumpConsoleCommands
    / cvar listing via console output is unreliable; instead we probe individual variables by name using
    SystemLibrary console-variable getters. Because we can't ENUMERATE from Python, this resolves a single
    candidate name (the substring treated as an exact-or-prefix cvar name) plus any obvious case variants.
    Best-effort: for true substring enumeration, run the C++ tool or `DumpConsoleCommands` in the log.
    """
    body = (
        "try:\n"
        "    sub = " + json.dumps(str(substring)) + "\n"
        "    lim = " + str(int(limit)) + "\n"
        "    results = {}\n"
        "    # Best-effort: query a handful of likely exact names. Python lacks IConsoleManager iteration,\n"
        "    # so substring fan-out isn't possible here without the C++ tool.\n"
        "    candidates = [sub]\n"
        "    for nm in candidates:\n"
        "        entry = {}\n"
        "        try:\n"
        "            entry['float'] = unreal.SystemLibrary.get_console_variable_float_value(nm)\n"   # VERIFY: SystemLibrary.get_console_variable_float_value(name) -> 0.0 if unknown (can't distinguish unset from 0)
        "        except Exception:\n"
        "            pass\n"
        "        try:\n"
        "            entry['int'] = unreal.SystemLibrary.get_console_variable_int_value(nm)\n"   # VERIFY: SystemLibrary.get_console_variable_int_value(name)
        "        except Exception:\n"
        "            pass\n"
        "        try:\n"
        "            entry['bool'] = unreal.SystemLibrary.get_console_variable_bool_value(nm)\n"   # VERIFY: SystemLibrary.get_console_variable_bool_value(name)
        "        except Exception:\n"
        "            pass\n"
        "        if entry:\n"
        "            results[nm] = entry\n"
        "    _emit({'best_effort': True, 'query': sub, 'count': len(results), 'cvars': results,\n"
        "           'note': 'Python cannot ENUMERATE cvars by substring (no IConsoleManager binding). '\n"
        "                   'For full search run the C++ SearchCVars tool or `DumpConsoleCommands` and read the log. '\n"
        "                   'Values reported are exact-name probes; 0/false may mean unset.'})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


# ---------------------------------------------------------------------------------------------------
# Viewport world<->screen projection (RISKIEST - heavily flagged best-effort)
# ---------------------------------------------------------------------------------------------------
#
# The C++ tool composes its own off-screen view-projection matrix and projects against a chosen render
# Size, so it does NOT need a live game viewport. From Python we have no access to that internal matrix.
# The only Python-reachable projection paths are GameplayStatics.project_world_to_screen /
# deproject_screen_to_world, which require a PLAYER CONTROLLER (i.e. an active PIE/game viewport). So:
#   - These work best while PIE is running (start_pie first).
#   - Outside PIE there is no player controller; we report a clear error telling the caller to start PIE.
# Both are flagged VERIFY because the player-controller acquisition + return-tuple shape are unconfirmed
# on this box.

def build_world_pos_to_screen(world_position, player_index=0) -> str:
    """Project a world-space [x,y,z] point to 2D screen coordinates [sx, sy] (best-effort).

    Uses GameplayStatics.project_world_to_screen via the active player controller - so it needs a live
    game/PIE viewport (start_pie first). Outside PIE there is no player controller and this returns an
    error. The C++ tool sidesteps this with its own off-screen matrix; that path isn't Python-reachable.
    """
    wx, wy, wz = [float(v) for v in world_position]
    body = (
        "try:\n"
        "    w = _ues().get_game_world()\n"   # need the PIE/game world for a player controller
        "    if w is None:\n"
        "        _emit({'error': 'no game world; start_pie first (world->screen needs a player controller)'})\n"
        "    else:\n"
        "        pc = unreal.GameplayStatics.get_player_controller(w, %d)\n" % int(player_index) +   # VERIFY: GameplayStatics.get_player_controller(world, index)
        "        if pc is None:\n"
        "            _emit({'error': 'no player controller in game world'})\n"
        "        else:\n"
        "            wp = unreal.Vector(%r, %r, %r)\n" % (wx, wy, wz) +
        "            sp = unreal.GameplayStatics.project_world_to_screen(pc, wp, True)\n"   # VERIFY: project_world_to_screen(player_controller, world_position, player_viewport_relative=True) -> Vector2D
        "            _emit({'best_effort': True, 'screen': [sp.x, sp.y], 'world': [wp.x, wp.y, wp.z]})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e), 'hint': 'needs PIE + player controller; binding shape unverified'})\n"
    )
    return wrap(body)


def build_screen_to_world(screen_position, player_index=0) -> str:
    """Deproject a 2D screen [sx, sy] to a world-space ray (origin + direction) (best-effort).

    Uses GameplayStatics.deproject_screen_to_world via the active player controller - needs a live
    game/PIE viewport (start_pie first). Returns the ray origin and unit direction; the caller can
    line-trace along it to hit geometry. Outside PIE this returns an error.
    """
    sx, sy = [float(v) for v in screen_position]
    body = (
        "try:\n"
        "    w = _ues().get_game_world()\n"
        "    if w is None:\n"
        "        _emit({'error': 'no game world; start_pie first (screen->world needs a player controller)'})\n"
        "    else:\n"
        "        pc = unreal.GameplayStatics.get_player_controller(w, %d)\n" % int(player_index) +   # VERIFY: GameplayStatics.get_player_controller(world, index)
        "        if pc is None:\n"
        "            _emit({'error': 'no player controller in game world'})\n"
        "        else:\n"
        "            res = unreal.GameplayStatics.deproject_screen_to_world(pc, unreal.Vector2D(%r, %r))\n" % (sx, sy) +   # VERIFY: deproject_screen_to_world(player_controller, screen_position) -> (world_position, world_direction)
        "            origin, direction = res[0], res[1]\n"
        "            _emit({'best_effort': True, 'screen': [%r, %r],\n" % (sx, sy) +
        "                   'world_origin': [origin.x, origin.y, origin.z],\n"
        "                   'world_direction': [direction.x, direction.y, direction.z]})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e), 'hint': 'needs PIE + player controller; binding shape unverified'})\n"
    )
    return wrap(body)
