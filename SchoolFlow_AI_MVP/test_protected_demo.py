import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parent.parent / "Start_Protected_Demo.py"
SPEC = importlib.util.spec_from_file_location("protected_demo_launcher", PATH)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def test_finds_per_user_portable_tool(monkeypatch, tmp_path):
    portable = tmp_path / "SchoolFlowAI" / "tools" / "cloudflared.exe"
    portable.parent.mkdir(parents=True)
    portable.touch()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(launcher.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        launcher.subprocess, "run",
        lambda args, **kwargs: SimpleNamespace(
            stdout="cloudflared version 2026.11.0" if args[-1] == "--version" else "--allowed-mail"
        ),
    )
    assert launcher.cloudflared_command() == str(portable)


@pytest.mark.parametrize("version", ["2026.9.2", "2026.9.3-rc1", "unknown"])
def test_rejects_unsupported_cloudflared(monkeypatch, version):
    monkeypatch.setattr(launcher.shutil, "which", lambda _: "fake-cloudflared")
    monkeypatch.setattr(
        launcher.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=f"cloudflared version {version}"),
    )
    with pytest.raises(RuntimeError, match="2026.9.3"):
        launcher.cloudflared_command()


def test_rejects_missing_email_protection_flag(monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda _: "fake-cloudflared")
    monkeypatch.setattr(
        launcher.subprocess, "run",
        lambda args, **kwargs: SimpleNamespace(
            stdout="cloudflared version 2026.11.0" if args[-1] == "--version" else "tunnel help"
        ),
    )
    with pytest.raises(RuntimeError, match="--allowed-mail"):
        launcher.cloudflared_command()


@pytest.mark.parametrize("email", ["", "*@example.invalid", "a@example.invalid,b@example.invalid"])
def test_invalid_email_never_starts_server(monkeypatch, email):
    monkeypatch.setattr(launcher, "cloudflared_command", lambda: "fake-cloudflared")
    monkeypatch.setattr(launcher, "listeners", lambda: [])
    monkeypatch.setattr("builtins.input", lambda _: email)
    monkeypatch.setattr(
        launcher.subprocess, "Popen",
        lambda *args, **kwargs: pytest.fail("A server was started"),
    )
    with pytest.raises(ValueError, match="wildcards"):
        launcher.main()


def test_confirmation_required(monkeypatch):
    monkeypatch.setattr(launcher, "cloudflared_command", lambda: "fake-cloudflared")
    monkeypatch.setattr(launcher, "listeners", lambda: [])
    responses = iter(["demo@example.invalid", "no"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    monkeypatch.setattr(
        launcher.subprocess, "Popen",
        lambda *args, **kwargs: pytest.fail("A server was started"),
    )
    launcher.main()


def test_occupied_port_refused_before_prompt(monkeypatch):
    monkeypatch.setattr(launcher, "cloudflared_command", lambda: "fake-cloudflared")
    monkeypatch.setattr(launcher, "listeners", lambda: [{"LocalAddress": "127.0.0.1"}])
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("Prompted with port occupied"))
    with pytest.raises(RuntimeError, match="already in use"):
        launcher.main()


def test_unexpected_listener_refused_before_health_or_tunnel(monkeypatch):
    monkeypatch.setattr(
        launcher, "listeners",
        lambda: [{"LocalAddress": "0.0.0.0", "OwningProcess": 42}],
    )
    server = SimpleNamespace(pid=42, poll=lambda: None)
    with pytest.raises(RuntimeError, match="loopback"):
        launcher.wait_for_server(server)


def test_protected_tunnel_arguments_and_server_cleanup(monkeypatch):
    monkeypatch.setattr(launcher, "cloudflared_command", lambda: "fake-cloudflared")
    monkeypatch.setattr(launcher, "listeners", lambda: [])
    responses = iter(["demo@example.invalid", "START"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    server = SimpleNamespace(pid=42, wait=lambda timeout: None)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: server)
    monkeypatch.setattr(launcher, "wait_for_server", lambda process: None)
    calls = []
    monkeypatch.setattr(launcher.subprocess, "run", lambda args, **kwargs: calls.append(args))
    stopped = []
    monkeypatch.setattr(launcher, "stop_process_tree", stopped.append)
    launcher.main()
    assert calls == [[
        "fake-cloudflared", "tunnel", "--url", "http://127.0.0.1:18764",
        "--allowed-mail", "demo@example.invalid",
    ]]
    assert stopped == [42]


def test_failed_readiness_stops_server_without_starting_tunnel(monkeypatch):
    monkeypatch.setattr(launcher, "cloudflared_command", lambda: "fake-cloudflared")
    monkeypatch.setattr(launcher, "listeners", lambda: [])
    responses = iter(["demo@example.invalid", "START"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    server = SimpleNamespace(pid=42, wait=lambda timeout: None)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: server)
    def fail_readiness(_):
        raise RuntimeError("Not ready")
    monkeypatch.setattr(launcher, "wait_for_server", fail_readiness)
    monkeypatch.setattr(
        launcher.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("A tunnel was started"),
    )
    stopped = []
    monkeypatch.setattr(launcher, "stop_process_tree", stopped.append)
    with pytest.raises(RuntimeError, match="Not ready"):
        launcher.main()
    assert stopped == [42]
