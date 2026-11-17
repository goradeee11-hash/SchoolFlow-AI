"""Start the synthetic shared demo behind an explicitly public Quick Tunnel."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from Start_Protected_Demo import (
    APP, PORT, PYTHON, ROOT, listeners, stop_process_tree, wait_for_server,
)

PUBLIC_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com\b", re.IGNORECASE)


def cloudflared_command():
    executable = shutil.which("cloudflared")
    if not executable and os.environ.get("LOCALAPPDATA"):
        portable = Path(os.environ["LOCALAPPDATA"]) / "SchoolFlowAI" / "tools" / "cloudflared.exe"
        if portable.is_file():
            executable = str(portable)
    if not executable:
        raise RuntimeError("cloudflared was not found on PATH or in the per-user tools folder.")
    return executable


def stop_started_process(process):
    if process is not None:
        if process.poll() is None:
            stop_process_tree(process.pid)
        process.wait(timeout=10)


def main():
    if sys.platform != "win32":
        raise RuntimeError("This launcher requires Windows.")
    if not PYTHON.is_file() or not APP.is_file():
        raise RuntimeError("Project Python environment or Shared_Demo.py is missing.")
    cloudflared = cloudflared_command()
    if listeners():
        raise RuntimeError("Port 18764 is already in use; stop its listener first.")

    print("WARNING: this is a PUBLIC link with NO authentication; anyone with it can access the demo.")
    print("Use synthetic data only. Do not enter real names, student data, credentials or sensitive information.")
    if input("Type START to start the public demo: ") != "START":
        print("Cancelled. No server or tunnel was started.")
        return

    server = subprocess.Popen(
        [str(PYTHON), "-m", "streamlit", "run", str(APP),
         "--server.address=127.0.0.1", "--server.port=18764",
         "--server.headless=true", "--browser.gatherUsageStats=false"],
        cwd=str(ROOT),
    )
    tunnel = None
    try:
        wait_for_server(server)
        print(f"Local synthetic demo is listening on 127.0.0.1:{PORT}.", flush=True)
        command = [cloudflared, "tunnel", "--url", "http://127.0.0.1:18764"]
        tunnel = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        found_url = False
        for line in tunnel.stdout:
            print(line, end="", flush=True)
            match = PUBLIC_URL.search(line)
            if match and not found_url:
                found_url = True
                print(
                    f"\nPUBLIC temporary link (anyone can access): {match.group(0)}\n"
                    "Share only after verifying it; press Ctrl+C to stop the demo.",
                    flush=True,
                )
        exit_code = tunnel.wait()
        if exit_code:
            raise subprocess.CalledProcessError(exit_code, command)
        if not found_url:
            raise RuntimeError("The tunnel exited without reporting a public URL.")
    finally:
        try:
            stop_started_process(tunnel)
        finally:
            stop_started_process(server)


if __name__ == "__main__":
    try:
        main()
    except (EOFError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        sys.exit(130)
