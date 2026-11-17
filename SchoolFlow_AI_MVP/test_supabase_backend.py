import base64
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
from postgrest.exceptions import APIError

from shared.supabase_backend import (
    SupabaseConfigurationError,
    _json_safe,
    _related_record,
    assign_student_to_class,
    assign_teacher_to_class,
    classify_legacy_class,
    create_school_class,
    load_class_management,
    load_class_import,
    load_audit_mode,
    load_database_audit_events,
    load_school_structure,
    load_teaching_assignments,
    load_workspace,
    remove_teacher_from_class,
    read_supabase_settings,
    source_rows_fingerprint,
    save_class_import,
    save_school_structure_name,
    save_teaching_assignment,
    sync_workspace,
    workspace_fingerprint,
    workspace_record_fingerprints,
)


class SupabaseSettingsTests(unittest.TestCase):
    def test_missing_settings_keep_the_local_mode_available(self):
        self.assertIsNone(read_supabase_settings({}, {}))

    def test_reads_public_settings_from_environment_or_streamlit_secrets(self):
        from_environment = read_supabase_settings(
            {"SUPABASE_URL": "https://school.supabase.co", "SUPABASE_ANON_KEY": "public"},
            {},
        )
        from_secrets = read_supabase_settings(
            {},
            {"supabase": {"url": "https://school.supabase.co", "anon_key": "public"}},
        )

        self.assertEqual(from_environment, from_secrets)
        self.assertEqual(from_environment.anon_key, "public")

    def test_rejects_partial_or_service_role_configuration(self):
        with self.assertRaises(SupabaseConfigurationError):
            read_supabase_settings({"SUPABASE_URL": "https://school.supabase.co"}, {})
        with self.assertRaises(SupabaseConfigurationError):
            read_supabase_settings(
                {
                    "SUPABASE_URL": "https://school.supabase.co",
                    "SUPABASE_ANON_KEY": "service_role-secret",
                },
                {},
            )
        service_role_claim = base64.urlsafe_b64encode(
            b'{"role":"service_role"}'
        ).decode().rstrip("=")
        with self.assertRaises(SupabaseConfigurationError):
            read_supabase_settings(
                {
                    "SUPABASE_URL": "https://school.supabase.co",
                    "SUPABASE_ANON_KEY": f"header.{service_role_claim}.signature",
                },
                {},
            )

    def test_json_conversion_keeps_missing_values_distinct_from_zero(self):
        result = _json_safe(
            {"missing": float("nan"), "pandas_missing": pd.NA, "zero": 0.0}
        )

        self.assertIsNone(result["missing"])
        self.assertIsNone(result["pandas_missing"])
        self.assertEqual(result["zero"], 0.0)

    def test_participation_payload_does_not_duplicate_student_name(self):
        saved = _related_record(
            "school-id",
            {
                "id": "p-1",
                "student_code": "S01",
                "student_name": "Sensitive Name",
                "lesson_id": "lesson-1",
                "skill_id": "reading",
                "timestamp": "2026-11-15T10:00:00+00:00",
            },
            "record_id",
            "participation",
        )

        self.assertEqual(saved["student_code"], "S01")
        self.assertNotIn("student_name", saved["record_data"])

    def test_unknown_legacy_skill_text_is_preserved_but_not_linked_as_a_fk(self):
        saved = _related_record(
            "school-id",
            {
                "id": "p-legacy",
                "student_code": "S01",
                "lesson_id": "lesson-1",
                "skill_id": "Legacy free text",
            },
            "record_id",
            "participation",
            valid_optional_skill_ids={"official-skill"},
        )

        self.assertIsNone(saved["skill_id"])
        self.assertEqual(saved["record_data"]["skill_id"], "Legacy free text")


class _FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table
        self.operation = "select"
        self.payload = None
        self.filters = {}
        self.selection = None
        self.order_column = None
        self.descending = False

    def select(self, columns):
        self.selection = columns
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def upsert(self, rows, on_conflict=None, ignore_duplicates=False):
        self.operation = "upsert"
        self.payload = rows
        self.conflict = on_conflict
        self.ignore_duplicates = ignore_duplicates
        return self

    def insert(self, rows):
        self.operation = "insert"
        self.payload = rows
        return self

    def update(self, row):
        self.operation = "update"
        self.payload = row
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def order(self, column, desc=False, **_kwargs):
        self.order_column = column
        self.descending = desc
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        self.client.calls.append(
            {
                "table": self.table_name,
                "operation": self.operation,
                "payload": self.payload,
                "filters": dict(self.filters),
            }
        )
        data = [
            row
            for row in self.client.responses.get(self.table_name, [])
            if all(row.get(key) == value for key, value in self.filters.items())
        ]
        if self.order_column:
            data.sort(
                key=lambda row: row.get(self.order_column),
                reverse=self.descending,
            )
        return SimpleNamespace(data=data)


class _FakeClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def table(self, name):
        return _FakeQuery(self, name)

    def rpc(self, name, params):
        client = self

        class FakeRPC:
            def execute(self):
                client.calls.append(
                    {"operation": "rpc", "name": name, "params": params}
                )
                return SimpleNamespace(data=None)

        return FakeRPC()


class SupabaseWorkspaceTests(unittest.TestCase):
    def test_legacy_teacher_workspace_is_blocked_before_any_database_io(self):
        client = _FakeClient()
        for role in ("teacher", "student", ""):
            with self.subTest(role=role):
                with self.assertRaisesRegex(ValueError, "assignment isolation"):
                    load_workspace(client, "school-id", "user-id", role)
                with self.assertRaisesRegex(ValueError, "assignment isolation"):
                    sync_workspace(client, "school-id", "user-id", {}, role=role)
        self.assertEqual(client.calls, [])

    def test_structure_loading_is_school_scoped_and_rejects_malformed_rows(self):
        client = _FakeClient({
            "school_stages": [
                {"school_id": "school", "stage_id": "s1", "stage_name": "Primary"},
                {"school_id": "other", "stage_id": "s2", "stage_name": "Other"},
            ],
        })
        result = load_school_structure(client, "school")
        self.assertEqual([row["stage_id"] for row in result["stages"]], ["s1"])
        self.assertTrue(all(call["filters"] == {"school_id": "school"} for call in client.calls))
        client.responses["school_stages"] = [{"school_id": "school", "stage_id": "s1"}]
        with self.assertRaises(ValueError):
            load_school_structure(client, "school")

    def test_structure_management_uses_selected_school_and_real_class_ids(self):
        client = Mock()
        client.table.return_value.insert.return_value.execute.return_value.data = [{}]
        save_school_structure_name(client, "school", "class", " A ", parent_id="grade")
        payload = client.table.return_value.insert.call_args.args[0]
        self.assertEqual(payload["school_id"], "school")
        self.assertEqual(payload["grade_id"], "grade")
        self.assertEqual(payload["class_name"], "A")
        self.assertTrue(payload["class_id"])
        with self.assertRaises(ValueError):
            save_school_structure_name(client, "school", "class", "B", record_id="class")

    def test_classification_only_updates_records_still_unclassified(self):
        client = Mock()
        query = client.table.return_value.update.return_value.eq.return_value.eq.return_value
        query.is_.return_value.execute.return_value.data = [{"class_id": "class"}]
        classify_legacy_class(client, "school", "class", "grade")
        query.is_.assert_called_with("grade_id", "null")
        assign_student_to_class(client, "school", "student", "class", only_unclassified=True)
        query.is_.assert_called_with("class_id", "null")
        query.is_.return_value.execute.return_value.data = []
        with self.assertRaises(ValueError):
            classify_legacy_class(client, "school", "class", "grade")

    def test_assignment_update_is_one_school_scoped_operation(self):
        client = Mock()
        client.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{}]
        save_teaching_assignment(
            client, "school", "new-class", "new-subject", "teacher",
            previous=("old-class", "old-subject", "teacher"),
        )
        client.table.return_value.update.assert_called_once_with({
            "class_id": "new-class", "subject_id": "new-subject", "teacher_id": "teacher",
        })
        query = client.table.return_value.update.return_value
        query.eq.assert_called_once_with("school_id", "school")
        query.eq.return_value.eq.assert_called_once_with("class_id", "old-class")

    def test_database_audit_load_requests_trusted_record_key(self):
        client = Mock()
        client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        self.assertEqual(load_database_audit_events(client, "school", "database"), [])
        columns = client.table.return_value.select.call_args.args[0]
        self.assertIn("database_generated", columns.split(","))
        self.assertIn("record_data", columns.split(","))

    def test_load_teaching_assignments_uses_authenticated_database_identity(self):
        client = Mock()
        assignment = {
            "stage_id": "stage", "stage_name": "Primary",
            "grade_id": "grade", "grade_name": "Grade 1",
            "class_id": "class", "class_name": "A",
            "subject_id": "subject", "subject_name": "Math",
        }
        client.rpc.return_value.execute.return_value.data = [assignment]
        self.assertEqual(load_teaching_assignments(client, "school"), [assignment])
        client.rpc.assert_called_once_with(
            "list_my_teaching_assignments", {"p_school_id": "school"}
        )
        client.rpc.return_value.execute.return_value.data = [{"class_id": "class"}]
        with self.assertRaises(ValueError):
            load_teaching_assignments(client, "school")

    def test_class_import_backend_normalizes_and_preserves_scoped_request(self):
        client = Mock()
        import_id = "00000000-0000-0000-0000-000000000001"
        client.rpc.return_value.execute.return_value.data = import_id
        result = save_class_import(
            client, "school", "class-a",
            [{"Student code": " S01 ", "Week": 1}], None,
        )
        self.assertEqual(result, import_id)
        client.rpc.assert_called_with("save_class_import", {
            "p_school_id": "school",
            "p_class_id": "class-a",
            "p_rows": [{"Student code": "S01", "Week": 1}],
            "p_expected_import_id": None,
        })
        client.rpc.return_value.execute.return_value.data = {
            "import_id": import_id, "rows": [{"Student code": "S01"}],
        }
        self.assertEqual(load_class_import(client, "school", "class-a"), (
            import_id, [{"Student code": "S01"}],
        ))
        client.rpc.assert_called_with("load_class_import", {
            "p_school_id": "school", "p_class_id": "class-a",
        })
        with self.assertRaises(ValueError):
            save_class_import(client, "school", "class-a", [], import_id)
        with self.assertRaises(ValueError):
            save_class_import(client, "school", "class-a", [{"Student code": " "}], import_id)
        client.rpc.return_value.execute.return_value.data = {"import_id": None, "rows": "invalid"}
        with self.assertRaises(ValueError):
            load_class_import(client, "school", "class-a")

    def test_database_audit_mode_disables_client_submitted_events(self):
        client = _FakeClient({
            "audit_events": [
                {"school_id": "school-a", "actor_user_id": "db-user", "occurred_at": "2026-01-01"},
                {"school_id": "school-b", "actor_user_id": "other", "occurred_at": "2026-01-01"},
            ],
        })
        state = {"audit_log": [{"event_id": "untrusted-client-event"}]}
        sync_workspace(client, "school-a", "user-id", state, role="school_admin", audit_mode="database")
        self.assertFalse(any(call["operation"] == "rpc" for call in client.calls))
        events = load_database_audit_events(client, "school-a", "database")
        self.assertEqual([event["actor_user_id"] for event in events], ["db-user"])
        self.assertEqual(client.calls[-1]["filters"], {"school_id": "school-a"})

    def test_audit_mode_requires_trusted_database_support(self):
        client = Mock()
        client.rpc.return_value.execute.return_value.data = "database"
        self.assertEqual(load_audit_mode(client), "database")
        client.rpc.return_value.execute.side_effect = APIError({
            "message": "Function not found", "code": "PGRST202"
        })
        with self.assertRaisesRegex(SupabaseConfigurationError, "202611170001_trusted_database_audit"):
            load_audit_mode(client)
        client.rpc.return_value.execute.side_effect = APIError({
            "message": "Permission denied", "code": "42501"
        })
        with self.assertRaises(APIError):
            load_audit_mode(client)
        client.rpc.return_value.execute.side_effect = None
        client.rpc.return_value.execute.return_value.data = None
        with self.assertRaises(SupabaseConfigurationError):
            load_audit_mode(client)

    def test_class_management_scopes_reads_and_saves_assignments(self):
        client = _FakeClient({
            "classes": [{"school_id": "school-a", "class_id": "c1", "class_name": "A"}],
            "school_memberships": [
                {"school_id": "school-a", "user_id": "teacher", "role": "teacher", "is_active": True},
                {"school_id": "school-a", "user_id": "inactive", "role": "teacher", "is_active": False},
                {"school_id": "school-b", "user_id": "other", "role": "teacher", "is_active": True},
            ],
            "students": [{"school_id": "school-a", "student_code": "S1"}],
            "class_assignments": [
                {"school_id": "school-a", "class_id": "c1", "teacher_id": "teacher"},
            ],
        })

        data = load_class_management(client, "school-a")
        self.assertEqual([row["user_id"] for row in data["teachers"]], ["teacher"])
        self.assertTrue(all(call["filters"].get("school_id") == "school-a" for call in client.calls))
        create_school_class(client, "school-a", " New class ")
        self.assertEqual(client.calls[-1]["payload"]["class_name"], "New class")
        assign_teacher_to_class(client, "school-a", "c1", "teacher")
        self.assertEqual(client.calls[-1]["payload"]["teacher_id"], "teacher")
        remove_teacher_from_class(client, "school-a", "c1", "teacher")
        self.assertEqual(client.calls[-1]["operation"], "delete")
        self.assertEqual(client.calls[-1]["filters"], {
            "school_id": "school-a", "class_id": "c1", "teacher_id": "teacher",
        })
        with self.assertRaises(ValueError):
            remove_teacher_from_class(client, "school-a", "c1", "missing")
        assign_student_to_class(client, "school-a", "S1", "c1")
        self.assertEqual(client.calls[-1]["payload"], {"class_id": "c1"})
        self.assertEqual(client.calls[-1]["filters"], {"school_id": "school-a", "student_code": "S1"})
        with self.assertRaises(ValueError):
            assign_student_to_class(client, "school-a", "missing", "c1")
        with self.assertRaises(ValueError):
            create_school_class(client, "school-a", "  ")

    def test_sync_writes_related_rows_without_submitting_client_audit(self):
        client = _FakeClient()
        state = {
            "clean": pd.DataFrame(
                [
                    {
                        "Student code": "S01",
                        "Student name": "Student One",
                        "Week": 1,
                        "Days scheduled": 5,
                        "Days attended": 4,
                        "Tasks set": 3,
                        "Tasks completed": 2,
                        "Quiz score / 10": 8,
                        "Observation": "",
                        "Next step": "",
                    }
                ]
            ),
            "lesson_records": [
                {
                    "lesson_id": "lesson-1",
                    "class": "Class 5A",
                    "attendance": {"S01": "Present"},
                }
            ],
            "lesson_draft": {},
            "skill_definitions": [{"id": "reading", "name": "Reading"}],
            "skill_assessments": [
                {
                    "id": "a-1",
                    "student_code": "S01",
                    "skill_id": "reading",
                    "lesson_id": "lesson-1",
                    "score": 8,
                    "max_score": 10,
                    "date": "2026-11-15",
                }
            ],
            "participation_log": [
                {
                    "id": "p-1",
                    "student_code": "S01",
                    "student_name": "Student One",
                    "lesson_id": "lesson-1",
                    "skill_id": "reading",
                    "timestamp": "2026-11-15T10:00:00+00:00",
                }
            ],
            "interventions": [
                {"id": "i-1", "student_code": "S01", "skill_id": "reading"}
            ],
            "intervention_checkpoints": [
                {
                    "id": "c-1",
                    "intervention_id": "i-1",
                    "student_code": "S01",
                    "skill_id": "reading",
                    "score": 7,
                    "max_score": 10,
                    "date": "2026-11-15",
                }
            ],
            "question_library": [
                {"id": "q-1", "lesson_id": "lesson-1", "skill_id": "reading"}
            ],
            "audit_log": [
                {
                    "event_id": "e-1",
                    "action": "assessment_created",
                    "status": "success",
                    "entity_type": "assessment",
                    "timestamp": "2026-11-15T10:00:00+00:00",
                    "actor_role": "teacher",
                }
            ],
            "_cloud_previous_skill_ids": ["reading"],
            "_cloud_previous_question_ids": ["q-1"],
            "_cloud_saved_audit_ids": [],
        }

        sync_workspace(client, "school-id", "user-id", state, role="school_admin")
        first_upsert_count = sum(
            call["operation"] == "upsert" for call in client.calls
        )
        sync_workspace(client, "school-id", "user-id", state, role="school_admin")
        second_upsert_count = sum(
            call["operation"] == "upsert" for call in client.calls
        )

        participation = next(
            call for call in client.calls
            if call["table"] == "participation_records"
            and call["operation"] == "upsert"
        )
        self.assertNotIn(
            "student_name", participation["payload"][0]["record_data"]
        )
        question = next(
            call for call in client.calls
            if call["table"] == "bloom_questions"
            and call["operation"] == "upsert"
        )
        self.assertEqual(
            set(question["payload"][0]),
            {"school_id", "record_id", "lesson_id", "skill_id", "record_data", "is_deleted"},
        )
        audit_calls = [
            call for call in client.calls
            if call["operation"] == "rpc"
            and call["name"] == "append_audit_events"
        ]
        self.assertEqual(audit_calls, [])
        self.assertEqual(first_upsert_count, second_upsert_count)
        self.assertEqual(state["_cloud_saved_audit_ids"], [])
        self.assertTrue(
            any(call["table"] == "lesson_attendance" for call in client.calls)
        )
        self.assertTrue(
            any(
                call["table"] == "active_imports"
                and call["operation"] == "upsert"
                for call in client.calls
            )
        )

    def test_invalid_new_import_is_rejected_before_any_write(self):
        client = _FakeClient()
        state = {
            "source_rows": pd.DataFrame([{
                "Student code": "", "Week": 1, "Days scheduled": 5,
                "Days attended": 4, "Tasks set": 3, "Tasks completed": 2,
                "Quiz score / 10": 8, "Observation": "", "Next step": "",
            }]),
            "_cloud_import_requested": True,
        }
        with self.assertRaisesRegex(ValueError, "invalid or duplicate"):
            sync_workspace(client, "school-id", "user-id", state, role="school_admin")
        self.assertEqual(client.calls, [])
        self.assertTrue(state["_cloud_import_requested"])

    def test_legacy_audit_mode_fails_before_any_workspace_write(self):
        client = _FakeClient()
        state = {
            "audit_log": [{
                "event_id": "e-1",
                "action": "report_generated",
                "status": "success",
                "entity_type": "report",
                "timestamp": "2026-11-15T10:00:00+00:00",
            }],
            "_cloud_saved_audit_ids": [],
        }

        with self.assertRaisesRegex(ValueError, "Trusted database audit mode"):
            sync_workspace(client, "school-id", "user-id", state, role="school_admin", audit_mode="legacy")
        self.assertEqual(client.calls, [])
        self.assertEqual(state["_cloud_saved_audit_ids"], [])

    def test_load_restores_names_without_trusting_client_audit_events(self):
        client = _FakeClient(
            {
                "participation_records": [
                    {
                        "school_id": "school-id",
                        "record_data": {
                            "id": "p-1",
                            "student_code": "S01",
                            "lesson_id": "lesson-1",
                        }
                    }
                ],
                "students": [
                    {
                        "school_id": "school-id",
                        "student_code": "S01",
                        "display_name": "Student One",
                    }
                ],
                "audit_events": [
                    {
                        "school_id": "school-id",
                        "event_id": "e-1",
                        "actor_user_id": "user-id",
                        "actor_role": "school_admin",
                        "action": "report_generated",
                        "status": "success",
                        "entity_type": "report",
                        "occurred_at": "2026-11-15T10:00:00+00:00",
                        "record_data": {},
                    }
                ],
            }
        )

        admin_workspace = load_workspace(
            client, "school-id", "user-id", "school_admin"
        )
        self.assertEqual(
            admin_workspace["participation_log"][0]["student_name"],
            "Student One",
        )
        self.assertEqual(admin_workspace["audit_log"], [])
        self.assertFalse(any(c["table"] == "audit_events" for c in client.calls))

    def test_load_uses_only_the_active_import_and_preserves_row_order(self):
        client = _FakeClient(
            {
                "active_imports": [
                    {"school_id": "school-id", "import_id": "batch-1"}
                ],
                "weekly_records": [
                    {
                        "record_id": "row-2",
                        "school_id": "school-id",
                        "import_id": "batch-1",
                        "row_index": 1,
                        "record_data": {"Student code": "S02"},
                    },
                    {
                        "record_id": "row-1",
                        "school_id": "school-id",
                        "import_id": "batch-1",
                        "row_index": 0,
                        "record_data": {"Student code": "S01"},
                    },
                ],
            }
        )

        workspace = load_workspace(client, "school-id", "user-id", "school_admin")

        self.assertEqual(workspace["source_import_id"], "batch-1")
        self.assertEqual(
            [row["Student code"] for row in workspace["source_rows"]],
            ["S01", "S02"],
        )

    def test_fingerprint_changes_only_when_persisted_content_changes(self):
        state = {"lesson_records": [], "audit_log": [], "clean": None}
        before = workspace_fingerprint(state)
        state["_cloud_saved_audit_ids"] = ["ignored"]
        self.assertEqual(before, workspace_fingerprint(state))
        state["audit_log"] = [{"event_id": "session-only"}]
        self.assertEqual(before, workspace_fingerprint(state))
        state["lesson_records"] = [{"lesson_id": "lesson-1"}]
        self.assertNotEqual(before, workspace_fingerprint(state))

    def test_sync_writes_only_the_record_changed_on_this_device(self):
        source_rows = [
            {"Student code": "S01", "Student name": "Student One", "Week": 1}
        ]
        state = {
            "source_rows": pd.DataFrame(source_rows),
            "clean": pd.DataFrame(source_rows),
            "lesson_records": [],
            "lesson_draft": {},
            "participation_log": [],
            "skill_definitions": [{"id": "reading", "name": "Reading"}],
            "skill_assessments": [
                {
                    "id": "a-1",
                    "student_code": "S01",
                    "skill_id": "reading",
                    "lesson_id": "",
                    "score": 8,
                    "max_score": 10,
                    "date": "2026-11-15",
                    "notes": "",
                }
            ],
            "interventions": [],
            "intervention_checkpoints": [],
            "question_library": [],
            "audit_log": [],
            "_cloud_source_fingerprint": source_rows_fingerprint(source_rows),
            "_cloud_previous_skill_ids": ["reading"],
            "_cloud_previous_question_ids": [],
            "_cloud_saved_audit_ids": [],
        }
        state["_cloud_record_hashes"] = workspace_record_fingerprints(
            state, "school-id"
        )
        state["skill_assessments"][0]["notes"] = "Updated note"
        client = _FakeClient()

        sync_workspace(client, "school-id", "user-id", state, role="school_admin")

        self.assertEqual(
            [
                call["table"]
                for call in client.calls
                if call["operation"] == "upsert"
            ],
            ["assessments"],
        )


class CloudSignOutTests(unittest.TestCase):
    def test_blocked_teacher_can_sign_out_without_loading_workspace(self):
        from pathlib import Path
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest

        settings = SimpleNamespace(url="https://invalid.local")
        client = Mock()
        client.auth.get_user.return_value.user = SimpleNamespace(id="synthetic-user")
        with (
            patch.dict("os.environ", {
                "SCHOOLFLOW_STANDARD_MODE": "1",
                "SCHOOLFLOW_SHARED_DEMO": "0",
                "SCHOOLFLOW_LOCAL_DEMO": "0",
            }),
            patch("shared.supabase_backend.read_supabase_settings", return_value=settings),
            patch("shared.supabase_backend.create_supabase_client", return_value=client),
            patch("shared.supabase_backend.load_memberships", return_value=[
                {"school_id": "synthetic-school", "role": "teacher"},
            ]),
            patch("shared.supabase_backend.load_workspace") as load,
        ):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30)
            for key, value in {
                "_supabase_client": client,
                "_supabase_url": settings.url,
                "_supabase_user_id": "synthetic-user",
            }.items():
                app.session_state[key] = value
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Teacher cloud workspaces are disabled" in item.value for item in app.error))
            load.assert_not_called()
            app.button(key="blocked_teacher_sign_out").click().run()
            client.auth.sign_out.assert_called_once()

    def _exercise_sign_out(self, *, save_fails):
        from pathlib import Path
        from unittest.mock import patch

        from httpx import HTTPError
        from streamlit.testing.v1 import AppTest

        settings = SimpleNamespace(url="https://invalid.local")
        client = Mock()
        client.auth.get_user.return_value.user = SimpleNamespace(id="synthetic-user")
        events = []

        def save(*args, **kwargs):
            events.append("save")
            if save_fails:
                raise HTTPError("synthetic save failure")

        client.auth.sign_out.side_effect = lambda: events.append("sign_out")
        with (
            patch.dict("os.environ", {
                "SCHOOLFLOW_STANDARD_MODE": "1",
                "SCHOOLFLOW_SHARED_DEMO": "0",
                "SCHOOLFLOW_LOCAL_DEMO": "0",
            }),
            patch("shared.supabase_backend.read_supabase_settings", return_value=settings),
            patch("shared.supabase_backend.create_supabase_client", return_value=client),
            patch("shared.supabase_backend.load_memberships", return_value=[
                {"school_id": "synthetic-school", "role": "school_admin"},
            ]),
            patch("shared.supabase_backend.workspace_fingerprint", return_value="same") as fingerprint,
            patch("shared.supabase_backend.sync_workspace", side_effect=save),
        ):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30)
            for key, value in {
                "_supabase_client": client,
                "_supabase_url": settings.url,
                "_supabase_user_id": "synthetic-user",
                "_supabase_school_id": "synthetic-school",
                "_cloud_loaded_for": "synthetic-school",
                "_cloud_loaded_role": "school_admin",
                "_cloud_audit_mode": "database",
                "_cloud_last_fingerprint": "same",
                "active_role": "school_admin",
            }.items():
                app.session_state[key] = value
            app.run()
            self.assertFalse(app.exception)
            fingerprint.return_value = "changed"
            app.button(key="supabase_sign_out").click().run()
            self.assertFalse(app.exception)
            if save_fails:
                self.assertEqual(events, ["save"])
                self.assertTrue(any("Cloud save failed" in item.value for item in app.error))
                self.assertFalse(app.success)
                self.assertEqual(app.session_state["_supabase_user_id"], "synthetic-user")
            else:
                self.assertEqual(events, ["save", "sign_out"])

    def test_failed_save_blocks_sign_out(self):
        self._exercise_sign_out(save_fails=True)

    def test_successful_save_precedes_sign_out(self):
        self._exercise_sign_out(save_fails=False)


if __name__ == "__main__":
    unittest.main()
