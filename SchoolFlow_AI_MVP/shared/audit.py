"""
shared/audit.py
---------------
Centralized Audit Log — SchoolFlow AI (Task 11).

Design rules
------------
* No Streamlit imports — fully testable offline.
* Event summaries are selected from fixed, non-personal templates.
* Extra metadata is limited to a small allowlist of aggregate counts and roles.
* Timestamps are ISO 8601 strings normalized to UTC.
* Actor identity is only the unverified local demo role.
* log_event() returns a new list; this in-memory list is NOT tamper-proof or
  durable storage.
* Filtering is pure Python — no database required.

Event structure (dict)
----------------------
  event_id    : str   — unique identifier (uuid4 hex)
  timestamp   : str   — ISO 8601 datetime string
  actor_id    : str   — same unverified demo role as actor_role
  actor_role  : str   — ROLE_TEACHER / ROLE_SCHOOL_ADMIN / "unknown"
  action      : str   — one of ACTION_* constants below
  entity_type : str   — one of ENTITY_* constants below
  entity_id   : str   — empty; entity identifiers are not stored
  status      : str   — STATUS_SUCCESS / STATUS_FAILURE
  summary     : str   — human-readable, safe (no raw PII/secrets)
  changed_fields: list[str] — field names that changed (may be empty)
  extra       : dict  — optional safe metadata (no secrets)
"""

from __future__ import annotations

import uuid
import re
from collections.abc import MutableMapping
from datetime import date, datetime, timezone
from copy import deepcopy

from shared.time_utils import timestamp_to_utc


def reset_page_audit_dedupe_state(
    session_state: MutableMapping,
    current_page: str,
    actor_role: object,
) -> bool:
    """Reset page-entry audit guards only when page or role context changes."""
    current_context = (current_page, actor_role)
    if session_state.get("_audit_page_context") == current_context:
        return False

    for key in (
        "_audit_denied_context",
        "_audit_denied_attempt",
        "_audit_log_page_access_logged",
    ):
        session_state.pop(key, None)
    session_state["_audit_page_context"] = current_context
    return True

# ---------------------------------------------------------------------------
# Action constants
# ---------------------------------------------------------------------------
ACTION_DATA_IMPORT          = "data_import"
ACTION_REPORT_GENERATED     = "report_generated"
ACTION_ASSESSMENT_CREATED   = "assessment_created"
ACTION_ASSESSMENT_UPDATED   = "assessment_updated"
ACTION_INTERVENTION_CREATED = "intervention_created"
ACTION_INTERVENTION_UPDATED = "intervention_updated"
ACTION_LESSON_STARTED       = "lesson_started"
ACTION_LESSON_ENDED         = "lesson_ended"
ACTION_LESSON_PLAN_UPDATED  = "lesson_plan_updated"
ACTION_PARTICIPATION_LOGGED = "participation_logged"
ACTION_SKILL_CREATED        = "skill_created"
ACTION_SKILL_REMOVED        = "skill_removed"
ACTION_ROLE_CHANGED         = "role_changed"
ACTION_PERMISSION_CHECK     = "permission_check"
ACTION_PAGE_ACCESS          = "page_access"
ACTION_PROFILE_VIEWED       = "profile_viewed"
ACTION_CHECKPOINT_ADDED     = "checkpoint_added"
ACTION_REPORT_DOWNLOADED   = "report_downloaded"

#: Complete set of defined actions
ALL_ACTIONS: frozenset[str] = frozenset({
    ACTION_DATA_IMPORT,
    ACTION_REPORT_GENERATED,
    ACTION_ASSESSMENT_CREATED,
    ACTION_ASSESSMENT_UPDATED,
    ACTION_INTERVENTION_CREATED,
    ACTION_INTERVENTION_UPDATED,
    ACTION_LESSON_STARTED,
    ACTION_LESSON_ENDED,
    ACTION_LESSON_PLAN_UPDATED,
    ACTION_PARTICIPATION_LOGGED,
    ACTION_SKILL_CREATED,
    ACTION_SKILL_REMOVED,
    ACTION_ROLE_CHANGED,
    ACTION_PERMISSION_CHECK,
    ACTION_PAGE_ACCESS,
    ACTION_PROFILE_VIEWED,
    ACTION_CHECKPOINT_ADDED,
    ACTION_REPORT_DOWNLOADED,
})

_SAFE_SUMMARIES: dict[str, str] = {
    ACTION_DATA_IMPORT: "Data import completed",
    ACTION_REPORT_GENERATED: "Report generated",
    ACTION_REPORT_DOWNLOADED: "Report downloaded",
    ACTION_ASSESSMENT_CREATED: "Assessment created",
    ACTION_ASSESSMENT_UPDATED: "Assessment updated",
    ACTION_INTERVENTION_CREATED: "Intervention created",
    ACTION_INTERVENTION_UPDATED: "Intervention updated",
    ACTION_LESSON_STARTED: "Lesson started",
    ACTION_LESSON_ENDED: "Lesson ended",
    ACTION_LESSON_PLAN_UPDATED: "Lesson plan updated",
    ACTION_PARTICIPATION_LOGGED: "Participation recorded",
    ACTION_SKILL_CREATED: "Skill created",
    ACTION_SKILL_REMOVED: "Skill removed",
    ACTION_ROLE_CHANGED: "Demo role changed",
    ACTION_PERMISSION_CHECK: "Permission check denied",
    ACTION_PAGE_ACCESS: "Audit log page accessed",
    ACTION_PROFILE_VIEWED: "Student profile viewed",
    ACTION_CHECKPOINT_ADDED: "Intervention checkpoint added",
}


def safe_event_summary(action: object) -> str:
    """Return a fixed, non-personal summary for a known action."""
    if not isinstance(action, str):
        return "Unrecognized audit event"
    return _SAFE_SUMMARIES.get(action, "Unrecognized audit event")


def sanitize_audit_log(audit_log: list[dict]) -> list[dict]:
    """Rebuild legacy session events using only validated, non-personal fields."""
    if not isinstance(audit_log, list):
        raise TypeError("audit_log must be a list.")

    sanitized = []
    for event in audit_log:
        if not isinstance(event, dict):
            raise ValueError("audit log contains a non-event record.")

        action_value = event.get("action")
        action = action_value if isinstance(action_value, str) and action_value in ALL_ACTIONS else "unknown"
        role_value = event.get("actor_role")
        role = role_value if isinstance(role_value, str) and role_value in _ACTOR_ROLES else "unknown"
        status_value = event.get("status")
        status = status_value if isinstance(status_value, str) and status_value in ALL_STATUSES else "unknown"
        entity_type_value = event.get("entity_type")
        entity_type = (
            entity_type_value
            if isinstance(entity_type_value, str) and entity_type_value in ALL_ENTITY_TYPES
            else ENTITY_SYSTEM
        )
        raw_fields = event.get("changed_fields")
        changed_fields = (
            [field for field in raw_fields if isinstance(field, str) and field in _SAFE_CHANGED_FIELDS]
            if isinstance(raw_fields, list)
            else []
        )
        raw_extra = event.get("extra")
        extra = {}
        if isinstance(raw_extra, dict):
            for key, value in raw_extra.items():
                try:
                    extra.update(_safe_extra({key: value}))
                except ValueError:
                    continue

        event_id_value = event.get("event_id")
        event_id = (
            event_id_value.lower()
            if isinstance(event_id_value, str)
            and re.fullmatch(r"[0-9a-fA-F]{12,32}", event_id_value)
            else uuid.uuid4().hex
        )
        timestamp = _event_datetime(event.get("timestamp", "")).isoformat(timespec="seconds")
        sanitized.append({
            "event_id": event_id,
            "timestamp": timestamp,
            "actor_id": role,
            "actor_role": role,
            "action": action,
            "entity_type": entity_type,
            "entity_id": "",
            "status": status,
            "summary": safe_event_summary(action),
            "changed_fields": changed_fields,
            "extra": extra,
        })
    return sanitized


# ---------------------------------------------------------------------------
# Entity type constants
# ---------------------------------------------------------------------------
ENTITY_STUDENT       = "student"
ENTITY_ASSESSMENT    = "assessment"
ENTITY_INTERVENTION  = "intervention"
ENTITY_LESSON        = "lesson"
ENTITY_SKILL         = "skill"
ENTITY_ROLE          = "role"
ENTITY_DATA_FILE     = "data_file"
ENTITY_REPORT        = "report"
ENTITY_PARTICIPATION = "participation"
ENTITY_CHECKPOINT    = "checkpoint"
ENTITY_SYSTEM        = "system"
ENTITY_PAGE          = "page"

ALL_ENTITY_TYPES: frozenset[str] = frozenset({
    ENTITY_STUDENT,
    ENTITY_ASSESSMENT,
    ENTITY_INTERVENTION,
    ENTITY_LESSON,
    ENTITY_SKILL,
    ENTITY_ROLE,
    ENTITY_DATA_FILE,
    ENTITY_REPORT,
    ENTITY_PARTICIPATION,
    ENTITY_CHECKPOINT,
    ENTITY_SYSTEM,
    ENTITY_PAGE,
})

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------
STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"

ALL_STATUSES: frozenset[str] = frozenset({STATUS_SUCCESS, STATUS_FAILURE})
_ACTOR_ROLES = frozenset({"teacher", "school_admin", "demo_reviewer", "unknown"})
_SAFE_EXTRA_KEYS = frozenset({
    "record_count",
    "issue_count",
    "role_from",
    "role_to",
})
_SAFE_CHANGED_FIELDS = frozenset({
    "active_role",
    "status",
    "mtss_tier",
    "teacher_notes",
    "gagne_plan",
    "score",
    "max_score",
    "notes",
    "date",
    "skill_id",
})


def _normalise_timestamp(value: str | None = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not isinstance(value, str):
        raise ValueError("audit timestamp must be an ISO 8601 string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("audit timestamp must be valid ISO 8601.") from exc
    if parsed.utcoffset() is None:
        raise ValueError("audit timestamp must include a timezone.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _event_datetime(value: str) -> datetime:
    try:
        return timestamp_to_utc(value)
    except ValueError as exc:
        raise ValueError("audit log contains an invalid timestamp.") from exc


def _safe_extra(extra: dict | None) -> dict:
    if extra is None:
        return {}
    if not isinstance(extra, dict):
        raise ValueError("audit extra metadata must be a dict.")
    if any(not isinstance(key, str) or key not in _SAFE_EXTRA_KEYS for key in extra):
        raise ValueError("audit extra metadata contains a non-allowlisted field.")

    safe = {}
    for key, value in extra.items():
        if key in {"record_count", "issue_count"}:
            if type(value) is not int or value < 0:
                raise ValueError(f"audit extra {key} must be a non-negative integer.")
        elif not isinstance(value, str) or value not in {"teacher", "school_admin", "demo_reviewer"}:
            raise ValueError(f"audit extra {key} must be a defined demo role.")
        safe[key] = value
    return safe

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def new_event(
    action: str,
    actor_role: str,
    entity_type: str = ENTITY_SYSTEM,
    entity_id: str = "",
    status: str = STATUS_SUCCESS,
    summary: str = "",
    actor_id: str = "",
    changed_fields: list[str] | None = None,
    extra: dict | None = None,
    _now: str | None = None,
) -> dict:
    """
    Build a new audit event dict.

    Parameters
    ----------
    action        : One of the ACTION_* constants.
    actor_role    : Role of the performing actor (ROLE_TEACHER etc.).
    entity_type   : Type of entity affected (ENTITY_* constant).
    entity_id     : Must be empty; entity identifiers are not stored.
    status        : STATUS_SUCCESS or STATUS_FAILURE.
    summary       : Must be the fixed safe summary for this action. If omitted,
                    the fixed summary is selected automatically.
    actor_id      : Optional duplicate of actor_role; identity is not verified.
    changed_fields: List of field names that changed (for update events).
    extra         : Optional safe metadata dict.
    _now          : ISO timestamp override (for testing).

    Returns
    -------
    A new event dict. The in-memory record is not tamper-proof.

    Raises
    ------
    ValueError if any field is invalid or could carry personal data.
    """
    if not isinstance(action, str) or action not in ALL_ACTIONS:
        raise ValueError("audit.new_event: action must be a defined audit action.")
    if not isinstance(summary, str):
        raise ValueError("audit.new_event: summary must be a string.")
    if summary and summary.strip() != _SAFE_SUMMARIES[action]:
        raise ValueError("audit.new_event: summary must use the fixed safe template.")

    if actor_role is not None and not isinstance(actor_role, str):
        raise ValueError("audit.new_event: actor_role must be a string.")
    role = (actor_role or "unknown").strip()
    if role not in _ACTOR_ROLES:
        raise ValueError("audit.new_event: actor_role must be a defined demo role.")
    if not isinstance(entity_type, str):
        raise ValueError("audit.new_event: entity_type must be a string.")
    if actor_id is not None and not isinstance(actor_id, str):
        raise ValueError("audit.new_event: actor_id must be a string.")
    if actor_id and actor_id.strip() != role:
        raise ValueError("audit.new_event: actor_id must not identify a person.")

    if entity_type not in ALL_ENTITY_TYPES:
        raise ValueError("audit.new_event: entity_type must be a defined entity type.")
    if not isinstance(entity_id, str):
        raise ValueError("audit.new_event: entity_id must be a string.")
    if entity_id.strip():
        raise ValueError("audit.new_event: entity_id must be empty.")
    if not isinstance(status, str) or status not in ALL_STATUSES:
        raise ValueError("audit.new_event: status must be success or failure.")

    if changed_fields is not None and not isinstance(changed_fields, list):
        raise ValueError("audit.new_event: changed_fields must be a list.")
    safe_fields = list(changed_fields) if changed_fields else []
    if any(not isinstance(field, str) or field not in _SAFE_CHANGED_FIELDS
           for field in safe_fields):
        raise ValueError("audit.new_event: changed_fields contains an unsafe field.")

    return {
        "event_id":      uuid.uuid4().hex,
        "timestamp":     _normalise_timestamp(_now),
        "actor_id":      role,
        "actor_role":    role,
        "action":        action,
        "entity_type":   entity_type,
        "entity_id":     "",
        "status":        status,
        "summary":       _SAFE_SUMMARIES[action],
        "changed_fields": safe_fields,
        "extra":         _safe_extra(extra),
    }


def log_event(
    audit_log: list[dict],
    action: str,
    actor_role: str,
    entity_type: str = ENTITY_SYSTEM,
    entity_id: str = "",
    status: str = STATUS_SUCCESS,
    summary: str = "",
    actor_id: str = "",
    changed_fields: list[str] | None = None,
    extra: dict | None = None,
    _now: str | None = None,
) -> list[dict]:
    """
    Return a new list with the event appended. Does NOT mutate audit_log.

    Parameters mirror new_event().

    Returns a deep-copied list with the new event appended.

    Invalid input raises ValueError; audit failures are never silently skipped.
    """
    if not isinstance(audit_log, list):
        raise TypeError("audit_log must be a list.")
    event = new_event(
        action=action,
        actor_role=actor_role,
        entity_type=entity_type,
        entity_id=entity_id,
        status=status,
        summary=summary,
        actor_id=actor_id,
        changed_fields=changed_fields,
        extra=extra,
        _now=_now,
    )
    return sanitize_audit_log(audit_log) + [event]


def get_audit_events(
    audit_log: list[dict],
    actor_role: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    status: str | None = None,
    date_from: str | None = None,   # ISO date prefix e.g. "2026-11-01"
    date_to: str | None = None,     # ISO date prefix e.g. "2026-11-30"
) -> list[dict]:
    """
    Return a filtered, deep-copied list of audit events.

    All filter parameters are optional; omit to return all events.
    Results are sorted oldest-first (ascending by timestamp).
    Each returned dict is a *copy* — mutating it does not affect the log.

    Parameters
    ----------
    audit_log   : The source list of audit event dicts.
    actor_role  : Filter by actor_role (exact match).
    actor_id    : Filter by actor_id (exact match).
    action      : Filter by action (exact match).
    entity_type : Filter by entity_type (exact match).
    entity_id   : Filter by entity_id (exact match).
    status      : Filter by status (exact match).
    date_from   : Inclusive UTC date lower bound (YYYY-MM-DD).
    date_to     : Inclusive UTC date upper bound (YYYY-MM-DD).
    """
    try:
        from_day = date.fromisoformat(date_from) if date_from else None
        to_day = date.fromisoformat(date_to) if date_to else None
        if from_day and from_day.isoformat() != date_from:
            raise ValueError("date_from must use YYYY-MM-DD.")
        if to_day and to_day.isoformat() != date_to:
            raise ValueError("date_to must use YYYY-MM-DD.")
    except (TypeError, ValueError) as exc:
        raise ValueError("audit date filters must use YYYY-MM-DD.") from exc

    result = []
    for ev in sanitize_audit_log(audit_log):
        event_dt = _event_datetime(ev.get("timestamp", ""))
        event_day = event_dt.date()
        if actor_role  and ev.get("actor_role")  != actor_role:
            continue
        if actor_id    and ev.get("actor_id")    != actor_id:
            continue
        if action      and ev.get("action")      != action:
            continue
        if entity_type and ev.get("entity_type") != entity_type:
            continue
        if entity_id   and ev.get("entity_id")   != entity_id:
            continue
        if status      and ev.get("status")      != status:
            continue
        if from_day and event_day < from_day:
            continue
        if to_day and event_day > to_day:
            continue
        copied = deepcopy(ev)
        copied["timestamp"] = event_dt.isoformat(timespec="seconds")
        result.append(copied)

    return sorted(result, key=lambda e: _event_datetime(e.get("timestamp", "")))


def audit_summary_stats(audit_log: list[dict]) -> dict:
    """
    Return lightweight summary statistics for the audit log.

    Returns
    -------
    dict:
        "total"    : int — total events
        "success"  : int — STATUS_SUCCESS events
        "failure"  : int — STATUS_FAILURE events
        "by_action": dict[action → int]
        "by_role"  : dict[role → int]
    """
    safe_events = sanitize_audit_log(audit_log)
    total = len(safe_events)
    success = sum(1 for e in safe_events if e.get("status") == STATUS_SUCCESS)
    failure = sum(1 for e in safe_events if e.get("status") == STATUS_FAILURE)

    by_action: dict[str, int] = {}
    by_role:   dict[str, int] = {}
    for ev in safe_events:
        a = ev.get("action", "unknown")
        r = ev.get("actor_role", "unknown")
        by_action[a] = by_action.get(a, 0) + 1
        by_role[r]   = by_role.get(r, 0) + 1

    return {
        "total":     total,
        "success":   success,
        "failure":   failure,
        "by_action": by_action,
        "by_role":   by_role,
    }
