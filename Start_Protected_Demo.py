"""Start the synthetic shared demo behind an explicitly protected Quick Tunnel."""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
APP = ROOT / "Shared_Demo.py"
PORT = 18764


def powershell(command):
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Local process inspection failed: {error.stderr.strip()}") from error
    return result.stdout.strip()


def listeners():
    output = powershell(
        "$ErrorActionPreference='Stop'; "
        "@(Get-NetTCPConnection -State Listen | "
        f"Where-Object {{$_.LocalPort -eq {PORT}}} | "
        "Select-Object LocalAddress,OwningProcess) | ConvertTo-Json -Compress"
    )
    if not output:
        return []
    result = json.loads(output)
    return result if isinstance(result, list) else [result]


def is_descendant(pid, ancestor):
    while pid > 0:
        if pid == ancestor:
            return True
        output = powershell(
            "$ErrorActionPreference='Stop'; "
            f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; "
            "if ($p) { $p.ParentProcessId }"
        )
        if not output:
            return False
        parent = int(output)
        if parent == pid:
            return False
        pid = parent
    return False


def stop_process_tree(pid):
    powershell(
        "$ErrorActionPreference='Stop'; "
        "function StopTree([int]$id) { "
        "foreach ($p in @(Get-CimInstance Win32_Process -Filter \"ParentProcessId=$id\")) "
        "{ StopTree ([int]$p.ProcessId) }; "
        "if (Get-Process -Id $id -ErrorAction SilentlyContinue) "
        "{ Stop-Process -Id $id -ErrorAction Stop } }; "
        f"StopTree {pid}"
    )


def cloudflared_command():
    executable = shutil.which("cloudflared")
    if not executable and os.environ.get("LOCALAPPDATA"):
        portable = Path(os.environ["LOCALAPPDATA"]) / "SchoolFlowAI" / "tools" / "cloudflared.exe"
        if portable.is_file():
            executable = str(portable)
    if not executable:
        raise RuntimeError("cloudflared was not found on PATH or in the per-user tools folder.")
    result = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=True,
    )
    match = re.search(r"cloudflared version (\d+)\.(\d+)\.(\d+)(?:\s|$)", result.stdout)
    if not match or tuple(map(int, match.groups())) < (2026, 9, 3):
        raise RuntimeError("cloudflared 2026.9.3 or newer is required.")
    help_result = subprocess.run(
        [executable, "tunnel", "--help"], capture_output=True, text=True, check=True,
    )
    if "--allowed-mail" not in help_result.stdout:
        raise RuntimeError("cloudflared does not advertise the required --allowed-mail option.")
    return executable


def wait_for_server(server):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("The demo server exited before becoming ready.")
        current = listeners()
        if current:
            for listener in current:
                if (listener["LocalAddress"] != "127.0.0.1"
                        or not is_descendant(int(listener["OwningProcess"]), server.pid)):
                    raise RuntimeError("The port is not exclusively bound to the demo on loopback.")
            try:
                with opener.open(f"http://127.0.0.1:{PORT}/_stcore/health", timeout=2) as response:
                    if response.read() == b"ok":
                        return
            except urllib.error.URLError:
                pass
        time.sleep(0.5)
    raise RuntimeError("The demo did not become ready; no tunnel was opened.")


def main():
    if sys.platform != "win32":
        raise RuntimeError("This launcher requires Windows.")
    if not PYTHON.is_file() or not APP.is_file():
        raise RuntimeError("Project Python environment or Shared_Demo.py is missing.")
    cloudflared = cloudflared_command()
    if listeners():
        raise RuntimeError("Port 18764 is already in use; stop its listener first.")

    email = input("Enter ONE allowed email address (no wildcard): ").strip()
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", email)
            or ".." in email):
        raise ValueError("An explicit email is required; wildcards and lists are not allowed.")
    print("The synthetic demo will be exposed through a Cloudflare email-PIN gateway.")
    print("Protection is not verified until authorized and unauthorized visitors are tested.")
    if input("Type START to start the local demo and protected tunnel: ") != "START":
        print("Cancelled. No server or tunnel was started.")
        return

    server = subprocess.Popen(
        [str(PYTHON), "-m", "streamlit", "run", str(APP),
         "--server.address=127.0.0.1", "--server.port=18764",
         "--server.headless=true", "--browser.gatherUsageStats=false"],
        cwd=str(ROOT),
    )
    try:
        wait_for_server(server)
        print("Local demo is listening only on 127.0.0.1:18764.", flush=True)
        print("Check cloudflared confirms email authentication before sharing its URL.", flush=True)
        subprocess.run(
            [cloudflared, "tunnel", "--url", "http://127.0.0.1:18764",
             "--allowed-mail", email],
            check=True,
        )
    finally:
        stop_process_tree(server.pid)
        server.wait(timeout=10)


if __name__ == "__main__":
    try:
        main()
    except (EOFError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        sys.exit(130)
