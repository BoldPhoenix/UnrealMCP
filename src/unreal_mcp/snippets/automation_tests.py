"""Snippet builders for the automation-test tools (harvested from UE5.8 AutomationTestToolset).

Epic's AutomationTestToolset drives IAutomationControllerManager directly in C++ (session manager,
worker discovery, filter collections, async result objects). NONE of that controller machinery is
exposed to the Python `unreal` API, so - exactly as the port brief calls for - we implement these
over the `Automation` console command family, which the same controller backs:

    Automation List                 -> dumps the discovered test list to the log
    Automation RunTests <filter>    -> runs tests whose name contains <filter> (+-separated, like
                                       the C++ RunTestsByFilter expression parser)
    Automation RunAll               -> runs every discovered test
    Automation StopTests            -> aborts the in-progress run

Console commands write their output to the editor LOG, not back to us, so every builder here returns
a small "started/ran" ack and a note telling the caller to read results via the existing log_search
tool (category "LogAutomationController" / "LogAutomation"). run_tests is modeled ASYNC like
render_sequence: it returns {"started": true} and the user polls the log.

The filter expression mirrors UE5.8's RunTestsByFilter syntax (AutomationTestToolset.cpp): plain
substrings, "Group:<name>", "StartsWith:<prefix>", joined with "+". We pass it through verbatim.
"""

import json

from unreal_mcp.snippets import wrap

# Shared guard: bail cleanly if no editor world is loaded (console commands need a world).
_GUARD = (
    "w = _world()\n"
    "if w is None:\n"
    "    _emit({'error': 'editor not ready', 'detail': 'no editor world loaded'})\n"
    "else:\n"
)

# Note appended to every result so the caller knows the real output lives in the log.
_LOG_NOTE = (
    "Output goes to the editor log, not this return value. Read it via "
    "log_search(\"LogAutomationController\") or log_search(\"Automation\")."
)


def build_list_tests() -> str:
    """Dump the discovered automation test list to the log via `Automation List`."""
    body = (
        _GUARD
        # VERIFY: 'Automation List' is the discovery/list console command. The C++ toolset reads the
        # VERIFY: list from IAutomationControllerManager::GetFilteredReports() instead; via console the
        # VERIFY: list is only retrievable from the log. Confirm command spelling on metal.
        + "    unreal.SystemLibrary.execute_console_command(w, 'Automation List')\n"
        + "    _emit({'ran': 'Automation List', 'note': " + json.dumps(_LOG_NOTE) + "})\n"
    )
    return wrap(body)


def build_run_tests(test_filter=None) -> str:
    """Run automation tests by filter (or all if no filter). ASYNC - returns started=true; poll the log.

    test_filter: a substring/expression like "Project.Maps" or "StartsWith:System+Group:Smoke".
    Empty/None -> `Automation RunAll`.
    """
    # Build the command in Python so the filter string is embedded safely as a console arg.
    cmd_expr = (
        "    if _filter:\n"
        "        _cmd = 'Automation RunTests ' + _filter\n"
        "    else:\n"
        "        _cmd = 'Automation RunAll'\n"
    )
    body = (
        f"_filter = {json.dumps((test_filter or '').strip())}\n"
        + _GUARD
        + cmd_expr
        # VERIFY: 'Automation RunTests <filter>' and 'Automation RunAll' are the run commands. The C++
        # VERIFY: toolset's RunTestsByFilter does richer +-expression parsing (Group:/StartsWith:/^$);
        # VERIFY: the console 'RunTests' takes a simpler substring filter. Confirm filter semantics + that
        # VERIFY: discovery has completed (run list_tests first) before relying on a match on metal.
        + "    unreal.SystemLibrary.execute_console_command(w, _cmd)\n"
        + "    _emit({'ran': _cmd, 'started': True, 'filter': _filter or None,\n"
        + "           'note': " + json.dumps("Tests started async; poll the log for completion + results. " + _LOG_NOTE) + "})\n"
    )
    return wrap(body)


def build_get_test_status() -> str:
    """Probe whether a test run is in progress. There is no Python controller API, so this re-emits a
    status console command and points the caller at the log for the actual pass/fail counts."""
    body = (
        _GUARD
        # VERIFY: There is no clean console command that returns automation status as a value. 'Automation
        # VERIFY: List' is the safest no-side-effect probe (it does not start a run); the real state
        # VERIFY: (Running/Ready, pass/fail counts) must be read from the log. If a status-only command
        # VERIFY: exists in this build (e.g. 'Automation Status'), prefer it - confirm on metal.
        + "    unreal.SystemLibrary.execute_console_command(w, 'Automation List')\n"
        + "    _emit({'ran': 'Automation List', 'note': "
        + json.dumps(
            "No Python automation-controller API is exposed; run state + pass/fail counts must be read "
            "from the log. " + _LOG_NOTE
        )
        + "})\n"
    )
    return wrap(body)


def build_stop_tests() -> str:
    """Abort an in-progress automation run via `Automation StopTests`."""
    body = (
        _GUARD
        # VERIFY: 'Automation StopTests' is the abort command (mirrors Controller->StopTests()). Confirm
        # VERIFY: spelling on metal - some builds expose 'Automation Quit' instead.
        + "    unreal.SystemLibrary.execute_console_command(w, 'Automation StopTests')\n"
        + "    _emit({'ran': 'Automation StopTests', 'stopped': True, 'note': " + json.dumps(_LOG_NOTE) + "})\n"
    )
    return wrap(body)
