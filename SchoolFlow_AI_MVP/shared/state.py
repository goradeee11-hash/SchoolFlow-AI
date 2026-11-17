"""
shared/state.py
---------------
Session-state initialisation for SchoolFlow AI.

Session state is the UI working cache. When Supabase is configured, app.py
hydrates and synchronizes the persistent school workspace through the backend
module; without it, data remains local to the current Streamlit session.

Usage (call once early in app.py, AFTER st.set_page_config):
    from shared.state import init_state
    init_state()

Design notes
------------
* init_state() uses the same `if key not in st.session_state` guard that
  app.py uses today — it will NEVER overwrite a value the user has already
  set during the session.
* Keys that are only written after the user clicks "Analyse Data"
  (clean / summary / weekly / has_name / issues) are intentionally NOT
  initialised here.  The rest of app.py detects their presence with
  `if "summary" in st.session_state`.
* The "page" key stores the active page route and defaults to "dashboard".
* Ordering is intentional: "ui_lang" must be first because
  _L / _IS_AR / _DIR in app.py depend on it immediately after init_state().
"""

_DEFAULTS: dict = {
    # Ordering matters: ui_lang first (used by T() immediately after)
    "ui_lang":           "en",
    "page":              "dashboard",
    # Role-based access control (Task 10)
    # Default to "teacher" so existing workflows are unaffected.
    # This is a local/demo role context — NOT production authentication.
    # Replace this key's value with a trusted identity provider in production.
    "active_role":       "teacher",
    "online_ai_enabled": False,
    "chat_history":      None,          # see _MUTABLE below
    "assistant_mode":    "offline",
    # Lesson Workspace (Task 1)
    "lesson_active":     False,
    "lesson_draft":      None,          # see _MUTABLE below
    "lesson_records":    None,          # see _MUTABLE below
    # Class Participation (Task 2)
    "participation_log": None,          # see _MUTABLE below
    # Recommendation Engine (Task 3)
    "rec_skipped":      None,           # see _MUTABLE below
    "rec_current":      None,           # see _MUTABLE below
    "rec_skill_input":  "",
    # Student Profile (Task 5)
    "profile_student_code": "",
    # Skills & Academic Progress (Task 6)
    "skill_definitions":          None,   # see _MUTABLE below
    "skill_assessments":          None,   # see _MUTABLE below
    "skill_progress_student_code": "",
    # Interventions & Recommendations (Task 7)
    "interventions":              None,   # see _MUTABLE below
    "intervention_checkpoints":   None,   # see _MUTABLE below
    "intervention_student_code":  "",
    # Bloom's Taxonomy & Question Library (Task 8)
    "question_library":           None,   # see _MUTABLE below
    # Gagné's Nine Events (Task 9) — stored inside lesson_draft["gagne_plan"]
    # No new top-level keys needed; the plan is a sub-key of lesson_draft.
    # Audit Log (Task 11)
    "audit_log": None,          # local cache; Supabase persists admin-visible events
}

# Keys whose default values are mutable (list/dict) — built fresh each call
# to avoid the Python "mutable default argument" pitfall.
_MUTABLE = {
    "chat_history":      list,
    "lesson_draft":      dict,
    "lesson_records":    list,
    "participation_log": list,
    "rec_skipped":       list,
    "rec_current":       dict,
    "skill_definitions":        list,
    "skill_assessments":        list,
    "interventions":            list,
    "intervention_checkpoints": list,
    "question_library":         list,
    "audit_log":                list,
}


def init_state() -> None:
    """Initialise all session-state keys with their default values.

    Safe to call on every Streamlit rerun — existing values are preserved.
    """
    import streamlit as st
    for key, default in _DEFAULTS.items():
        if key not in st.session_state:
            if key in _MUTABLE:
                st.session_state[key] = _MUTABLE[key]()   # e.g. list()
            else:
                st.session_state[key] = default
