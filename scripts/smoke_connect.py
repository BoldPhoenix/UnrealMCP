"""Throwaway smoke test (build increment 2): can the bridge phone the editor?

Run with the venv python:
    .venv\\Scripts\\python.exe scripts\\smoke_connect.py

It discovers a running UE editor via multicast, opens a command connection, runs a
trivial bit of Python *inside* the editor, prints the result, and hangs up. This is
NOT part of the server - it's a one-off proof that the transport layer reaches UE.
"""

import sys
import time

from unreal_mcp.vendor import remote_execution as re


def main() -> int:
    cfg = re.RemoteExecutionConfig()  # defaults already match the editor's Python settings
    conn = re.RemoteExecution(cfg)
    conn.start()  # begins async UDP discovery (pings ~1/sec)
    print("[smoke] discovery started; multicast ->", cfg.multicast_group_endpoint,
          "| our TCP command listener ->", cfg.command_endpoint)
    try:
        # 1) Wait for the editor to announce itself (it 'pongs' our 'pings').
        node = None
        deadline = time.time() + 10
        while time.time() < deadline:
            nodes = conn.remote_nodes
            if nodes:
                node = nodes[0]
                break
            time.sleep(0.5)
        if not node:
            print("[smoke] FAIL: no editor discovered within 10s.")
            print("        - is the editor running with the Python plugin + Remote Execution on?")
            print("        - did Windows Firewall prompt for python.exe? allow it on Private networks.")
            return 1
        print("[smoke] discovered editor node:", node.get("node_id"))

        # 2) Open the TCP command channel (the editor connects back to us on 6776).
        conn.open_command_connection(node["node_id"])
        print("[smoke] command connection open.")

        # 3) Run a trivial statement INSIDE the editor and read the result back.
        result = conn.run_command("print('hello from inside Unreal:', 1 + 1)",
                                  exec_mode=re.MODE_EXEC_FILE)
        print("[smoke] run_command ->", result)
        ok = bool(result.get("success"))
        print("[smoke]", "PASS - the bridge can drive the editor."
              if ok else "FAIL - command returned success=False.")
        return 0 if ok else 1
    except RuntimeError as e:
        print("[smoke] FAIL (connection/command error):", e)
        print("        - if discovery worked but this timed out, the editor couldn't connect")
        print("          back to our TCP listener (firewall on 127.0.0.1:6776?).")
        return 1
    finally:
        conn.stop()
        print("[smoke] disconnected; discovery stopped.")


if __name__ == "__main__":
    sys.exit(main())
