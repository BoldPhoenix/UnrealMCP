"""Snippet builder for the compile_live_coding tool (harvested from UE5.8 LiveCodingToolset).

Epic's ULiveCodingToolset::CompileLiveCoding drives ILiveCodingModule::Compile(WaitForCompletion)
in C++ - that module interface is NOT exposed to the Python `unreal` API, so we trigger the same
pipeline the only way Python can: the `LiveCoding.Compile` console command (the canonical hotkey-less
compile trigger; same path the Ctrl+Alt+F11 binding fires).

This KICKS the compile but cannot synchronously capture its result the way the C++ toolset does
(that relies on an in-process FOutputDevice hook + a WaitForCompletion flag we can't reach from a
console command). So: fire the command, then read the outcome from the editor log via the existing
log_search tool, filtering on the "LogLiveCoding" category. Returns {"ran": ...} immediately.
"""

from unreal_mcp.snippets import wrap


def build() -> str:
    body = (
        "w = _world()\n"
        "if w is None:\n"
        "    _emit({'error': 'editor not ready', 'detail': 'no editor world loaded'})\n"
        "else:\n"
        # VERIFY: 'LiveCoding.Compile' is the standard console command that triggers a Live Coding
        # VERIFY: compile. Requires Live Coding enabled for the session (Editor Preferences > Live Coding);
        # VERIFY: if disabled, the command no-ops and LogLiveCoding will say so. Confirm the exact command
        # VERIFY: token on metal - some builds also expose 'LiveCoding.Enable 1' as a prerequisite.
        "    unreal.SystemLibrary.execute_console_command(w, 'LiveCoding.Compile')\n"
        "    _emit({'ran': 'LiveCoding.Compile', 'started': True,\n"
        "           'note': 'Compile triggered async. Read results via log_search(\"LogLiveCoding\"). "
        "Requires Live Coding enabled for the session.'})\n"
    )
    return wrap(body)
