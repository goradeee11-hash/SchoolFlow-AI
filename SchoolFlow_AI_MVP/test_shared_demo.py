import os
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from assistant.llm_client import call_llm, is_online
from shared.supabase_backend import (
    SupabaseConfigurationError,
    SupabaseSettings,
    create_supabase_client,
)


ENTRYPOINT = Path(__file__).resolve().parent.parent / "Shared_Demo.py"


@pytest.fixture(autouse=True)
def isolate_reviewer_storage(tmp_path):
    with patch.dict(os.environ), \
         patch("shared.demo_storage.reviewer_demo_path", return_value=tmp_path / "reviewer.dat"):
        yield


def _app():
    return AppTest.from_file(str(ENTRYPOINT), default_timeout=30)


def test_shared_demo_does_not_load_cloud_or_local_snapshot():
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://example.invalid",
        "SUPABASE_ANON_KEY": "synthetic-public-key",
        "OPENAI_API_KEY": "synthetic-key",
    }), \
         patch("shared.supabase_backend.read_supabase_settings",
               side_effect=AssertionError("Cloud settings were read")), \
         patch("shared.demo_storage.demo_path",
               side_effect=AssertionError("Shared snapshot was accessed")), \
         patch("assistant.llm_client._resolve_api_key",
               side_effect=AssertionError("OpenAI key was read")):
        app = _app().run()
        assert not app.exception
        assert any("synthetic data only" in warning.value for warning in app.warning)
        assert not [item for item in app.toggle if item.key == "online_ai_toggle"]
        if os.name == "nt":
            assert app.button(key="save_synthetic_demo")
        assert not [item for item in app.selectbox if item.key == "role_selector"]
        app.button(key="nav_upload").click().run()
        assert not app.exception
        assert any("File uploads are disabled" in item.value for item in app.info)
        assert not app.get("file_uploader")


@pytest.mark.parametrize("explicit_shared", [False, True])
def test_direct_app_entrypoint_defaults_to_isolated_demo(monkeypatch, explicit_shared):
    for key in ("SCHOOLFLOW_SHARED_DEMO", "SCHOOLFLOW_STANDARD_MODE", "SCHOOLFLOW_LOCAL_DEMO"):
        monkeypatch.delenv(key, raising=False)
    if explicit_shared:
        monkeypatch.setenv("SCHOOLFLOW_SHARED_DEMO", "1")
        monkeypatch.setenv("SCHOOLFLOW_STANDARD_MODE", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "synthetic-public-key")
    with patch("shared.supabase_backend.read_supabase_settings",
               side_effect=AssertionError("Cloud configuration must not be read")):
        app = AppTest.from_file(str(ENTRYPOINT.parent / "SchoolFlow_AI_MVP" / "app.py"),
                                default_timeout=30).run()
        assert not app.exception
        assert app.session_state["active_role"] == "demo_reviewer"
        assert os.environ["SCHOOLFLOW_SHARED_DEMO"] == "1"
        with pytest.raises(SupabaseConfigurationError, match="disabled"):
            create_supabase_client(SupabaseSettings("https://example.invalid", "synthetic-key"))
        with pytest.raises(RuntimeError, match="shared_demo_disabled"):
            call_llm("synthetic prompt")
        app.button(key="nav_upload").click().run()
        assert not app.exception
        assert not app.get("file_uploader")


@pytest.mark.parametrize("page", [
    "academic_progress", "audit_log", "bloom_questions", "interventions",
    "lesson_workspace", "school_structure", "student_profile",
])
def test_internal_page_redirects_when_run_directly(page):
    class Redirected(Exception):
        pass

    with patch("streamlit.switch_page", side_effect=Redirected) as switch:
        with pytest.raises(Redirected):
            runpy.run_path(str(ENTRYPOINT.parent / "SchoolFlow_AI_MVP" / "pages" / f"{page}.py"),
                           run_name="__main__")
        switch.assert_called_once_with("app.py")


def test_reviewer_role_is_server_selected_and_admin_is_read_only():
    from shared.permissions import (
        ROLE_DEMO_REVIEWER, MANAGE_CLASS_ASSIGNMENTS, VIEW_ADMIN_DASHBOARD,
        VIEW_AUDIT_LOG, has_permission,
    )

    app = _app().run()
    app.session_state["active_role"] = "school_admin"
    app.run()
    assert app.session_state["active_role"] == ROLE_DEMO_REVIEWER
    assert has_permission(ROLE_DEMO_REVIEWER, VIEW_ADMIN_DASHBOARD)
    assert has_permission(ROLE_DEMO_REVIEWER, VIEW_AUDIT_LOG)
    assert not has_permission(ROLE_DEMO_REVIEWER, MANAGE_CLASS_ASSIGNMENTS)
    app.button(key="nav_admin_dashboard").click().run()
    assert not app.exception and not app.error
    assert not [item for item in app.button if "assign" in str(item.key).lower()]
    app.button(key="nav_audit_log").click().run()
    assert not app.exception and not app.error
    assert any(event["actor_role"] == ROLE_DEMO_REVIEWER
               for event in app.session_state["audit_log"])


def test_gemini_missing_key_is_reported_without_network():
    with patch("assistant.synthetic_ai._gemini_config", return_value=(None, "gemini-2.5-flash")), \
         patch("google.genai.Client") as client:
        app = _app().run()
        app.button(key="nav_assistant").click().run()
        app.button(key="request_gemini").click().run()
        assert not app.exception
        assert any("not configured" in message.value for message in app.error)
        client.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is required")
def test_shared_reviewer_explicitly_saves_and_restores_encrypted_data():
    app = _app().run()
    app.button(key="load_synthetic_demo").click().run()
    app.checkbox(key="demo_synthetic_confirmation").set_value(True).run()
    app.button(key="save_synthetic_demo").click().run()
    assert not app.exception and not app.error
    assert any("Encrypted demo saved" in message.value for message in app.success)
    reloaded = _app().run()
    assert not reloaded.exception and not reloaded.error
    assert set(reloaded.session_state["summary"]["Student code"]) == {"DEMO-01", "DEMO-02"}


def test_provider_and_database_client_fail_closed():
    with patch.dict(os.environ, {"SCHOOLFLOW_SHARED_DEMO": "1"}), \
         patch("assistant.llm_client._resolve_api_key",
               side_effect=AssertionError("OpenAI key was read")):
        assert not is_online()
        with pytest.raises(RuntimeError, match="shared_demo_disabled"):
            call_llm("synthetic prompt")
        with pytest.raises(SupabaseConfigurationError, match="disabled"):
            create_supabase_client(SupabaseSettings("https://example.invalid", "synthetic-key"))


def test_sessions_have_separate_demo_data():
    with patch.dict(os.environ, {}):
        first = _app().run()
        second = _app().run()
        first.button(key="load_synthetic_demo").click().run()
        first.session_state["lesson_draft"] = {"title": "First synthetic session"}
        first.run()
        assert not first.exception and not second.exception
        assert "summary" not in second.session_state
        assert second.session_state["lesson_draft"] == {}
        second.button(key="load_synthetic_demo").click().run()
        assert second.session_state["lesson_draft"] == {}
        assert "First synthetic session" not in str(second.session_state["lesson_draft"])


def test_demo_navigation_with_synthetic_data():
    with patch.dict(os.environ, {}):
        app = _app().run()
        app.button(key="load_synthetic_demo").click().run()
        for page in (
            "upload", "analysis", "reports", "messages", "assistant",
            "lesson_workspace", "student_profile", "academic_progress",
            "interventions", "bloom_questions", "settings", "admin_dashboard", "audit_log",
        ):
            app.button(key=f"nav_{page}").click().run()
            assert not app.exception, page
            assert not app.error, page


def test_synthetic_rows_can_be_added_edited_and_deleted():
    with patch.dict(os.environ, {}):
        app = _app().run()
        app.button(key="load_synthetic_demo").click().run()
        app.button(key="nav_upload").click().run()
        app.session_state["synthetic_data_editor_0"] = {
            "edited_rows": {0: {"Student name": "Synthetic Edited"}},
            "added_rows": [{
                "Student code": "DEMO-03", "Student name": "Synthetic C", "Week": 1,
                "Days scheduled": 5, "Days attended": 5, "Tasks set": 4,
                "Tasks completed": 3, "Quiz score / 10": 8,
                "Observation": "Synthetic", "Next step": "Review",
            }],
            "deleted_rows": [2, 3],
        }
        app.button(key="FormSubmitter:synthetic_data_editor_form-Apply synthetic data").click().run()
        assert not app.error and not app.exception
        rows = app.session_state["source_rows"]
        assert list(rows["Student code"]) == ["DEMO-01", "DEMO-01", "DEMO-03"]
        assert rows.iloc[0]["Student name"] == "Synthetic Edited"
        assert set(app.session_state["summary"]["Student code"]) == {"DEMO-01", "DEMO-03"}


def test_invalid_synthetic_edits_leave_existing_data_unchanged():
    with patch.dict(os.environ, {}):
        app = _app().run()
        app.button(key="load_synthetic_demo").click().run()
        app.button(key="nav_upload").click().run()
        app.session_state["synthetic_data_editor_0"] = {
            "edited_rows": {1: {"Week": 1}}, "added_rows": [], "deleted_rows": [],
        }
        app.button(key="FormSubmitter:synthetic_data_editor_form-Apply synthetic data").click().run()
        assert app.error
        assert list(app.session_state["source_rows"]["Week"]) == [1, 2, 1, 2]


def test_removing_all_synthetic_rows_preserves_lesson_history():
    with patch.dict(os.environ, {}):
        app = _app().run()
        app.button(key="load_synthetic_demo").click().run()
        app.session_state["lesson_records"] = [{"lesson_id": "synthetic-lesson"}]
        app.button(key="nav_upload").click().run()
        app.session_state["synthetic_data_editor_0"] = {
            "edited_rows": {}, "added_rows": [], "deleted_rows": [0, 1, 2, 3],
        }
        app.button(key="FormSubmitter:synthetic_data_editor_form-Apply synthetic data").click().run()
        assert not app.error and not app.exception
        assert "summary" not in app.session_state
        assert app.session_state["lesson_records"] == [{"lesson_id": "synthetic-lesson"}]


def test_active_lesson_blocks_applying_student_changes():
    with patch.dict(os.environ, {}):
        app = _app().run()
        app.session_state["lesson_active"] = True
        app.button(key="nav_upload").click().run()
        assert app.button(key="FormSubmitter:synthetic_data_editor_form-Apply synthetic data").disabled
