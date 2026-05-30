# UnrealMCP

A self-owned [Model Context Protocol](https://modelcontextprotocol.io) server that drives the
**Unreal Engine 5.7 editor** for AI-assisted development and **deterministic cinematic production** —
designed to be controlled by Claude Code (or any MCP client).

It speaks MCP over **stdio** on one side and the Unreal Editor's built-in **Python Remote Execution**
on the other, so it needs **no compiled C++ plugin** — which keeps it portable across engine builds.

## Why

It replaces a two-server setup (a C++ in-editor HTTP plugin + a separate Python bridge) with one server
you own end to end, and fixes two hard-won bugs *by construction*:

- **Level saves write `.umap`, never `.uasset`.** A duplicate `.uasset` sharing a level's package name
  causes non-deterministic stale-level loads; the one save tool routes worlds through the level-save API
  and refuses to save a `World` as an asset.
- **Mutations actually persist** — every edit does `Modify(True)` + dirties the package and saves through
  the real editor path, so spawned/edited actors survive a reload.

And it adds a deterministic **film / illustration pipeline**: render your real, canon-consistent 3D assets
through Sequencer + Movie Render Queue instead of fighting generative-AI character drift.

## Tools (35)

- **Editor & level:** `get_status`, `get_level_actors`, `run_console_command`, `open_level`,
  `save_level` (`.umap`-guarded), `get_output_log`, `restart_editor` (clean quit + relaunch),
  `execute_python` (arbitrary editor Python — the escape hatch).
- **Actors:** `spawn_actor`, `set_property`, `move_actor`, `delete_actors`.
- **Assets:** `asset_search`, `asset_save`, `asset_edit` (CRUD), `asset_dependencies`,
  `asset_referencers`, `asset_import`, `material_instance`.
- **Eyes** (anti-stale `SceneCapture2D`, returns images): `eyes_mirror`, `eyes_focus`, `eyes_look`,
  `eyes_overview` (top-down orthographic floor plan).
- **Camera / DoF:** `set_camera` (aperture, focal length, focus method + distance).
- **Cinematic / film authoring** (Sequencer): `create_sequence`, `animate_actor`, `play_animation`
  (skeletal), `add_camera_cut`, `add_audio`, `add_fade`, `set_actor_visibility_track`,
  `add_shot` (master / sub-sequence), `sequence_inspect`.
- **Render** (Movie Render Queue, async request → poll): `render_sequence`, `render_status`.

## Architecture

```
Claude Code  ⇄  (stdio MCP / FastMCP)  ⇄  this bridge  ⇄  (UE Python Remote Execution,
                                                            multicast 239.0.0.1:6766 / TCP 6776)  ⇄  Unreal Editor
```

The bridge sends short Python snippets that run on the editor's game thread; each prints a
`UMCP_RESULT:<json>` line the bridge parses back. Images (`eyes_*` and render previews) are written to
disk by the editor and returned as MCP image content. The bridge lives **outside** the editor, so it
survives editor restarts and auto-reconnects.

## Requirements

- Windows + Unreal Engine 5.7 (tested), Python 3.11.
- In your UE project: enable the **Python Editor Script Plugin**, and
  **Project Settings → Plugins → Python → Enable Remote Execution** (defaults: multicast
  `239.0.0.1:6766`, bind `127.0.0.1`). Allow your `python.exe` through the firewall on first run.

## Setup

```powershell
# 1) install
py -3.11 -m venv .venv
.venv\Scripts\pip install -e .

# 2) vendor Epic's Remote Execution client.
#    It is NOT redistributed in this repo (Copyright Epic Games, All Rights Reserved) — copy it from
#    your own engine install:
Copy-Item "C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python\remote_execution.py" `
          "src\unreal_mcp\vendor\remote_execution.py"
```

## Use with Claude Code

Copy `.mcp.json.example` to `.mcp.json` (in this repo, or in your UE project), fix the paths, then run
`/mcp` to connect:

```json
{
  "mcpServers": {
    "unrealmcp": {
      "command": "C:/Projects/UnrealMCP/.venv/Scripts/python.exe",
      "args": ["-m", "unreal_mcp"],
      "env": { "UNREAL_PROJECT_DIR": "C:/Path/To/YourUEProject" }
    }
  }
}
```

Launch the editor on your project, `/mcp` connect, and the tools appear.

## Notes

- `restart_editor` requests a clean editor quit (never a force-kill) and relaunches it detached.
- Tested against vanilla UE 5.7. A deferred **ARK Survival Ascended DevKit** layer (additive, same
  architecture) is planned.
- This server intentionally has **no** generic "save asset on a World" path — worlds save as `.umap` only.
