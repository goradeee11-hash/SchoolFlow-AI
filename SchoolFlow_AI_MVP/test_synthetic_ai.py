from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sqlite3

import httpx2
import pytest
from google.genai import errors

from assistant import synthetic_ai


@pytest.fixture
def configured_demo(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOOLFLOW_SHARED_DEMO", "1")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(synthetic_ai, "_gemini_config", lambda: ("fake-key", "gemini-2.5-flash"))


def test_gemini_sends_only_fixed_template_and_bounds_output(configured_demo):
    generate = Mock(return_value=SimpleNamespace(text="  synthetic answer  "))
    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    with patch("google.genai.Client", return_value=client) as factory:
        result = synthetic_ai.generate_synthetic_template("lesson")
    assert result == "synthetic answer"
    assert factory.call_args.kwargs["api_key"] == "fake-key"
    assert factory.call_args.kwargs["http_options"].retry_options.attempts == 1
    request = generate.call_args.kwargs
    assert request["contents"] == synthetic_ai.TEMPLATES["lesson"]
    assert request["config"].max_output_tokens == 512
    assert request["config"].thinking_config.thinking_budget == 0


def test_arbitrary_text_and_other_providers_are_rejected(configured_demo):
    with patch("google.genai.Client") as factory:
        with pytest.raises(RuntimeError, match="invalid_template"):
            synthetic_ai.generate_synthetic_template("private student data")
        with pytest.raises(RuntimeError, match="shared_demo_disabled"):
            synthetic_ai.generate_synthetic_template("lesson", provider="openai")
        factory.assert_not_called()


def test_missing_key_never_reserves_or_calls_provider(configured_demo, monkeypatch, tmp_path):
    monkeypatch.setattr(synthetic_ai, "_gemini_config", lambda: (None, "gemini-2.5-flash"))
    with patch("google.genai.Client") as factory:
        with pytest.raises(RuntimeError, match="no_key"):
            synthetic_ai.generate_synthetic_template("lesson")
        factory.assert_not_called()
    assert not (tmp_path / "SchoolFlowAI" / "gemini-demo-quota.sqlite3").exists()


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (errors.APIError(429, {"message": "fake-secret"}), "rate_limit"),
        (errors.APIError(403, {"message": "fake-secret"}), "bad_key"),
        (errors.APIError(500, {"message": "fake-secret"}), "api_error"),
        (httpx2.ConnectError("fake-secret"), "connection_error"),
    ],
)
def test_provider_errors_are_explicit_and_sanitized(configured_demo, failure, message):
    client = SimpleNamespace(models=SimpleNamespace(generate_content=Mock(side_effect=failure)))
    with patch("google.genai.Client", return_value=client):
        with pytest.raises(RuntimeError) as caught:
            synthetic_ai.generate_synthetic_template("lesson")
    assert str(caught.value) == message
    assert caught.value.__suppress_context__


def test_shared_minute_and_rolling_day_limits_persist(configured_demo, monkeypatch):
    now = [1000000.0]
    monkeypatch.setattr(synthetic_ai.time, "time", lambda: now[0])
    for _ in range(4):
        for _ in range(5):
            synthetic_ai._reserve_request()
        with pytest.raises(RuntimeError, match="local_rate_limit"):
            synthetic_ai._reserve_request()
        now[0] += 61
    with pytest.raises(RuntimeError, match="local_rate_limit"):
        synthetic_ai._reserve_request()
    now[0] += 86400
    synthetic_ai._reserve_request()


def test_concurrent_sessions_cannot_exceed_minute_limit(configured_demo):
    def attempt(_):
        try:
            synthetic_ai._reserve_request()
            return True
        except RuntimeError as error:
            assert str(error) == "local_rate_limit"
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, range(10)))
    assert sum(results) == 5


def test_quota_storage_failure_blocks_request(configured_demo):
    with patch("assistant.synthetic_ai.sqlite3.connect", side_effect=sqlite3.OperationalError("private")), \
         patch("google.genai.Client") as factory:
        with pytest.raises(RuntimeError, match="quota_unavailable"):
            synthetic_ai.generate_synthetic_template("lesson")
        factory.assert_not_called()
