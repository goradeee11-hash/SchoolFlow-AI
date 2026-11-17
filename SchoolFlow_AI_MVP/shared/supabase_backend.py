"""Optional Supabase configuration, authentication helpers, and workspace storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
import os
import base64
from typing import Any, Mapping, MutableMapping
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pandas as pd
from postgrest.exceptions import APIError

from app_logic import REQUIRED, validate


class SupabaseConfigurationError(ValueError):
    """Raised when Supabase settings are present but incomplete or invalid."""


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    anon_key: str


def read_supabase_settings(
    environ: Mapping[str, str] | None = None,
    secrets: Mapping[str, Any] | None = None,
) -> SupabaseSettings | None:
    """Read public Supabase URL/key from environment variables or Streamlit secrets."""
    environ = os.environ if environ is None else environ
    secrets = {} if secrets is None else secrets

    section = secrets.get("supabase", {})
    if not isinstance(section, Mapping):
        raise SupabaseConfigurationError(
            "The [supabase] secrets section must be a mapping."
        )

    url = str(environ.get("SUPABASE_URL") or section.get("url") or "").strip()
    anon_key = str(
        environ.get("SUPABASE_ANON_KEY") or section.get("anon_key") or ""
    ).strip()
    if not url and not anon_key:
        return None
    if not url or not anon_key:
        raise SupabaseConfigurationError(
            "Both SUPABASE_URL and SUPABASE_ANON_KEY must be configured."
        )
    if not url.startswith("https://"):
        raise SupabaseConfigurationError(
            "SUPABASE_URL must be an HTTPS Supabase project URL."
        )
    if _is_service_role_key(anon_key):
        raise SupabaseConfigurationError(
            "Use the public anon/publishable key; service-role keys are not supported."
        )
    return SupabaseSettings(url=url.rstrip("/"), anon_key=anon_key)


def create_supabase_client(settings: SupabaseSettings):
    """Create an uncached, per-Streamlit-session client using only the public key."""
    if os.environ.get("SCHOOLFLOW_SHARED_DEMO") == "1":
        raise SupabaseConfigurationError("Supabase is disabled in the shared demo.")
    from supabase import create_client

    return create_client(settings.url, settings.anon_key)


def load_memberships(client, user_id: str) -> list[dict]:
    """Return active school memberships visible to the authenticated user."""
    response = (
        client.table("school_memberships")
        .select("school_id,role")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )
    return list(response.data or [])


def load_teaching_assignments(client, school_id: str) -> list[dict]:
    """Load the authenticated teacher's assigned stage/grade/class/subject tuples."""
    data = client.rpc(
        "list_my_teaching_assignments", {"p_school_id": school_id}
    ).execute().data
    fields = (
        "stage_id", "stage_name", "grade_id", "grade_name",
        "class_id", "class_name", "subject_id", "subject_name",
    )
    if not isinstance(data, list) or any(
        not isinstance(row, dict)
        or any(not isinstance(row.get(field), str) or not row[field] for field in fields)
        for row in data
    ):
        raise ValueError("Invalid teaching assignment response.")
    return data


def load_audit_mode(client) -> str:
    """Require the database-generated audit mechanism before opening a workspace."""
    try:
        response = client.rpc("schoolflow_audit_mode", {}).execute()
    except APIError as error:
        if error.code == "PGRST202":
            raise SupabaseConfigurationError(
                "Trusted database auditing is unavailable. Review and apply "
                "202611170001_trusted_database_audit.sql to the target database, "
                "then reload the PostgREST schema cache."
            ) from error
        raise
    if response.data != "database":
        raise SupabaseConfigurationError("Unexpected database audit mode response.")
    return "database"


def load_database_audit_events(client, school_id: str, audit_mode: str) -> list[dict]:
    """Load database audit fields directly, separately from client session events."""
    columns = (
        "event_id,actor_user_id,actor_role,action,status,entity_type,occurred_at"
    )
    if audit_mode == "database":
        columns += ",database_generated,record_data"
    elif audit_mode != "legacy":
        raise ValueError("Unknown audit mode.")
    response = (
        client.table("audit_events")
        .select(columns)
        .eq("school_id", school_id)
        .order("occurred_at", desc=True)
        .limit(2000)
        .execute()
    )
    return list(response.data or [])


def load_class_management(client, school_id: str) -> dict[str, list[dict]]:
    """Load school-scoped records needed to manage class assignments."""
    def rows(table: str, columns: str) -> list[dict]:
        response = (
            client.table(table).select(columns).eq("school_id", school_id).execute()
        )
        return list(response.data or [])

    return {
        "classes": rows("classes", "class_id,class_name"),
        "teachers": [
            row for row in rows("school_memberships", "user_id,role,is_active")
            if row.get("role") == "teacher" and row.get("is_active") is True
        ],
        "assignments": rows("class_assignments", "class_id,teacher_id"),
        "students": rows("students", "student_code,display_name,class_id"),
    }


def load_school_structure(client, school_id: str) -> dict[str, list[dict]]:
    """Load the selected school's structure and subject assignments under RLS."""
    tables = {
        "stages": ("school_stages", "stage_id,stage_name"),
        "grades": ("school_grades", "grade_id,stage_id,grade_name"),
        "classes": ("classes", "class_id,grade_id,class_name"),
        "subjects": ("school_subjects", "subject_id,subject_name"),
        "assignments": (
            "teacher_subject_assignments", "class_id,subject_id,teacher_id"
        ),
        "memberships": ("school_memberships", "user_id,role,is_active"),
        "students": ("students", "student_code,display_name,class_id"),
    }
    result = {}
    for key, (table, columns) in tables.items():
        data = client.table(table).select(columns).eq("school_id", school_id).execute().data
        if not isinstance(data, list) or any(
            not isinstance(row, dict) or any(column not in row for column in columns.split(","))
            for row in data
        ):
            raise ValueError(f"Invalid {key} response.")
        result[key] = data
    return result


def save_school_structure_name(
    client, school_id: str, kind: str, name: str, *,
    record_id: str | None = None, parent_id: str | None = None,
) -> None:
    """Create or rename a stage, grade, class or subject in one school."""
    definitions = {
        "stage": ("school_stages", "stage_id", "stage_name"),
        "grade": ("school_grades", "grade_id", "grade_name"),
        "class": ("classes", "class_id", "class_name"),
        "subject": ("school_subjects", "subject_id", "subject_name"),
    }
    if kind not in definitions:
        raise ValueError("Unknown school structure type.")
    name = name.strip()
    if not name:
        raise ValueError("Name is required.")
    table, id_column, name_column = definitions[kind]
    if record_id is not None:
        if kind == "class":
            raise ValueError("Class renaming requires the classroom workspace integration.")
        result = (
            client.table(table).update({name_column: name})
            .eq("school_id", school_id).eq(id_column, record_id).execute()
        )
        if not result.data:
            raise ValueError("Record was not found or could not be updated.")
        return
    row = {"school_id": school_id, name_column: name}
    if kind in {"grade", "class"}:
        if not parent_id:
            raise ValueError("A parent stage or grade is required.")
        row["stage_id" if kind == "grade" else "grade_id"] = parent_id
    if kind == "class":
        row["class_id"] = str(uuid4())
    if not client.table(table).insert(row).execute().data:
        raise ValueError("Record could not be created.")


def classify_legacy_class(client, school_id: str, class_id: str, grade_id: str) -> None:
    """Classify only a previously unclassified class after administrator review."""
    result = (
        client.table("classes").update({"grade_id": grade_id})
        .eq("school_id", school_id).eq("class_id", class_id).is_("grade_id", "null")
        .execute()
    )
    if not result.data:
        raise ValueError("Class is no longer unclassified or could not be updated.")


def save_teaching_assignment(
    client, school_id: str, class_id: str, subject_id: str, teacher_id: str,
    *, previous: tuple[str, str, str] | None = None,
) -> None:
    """Create or atomically replace an assignment; RLS validates authority."""
    if not all((class_id, subject_id, teacher_id)):
        raise ValueError("Class, subject and teacher are required.")
    values = {"class_id": class_id, "subject_id": subject_id, "teacher_id": teacher_id}
    if previous is None:
        result = client.table("teacher_subject_assignments").insert(
            {"school_id": school_id, **values}
        ).execute()
        if not result.data:
            raise ValueError("Assignment could not be created.")
        return
    result = (
        client.table("teacher_subject_assignments").update(values)
        .eq("school_id", school_id).eq("class_id", previous[0])
        .eq("subject_id", previous[1]).eq("teacher_id", previous[2]).execute()
    )
    if not result.data:
        raise ValueError("Assignment was not found or could not be updated.")


def remove_teaching_assignment(
    client, school_id: str, class_id: str, subject_id: str, teacher_id: str,
) -> None:
    result = (
        client.table("teacher_subject_assignments").delete()
        .eq("school_id", school_id).eq("class_id", class_id)
        .eq("subject_id", subject_id).eq("teacher_id", teacher_id).execute()
    )
    if not result.data:
        raise ValueError("Assignment was not found or could not be removed.")


def create_school_class(client, school_id: str, class_name: str) -> None:
    """Create a class using the same stable identifier as lesson synchronization."""
    class_name = class_name.strip()
    if not class_name:
        raise ValueError("Class name is required.")
    rows, _ = _class_rows(school_id, [{"class": class_name}])
    client.table("classes").insert(rows[0]).execute()


def assign_teacher_to_class(
    client, school_id: str, class_id: str, teacher_id: str
) -> None:
    """Assign a teacher; database permissions and foreign keys enforce authority."""
    client.table("class_assignments").insert({
        "school_id": school_id,
        "class_id": class_id,
        "teacher_id": teacher_id,
    }).execute()


def remove_teacher_from_class(
    client, school_id: str, class_id: str, teacher_id: str
) -> None:
    """Remove an existing assignment without deleting the class or teacher."""
    result = (
        client.table("class_assignments")
        .delete()
        .eq("school_id", school_id)
        .eq("class_id", class_id)
        .eq("teacher_id", teacher_id)
        .execute()
    )
    if not result.data:
        raise ValueError("Assignment was not found or could not be removed.")


def assign_student_to_class(
    client, school_id: str, student_code: str, class_id: str,
    *, only_unclassified: bool = False,
) -> None:
    """Assign an existing student without replacing other student fields."""
    query = (
        client.table("students")
        .update({"class_id": class_id})
        .eq("school_id", school_id)
        .eq("student_code", student_code)
    )
    if only_unclassified:
        query = query.is_("class_id", "null")
    result = query.execute()
    if not result.data:
        raise ValueError("Student was not found or could not be updated.")


def load_class_import(client, school_id: str, class_id: str) -> tuple[str | None, list[dict]]:
    """Load one class's active import through database-enforced authorization."""
    result = client.rpc("load_class_import", {
        "p_school_id": school_id,
        "p_class_id": class_id,
    }).execute().data
    if not isinstance(result, Mapping):
        raise ValueError("Invalid class import response.")
    import_id = result.get("import_id")
    rows = result.get("rows")
    if import_id is not None:
        if not isinstance(import_id, str):
            raise ValueError("Invalid class import identifier.")
        UUID(import_id)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Invalid class import rows.")
    return import_id, rows


def save_class_import(
    client, school_id: str, class_id: str, rows: list[dict],
    expected_import_id: str | None,
) -> str:
    """Atomically replace one class's active import with an optimistic check."""
    if expected_import_id is not None:
        UUID(expected_import_id)
    if not rows:
        raise ValueError("At least one student row is required.")
    normalized = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Every import row must be an object.")
        code = _as_text(row.get("Student code"))
        if not code:
            raise ValueError("Every import row must have a student code.")
        safe_row = _json_safe(row)
        safe_row["Student code"] = code
        normalized.append(safe_row)
    result = client.rpc("save_class_import", {
        "p_school_id": school_id,
        "p_class_id": class_id,
        "p_rows": normalized,
        "p_expected_import_id": expected_import_id,
    }).execute().data
    if not isinstance(result, str):
        raise ValueError("Invalid saved class import identifier.")
    UUID(result)
    return result


def load_workspace(
    client, school_id: str, user_id: str, role: str, *, audit_mode: str = "database"
) -> dict:
    """Load the selected school's persisted entities into app-shaped collections."""
    if audit_mode != "database":
        raise ValueError("Trusted database audit mode is required.")
    if role != "school_admin":
        raise ValueError(
            "Teacher cloud workspaces are disabled until assignment isolation is implemented."
        )
    workspace = {
        "source_rows": [],
        "lesson_records": _load_payloads(client, "lessons", school_id),
        "lesson_draft": {},
        "participation_log": _load_payloads(client, "participation_records", school_id),
        "skill_definitions": _load_payloads(
            client, "skills", school_id, active_only=True
        ),
        "skill_assessments": _load_payloads(client, "assessments", school_id),
        "interventions": _load_payloads(client, "interventions", school_id),
        "intervention_checkpoints": _load_payloads(
            client, "intervention_checkpoints", school_id
        ),
        "question_library": _load_payloads(
            client, "bloom_questions", school_id, active_only=True
        ),
        "audit_log": [],
    }

    active_import_response = (
        client.table("active_imports")
        .select("import_id")
        .eq("school_id", school_id)
        .limit(1)
        .execute()
    )
    active_import_id = (
        active_import_response.data[0].get("import_id")
        if active_import_response.data
        else None
    )
    weekly_response = None
    if active_import_id:
        weekly_response = (
            client.table("weekly_records")
            .select("record_id,row_index,record_data")
            .eq("school_id", school_id)
            .eq("import_id", active_import_id)
            .order("row_index")
            .execute()
        )
    weekly_data = weekly_response.data if weekly_response else []
    workspace["source_import_id"] = active_import_id
    workspace["weekly_record_ids"] = [
        row.get("record_id")
        for row in (weekly_data or [])
        if row.get("record_id")
    ]
    workspace["source_rows"] = [
        _json_safe(row.get("record_data"))
        for row in (weekly_data or [])
    ]

    student_response = (
        client.table("students")
        .select("student_code,display_name")
        .eq("school_id", school_id)
        .execute()
    )
    names = {
        row["student_code"]: row.get("display_name") or ""
        for row in (student_response.data or [])
    }
    for entry in workspace["participation_log"]:
        entry.setdefault("student_name", names.get(entry.get("student_code", ""), ""))

    draft_response = (
        client.table("lesson_drafts")
        .select("record_data")
        .eq("school_id", school_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if draft_response.data:
        workspace["lesson_draft"] = _json_safe(
            draft_response.data[0].get("record_data")
        )

    return workspace


def sync_workspace(
    client,
    school_id: str,
    user_id: str,
    state: MutableMapping[str, Any],
    *,
    role: str,
    audit_mode: str = "database",
) -> None:
    """Upsert changed entities; database triggers record successful changes."""
    if audit_mode != "database":
        raise ValueError("Trusted database audit mode is required.")
    if role != "school_admin":
        raise ValueError(
            "Teacher cloud workspaces are disabled until assignment isolation is implemented."
        )
    clean_rows = _dataframe_records(state.get("clean"))
    source_rows = (
        _dataframe_records(state.get("source_rows"))
        if "source_rows" in state
        else clean_rows
    )
    has_import = "source_rows" in state or state.get("clean") is not None
    import_changed = has_import and (
        source_rows_fingerprint(source_rows) != state.get("_cloud_source_fingerprint")
        or state.get("_cloud_import_requested")
    )
    if import_changed:
        frame = pd.DataFrame(source_rows)
        missing_columns = [column for column in REQUIRED if column not in frame.columns]
        if missing_columns:
            raise ValueError(f"Import is missing required columns: {', '.join(missing_columns)}")
        issues = validate(frame)
        if not issues.empty and issues["Blocking"].any():
            raise ValueError("Import contains invalid or duplicate records; correct the file before saving.")
    student_names = _student_names(source_rows, state)
    lesson_records = list(state.get("lesson_records", []))
    draft = state.get("lesson_draft")
    if (
        isinstance(draft, Mapping)
        and _as_text(draft.get("lesson_id"))
        and not any(
            isinstance(record, Mapping)
            and _as_text(record.get("lesson_id")) == _as_text(draft.get("lesson_id"))
            for record in lesson_records
        )
    ):
        lesson_records.append(draft)
    class_rows, class_ids = _class_rows(
        school_id, lesson_records
    )
    _upsert_changed(
        client,
        "classes",
        class_rows,
        [row["class_id"] for row in class_rows],
        [{"class_name": row["class_name"]} for row in class_rows],
        state,
        "school_id,class_id",
    )

    students = [
        {
            "school_id": school_id,
            "student_code": code,
            "display_name": name or None,
        }
        for code, name in student_names.items()
        if code
    ]
    _upsert_changed(
        client,
        "students",
        students,
        [row["student_code"] for row in students],
        [{"display_name": row["display_name"]} for row in students],
        state,
        "school_id,student_code",
    )

    weekly = []
    if has_import:
        source_fingerprint = source_rows_fingerprint(source_rows)
        if import_changed:
            import_id = _stable_record_id(
                source_rows, namespace=f"{school_id}:import"
            )
            weekly = [
                {
                    "school_id": school_id,
                    "record_id": _stable_record_id(
                        {"import_id": import_id, "position": index},
                        namespace=f"{school_id}:weekly",
                    ),
                    "import_id": import_id,
                    "student_code": _as_text(row.get("Student code")) or None,
                    "week_label": _as_text(row.get("Week")) or f"row-{index}",
                    "row_index": index,
                    "record_data": _json_safe(row),
                }
                for index, row in enumerate(source_rows)
            ]
            _upsert(
                client,
                "import_batches",
                [
                    {
                        "school_id": school_id,
                        "import_id": import_id,
                        "uploaded_by": user_id,
                        "record_count": len(weekly),
                    }
                ],
                "school_id,import_id",
            )
            _upsert(client, "weekly_records", weekly, "school_id,record_id")
            _upsert(
                client,
                "active_imports",
                [
                    {
                        "school_id": school_id,
                        "import_id": import_id,
                        "updated_by": user_id,
                    }
                ],
                "school_id",
            )
            state["_cloud_source_fingerprint"] = source_fingerprint
            state["_cloud_import_requested"] = False

    skills = [
        {
            "school_id": school_id,
            "skill_id": _as_text(record.get("id")),
            "name": _as_text(record.get("name")) or _as_text(record.get("id")),
            "record_data": _json_safe(record),
            "is_active": True,
        }
        for record in state.get("skill_definitions", [])
        if isinstance(record, Mapping) and _as_text(record.get("id"))
    ]
    _upsert_changed(
        client,
        "skills",
        skills,
        [row["skill_id"] for row in skills],
        [
            next(
                record for record in state.get("skill_definitions", [])
                if isinstance(record, Mapping)
                and _as_text(record.get("id")) == row["skill_id"]
            )
            for row in skills
        ],
        state,
        "school_id,skill_id",
    )
    skill_ids = {row["skill_id"] for row in skills}
    _soft_delete_missing(
        client,
        "skills",
        "skill_id",
        state.get("_cloud_previous_skill_ids", []),
        {record["skill_id"] for record in skills},
        school_id,
        "is_active",
    )
    for removed_id in set(state.get("_cloud_previous_skill_ids", [])) - skill_ids:
        state.get("_cloud_record_hashes", {}).get("skills", {}).pop(
            _as_text(removed_id), None
        )

    lessons = []
    attendance = []
    for record in lesson_records:
        if not isinstance(record, Mapping):
            continue
        lesson_id = _as_text(record.get("lesson_id"))
        if not lesson_id:
            continue
        class_name = _as_text(record.get("class"))
        class_id = class_ids.get(class_name)
        lessons.append(
            {
                "school_id": school_id,
                "lesson_id": lesson_id,
                "class_id": class_id,
                "class_name": class_name or None,
                "record_data": _json_safe(record),
            }
        )
        lesson_attendance = record.get("attendance", {})
        if isinstance(lesson_attendance, Mapping):
            for student_code, status in lesson_attendance.items():
                code = _as_text(student_code)
                if code and status is not None:
                    attendance.append(
                        {
                            "school_id": school_id,
                            "lesson_id": lesson_id,
                            "student_code": code,
                            "attendance_status": _as_text(status),
                        }
                    )
    _upsert_changed(
        client,
        "lessons",
        lessons,
        [row["lesson_id"] for row in lessons],
        [
            next(
                record for record in lesson_records
                if isinstance(record, Mapping)
                and _as_text(record.get("lesson_id")) == row["lesson_id"]
            )
            for row in lessons
        ],
        state,
        "school_id,lesson_id",
    )
    attendance_sources = [
        {"attendance_status": row["attendance_status"]}
        for row in attendance
    ]
    _upsert_changed(
        client,
        "lesson_attendance",
        attendance,
        [f"{row['lesson_id']}|{row['student_code']}" for row in attendance],
        attendance_sources,
        state,
        "school_id,lesson_id,student_code",
    )

    participation_records = [
        record
        for record in state.get("participation_log", [])
        if isinstance(record, Mapping)
    ]
    _upsert_changed(
        client,
        "participation_records",
        [
            _related_record(
                school_id,
                record,
                "record_id",
                "participation",
                valid_optional_skill_ids=skill_ids,
            )
            for record in participation_records
        ],
        [
            record.get("id") or record.get("event_id") or _stable_record_id(
                record, namespace=f"{school_id}:participation"
            )
            for record in participation_records
        ],
        participation_records,
        state,
        "school_id,record_id",
    )
    assessment_records = [
        record
        for record in state.get("skill_assessments", [])
        if isinstance(record, Mapping)
    ]
    _upsert_changed(
        client,
        "assessments",
        [
            _related_record(school_id, record, "record_id", "assessment")
            for record in assessment_records
        ],
        [
            record.get("id") or record.get("event_id") or _stable_record_id(
                record, namespace=f"{school_id}:assessment"
            )
            for record in assessment_records
        ],
        assessment_records,
        state,
        "school_id,record_id",
    )
    intervention_records = [
        record
        for record in state.get("interventions", [])
        if isinstance(record, Mapping)
    ]
    _upsert_changed(
        client,
        "interventions",
        [
            _related_record(school_id, record, "record_id", "intervention")
            for record in intervention_records
        ],
        [
            record.get("id") or record.get("event_id") or _stable_record_id(
                record, namespace=f"{school_id}:intervention"
            )
            for record in intervention_records
        ],
        intervention_records,
        state,
        "school_id,record_id",
    )
    checkpoint_records = [
        record
        for record in state.get("intervention_checkpoints", [])
        if isinstance(record, Mapping)
    ]
    _upsert_changed(
        client,
        "intervention_checkpoints",
        [
            _related_record(school_id, record, "record_id", "checkpoint")
            for record in checkpoint_records
        ],
        [
            record.get("id") or record.get("event_id") or _stable_record_id(
                record, namespace=f"{school_id}:checkpoint"
            )
            for record in checkpoint_records
        ],
        checkpoint_records,
        state,
        "school_id,record_id",
    )

    question_records = [
        record
        for record in state.get("question_library", [])
        if isinstance(record, Mapping)
    ]
    questions = [
        {
            **_related_record(
                school_id,
                record,
                "record_id",
                "question",
                valid_optional_skill_ids=skill_ids,
            ),
            "is_deleted": False,
        }
        for record in question_records
    ]
    _upsert_changed(
        client,
        "bloom_questions",
        questions,
        [row["record_id"] for row in questions],
        question_records,
        state,
        "school_id,record_id",
    )
    _soft_delete_missing(
        client,
        "bloom_questions",
        "record_id",
        state.get("_cloud_previous_question_ids", []),
        {record["record_id"] for record in questions},
        school_id,
        "is_deleted",
        deleted_value=True,
    )
    current_question_ids = {row["record_id"] for row in questions}
    for removed_id in set(state.get("_cloud_previous_question_ids", [])) - current_question_ids:
        state.get("_cloud_record_hashes", {}).get("bloom_questions", {}).pop(
            _as_text(removed_id), None
        )

    if isinstance(draft, Mapping) and _as_text(draft.get("lesson_id")):
        _upsert_changed(
            client,
            "lesson_drafts",
            [
                {
                    "school_id": school_id,
                    "user_id": user_id,
                    "lesson_id": _as_text(draft.get("lesson_id")),
                    "record_data": _json_safe(draft),
                }
            ],
            ["current"],
            [draft],
            state,
            "school_id,user_id",
        )
    elif "current" in state.get("_cloud_record_hashes", {}).get(
        "lesson_drafts", {}
    ):
        (
            client.table("lesson_drafts")
            .delete()
            .eq("school_id", school_id)
            .eq("user_id", user_id)
            .execute()
        )
        state["_cloud_record_hashes"]["lesson_drafts"].pop("current", None)

    state["_cloud_previous_skill_ids"] = [row["skill_id"] for row in skills]
    state["_cloud_previous_question_ids"] = [
        row["record_id"] for row in questions
    ]


def workspace_fingerprint(state: Mapping[str, Any]) -> str:
    """Return a stable digest for persisted state, excluding backend bookkeeping."""
    data = {
        key: _json_safe(state.get(key))
        for key in (
            "lesson_records",
            "lesson_draft",
            "participation_log",
            "skill_definitions",
            "skill_assessments",
            "interventions",
            "intervention_checkpoints",
            "question_library",
        )
    }
    data["import_requested"] = bool(state.get("_cloud_import_requested"))
    data["source_rows"] = (
        _dataframe_records(state.get("source_rows"))
        if "source_rows" in state
        else _dataframe_records(state.get("clean"))
    )
    encoded = json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def workspace_record_fingerprints(
    state: Mapping[str, Any], school_id: str = ""
) -> dict[str, dict[str, str]]:
    """Build per-record baselines so a device only writes records it changed."""
    baseline: dict[str, dict[str, str]] = {}

    def add(table: str, record_id: Any, source: Any) -> None:
        key = _as_text(record_id)
        if key:
            baseline.setdefault(table, {})[key] = _fingerprint(source)

    records = list(state.get("lesson_records", []))
    draft = state.get("lesson_draft")
    if isinstance(draft, Mapping) and _as_text(draft.get("lesson_id")):
        if not any(
            isinstance(record, Mapping)
            and _as_text(record.get("lesson_id")) == _as_text(draft.get("lesson_id"))
            for record in records
        ):
            records.append(draft)

    classes, _class_ids = _class_rows(school_id, records)
    for row in classes:
        add("classes", row["class_id"], {"class_name": row["class_name"]})
    for code, name in _student_names(
        _dataframe_records(state.get("source_rows"))
        if "source_rows" in state
        else _dataframe_records(state.get("clean")),
        state,
    ).items():
        add("students", code, {"display_name": name or None})

    for record in state.get("skill_definitions", []):
        if isinstance(record, Mapping):
            add("skills", record.get("id"), record)
    for record in records:
        if isinstance(record, Mapping):
            lesson_id = _as_text(record.get("lesson_id"))
            if lesson_id:
                add("lessons", lesson_id, record)
                attendance = record.get("attendance", {})
                if isinstance(attendance, Mapping):
                    for student_code, status in attendance.items():
                        add(
                            "lesson_attendance",
                            f"{lesson_id}|{_as_text(student_code)}",
                            {"attendance_status": _as_text(status)},
                        )
    for collection, table in (
        ("participation_log", "participation_records"),
        ("skill_assessments", "assessments"),
        ("interventions", "interventions"),
        ("intervention_checkpoints", "intervention_checkpoints"),
        ("question_library", "bloom_questions"),
    ):
        id_namespace = {
            "participation_records": "participation",
            "assessments": "assessment",
            "interventions": "intervention",
            "intervention_checkpoints": "checkpoint",
            "bloom_questions": "question",
        }[table]
        for record in state.get(collection, []):
            if isinstance(record, Mapping):
                record_id = (
                    record.get("id")
                    or record.get("event_id")
                    or _stable_record_id(
                        record, namespace=f"{school_id}:{id_namespace}"
                    )
                )
                add(table, record_id, record)
    if isinstance(draft, Mapping) and _as_text(draft.get("lesson_id")):
        add("lesson_drafts", "current", draft)
    return baseline


def source_rows_fingerprint(rows: list[dict]) -> str:
    encoded = json.dumps(
        _json_safe(rows),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load_payloads(
    client,
    table: str,
    school_id: str,
    active_only: bool = False,
) -> list[dict]:
    query = client.table(table).select("record_data")
    query = query.eq("school_id", school_id)
    if active_only:
        active_column = "is_active" if table == "skills" else "is_deleted"
        active_value = True if table == "skills" else False
        query = query.eq(active_column, active_value)
    response = query.execute()
    return [
        _json_safe(row.get("record_data"))
        for row in (response.data or [])
        if isinstance(row.get("record_data"), Mapping)
    ]


def _related_record(
    school_id: str,
    record: Mapping[str, Any],
    id_key: str,
    namespace: str,
    valid_optional_skill_ids: set[str] | None = None,
) -> dict:
    record_id = _as_text(record.get("id") or record.get("event_id"))
    if not record_id:
        record_id = _stable_record_id(record, namespace=f"{school_id}:{namespace}")
    safe_record = dict(record)
    if namespace == "participation":
        safe_record.pop("student_name", None)
    result = {
        "school_id": school_id,
        id_key: record_id,
        "skill_id": _as_text(record.get("skill_id")) or None,
        "record_data": _json_safe(safe_record),
    }
    if namespace != "question":
        result["student_code"] = _as_text(record.get("student_code"))
    if (
        namespace in {"participation", "question"}
        and result["skill_id"] is not None
        and valid_optional_skill_ids is not None
        and result["skill_id"] not in valid_optional_skill_ids
    ):
        result["skill_id"] = None
    if namespace == "participation":
        result["lesson_id"] = _as_text(record.get("lesson_id"))
        result["occurred_at"] = _as_text(record.get("timestamp")) or None
    elif namespace == "assessment":
        result["lesson_id"] = _as_text(record.get("lesson_id")) or None
        result["assessment_date"] = _as_text(record.get("date")) or None
        result["score"] = float(record.get("score", 0))
        result["max_score"] = float(record.get("max_score", 1))
    elif namespace == "intervention":
        pass
    elif namespace == "checkpoint":
        result["intervention_id"] = _as_text(record.get("intervention_id"))
        result["checkpoint_date"] = _as_text(record.get("date")) or None
        result["score"] = float(record.get("score", 0))
        result["max_score"] = float(record.get("max_score", 1))
    elif namespace == "question":
        result["lesson_id"] = _as_text(record.get("lesson_id")) or None
    return result


def _class_rows(school_id: str, lesson_records: Any) -> tuple[list[dict], dict[str, str]]:
    names = {
        _as_text(record.get("class"))
        for record in lesson_records
        if isinstance(record, Mapping) and _as_text(record.get("class"))
    }
    ids = {
        name: f"class-{uuid5(NAMESPACE_URL, f'{school_id}:{name}').hex}"
        for name in names
    }
    return (
        [
            {
                "school_id": school_id,
                "class_id": class_id,
                "class_name": name,
            }
            for name, class_id in ids.items()
        ],
        ids,
    )


def _student_names(clean_rows: list[dict], state: Mapping[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in clean_rows:
        code = _as_text(row.get("Student code"))
        if code:
            names[code] = _as_text(row.get("Student name"))
    for collection in (
        "participation_log",
        "skill_assessments",
        "interventions",
        "intervention_checkpoints",
    ):
        for record in state.get(collection, []):
            if isinstance(record, Mapping):
                code = _as_text(record.get("student_code"))
                if code:
                    names.setdefault(code, _as_text(record.get("student_name")))
    lesson_records = list(state.get("lesson_records", []))
    draft = state.get("lesson_draft")
    if isinstance(draft, Mapping):
        lesson_records.append(draft)
    for lesson in lesson_records:
        if not isinstance(lesson, Mapping):
            continue
        attendance = lesson.get("attendance", {})
        if isinstance(attendance, Mapping):
            for student_code in attendance:
                code = _as_text(student_code)
                if code:
                    names.setdefault(code, "")
    return names


def _soft_delete_missing(
    client,
    table: str,
    id_column: str,
    previous_ids: Any,
    current_ids: set[str],
    school_id: str,
    flag_column: str,
    deleted_value: bool = False,
) -> None:
    for record_id in set(previous_ids or []) - current_ids:
        (
            client.table(table)
            .update({flag_column: deleted_value})
            .eq("school_id", school_id)
            .eq(id_column, record_id)
            .execute()
        )


def _upsert(client, table: str, rows: list[dict], conflict: str) -> None:
    if rows:
        client.table(table).upsert(rows, on_conflict=conflict).execute()


def _upsert_changed(
    client,
    table: str,
    rows: list[dict],
    keys: list[str],
    sources: list[Any],
    state: MutableMapping[str, Any],
    conflict: str,
) -> None:
    record_hashes = state.setdefault("_cloud_record_hashes", {})
    table_hashes = record_hashes.setdefault(table, {})
    changed_rows = []
    changed_hashes = {}
    for row, key, source in zip(rows, keys, sources):
        record_key = _as_text(key)
        digest = _fingerprint(source)
        if table_hashes.get(record_key) != digest:
            changed_rows.append(row)
            changed_hashes[record_key] = digest
    _upsert(client, table, changed_rows, conflict)
    table_hashes.update(changed_hashes)


def _dataframe_records(frame: Any) -> list[dict]:
    if frame is None:
        return []
    to_dict = getattr(frame, "to_dict", None)
    if not callable(to_dict):
        return []
    return [_json_safe(row) for row in to_dict(orient="records")]


def _stable_record_id(record: Any, namespace: str) -> str:
    encoded = json.dumps(
        _json_safe(record), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return uuid5(NAMESPACE_URL, f"{namespace}:{encoded}").hex


def _fingerprint(record: Any) -> str:
    encoded = json.dumps(
        _json_safe(record), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _as_text(value: Any) -> str:
    if value is None or type(value).__name__ in {"NAType", "NaTType"}:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return str(value).strip()


def _is_service_role_key(key: str) -> bool:
    lowered = key.lower()
    if "service_role" in lowered or lowered.startswith("sb_secret_"):
        return True
    parts = key.split(".")
    if len(parts) != 3:
        return False
    try:
        payload = parts[1] + ("=" * (-len(parts[1]) % 4))
        claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(claims, dict) and claims.get("role") == "service_role"


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if type(value).__name__ in {"NAType", "NaTType"}:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except (ValueError, TypeError):
            pass
    return value
