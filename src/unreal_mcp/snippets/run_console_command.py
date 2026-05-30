"""Snippet builder for the run_console_command tool.

Runs a console command on the live editor world. We pass the command in as a Python
literal via json.dumps() so quotes/backslashes in the command can't break the snippet.
"""

import json

from unreal_mcp.snippets import wrap


def build(command: str) -> str:
    # json.dumps yields a safe Python string literal, e.g.  stat fps  ->  "stat fps"
    body = (
        f"_cmd = {json.dumps(command)}\n"
        "w = _world()\n"
        "if w is None:\n"
        "    _emit({'error': 'editor not ready', 'detail': 'no editor world loaded'})\n"
        "else:\n"
        "    unreal.SystemLibrary.execute_console_command(w, _cmd)\n"
        "    _emit({'ran': _cmd})\n"
    )
    return wrap(body)
