"""The bridge's phone to the Unreal editor.

Wraps Epic's vendored Remote Execution client into something the MCP tools can lean on:

  * lazily discovers + connects to a running editor on first use,
  * keeps that one connection open and reuses it across every tool call,
  * reconnects automatically if the editor went away and came back (one retry),
  * run_snippet() sends our Python and digs the "UMCP_RESULT:" line back out as a dict.

Everything funnels through a single lock so two tool calls can't trample the one command
socket at the same time.
"""

import json
import os
import subprocess
import threading
import time

from unreal_mcp import config
from unreal_mcp.vendor import remote_execution as _re


class EditorNotReachable(RuntimeError):
    """No running editor could be discovered/connected on the Remote Execution channel."""


class EditorClient:
    def __init__(self, discover_timeout: float = 10.0):
        self._discover_timeout = discover_timeout
        self._remote = None          # the live RemoteExecution session (None until connected)
        self._lock = threading.Lock()

    # --- connection management (all called while holding self._lock) ---

    def _connect_locked(self) -> None:
        cfg = _re.RemoteExecutionConfig()
        cfg.multicast_group_endpoint = config.MULTICAST_GROUP_ENDPOINT
        cfg.multicast_bind_address = config.MULTICAST_BIND_ADDRESS
        cfg.command_endpoint = (config.MULTICAST_BIND_ADDRESS, config.COMMAND_ENDPOINT_PORT)

        remote = _re.RemoteExecution(cfg)
        remote.start()  # async UDP discovery begins

        node = None
        deadline = time.time() + self._discover_timeout
        while time.time() < deadline:
            nodes = remote.remote_nodes
            if nodes:
                node = nodes[0]
                break
            time.sleep(0.25)

        if not node:
            remote.stop()
            raise EditorNotReachable(
                "No Unreal editor found on the Remote Execution multicast group "
                f"{config.MULTICAST_GROUP_ENDPOINT}. Is the editor running with the Python "
                "plugin + Remote Execution enabled, and python.exe allowed through the firewall?"
            )

        remote.open_command_connection(node["node_id"])
        self._remote = remote

    def _drop_locked(self) -> None:
        if self._remote is not None:
            try:
                self._remote.stop()
            except Exception:
                pass
            self._remote = None

    def _ensure_connected_locked(self) -> None:
        if self._remote is None or not self._remote.has_command_connection():
            self._drop_locked()
            self._connect_locked()

    # --- running code ---

    def run_python(self, code: str, exec_mode: str = _re.MODE_EXEC_FILE) -> dict:
        """Run raw Python inside the editor; return the protocol result dict. One reconnect retry."""
        with self._lock:
            last_exc = None
            for attempt in (1, 2):
                try:
                    self._ensure_connected_locked()
                    return self._remote.run_command(code, exec_mode=exec_mode)
                except EditorNotReachable:
                    raise  # nothing to retry - there's no editor to talk to
                except Exception as exc:  # socket likely died (editor restarted) -> drop + retry once
                    last_exc = exc
                    self._drop_locked()
            raise RuntimeError(f"editor command failed after reconnect: {last_exc}")

    def run_snippet(self, code: str) -> dict:
        """Run a snippet that prints a 'UMCP_RESULT:<json>' line; return that parsed object."""
        result = self.run_python(code, exec_mode=_re.MODE_EXEC_FILE)
        payload = _extract_sentinel(result)
        if payload is None:
            raise RuntimeError(f"snippet emitted no {config.RESULT_SENTINEL} line. Raw result: {result}")
        return payload

    def read_binary(self, path: str, delete_after: bool = False) -> bytes:
        """Read a file the editor wrote (e.g. a PNG capture). Same machine, so no editor round-trip
        and no lock needed - the bridge just opens the file the snippet reported writing."""
        with open(path, "rb") as f:
            data = f.read()
        if delete_after:
            try:
                os.remove(path)
            except OSError:
                pass
        return data

    def read_text_tail(self, path: str, lines: int = 200) -> str:
        """Return the last `lines` lines of a text file (e.g. the editor log). Bridge-side, no editor."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                rows = f.readlines()
        except OSError as e:
            return f"<could not read {path}: {e}>"
        return "".join(rows[-lines:])

    # --- editor process supervision (used by the restart_editor tool) ---

    def request_quit(self) -> None:
        """Ask the editor to quit CLEANLY via the normal path (never force-kill, per R4). The command
        connection drops as it exits, so we swallow that and drop our side."""
        with self._lock:
            try:
                self._ensure_connected_locked()
                self._remote.run_command("import unreal; unreal.SystemLibrary.quit_editor()",
                                         exec_mode=_re.MODE_EXEC_FILE)
            except Exception:
                pass
            finally:
                self._drop_locked()

    @staticmethod
    def editor_running() -> bool:
        """True if an UnrealEditor.exe process is present (Windows tasklist; no extra deps)."""
        try:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq UnrealEditor.exe", "/NH"],
                                 capture_output=True, text=True, timeout=15).stdout
        except Exception:
            return False
        return "UnrealEditor.exe" in out

    def wait_for_exit(self, timeout: float = 90.0) -> bool:
        """Block until no UnrealEditor.exe remains (so we never relaunch into a project lock)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.editor_running():
                return True
            time.sleep(2.0)
        return not self.editor_running()

    def relaunch_editor(self) -> None:
        """Launch the editor DETACHED so it outlives this bridge process."""
        subprocess.Popen([config.UNREAL_EDITOR_EXE, config.UNREAL_UPROJECT],
                         creationflags=0x00000008, close_fds=True)  # 0x8 = DETACHED_PROCESS

    def close(self) -> None:
        with self._lock:
            self._drop_locked()


def _extract_sentinel(result: dict):
    """Find our 'UMCP_RESULT:<json>' line in the editor's captured stdout and parse it."""
    for entry in (result or {}).get("output") or []:
        for line in (entry.get("output") or "").splitlines():
            if line.startswith(config.RESULT_SENTINEL):
                return json.loads(line[len(config.RESULT_SENTINEL):])
    return None


# Module-level singleton that all tools share - one phone, reused for the whole session.
client = EditorClient()
