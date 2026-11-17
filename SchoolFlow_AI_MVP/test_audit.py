"""Focused tests for Task 11 audit events, privacy, access, and wiring."""

from __future__ import annotations

import sys
import types
import unittest
import importlib
from datetime import date
from pathlib import Path


class _Column:
    def __init__(self, owner):
        self.owner = owner

    def metric(self, label, value):
        self.owner.metrics.append((label, value))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _StreamlitStub(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.errors = []
        self.dataframes = []
        self.metrics = []
        self.select_overrides = {}
        self.date_range_override = None

    def markdown(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, message, **kwargs):
        self.errors.append(message)

    def caption(self, *args, **kwargs):
        return None

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_Column(self) for _ in range(count)]

    def date_input(self, label, value=None, **kwargs):
        return self.date_range_override or (date.min, date.max)

    def selectbox(self, label, options, **kwargs):
        return self.select_overrides.get(kwargs.get("key"), options[0])

    def dataframe(self, data, **kwargs):
        self.dataframes.append(data)


_st = _StreamlitStub()
sys.modules["streamlit"] = _st
PROJECT_DIR = Path(__file__).parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from shared.audit import (  # noqa: E402
    ACTION_ASSESSMENT_CREATED,
    ACTION_INTERVENTION_UPDATED,
    ACTION_LESSON_ENDED,
    ACTION_PAGE_ACCESS,
    ACTION_PERMISSION_CHECK,
    ENTITY_ASSESSMENT,
    STATUS_FAILURE,
    STATUS_SUCCESS,
    audit_summary_stats,
    get_audit_events,
    log_event,
    new_event,
    reset_page_audit_dedupe_state,
    sanitize_audit_log,
    safe_event_summary,
)
from shared.permissions import (  # noqa: E402
    ROLE_SCHOOL_ADMIN,
    ROLE_TEACHER,
    VIEW_AUDIT_LOG,
    has_permission,
    get_permitted_nav_keys,
    require_permission,
)

class TestAuditEventCreation(unittest.TestCase):
    def test_event_has_utc_aware_timestamp(self):
        event = new_event(
            ACTION_ASSESSMENT_CREATED,
            ROLE_TEACHER,
            ENTITY_ASSESSMENT,
            _now="2025-01-02T03:04:05-05:00",
        )
        self.assertEqual(event["timestamp"], "2025-01-02T08:04:05+00:00")
        self.assertEqual(len(event["event_id"]), 32)

    def test_success_and_failure_statuses_are_preserved(self):
        success = new_event(ACTION_ASSESSMENT_CREATED, ROLE_TEACHER)
        failure = new_event(
            ACTION_PERMISSION_CHECK,
            ROLE_TEACHER,
            status=STATUS_FAILURE,
        )
        self.assertEqual(success["status"], STATUS_SUCCESS)
        self.assertEqual(failure["status"], STATUS_FAILURE)

    def test_invalid_status_and_unaware_timestamp_raise(self):
        with self.assertRaises(ValueError):
            new_event(ACTION_ASSESSMENT_CREATED, ROLE_TEACHER, status="unknown")
        with self.assertRaises(ValueError):
            new_event(
                ACTION_ASSESSMENT_CREATED,
                ROLE_TEACHER,
                _now="2025-01-02T03:04:05",
            )

    def test_invalid_action_role_and_summary_raise(self):
        with self.assertRaises(ValueError):
            new_event("unknown_action", ROLE_TEACHER)
        with self.assertRaises(ValueError):
            new_event(ACTION_ASSESSMENT_CREATED, "not_a_role")
        with self.assertRaises(ValueError):
            new_event(
                ACTION_ASSESSMENT_CREATED,
                ROLE_TEACHER,
                summary="Assessment created for Student A",
            )


class TestAuditPageRerunDedupe(unittest.TestCase):
    def test_same_page_and_role_keep_rerun_guards(self):
        state = {
            "_audit_page_context": ("audit_log", ROLE_SCHOOL_ADMIN),
            "_audit_log_page_access_logged": True,
            "_audit_denied_attempt": "existing-attempt",
        }
        changed = reset_page_audit_dedupe_state(
            state, "audit_log", ROLE_SCHOOL_ADMIN
        )
        self.assertFalse(changed)
        self.assertTrue(state["_audit_log_page_access_logged"])
        self.assertEqual(state["_audit_denied_attempt"], "existing-attempt")

    def test_navigation_or_role_change_resets_guards_for_next_entry(self):
        state = {
            "_audit_page_context": ("audit_log", ROLE_SCHOOL_ADMIN),
            "_audit_log_page_access_logged": True,
            "_audit_denied_context": ("audit_log", VIEW_AUDIT_LOG, ROLE_TEACHER),
            "_audit_denied_attempt": "teacher:audit_log",
        }
        self.assertTrue(
            reset_page_audit_dedupe_state(
                state, "dashboard", ROLE_SCHOOL_ADMIN
            )
        )
        for key in (
            "_audit_log_page_access_logged",
            "_audit_denied_context",
            "_audit_denied_attempt",
        ):
            self.assertNotIn(key, state)

        self.assertTrue(
            reset_page_audit_dedupe_state(
                state, "audit_log", ROLE_SCHOOL_ADMIN
            )
        )
        state["_audit_log_page_access_logged"] = True
        self.assertTrue(
            reset_page_audit_dedupe_state(
                state, "audit_log", ROLE_TEACHER
            )
        )
        self.assertNotIn("_audit_log_page_access_logged", state)


class TestAuditPrivacyAndCopies(unittest.TestCase):
    def test_personal_data_is_rejected_from_summary_metadata_and_ids(self):
        with self.assertRaises(ValueError):
            new_event(
                ACTION_ASSESSMENT_CREATED,
                ROLE_TEACHER,
                summary="Student A scored 9/10",
            )
        with self.assertRaises(ValueError):
            new_event(
                ACTION_ASSESSMENT_CREATED,
                ROLE_TEACHER,
                extra={"student_code": "STU-001"},
            )
        with self.assertRaises(ValueError):
            new_event(
                ACTION_ASSESSMENT_CREATED,
                ROLE_TEACHER,
                extra={"score": 9},
            )
        with self.assertRaises(ValueError):
            new_event(
                ACTION_ASSESSMENT_CREATED,
                ROLE_TEACHER,
                entity_id="STU-001",
            )
        with self.assertRaises(ValueError):
            new_event(
                ACTION_ASSESSMENT_CREATED,
                ROLE_TEACHER,
                actor_id="A Teacher",
            )

    def test_allowlisted_aggregate_metadata_is_copied(self):
        extra = {"record_count": 4}
        event = new_event(
            ACTION_ASSESSMENT_CREATED,
            ROLE_TEACHER,
            extra=extra,
        )
        extra["record_count"] = 99
        self.assertEqual(event["extra"], {"record_count": 4})

    def test_log_event_returns_deep_copy_and_never_swallows_invalid_input(self):
        original = [new_event(ACTION_ASSESSMENT_CREATED, ROLE_TEACHER)]
        updated = log_event(original, ACTION_LESSON_ENDED, ROLE_TEACHER)
        self.assertEqual(len(original), 1)
        self.assertEqual(len(updated), 2)
        self.assertIsNot(original[0], updated[0])

        updated[0]["extra"]["record_count"] = 7
        self.assertEqual(original[0]["extra"], {})
        with self.assertRaises(ValueError):
            log_event(original, ACTION_LESSON_ENDED, ROLE_TEACHER, status="bad")

    def test_legacy_events_are_redacted_before_they_are_kept(self):
        original_timestamp = "2025-01-02T03:04:05"
        legacy = [{
            "event_id": "a" * 12,
            "timestamp": original_timestamp,
            "actor_id": "Teacher Name",
            "actor_role": ROLE_TEACHER,
            "action": ACTION_ASSESSMENT_CREATED,
            "entity_type": ENTITY_ASSESSMENT,
            "entity_id": "STU-001",
            "status": STATUS_SUCCESS,
            "summary": "Student STU-001 scored 9/10",
            "changed_fields": ["student_code", "score"],
            "extra": {"student_name": "Student A", "record_count": 1},
        }]
        sanitized = sanitize_audit_log(legacy)
        event = sanitized[0]
        self.assertEqual(event["actor_id"], ROLE_TEACHER)
        self.assertEqual(event["entity_id"], "")
        self.assertEqual(event["summary"], "Assessment created")
        self.assertEqual(event["changed_fields"], ["score"])
        self.assertEqual(event["extra"], {"record_count": 1})
        self.assertTrue(event["timestamp"].endswith("+00:00"))
        self.assertNotIn("STU-001", str(event))
        self.assertNotIn("Student A", str(event))
        listed = get_audit_events(legacy)
        self.assertEqual(legacy[0]["timestamp"], original_timestamp)
        self.assertNotIn("STU-001", str(listed))
        self.assertNotIn("Student A", str(listed))

    def test_get_events_filters_inclusive_dates_and_returns_deep_copies(self):
        events = [
            new_event(
                ACTION_ASSESSMENT_CREATED,
                ROLE_TEACHER,
                _now="2025-01-01T23:59:59+00:00",
                extra={"record_count": 2},
            ),
            new_event(
                ACTION_INTERVENTION_UPDATED,
                ROLE_SCHOOL_ADMIN,
                status=STATUS_FAILURE,
                _now="2025-01-02T00:00:00+00:00",
            ),
        ]
        filtered = get_audit_events(
            events,
            actor_role=ROLE_TEACHER,
            action=ACTION_ASSESSMENT_CREATED,
            date_from="2025-01-01",
            date_to="2025-01-01",
        )
        self.assertEqual(len(filtered), 1)
        filtered[0]["extra"]["record_count"] = 9
        self.assertEqual(events[0]["extra"]["record_count"], 2)

        next_day = get_audit_events(events, date_from="2025-01-02")
        self.assertEqual(len(next_day), 1)
        self.assertEqual(next_day[0]["status"], STATUS_FAILURE)
        self.assertEqual(audit_summary_stats(events)["total"], 2)

    def test_invalid_date_filter_is_reported(self):
        with self.assertRaises(ValueError):
            get_audit_events([], date_from="not-a-date")


class TestAuditPermissionsAndPage(unittest.TestCase):
    def setUp(self):
        _st.session_state = {}
        _st.errors.clear()
        _st.dataframes.clear()
        _st.metrics.clear()
        _st.select_overrides.clear()
        _st.date_range_override = None
        self.audit_page = importlib.import_module("pages.audit_log")
        self._page_originals = {
            "st": self.audit_page.st,
            "T": self.audit_page.T,
            "is_arabic": self.audit_page.is_arabic,
            "text_dir": self.audit_page.text_dir,
        }
        self.audit_page.st = _st
        self.audit_page.T = lambda en, ar: en
        self.audit_page.is_arabic = lambda: False
        self.audit_page.text_dir = lambda: "ltr"

    def tearDown(self):
        for name, value in self._page_originals.items():
            setattr(self.audit_page, name, value)

    def test_only_school_admin_has_audit_permission(self):
        self.assertTrue(has_permission(ROLE_SCHOOL_ADMIN, VIEW_AUDIT_LOG))
        self.assertFalse(has_permission(ROLE_TEACHER, VIEW_AUDIT_LOG))
        self.assertFalse(require_permission(ROLE_TEACHER, VIEW_AUDIT_LOG)["allowed"])
        self.assertIn("audit_log", get_permitted_nav_keys(ROLE_SCHOOL_ADMIN))
        self.assertNotIn("audit_log", get_permitted_nav_keys(ROLE_TEACHER))

    def test_page_denies_teacher_and_records_failure_without_rendering_data(self):
        _st.session_state.update({
            "active_role": ROLE_TEACHER,
            "page": "audit_log",
            "audit_log": [],
        })
        self.audit_page.render()
        self.assertTrue(_st.errors)
        self.assertFalse(_st.dataframes)
        event = _st.session_state["audit_log"][0]
        self.assertEqual(event["action"], ACTION_PERMISSION_CHECK)
        self.assertEqual(event["status"], STATUS_FAILURE)

    def test_database_events_show_database_actor_and_distinguish_legacy_events(self):
        _st.session_state.update({
            "active_role": ROLE_SCHOOL_ADMIN,
            "page": "audit_log",
            "audit_log": [],
        })
        events = [
            {"actor_user_id": "database-user", "actor_role": ROLE_TEACHER,
             "action": "update", "entity_type": "students", "status": "success",
             "occurred_at": "2025-01-02T08:00:00+00:00", "database_generated": True,
             "record_data": {"entity_key": {"student_code": "synthetic"}}},
            {"actor_user_id": "legacy-user", "actor_role": ROLE_TEACHER,
             "action": "claimed", "entity_type": "students", "status": "success",
             "occurred_at": "2025-01-02T08:00:00+00:00", "database_generated": False,
             "record_data": {"entity_key": {"student_code": "forged"}}},
        ]
        self.audit_page.render(database_events=events, database_managed=True)
        database_table = _st.dataframes[0]
        self.assertEqual(database_table["Actor ID"].tolist(), ["database-user", "legacy-user"])
        self.assertEqual(database_table["Source"].tolist(), ["Database", "Unverified"])
        self.assertEqual(database_table["Record key"].tolist(), ['{"student_code": "synthetic"}', ""])

        _st.dataframes.clear()
        self.audit_page.render(database_events=events, database_managed=False)
        self.assertEqual(_st.dataframes[0]["Source"].tolist(), ["Unverified", "Unverified"])

    def test_admin_page_displays_only_allowlisted_nonpersonal_fields(self):
        _st.session_state.update({
            "active_role": ROLE_SCHOOL_ADMIN,
            "page": "audit_log",
            "audit_log": [
                new_event(
                    ACTION_ASSESSMENT_CREATED,
                    ROLE_TEACHER,
                    entity_type=ENTITY_ASSESSMENT,
                    _now="2025-01-02T08:00:00+00:00",
                ),
                new_event(
                    ACTION_INTERVENTION_UPDATED,
                    ROLE_SCHOOL_ADMIN,
                    status=STATUS_FAILURE,
                    _now="2025-01-03T08:00:00+00:00",
                )
            ],
        })
        _st.date_range_override = (date(2025, 1, 2), date(2025, 1, 2))
        _st.select_overrides.update({
            "audit_role_filter": "Teacher",
            "audit_action_filter": "Assessment created",
            "audit_status_filter": "Success",
        })
        self.audit_page.render()
        self.assertTrue(_st.dataframes)
        event_table = _st.dataframes[-1]
        self.assertEqual(
            list(event_table.columns),
            ["timestamp", "actor_role", "action", "status", "summary"],
        )
        self.assertNotIn("entity_id", event_table.columns)
        self.assertNotIn("extra", event_table.columns)
        self.assertIn("Assessment created", event_table["summary"].tolist())
        self.assertEqual(event_table["action"].tolist(), [ACTION_ASSESSMENT_CREATED])
        self.assertEqual(
            event_table["timestamp"].tolist(),
            ["2025-01-02 11:00:00 +0300 (Asia/Riyadh)"],
        )
        self.assertEqual(_st.metrics, [("Operations", 3), ("Success", 2), ("Failure", 1)])
        self.assertEqual(safe_event_summary(ACTION_ASSESSMENT_CREATED), "Assessment created")


class TestAuditEventWiring(unittest.TestCase):
    def test_workflow_modules_reference_expected_audit_actions(self):
        source = {
            name: (PROJECT_DIR / name).read_text(encoding="utf-8")
            for name in (
                "app.py",
                "pages/academic_progress.py",
                "pages/interventions.py",
                "pages/lesson_workspace.py",
                "pages/student_profile.py",
            )
        }
        expected = {
            "app.py": (
                "ACTION_DATA_IMPORT",
                "ACTION_REPORT_GENERATED",
                "ACTION_REPORT_DOWNLOADED",
                "ACTION_ROLE_CHANGED",
                "ACTION_PERMISSION_CHECK",
                "VIEW_AUDIT_LOG",
            ),
            "pages/academic_progress.py": (
                "ACTION_ASSESSMENT_CREATED",
                "ACTION_SKILL_CREATED",
                "ACTION_SKILL_REMOVED",
            ),
            "pages/interventions.py": (
                "ACTION_INTERVENTION_CREATED",
                "ACTION_INTERVENTION_UPDATED",
                "ACTION_CHECKPOINT_ADDED",
            ),
            "pages/lesson_workspace.py": (
                "ACTION_LESSON_STARTED",
                "ACTION_LESSON_ENDED",
                "ACTION_LESSON_PLAN_UPDATED",
                "ACTION_PARTICIPATION_LOGGED",
            ),
            "pages/student_profile.py": ("ACTION_PROFILE_VIEWED",),
        }
        for path, action_names in expected.items():
            for action_name in action_names:
                with self.subTest(path=path, action=action_name):
                    self.assertIn(action_name, source[path])
        self.assertEqual(source["app.py"].count("on_click=_audit_report_download"), 2)
        self.assertIn("reset_page_audit_dedupe_state(", source["app.py"])
        self.assertIn('if _current_page == "audit_log":', source["app.py"])
        self.assertIn("has_permission(st.session_state.get(\"active_role\"), VIEW_AUDIT_LOG)", source["app.py"])

    def test_successful_lesson_end_records_only_after_saving(self):
        lesson_workspace = importlib.import_module("pages.lesson_workspace")
        original_streamlit = lesson_workspace.st
        lesson_workspace.st = _st
        _st.session_state = {
            "active_role": ROLE_TEACHER,
            "lesson_active": True,
            "lesson_draft": {"lesson_id": "private-lesson-id", "attendance": {}},
            "lesson_records": [],
            "audit_log": [],
        }
        try:
            lesson_workspace._save_lesson_record()
            self.assertFalse(_st.session_state["lesson_active"])
            self.assertEqual(len(_st.session_state["lesson_records"]), 1)
            self.assertEqual(len(_st.session_state["audit_log"]), 1)
            self.assertEqual(_st.session_state["audit_log"][0]["action"], ACTION_LESSON_ENDED)
            self.assertNotIn("private-lesson-id", str(_st.session_state["audit_log"]))
        finally:
            lesson_workspace.st = original_streamlit


if __name__ == "__main__":
    unittest.main()
