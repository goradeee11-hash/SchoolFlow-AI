import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from shared.demo_storage import DemoStorageError, load_demo, restore_snapshot, save_demo, snapshot

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is required")


@pytest.fixture(autouse=True)
def local_demo_mode(monkeypatch):
    monkeypatch.setenv("SCHOOLFLOW_LOCAL_DEMO", "1")
    monkeypatch.delenv("SCHOOLFLOW_SHARED_DEMO", raising=False)


def _state():
    return {
        "source_rows": pd.DataFrame([{
            "Student code": "FAKE-01", "Student name": "Synthetic Name",
            "Week": 1, "Days scheduled": 5, "Days attended": 4,
            "Tasks set": 3, "Tasks completed": 2, "Quiz score / 10": 8,
            "Observation": "synthetic observation", "Next step": "review",
        }]),
        "lesson_draft": {"lesson_id": "lesson-1", "title": "Synthetic lesson"},
        "lesson_records": [{"lesson_id": "lesson-1"}],
        "participation_log": [{"student_code": "FAKE-01", "lesson_id": "lesson-1"}],
        "skill_definitions": [],
        "skill_assessments": [{"student_code": "FAKE-01", "score": 8}],
        "interventions": [],
        "intervention_checkpoints": [],
        "question_library": [],
        "chat_history": [{"text": "never persist this chat"}],
        "_supabase_password": "never persist this credential",
    }


def test_encrypted_snapshot_roundtrip_and_excluded_data(tmp_path):
    path = tmp_path / "demo.dat"
    original = _state()
    file_digest = save_demo(path, snapshot(original), None)
    raw = path.read_bytes()
    assert b"FAKE-01" not in raw
    assert b"never persist this credential" not in raw
    assert b"never persist this chat" not in raw
    loaded, observed_digest = load_demo(path)
    assert observed_digest == file_digest
    assert "chat_history" not in loaded and "_supabase_password" not in loaded
    restored = {}
    restore_snapshot(restored, loaded)
    assert restored["summary"].iloc[0]["Student code"] == "FAKE-01"
    assert restored["lesson_active"] is True
    assert restored["participation_log"] == original["participation_log"]
    assert restored["skill_assessments"] == original["skill_assessments"]


def test_concurrent_save_refuses_to_overwrite_and_invalid_file_is_preserved(tmp_path):
    path = tmp_path / "demo.dat"
    state = snapshot(_state())
    first_digest = save_demo(path, state, None)
    stale_digest = first_digest
    state["lesson_draft"]["title"] = "New synthetic title"
    save_demo(path, state, first_digest)
    newer_bytes = path.read_bytes()
    with pytest.raises(DemoStorageError, match="another session"):
        save_demo(path, state, stale_digest)
    assert path.read_bytes() == newer_bytes

    unrelated = tmp_path / "unrelated.dat"
    unrelated.write_bytes(b"existing file")
    with pytest.raises(DemoStorageError, match="unrecognized format"):
        load_demo(unrelated)
    with pytest.raises(DemoStorageError, match="another session"):
        save_demo(unrelated, state, None)
    assert unrelated.read_bytes() == b"existing file"


def _app(path):
    app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30)
    return app


def test_streamlit_saves_then_restores_a_new_session(tmp_path):
    path = tmp_path / "demo.dat"
    with patch("shared.supabase_backend.read_supabase_settings", return_value=None), \
         patch("shared.demo_storage.demo_path", return_value=path):
        app = _app(path)
        for key, value in _state().items():
            app.session_state[key] = value
        app.run()
        assert not app.exception
        app.checkbox(key="demo_synthetic_confirmation").set_value(True).run()
        app.button(key="save_synthetic_demo").click().run()
        assert not app.exception
        assert any("Encrypted demo saved" in message.value for message in app.success)
        assert path.exists()
        reloaded = _app(path).run()
        assert not reloaded.exception
        assert reloaded.session_state["summary"].iloc[0]["Student code"] == "FAKE-01"
        assert reloaded.session_state["lesson_draft"]["lesson_id"] == "lesson-1"
        assert reloaded.session_state["participation_log"][0]["student_code"] == "FAKE-01"


def test_streamlit_failed_save_never_reports_success_or_discards_state(tmp_path):
    with patch("shared.supabase_backend.read_supabase_settings", return_value=None), \
         patch("shared.demo_storage.demo_path", return_value=tmp_path / "demo.dat"), \
         patch("shared.demo_storage.save_demo", side_effect=DemoStorageError("synthetic failure")):
        app = _app(tmp_path).run()
        app.session_state["lesson_draft"] = {"lesson_id": "unsaved"}
        app.checkbox(key="demo_synthetic_confirmation").set_value(True).run()
        app.button(key="save_synthetic_demo").click().run()
        assert not app.exception
        assert any("Demo save failed" in message.value for message in app.error)
        assert not app.success
        assert app.session_state["lesson_draft"]["lesson_id"] == "unsaved"


def test_forced_demo_ignores_cloud_settings(tmp_path):
    with patch.dict(os.environ, {
        "SCHOOLFLOW_LOCAL_DEMO": "1",
        "SUPABASE_URL": "https://example.invalid",
        "SUPABASE_ANON_KEY": "synthetic-public-key",
    }), patch("shared.supabase_backend.read_supabase_settings",
              side_effect=AssertionError("Cloud configuration must not be read")), \
         patch("shared.demo_storage.demo_path", return_value=tmp_path / "demo.dat"):
        app = _app(tmp_path).run()
        assert not app.exception
        assert app.button(key="save_synthetic_demo")
        assert not app.session_state.get("_supabase_client")


def test_synthetic_demo_loads_only_into_an_empty_local_workspace(tmp_path):
    with patch.dict(os.environ, {"SCHOOLFLOW_LOCAL_DEMO": "1"}), \
         patch("shared.demo_storage.demo_path", return_value=tmp_path / "demo.dat"):
        app = _app(tmp_path).run()
        app.button(key="load_synthetic_demo").click().run()
        assert not app.exception
        assert set(app.session_state["summary"]["Student code"]) == {"DEMO-01", "DEMO-02"}
        assert "load_synthetic_demo" not in [button.key for button in app.button]
        assert not (tmp_path / "demo.dat").exists()


def test_assistant_shows_missing_key_when_online_is_requested(tmp_path):
    with patch.dict(os.environ, {"SCHOOLFLOW_LOCAL_DEMO": "1"}), \
         patch("shared.demo_storage.demo_path", return_value=tmp_path / "demo.dat"), \
         patch("assistant.llm_client._resolve_api_key", return_value=None):
        app = _app(tmp_path).run()
        app.toggle(key="online_ai_toggle").set_value(True).run()
        app.button(key="nav_assistant").click().run()
        assert not app.exception
        assert any("Online AI unavailable" in item.value for item in app.markdown)
        app.chat_input[0].set_value("Plan a synthetic lesson").run()
        assert not app.exception
        assert any("key is not configured" in item.value for item in app.markdown)
