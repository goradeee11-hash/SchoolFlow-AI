import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parent.parent / "Start_Public_Demo.py"
SPEC = importlib.util.spec_from_file_location("public_demo_launcher", PATH)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def test_cancel_does_not_start_any_process(monkeypatch):
    monkeypatch.setattr(launcher, "cloudflared_command", lambda: "fake-cloudflared")
    monkeypatch.setattr(launcher, "listeners", lambda: [])
    monkeypatch.setattr("builtins.input", lambda _: "NO")
    monkeypatch.setattr(
        launcher.subprocess, "Popen",
        lambda *args, **kwargs: pytest.fail("A process was started"),
    )
    launcher.main()


def test_busy_port_rejected_before_start(monkeypatch):
    monkeypatch.setattr(launcher, "cloudflared_command", lambda: "fake-cloudflared")
    monkeypatch.setattr(launcher, "listeners", lambda: [{"LocalAddress": "127.0.0.1"}])
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("Prompted with port occupied"))
    with pytest.raises(RuntimeError, match="already in use"):
        launcher.main()


def test_readiness_failure_stops_only_the_started_server(monkeypatch):
    monkeypatch.setattr(launcher, "cloudflared_command", lambda: "fake-cloudflared")
    monkeypatch.setattr(launcher, "listeners", lambda: [])
    monkeypatch.setattr("builtins.input", lambda _: "START")
    server = SimpleNamespace(pid=123, poll=lambda: None, wait=lambda timeout: None)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: server)

    def fail_readiness(_server):
        raise RuntimeError("Not ready")

    monkeypatch.setattr(launcher, "wait_for_server", fail_readiness)
    stopped = []
    monkeypatch.setattr(launcher, "stop_process_tree", stopped.append)
    with pytest.raises(RuntimeError, match="Not ready"):
        launcher.main()
    assert stopped == [server.pid]


def test_interrupt_stops_only_the_started_tunnel_and_server(monkeypatch):
    monkeypatch.setattr(launcher, "cloudflared_command", lambda: "fake-cloudflared")
    monkeypatch.setattr(launcher, "listeners", lambda: [])
    monkeypatch.setattr("builtins.input", lambda _: "START")
    monkeypatch.setattr(launcher, "wait_for_server", lambda server: None)

    class InterruptedOutput:
        def __iter__(self):
            raise KeyboardInterrupt

    server = SimpleNamespace(pid=123, poll=lambda: None, wait=lambda timeout: None)
    tunnel = SimpleNamespace(
        pid=456, poll=lambda: None, wait=lambda timeout: None,
        stdout=InterruptedOutput(),
    )
    processes = iter([server, tunnel])
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: next(processes))
    stopped = []
    monkeypatch.setattr(launcher, "stop_process_tree", stopped.append)
    with pytest.raises(KeyboardInterrupt):
        launcher.main()
    assert stopped == [tunnel.pid, server.pid]


@pytest.mark.parametrize("exit_code", [0, 23])
def test_offline_fake_cloudflared_and_real_local_server(
    monkeypatch, tmp_path, capsys, exit_code,
):
    if sys.platform != "win32":
        pytest.skip("The launcher and local process checks require Windows.")
    if launcher.listeners():
        pytest.skip("The demo port is already in use; no existing process is touched.")

    fake = tmp_path / "fake_cloudflared.py"
    log = tmp_path / "fake_calls.json"
    fake.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['FAKE_CF_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
        "print('https://synthetic-fake.trycloudflare.com', flush=True)\n"
        "sys.exit(int(os.environ['FAKE_CF_EXIT']))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FAKE_CF_LOG", str(log))
    monkeypatch.setenv("FAKE_CF_EXIT", str(exit_code))
    monkeypatch.setattr(launcher, "cloudflared_command", lambda: "fake-cloudflared")
    monkeypatch.setattr("builtins.input", lambda _: "START")

    original_popen = subprocess.Popen
    server_commands = []

    def fake_popen(args, *popen_args, **kwargs):
        if args[0] == "fake-cloudflared":
            args = [sys.executable, str(fake), *args[1:]]
        elif "streamlit" in args:
            server_commands.append(args)
        return original_popen(args, *popen_args, **kwargs)

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    if exit_code:
        with pytest.raises(subprocess.CalledProcessError) as error:
            launcher.main()
        assert error.value.returncode == exit_code
    else:
        launcher.main()
        output = capsys.readouterr().out
        assert "PUBLIC temporary link" in output
        assert "https://synthetic-fake.trycloudflare.com" in output

    assert json.loads(log.read_text(encoding="utf-8")) == [
        "tunnel", "--url", "http://127.0.0.1:18764",
    ]
    assert len(server_commands) == 1
    assert "--server.address=127.0.0.1" in server_commands[0]
    assert "--server.port=18764" in server_commands[0]
    assert not launcher.listeners()
