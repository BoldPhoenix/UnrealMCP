"""Connection + project configuration. Env-overridable so .mcp.json can point us at a project."""

import os

# --- UE Python Remote Execution endpoints ---
# These MUST match the editor's Project Settings > Plugins > Python and the vendored
# remote_execution.py defaults. Multicast is how we *discover* a running editor; the TCP
# command port is the actual channel we send Python snippets over.
MULTICAST_GROUP_ENDPOINT = ("239.0.0.1", 6766)
MULTICAST_BIND_ADDRESS = "127.0.0.1"
COMMAND_ENDPOINT_PORT = 6776

# --- Project under control (the editor we attach to) ---
UNREAL_PROJECT_DIR = os.environ.get("UNREAL_PROJECT_DIR", r"C:\Projects\PrimalErrorsUnreal")

# --- Snippet result protocol ---
# Every snippet we send into the editor prints exactly one line of the form
# "UMCP_RESULT:<json>". The bridge fishes that line out of the editor's captured stdout
# (Remote Execution only hands us text, so a sentinel + JSON is how we get structure back).
RESULT_SENTINEL = "UMCP_RESULT:"

# --- Editor launch (used by the restart_editor supervisor) ---
UNREAL_UPROJECT = os.environ.get(
    "UNREAL_UPROJECT", r"C:\Projects\PrimalErrorsUnreal\PrimalErrorsUnreal.uproject")
UNREAL_EDITOR_EXE = os.environ.get(
    "UNREAL_EDITOR_EXE", r"C:\Program Files\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor.exe")
