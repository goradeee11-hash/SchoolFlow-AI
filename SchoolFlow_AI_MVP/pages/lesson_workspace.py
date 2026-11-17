"""
pages/lesson_workspace.py
--------------------------
Lesson Workspace — a focused page where the teacher:
  1. Fills in lesson metadata (class, subject, title, objective, date).
  2. Records per-student attendance (Present / Absent / Late).
  3. Starts and ends the lesson, keeping an app-state copy for the current session.
  4. Records class participation responses per student, per question/activity.

Design rules
------------
* Re-uses shared.i18n (T, is_arabic, text_dir) and shared.styles (inject_css).
* Lesson and participation records remain in session_state for the UI and are
  synchronized by app.py when optional authenticated cloud storage is enabled.
* Bilingual (AR / EN) throughout.
* Participation is NEVER mixed with academic attainment:
    - No Response is NOT counted as Incorrect.
    - No Opportunity is NOT counted as a failure.
    - No aggregate score or grade is computed here.
"""

from __future__ import annotations

import streamlit as st

if __name__ == "__main__":
    st.switch_page("app.py")

import pandas as pd
from datetime import date, datetime, timezone
import uuid

import sys, os
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_HERE)          # SchoolFlow_AI_MVP/
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from shared.i18n   import T, is_arabic, text_dir
from shared.html_utils import escape_html
from shared.streamlit_compat import full_width
from shared.styles import PRIMARY_NAVY, WHITE, inject_css
from shared.time_utils import format_timestamp_riyadh, timestamp_sort_key
from shared.skills import resolve_participation_skill_id
from shared.audit import (
    ACTION_LESSON_ENDED,
    ACTION_LESSON_PLAN_UPDATED,
    ACTION_LESSON_STARTED,
    ACTION_PARTICIPATION_LOGGED,
    ENTITY_LESSON,
    ENTITY_PARTICIPATION,
    log_event,
)
from shared.gagne  import (
    GAGNE_EVENTS, EVENT_BY_ID, PLAN_STATUSES,
    new_gagne_plan, get_plan_event, update_plan_event, plan_summary,
    events_done, events_skipped, events_pending,
    MIN_DURATION_MIN, MAX_DURATION_MIN,
)

# ---------------------------------------------------------------------------
# Recommendation Engine — pure functions (no Streamlit dependency)
# ---------------------------------------------------------------------------

def recommend_next_student(
    student_codes: list[str],
    attendance: dict[str, str],
    participation_log: list[dict],
    lesson_id: str,
    target_skill: str = "",
    skipped_codes: list[str] | None = None,
    skill_definitions: list[dict] | None = None,
) -> dict:
    """
    Suggest the next student to call on during an active lesson.

    Parameters
    ----------
    student_codes    : Ordered list of all student codes in the class.
    attendance       : dict mapping student_code → attendance status string
                       (English or Arabic value from STATUS_OPTIONS).
    participation_log: All participation entries (across lessons); filtered
                       internally to lesson_id.
    lesson_id        : The active lesson's unique identifier.
    target_skill     : Optional skill ID for the current question/activity.
                       When non-empty, students who have already practised
                       this skill in this lesson are deprioritised.
    skipped_codes    : List of student codes the teacher has just skipped
                       (excluded from this suggestion cycle).

    Returns
    -------
    dict with keys:
        "student_code"  — recommended student code, or "" if none available
        "student_name"  — name from participation_log if available, else ""
        "reason"        — bilingual human-readable explanation (never a grade)
        "ok"            — True if a recommendation was made, False otherwise

    Algorithm (priority order — no randomness, fully deterministic)
    ---------------------------------------------------------------
    1. Remove absent students (attendance value contains "Absent" / "غائب").
    2. Remove explicitly skipped students (skipped_codes).
    3. Count per-student opportunities in this lesson
       (all entries where response_code != "NO" are counted as opportunities;
        "NO" itself was recorded only as a note, so it doesn't add to count).
       Actually: ANY entry in this lesson counts as one interaction; the
       filter is simply entry["lesson_id"] == lesson_id.
    4. Students with zero interactions this lesson → highest priority (Group A).
    5. Among Group A, prefer:
       a. Students who already practised target_skill → lower priority
          (they've had a turn at this skill).
       b. Otherwise: order by student_codes list order (teacher's roster order).
    6. If all eligible students have ≥1 interaction (Group B):
       a. Sort ascending by interaction count (least called first).
       b. Among ties, prefer the one whose last interaction timestamp is
          the earliest (longest ago).
    7. If no eligible student remains → return ok=False.

    Rules enforced
    --------------
    * Absent students are NEVER suggested.
    * "NO" (No Opportunity) in a previous round is NOT penalised —
      that student is still eligible and treated as "not yet interacted".
    * No grade, score, or academic judgement is used in ranking.
    * The returned dict is a pure recommendation — no state is mutated here.
    """
    if skipped_codes is None:
        skipped_codes = []

    ABSENT_VALUES = {"Absent", "غائب"}

    # ── Step 1: eligible set ─────────────────────────────────────────────────
    eligible = [
        c for c in student_codes
        if attendance.get(c, "Present") not in ABSENT_VALUES
        and c not in skipped_codes
    ]
    if not eligible:
        return {
            "student_code": "",
            "student_name": "",
            "reason": T(
                "No eligible students available (all absent or skipped).",
                "لا يوجد طلاب متاحون (جميعهم غائبون أو تم تخطيهم).",
            ),
            "ok": False,
        }

    # ── Step 2: per-student interaction counts this lesson ───────────────────
    lesson_entries = [e for e in participation_log if e.get("lesson_id") == lesson_id]

    # Count interactions; "NO" entries count too (teacher did note them)
    # but only entries that are NOT "NO" count as a real "turn"
    turn_count: dict[str, int] = {c: 0 for c in eligible}
    last_ts:    dict[str, datetime] = {
        c: datetime.min.replace(tzinfo=timezone.utc) for c in eligible
    }
    skill_turns: dict[str, int] = {c: 0 for c in eligible}  # skill-specific

    for e in lesson_entries:
        c = e.get("student_code", "")
        if c not in turn_count:
            continue
        # "NO" = no opportunity — not a real turn for the student
        if e.get("response_code") != "NO":
            turn_count[c] += 1
            ts = timestamp_sort_key(e.get("timestamp", ""))
            if ts > last_ts[c]:
                last_ts[c] = ts
        if target_skill and resolve_participation_skill_id(
            e, skill_definitions or []
        ) == target_skill:
            skill_turns[c] += 1

    # ── Step 3: split into Group A (zero turns) and Group B (≥1 turn) ────────
    group_a = [c for c in eligible if turn_count[c] == 0]
    group_b = [c for c in eligible if turn_count[c] >  0]

    # ── Step 4: pick best candidate ──────────────────────────────────────────
    # Build name lookup from participation_log entries
    name_lookup: dict[str, str] = {}
    for e in participation_log:
        c = e.get("student_code", "")
        n = e.get("student_name", "")
        if c and n and c not in name_lookup:
            name_lookup[c] = n

    if group_a:
        # Prefer students who have NOT yet practised target_skill (skill_turns == 0)
        no_skill = [c for c in group_a if skill_turns[c] == 0]
        candidates = no_skill if no_skill else group_a
        chosen = candidates[0]   # roster order preserved
        name   = name_lookup.get(chosen, "")

        if target_skill and not no_skill:
            reason = T(
                f"{chosen} has not participated yet this lesson "
                f"(all zero-turn students have already practised '{target_skill}').",
                f"لم يشارك {chosen} بعد في هذه الحصة "
                f"(جميع الطلاب الذين لم يشاركوا تدرّبوا بالفعل على مهارة '{target_skill}').",
            )
        elif target_skill:
            reason = T(
                f"{chosen} has not participated yet this lesson "
                f"and has not yet practised the skill '{target_skill}'.",
                f"لم يشارك {chosen} بعد في هذه الحصة "
                f"ولم يتدرّب بعد على مهارة '{target_skill}'.",
            )
        else:
            reason = T(
                f"{chosen} has not had a turn yet this lesson.",
                f"لم يحظَ {chosen} بدور بعد في هذه الحصة.",
            )
    elif group_b:
        # Sort: fewest turns first, then earliest last-timestamp
        sorted_b = sorted(group_b, key=lambda c: (turn_count[c], last_ts[c]))
        chosen = sorted_b[0]
        name   = name_lookup.get(chosen, "")
        reason = T(
            f"{chosen} has the fewest turns this lesson ({turn_count[chosen]}) "
            f"and participated longest ago.",
            f"حصل {chosen} على أقل عدد من الأدوار في هذه الحصة ({turn_count[chosen]}) "
            f"وكانت مشاركته الأخيرة منذ أطول وقت.",
        )
    else:
        return {
            "student_code": "",
            "student_name": "",
            "reason": T(
                "No eligible students available.",
                "لا يوجد طلاب متاحون.",
            ),
            "ok": False,
        }

    return {
        "student_code": chosen,
        "student_name": name,
        "reason":       reason,
        "ok":           True,
    }


# ---------------------------------------------------------------------------
# Participation constants
# ---------------------------------------------------------------------------

#: Response type codes — language-neutral internal identifiers
RESPONSE_TYPES = ["C", "P", "I", "NR", "NO"]

#: Participation source identifiers
SOURCE_TYPES = ["TS", "SI", "GP"]

def _response_label(code: str) -> str:
    """Return the bilingual display label for a response-type code."""
    return {
        "C":  T("C — Correct",           "C — صحيح"),
        "P":  T("P — Partially Correct",  "P — صحيح جزئيًا"),
        "I":  T("I — Incorrect",          "I — غير صحيح"),
        "NR": T("NR — No Response",       "NR — لا استجابة"),
        "NO": T("NO — No Opportunity",    "NO — لم تُتَح الفرصة"),
    }.get(code, code)

def _source_label(code: str) -> str:
    """Return the bilingual display label for a source-type code."""
    return {
        "TS": T("Teacher Selected",   "اختيار المعلم"),
        "SI": T("Student Initiated",  "مبادرة الطالب"),
        "GP": T("Group Participation","مشاركة جماعية"),
    }.get(code, code)

def _response_options() -> list[str]:
    return [_response_label(c) for c in RESPONSE_TYPES]

def _source_options() -> list[str]:
    return [_source_label(c) for c in SOURCE_TYPES]

def _code_from_label(label: str, mapping_fn) -> str:
    """Reverse-lookup: given a translated label, return its internal code."""
    for code in (RESPONSE_TYPES if mapping_fn is _response_label else SOURCE_TYPES):
        if mapping_fn(code) == label:
            return code
    return label   # fallback: store label as-is (should not happen)

# ---------------------------------------------------------------------------
# Public function — called from app.py router
# ---------------------------------------------------------------------------

def render() -> None:
    """Render the full Lesson Workspace page inside the existing app layout."""
    _IS_AR = is_arabic()
    _DIR   = text_dir()

    # ── Page title ───────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="sf-section-header" style="direction:{_DIR};">
          <div class="sf-section-num">📖</div>
          <div class="sf-section-title">
            {T("Lesson Workspace", "مساحة عمل الحصة")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Guard: data must be loaded ───────────────────────────────────────────
    if "summary" not in st.session_state:
        st.warning(
            T(
                "⚠️ No class data loaded yet. Please upload your Excel file first "
                "(Upload Student Data page).",
                "⚠️ لم يتم تحميل بيانات الفصل بعد. يرجى رفع ملف Excel أولاً "
                "من صفحة (رفع بيانات الطلاب).",
            )
        )
        return

    summary  = st.session_state["summary"]
    has_name = st.session_state.get("has_name", False)

    # ── Lesson state helpers ──────────────────────────────────────────────────
    if "lesson_active"       not in st.session_state:
        st.session_state["lesson_active"]       = False
    if "lesson_draft"        not in st.session_state:
        st.session_state["lesson_draft"]        = {}
    if "lesson_records"      not in st.session_state:
        st.session_state["lesson_records"]      = []
    if "participation_log"   not in st.session_state:
        st.session_state["participation_log"]   = []

    lesson_active      = st.session_state["lesson_active"]
    lesson_records     = st.session_state["lesson_records"]
    participation_log  = st.session_state["participation_log"]

    # ── Section 1: Lesson Metadata ────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="sf-card" style="direction:{_DIR};margin-bottom:1.2rem;">
          <div class="sf-card-header">
            <div class="sf-card-header-icon">📝</div>
            <div class="sf-card-title">
              {T("Lesson Details", "تفاصيل الحصة")}
            </div>
          </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        lesson_class = st.text_input(
            T("Class", "الفصل الدراسي"),
            value=st.session_state["lesson_draft"].get("class", ""),
            placeholder=T("e.g. Grade 5B", "مثال: الصف الخامس ب"),
            disabled=lesson_active,
            key="lw_class",
        )
        lesson_subject = st.text_input(
            T("Subject", "المادة"),
            value=st.session_state["lesson_draft"].get("subject", ""),
            placeholder=T("e.g. English Language", "مثال: اللغة الإنجليزية"),
            disabled=lesson_active,
            key="lw_subject",
        )
    with col2:
        lesson_title = st.text_input(
            T("Lesson Title", "عنوان الدرس"),
            value=st.session_state["lesson_draft"].get("title", ""),
            placeholder=T("e.g. Reading Comprehension", "مثال: فهم المقروء"),
            disabled=lesson_active,
            key="lw_title",
        )
        lesson_date = st.date_input(
            T("Lesson Date", "تاريخ الحصة"),
            value=st.session_state["lesson_draft"].get("date", date.today()),
            disabled=lesson_active,
            key="lw_date",
        )

    lesson_objective = st.text_area(
        T("Learning Objective", "الهدف التعليمي"),
        value=st.session_state["lesson_draft"].get("objective", ""),
        placeholder=T(
            "e.g. Students will be able to identify the main idea in a passage.",
            "مثال: يستطيع الطالب تحديد الفكرة الرئيسية في النص.",
        ),
        height=90,
        disabled=lesson_active,
        key="lw_objective",
    )

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Section 1b: Gagné Planning (collapsible, pre-lesson) ─────────────────
    if not lesson_active:
        _render_gagne_plan_editor(_DIR)

    # ── Section 2: Attendance ─────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin:1.2rem 0 0.6rem;">
          <div class="sf-card-header-icon">📋</div>
          <div class="sf-card-title">
            {T("Attendance", "سجل الحضور")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    STATUS_OPTIONS = [
        T("Present", "حاضر"),
        T("Absent",  "غائب"),
        T("Late",    "متأخر"),
    ]

    student_codes = summary["Student code"].tolist()
    name_map: dict[str, str] = {}
    if has_name and "Student name" in summary.columns:
        name_map = dict(zip(summary["Student code"], summary["Student name"]))

    if "attendance" not in st.session_state["lesson_draft"]:
        st.session_state["lesson_draft"]["attendance"] = {
            code: T("Present", "حاضر") for code in student_codes
        }

    att_dict = st.session_state["lesson_draft"]["attendance"]

    hdr_code = T("Code",   "الرمز")
    hdr_name = T("Name",   "الاسم")
    hdr_stat = T("Status", "الحالة")

    if has_name:
        hcols = st.columns([1, 2, 2])
        hcols[0].markdown(f"**{hdr_code}**")
        hcols[1].markdown(f"**{hdr_name}**")
        hcols[2].markdown(f"**{hdr_stat}**")
    else:
        hcols = st.columns([1, 2])
        hcols[0].markdown(f"**{hdr_code}**")
        hcols[1].markdown(f"**{hdr_stat}**")

    for code in student_codes:
        current_val = att_dict.get(code, T("Present", "حاضر"))
        if current_val not in STATUS_OPTIONS:
            current_val = STATUS_OPTIONS[0]

        if has_name:
            rcols = st.columns([1, 2, 2])
            rcols[0].markdown(
                f'<span style="background:{PRIMARY_NAVY};color:{WHITE};padding:2px 8px;'
                f'border-radius:5px;font-size:0.78rem;font-weight:700;">{escape_html(code)}</span>',
                unsafe_allow_html=True,
            )
            rcols[1].markdown(name_map.get(code, ""))
            new_val = rcols[2].selectbox(
                label=" ",
                options=STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(current_val),
                key=f"att_{code}",
                label_visibility="collapsed",
                disabled=lesson_active,
            )
        else:
            rcols = st.columns([1, 2])
            rcols[0].markdown(
                f'<span style="background:{PRIMARY_NAVY};color:{WHITE};padding:2px 8px;'
                f'border-radius:5px;font-size:0.78rem;font-weight:700;">{escape_html(code)}</span>',
                unsafe_allow_html=True,
            )
            new_val = rcols[1].selectbox(
                label=" ",
                options=STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(current_val),
                key=f"att_{code}",
                label_visibility="collapsed",
                disabled=lesson_active,
            )

        att_dict[code] = new_val

    st.session_state["lesson_draft"]["attendance"] = att_dict

    # ── Section 3: Lesson controls ────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    btn_col1, btn_col2, _spacer = st.columns([2, 2, 4])

    if not lesson_active:
        with btn_col1:
            if st.button(
                T("▶ Start Lesson", "▶ بدء الحصة"),
                type="primary",
                **full_width(),
                key="lw_start",
            ):
                # Preserve existing gagne_plan if already edited; create fresh if not
                existing_plan = st.session_state["lesson_draft"].get("gagne_plan")
                st.session_state["lesson_draft"].update(
                    {
                        "class":      lesson_class,
                        "subject":    lesson_subject,
                        "title":      lesson_title,
                        "objective":  lesson_objective,
                        "date":       lesson_date,
                        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "lesson_id":  datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                        "gagne_plan": existing_plan if existing_plan else new_gagne_plan(),
                    }
                )
                st.session_state["lesson_active"] = True
                role = st.session_state.get("active_role", "unknown")
                if role not in {"teacher", "school_admin", "demo_reviewer"}:
                    role = "unknown"
                st.session_state["audit_log"] = log_event(
                    st.session_state.get("audit_log", []),
                    action=ACTION_LESSON_STARTED,
                    actor_role=role,
                    entity_type=ENTITY_LESSON,
                )
                st.rerun()
    else:
        with btn_col1:
            st.markdown(
                f'<span class="sf-pill-ok">● '
                f'{T("Lesson in progress", "الحصة جارية")}'
                f'</span>',
                unsafe_allow_html=True,
            )
        with btn_col2:
            if st.button(
                T("⏹ End Lesson", "⏹ إنهاء الحصة"),
                type="primary",
                **full_width(),
                key="lw_end",
            ):
                _save_lesson_record()
                st.rerun()

    # ── Section 4: Next Student Recommendation ───────────────────────────────
    if lesson_active:
        _render_recommendation_widget(
            student_codes=student_codes,
            attendance=att_dict,
            name_map=name_map,
            lesson_id=st.session_state["lesson_draft"].get("lesson_id", ""),
        )

    # ── Section 5 (task 2): Participation Quick-Logger ────────────────────────
    if lesson_active:
        _render_participation_logger(
            student_codes=student_codes,
            name_map=name_map,
            lesson_id=st.session_state["lesson_draft"].get("lesson_id", ""),
        )

    # ── Section 6: Participation Log (current lesson) ─────────────────────────
    if lesson_active and participation_log:
        _render_participation_table_current(participation_log, _DIR)

    # ── Section 7: Gagné Live Event Tracker (active lesson) ──────────────────
    if lesson_active:
        _render_gagne_live_tracker(_DIR)

    # ── Section 8: Session lesson history ─────────────────────────────────────
    if lesson_records:
        st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.8rem;">
              <div class="sf-card-header-icon">🗂</div>
              <div class="sf-card-title">
                {T("Lesson History (this session)", "سجل الحصص (الجلسة الحالية)")}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        rows = []
        for rec in lesson_records:
            att = rec.get("attendance", {})
            present_count = sum(1 for v in att.values() if v in ("Present", "حاضر"))
            late_count    = sum(1 for v in att.values() if v in ("Late",    "متأخر"))
            absent_count  = sum(1 for v in att.values() if v in ("Absent",  "غائب"))
            lid = rec.get("lesson_id", "")
            part_entries  = [e for e in participation_log if e.get("lesson_id") == lid]
            rows.append(
                {
                    T("Date",          "التاريخ"):       str(rec.get("date",    "")),
                    T("Class",         "الفصل"):         rec.get("class",   ""),
                    T("Subject",       "المادة"):        rec.get("subject", ""),
                    T("Title",         "عنوان الدرس"):   rec.get("title",   ""),
                    T("Present",       "حاضر"):          present_count,
                    T("Late",          "متأخر"):         late_count,
                    T("Absent",        "غائب"):          absent_count,
                    T("Participations","مشاركات"):       len(part_entries),
                    T("Started",       "وقت البداية"):   format_timestamp_riyadh(rec.get("started_at")),
                    T("Ended",         "وقت النهاية"):   format_timestamp_riyadh(rec.get("ended_at")),
                }
            )

        st.markdown('<div class="sf-card">', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(rows), **full_width(), hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)



# ---------------------------------------------------------------------------
# Gagné sub-renderers
# ---------------------------------------------------------------------------

_STATUS_ICON = {
    "planned":     "🔲",
    "in_progress": "🔄",
    "done":        "✅",
    "skipped":     "⏭",
}
_STATUS_COLOR = {
    "planned":     "#6B7280",
    "in_progress": "#D4A017",
    "done":        "#16a34a",
    "skipped":     "#9CA3AF",
}
_STATUS_LABEL_EN = {
    "planned":     "Planned",
    "in_progress": "In progress",
    "done":        "Done",
    "skipped":     "Skipped",
}
_STATUS_LABEL_AR = {
    "planned":     "مخطَّط",
    "in_progress": "جارٍ",
    "done":        "منجَز",
    "skipped":     "متجاوَز",
}


def _gagne_plan_from_draft() -> list[dict]:
    """Return the gagne_plan from lesson_draft, creating it if absent."""
    if "gagne_plan" not in st.session_state["lesson_draft"]:
        st.session_state["lesson_draft"]["gagne_plan"] = new_gagne_plan()
    return st.session_state["lesson_draft"]["gagne_plan"]


def _render_gagne_plan_editor(_DIR: str) -> None:
    """
    Pre-lesson Gagné planning panel (shown only when lesson is NOT active).
    Collapsible expander — teacher fills in activities for each event.
    Entirely optional; leaving it empty has no consequences.
    """
    with st.expander(
        T(
            "🧩 Gagné Lesson Plan (optional — flexible guide)",
            "🧩 تخطيط غانييه للحصة (اختياري — إطار مرشد)",
        ),
        expanded=False,
    ):
        st.caption(
            T(
                "Gagné's Nine Events are a flexible instructional guide — not a rigid checklist. "
                "Skip any event, reorder freely, or leave this section blank. "
                "Nothing here affects your ability to start or end the lesson.",
                "أحداث غانييه التسعة إطار تعليمي مرن، وليست قائمة إلزامية. "
                "تجاوز أي حدث، أو عدِّل الترتيب، أو اترك هذا القسم فارغًا تمامًا. "
                "لا شيء هنا يؤثر على بدء الحصة أو إنهائها.",
            )
        )

        plan = _gagne_plan_from_draft()
        q_library = st.session_state.get("question_library") or []
        skill_defs = st.session_state.get("skill_definitions") or []

        for ev in GAGNE_EVENTS:
            pe = get_plan_event(plan, ev["id"])
            if pe is None:
                continue

            status  = pe.get("status", "planned")
            icon    = _STATUS_ICON.get(status, "🔲")
            color   = _STATUS_COLOR.get(status, "#6B7280")

            with st.expander(
                f"{icon} {ev['number']}. "
                f"{T(ev['name_en'], ev['name_ar'])}",
                expanded=False,
            ):
                st.caption(T(ev["description_en"], ev["description_ar"]))

                # Suggested activities (starting points)
                sugg = ev["example_activities_ar"] if is_arabic() else ev["example_activities_en"]
                if sugg:
                    sugg_label = T("💡 Suggested activities (starting points, not prescriptions):",
                                   "💡 أنشطة مقترحة (نقطة انطلاق، لا إلزام):")
                    st.markdown(
                        f'<div style="font-size:0.76rem;color:#435F76;direction:{_DIR};">'
                        f"{sugg_label}</div>",
                        unsafe_allow_html=True,
                    )
                    for s in sugg:
                        st.markdown(
                            f'<div style="font-size:0.76rem;color:#435F76;'
                            f'padding-left:0.8rem;direction:{_DIR};">• {escape_html(s)}</div>',
                            unsafe_allow_html=True,
                        )

                # Teacher input row
                ec1, ec2 = st.columns([3, 1])
                with ec1:
                    new_activity = st.text_input(
                        T("Activity / plan note", "النشاط / ملاحظة التخطيط"),
                        value=pe.get("activity", ""),
                        placeholder=T(
                            "Describe your planned activity…",
                            "صف النشاط المخطَّط…",
                        ),
                        key=f"gagne_activity_{ev['id']}",
                    )
                with ec2:
                    status_opts = [
                        f"{_STATUS_ICON[s]} {T(_STATUS_LABEL_EN[s], _STATUS_LABEL_AR[s])}"
                        for s in PLAN_STATUSES
                    ]
                    cur_idx = PLAN_STATUSES.index(status)
                    new_status_disp = st.selectbox(
                        T("Status", "الحالة"),
                        status_opts,
                        index=cur_idx,
                        key=f"gagne_status_{ev['id']}",
                    )
                    new_status = PLAN_STATUSES[status_opts.index(new_status_disp)]

                # Optional: link to skill or question
                ec3, ec4 = st.columns(2)
                with ec3:
                    dur = st.number_input(
                        T("Duration (min, optional)", "المدة (دقيقة، اختياري)"),
                        min_value=MIN_DURATION_MIN, max_value=MAX_DURATION_MIN,
                        value=pe.get("duration_min") or 0,
                        step=5,
                        key=f"gagne_dur_{ev['id']}",
                    )
                with ec4:
                    skill_opts = ["—"] + [f"{s['id']} — {s['name']}" for s in skill_defs]
                    skill_sel = st.selectbox(
                        T("Link skill (optional)", "ربط مهارة (اختياري)"),
                        skill_opts,
                        key=f"gagne_skill_{ev['id']}",
                    )
                    linked_skill = ""
                    if skill_sel != "—" and skill_defs:
                        idx = skill_opts.index(skill_sel) - 1
                        linked_skill = skill_defs[idx]["id"]

                notes_val = st.text_input(
                    T("Notes", "ملاحظات"),
                    value=pe.get("notes", ""),
                    key=f"gagne_notes_{ev['id']}",
                )

                if st.button(
                    T("💾 Save", "💾 حفظ"),
                    key=f"gagne_save_{ev['id']}",
                ):
                    updated = update_plan_event(
                        plan,
                        event_id=ev["id"],
                        status=new_status,
                        activity=new_activity,
                        notes=notes_val,
                        skill_id=linked_skill,
                        duration_min=dur if dur != 0 else None,
                        clear_duration=dur == 0,
                    )
                    st.session_state["lesson_draft"]["gagne_plan"] = updated
                    if updated != plan:
                        role = st.session_state.get("active_role", "unknown")
                        if role not in {"teacher", "school_admin", "demo_reviewer"}:
                            role = "unknown"
                        st.session_state["audit_log"] = log_event(
                            st.session_state.get("audit_log", []),
                            action=ACTION_LESSON_PLAN_UPDATED,
                            actor_role=role,
                            entity_type=ENTITY_LESSON,
                            changed_fields=["gagne_plan"],
                        )
                    st.rerun()

        # Plan summary strip
        plan = _gagne_plan_from_draft()
        ps = plan_summary(plan)
        done_count    = ps["done"]
        skipped_count = ps["skipped"]
        planned_count = ps["planned"]
        inprog_count  = ps["in_progress"]
        st.markdown(
            f"""
            <div style="background:var(--sf-surface-raised);border:1px solid #A9C0D5;border-radius:8px;
                        padding:0.5rem 0.9rem;font-size:0.80rem;direction:{_DIR};
                        display:flex;gap:1.2rem;flex-wrap:wrap;margin-top:0.5rem;">
              <span>✅ {T(f"Done: {done_count}","منجَز: {done_count}")}</span>
              <span>🔄 {T(f"In progress: {inprog_count}","جارٍ: {inprog_count}")}</span>
              <span>⏭ {T(f"Skipped: {skipped_count}","متجاوَز: {skipped_count}")}</span>
              <span>🔲 {T(f"Planned: {planned_count}","مخطَّط: {planned_count}")}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_gagne_live_tracker(_DIR: str) -> None:
    """
    Compact Gagné live event tracker shown during an active lesson.
    Allows the teacher to quickly mark events done/skipped without leaving
    the main lesson flow.
    """
    plan = _gagne_plan_from_draft()
    ps   = plan_summary(plan)

    if ps["untouched"] == 9:
        # Plan was never touched — show a minimal invitation, not a wall of inputs
        st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)
        st.caption(
            T(
                "💡 Gagné plan not set. You can plan next time via the "
                "'Gagné Lesson Plan' panel before starting the lesson.",
                "💡 لم يُعَدَّ تخطيط غانييه. يمكنك التخطيط في المرة القادمة "
                "عبر لوحة 'تخطيط غانييه للحصة' قبل بدء الحصة.",
            )
        )
        return

    st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.5rem;">
          <div class="sf-card-header-icon">🧩</div>
          <div class="sf-card-title">
            {T("Gagné Events — Live Tracker", "أحداث غانييه — المتابعة المباشرة")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        T(
            "Mark events as you go — this is an optional live aide, not a requirement.",
            "حدِّث حالة الأحداث أثناء الحصة — هذا مساعد اختياري، وليس شرطًا.",
        )
    )

    # Show all events as a compact grid of status buttons
    cols = st.columns(3)
    for i, ev in enumerate(GAGNE_EVENTS):
        pe     = get_plan_event(plan, ev["id"])
        status = pe.get("status", "planned") if pe else "planned"
        icon   = _STATUS_ICON.get(status, "🔲")
        col    = cols[i % 3]

        with col:
            # Compact display: icon + number + name
            st.markdown(
                f'<div style="font-size:0.76rem;font-weight:700;color:#102B4E;'
                f'direction:{_DIR};">'
                f'{icon} {ev["number"]}. {T(ev["name_en"], ev["name_ar"])}</div>',
                unsafe_allow_html=True,
            )
            new_opts  = [
                f"{_STATUS_ICON[s]} {T(_STATUS_LABEL_EN[s], _STATUS_LABEL_AR[s])}"
                for s in PLAN_STATUSES
            ]
            cur_idx   = PLAN_STATUSES.index(status)
            sel_disp  = st.selectbox(
                " ", new_opts, index=cur_idx,
                key=f"live_status_{ev['id']}",
                label_visibility="collapsed",
            )
            sel_status = PLAN_STATUSES[new_opts.index(sel_disp)]

            if sel_status != status:
                updated = update_plan_event(plan, ev["id"], status=sel_status)
                st.session_state["lesson_draft"]["gagne_plan"] = updated
                role = st.session_state.get("active_role", "unknown")
                if role not in {"teacher", "school_admin", "demo_reviewer"}:
                    role = "unknown"
                st.session_state["audit_log"] = log_event(
                    st.session_state.get("audit_log", []),
                    action=ACTION_LESSON_PLAN_UPDATED,
                    actor_role=role,
                    entity_type=ENTITY_LESSON,
                    changed_fields=["gagne_plan"],
                )
                st.rerun()

    # Summary strip
    ps2 = plan_summary(plan)
    done_pct = ps2["completion_pct"]
    st.markdown(
        f"""
        <div style="background:var(--sf-surface-raised);border:1px solid #A9C0D5;border-radius:8px;
                    padding:0.4rem 0.8rem;font-size:0.78rem;direction:{_DIR};
                    margin-top:0.5rem;display:flex;gap:1rem;flex-wrap:wrap;">
          <span>✅ {T(f"Done: {ps2['done']}","منجَز: {ps2['done']}")}</span>
          <span>⏭ {T(f"Skipped: {ps2['skipped']}","متجاوَز: {ps2['skipped']}")}</span>
          <span>🔄 {T(f"In progress: {ps2['in_progress']}","جارٍ: {ps2['in_progress']}")}</span>
          <span style="color:#435F76;">
            {T(f"({done_pct}% done or skipped)","({done_pct}% منجَز أو متجاوَز)")}
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Recommendation sub-renderer
# ---------------------------------------------------------------------------

def _render_recommendation_widget(
    student_codes: list,
    attendance: dict,
    name_map: dict,
    lesson_id: str,
) -> None:
    """
    Render the Next Student Recommendation widget inside an active lesson.

    State keys used (all in st.session_state):
        "rec_skipped"   : list[str] — codes skipped in the current cycle
        "rec_current"   : dict      — the last computed recommendation
        "rec_skill_input": str      — skill filter typed by the teacher
    """
    _DIR = text_dir()
    participation_log = st.session_state.get("participation_log", [])

    # ── State helpers ──────────────────────────────────────────────────────
    if "rec_skipped"    not in st.session_state:
        st.session_state["rec_skipped"]     = []
    if "rec_current"    not in st.session_state:
        st.session_state["rec_current"]     = {}
    if "rec_skill_input" not in st.session_state:
        st.session_state["rec_skill_input"] = ""

    st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.6rem;">
          <div class="sf-card-header-icon">🎯</div>
          <div class="sf-card-title">
            {T("Next Student Suggestion", "اقتراح الطالب التالي")}
          </div>
        </div>
        <div style="font-size:0.80rem;color:#435F76;direction:{_DIR};margin-bottom:0.6rem;">
          {T(
            "The engine suggests who to call on next based on participation fairness — "
            "not academic ability.",
            "يقترح النظام الطالب التالي بناءً على توازن الفرص، وليس القدرة الأكاديمية."
          )}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Skill filter ───────────────────────────────────────────────────────
    skill_definitions = st.session_state.get("skill_definitions") or []
    skill_by_id = {
        skill["id"]: skill
        for skill in skill_definitions
        if isinstance(skill.get("id"), str)
    }
    if st.session_state["rec_skill_input"] not in skill_by_id:
        st.session_state["rec_skill_input"] = ""

    def _skill_option_label(skill_id: str) -> str:
        if not skill_id:
            return T("— No skill filter —", "— بدون تصفية مهارة —")
        return f"{skill_id} — {skill_by_id[skill_id]['name']}"

    skill_input = st.selectbox(
        T("Target Skill (optional)", "المهارة المستهدفة (اختياري)"),
        options=["", *skill_by_id],
        format_func=_skill_option_label,
        key="rec_skill_id_field",
    )
    st.session_state["rec_skill_input"] = skill_input

    # ── Compute recommendation ─────────────────────────────────────────────
    rec = recommend_next_student(
        student_codes=student_codes,
        attendance=attendance,
        participation_log=participation_log,
        lesson_id=lesson_id,
        target_skill=skill_input,
        skipped_codes=st.session_state["rec_skipped"],
        skill_definitions=skill_definitions,
    )
    st.session_state["rec_current"] = rec

    # ── Display ────────────────────────────────────────────────────────────
    if rec["ok"]:
        code = rec["student_code"]
        name = rec["student_name"] or name_map.get(code, "")
        display = f"{code} — {name}" if name else code
        reason  = rec["reason"]

        st.markdown(
            f"""
            <div style="background:var(--sf-surface-raised);border:1.5px solid #A9C0D5;
                        border-radius:12px;padding:0.9rem 1.2rem;
                        direction:{_DIR};margin-bottom:0.6rem;">
              <div style="font-size:1.05rem;font-weight:900;color:#102B4E;">
                🎓 {escape_html(display)}
              </div>
              <div style="font-size:0.82rem;color:#435F76;margin-top:0.3rem;">
                {escape_html(reason)}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Action buttons ─────────────────────────────────────────────────
        b1, b2, b3, _sp = st.columns([2, 2, 2, 2])
        with b1:
            if st.button(
                T("✅ Accept", "✅ قبول"),
                key="rec_accept",
                **full_width(),
                type="primary",
            ):
                # Reset skip list — a new round begins; do NOT log participation
                st.session_state["rec_skipped"] = []
                st.rerun()
        with b2:
            if st.button(
                T("⏭ Skip", "⏭ تخطّي"),
                key="rec_skip",
                **full_width(),
            ):
                skipped = st.session_state["rec_skipped"]
                if code not in skipped:
                    skipped.append(code)
                st.rerun()
        with b3:
            if st.button(
                T("🔄 Refresh", "🔄 تحديث"),
                key="rec_refresh",
                **full_width(),
            ):
                # Clear skipped list to get a fresh recommendation
                st.session_state["rec_skipped"] = []
                st.rerun()

        if st.session_state["rec_skipped"]:
            st.caption(
                T(
                    f"Skipped this round: {', '.join(st.session_state['rec_skipped'])}",
                    f"تم تخطيهم في هذه الجولة: {', '.join(st.session_state['rec_skipped'])}",
                )
            )
    else:
        st.markdown(
            f"""
            <div style="background:var(--sf-surface-raised);border:1px solid #D4A017;
                        border-radius:10px;padding:0.7rem 1rem;
                        direction:{_DIR};font-size:0.85rem;color:#102B4E;">
              ⚠️ {escape_html(rec["reason"])}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(T("🔄 Refresh", "🔄 تحديث"), key="rec_refresh_no_ok"):
            st.session_state["rec_skipped"] = []
            st.rerun()


# ---------------------------------------------------------------------------
# Participation sub-renderers
# ---------------------------------------------------------------------------

def _render_participation_logger(
    student_codes: list,
    name_map: dict,
    lesson_id: str,
) -> None:
    """Render the Quick Participation Logger inside an active lesson."""
    _IS_AR = is_arabic()
    _DIR   = text_dir()

    st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.8rem;">
          <div class="sf-card-header-icon">✋</div>
          <div class="sf-card-title">
            {T("Quick Participation Logger", "تسجيل المشاركة السريع")}
          </div>
        </div>
        <div style="font-size:0.80rem;color:#435F76;direction:{_DIR};margin-bottom:0.8rem;">
          {T(
            "Log each student interaction — multiple entries per student per question are allowed.",
            "سجّل كل تفاعل للطالب — يمكن تسجيل أكثر من استجابة للطالب نفسه في السؤال ذاته."
          )}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Input row ─────────────────────────────────────────────────────────────
    r_opts  = _response_options()
    s_opts  = _source_options()

    # Build student display list
    student_display = [
        f"{code} — {name_map[code]}" if code in name_map else code
        for code in student_codes
    ]

    pc1, pc2 = st.columns(2)
    with pc1:
        sel_student = st.selectbox(
            T("Student", "الطالب"),
            student_display,
            key="part_student",
        )
    with pc2:
        question_text = st.text_input(
            T("Question / Activity", "السؤال / النشاط"),
            placeholder=T("Brief description…", "وصف مختصر…"),
            key="part_question",
        )

    skill_definitions = st.session_state.get("skill_definitions") or []
    skill_by_id = {
        skill["id"]: skill
        for skill in skill_definitions
        if isinstance(skill.get("id"), str)
    }

    def _skill_option_label(skill_id: str) -> str:
        if not skill_id:
            return T("— No skill —", "— بدون مهارة —")
        return f"{skill_id} — {skill_by_id[skill_id]['name']}"

    pc3, pc4, pc5 = st.columns(3)
    with pc3:
        sel_response = st.selectbox(
            T("Response", "الاستجابة"),
            r_opts,
            key="part_response",
        )
    with pc4:
        sel_source = st.selectbox(
            T("Source", "مصدر المشاركة"),
            s_opts,
            key="part_source",
        )
    with pc5:
        skill_id = st.selectbox(
            T("Skill (optional)", "المهارة (اختياري)"),
            options=["", *skill_by_id],
            format_func=_skill_option_label,
            key="part_skill_id",
        )

    if st.button(
        T("➕ Log Response", "➕ تسجيل الاستجابة"),
        type="primary",
        key="part_log_btn",
    ):
        # Resolve student code from display label
        idx = student_display.index(sel_student)
        s_code = student_codes[idx]
        s_name = name_map.get(s_code, "")

        # Resolve internal codes
        r_code = _code_from_label(sel_response, _response_label)
        src_code = _code_from_label(sel_source, _source_label)

        entry = build_participation_entry(
            student_code=s_code,
            student_name=s_name,
            lesson_id=lesson_id,
            question=question_text.strip(),
            response_code=r_code,
            source_code=src_code,
            skill_id=skill_id,
        )
        st.session_state["participation_log"].append(entry)
        role = st.session_state.get("active_role", "unknown")
        if role not in {"teacher", "school_admin", "demo_reviewer"}:
            role = "unknown"
        st.session_state["audit_log"] = log_event(
            st.session_state.get("audit_log", []),
            action=ACTION_PARTICIPATION_LOGGED,
            actor_role=role,
            entity_type=ENTITY_PARTICIPATION,
        )
        st.rerun()


def _render_participation_table_current(
    participation_log: list,
    _DIR: str,
) -> None:
    """Display participation entries for the active lesson."""
    lesson_id = st.session_state.get("lesson_draft", {}).get("lesson_id", "")
    current   = [e for e in participation_log if e.get("lesson_id") == lesson_id]
    if not current:
        return

    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin:1rem 0 0.5rem;">
          <div class="sf-card-header-icon">📊</div>
          <div class="sf-card-title">
            {T("Participation Log — Current Lesson", "سجل المشاركة — الحصة الحالية")}
            &nbsp;<span style="color:#435F76;font-size:0.80rem;">({len(current)})</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rows = []
    skill_definitions = st.session_state.get("skill_definitions") or []
    skill_names = {
        skill["id"]: skill.get("name", skill["id"])
        for skill in skill_definitions
        if isinstance(skill.get("id"), str)
    }
    for e in current:
        skill_id = resolve_participation_skill_id(e, skill_definitions)
        if skill_id:
            skill_label = skill_names[skill_id]
        else:
            unlinked_value = e.get("skill") or e.get("skill_id") or ""
            skill_label = (
                f"{unlinked_value} ({T('unlinked', 'غير مرتبطة')})"
                if unlinked_value
                else T("—", "—")
            )
        rows.append(
            {
                T("Time",     "الوقت"):         format_timestamp_riyadh(e.get("timestamp")),
                T("Student",  "الطالب"):        e.get("student_code", ""),
                T("Question", "السؤال"):        e.get("question", ""),
                T("Response", "الاستجابة"):    _response_label(e.get("response_code", "")),
                T("Source",   "المصدر"):        _source_label(e.get("source_code", "")),
                T("Skill",    "المهارة"):       skill_label,
            }
        )

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(rows), **full_width(), hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public pure functions — no Streamlit dependency; fully testable
# ---------------------------------------------------------------------------

def build_participation_entry(
    student_code: str,
    student_name: str,
    lesson_id: str,
    question: str,
    response_code: str,
    source_code: str,
    skill_id: str = "",
    _now: str | None = None,
) -> dict:
    """
    Build a single participation log entry dict.

    Parameters
    ----------
    student_code  : Student identifier (e.g. "S01").
    student_name  : Student display name (empty string if unavailable).
    lesson_id     : ISO-format timestamp string identifying the active lesson.
    question      : Brief description of the question or activity.
    response_code : One of RESPONSE_TYPES: "C", "P", "I", "NR", "NO".
    source_code   : One of SOURCE_TYPES: "TS", "SI", "GP".
    skill_id      : Optional skill definition ID.
    _now          : Optional ISO timestamp override (for testing).

    Returns
    -------
    dict with keys:
        student_code, student_name, lesson_id, question,
        response_code, source_code, skill_id, timestamp.

    Rules enforced
    --------------
    * response_code must be one of RESPONSE_TYPES; raises ValueError otherwise.
    * source_code must be one of SOURCE_TYPES; raises ValueError otherwise.
    * "NR" (No Response) is distinct from "I" (Incorrect) — not an academic fail.
    * "NO" (No Opportunity) is distinct from all response types — not a failure.
    """
    if response_code not in RESPONSE_TYPES:
        raise ValueError(
            f"Invalid response_code {response_code!r}. "
            f"Must be one of {RESPONSE_TYPES}."
        )
    if source_code not in SOURCE_TYPES:
        raise ValueError(
            f"Invalid source_code {source_code!r}. "
            f"Must be one of {SOURCE_TYPES}."
        )
    if not isinstance(skill_id, str):
        raise ValueError("skill_id must be a string.")

    return {
        "id":            uuid.uuid4().hex,
        "student_code":  student_code,
        "student_name":  student_name,
        "lesson_id":     lesson_id,
        "question":      question,
        "response_code": response_code,
        "source_code":   source_code,
        "skill_id":      skill_id.strip(),
        "timestamp":     _now if _now is not None else datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def summarise_participation(entries: list, lesson_id: str | None = None) -> dict:
    """
    Compute a summary of participation entries, optionally filtered to one lesson.

    Parameters
    ----------
    entries   : List of dicts produced by build_participation_entry().
    lesson_id : If given, only count entries for this lesson.

    Returns
    -------
    dict with keys:
        total          — total entries counted
        by_response    — dict mapping response_code → count
        by_source      — dict mapping source_code   → count
        by_student     — dict mapping student_code  → count
        no_response    — count of "NR" entries  (distinct from Incorrect)
        no_opportunity — count of "NO" entries  (distinct from all responses)
        substantive    — count of "C"+"P"+"I" entries (excludes NR and NO)

    Rules
    -----
    * "NR" is counted separately and NOT added to `substantive`.
    * "NO" is counted separately and NOT added to `substantive`.
    * No grade or average is computed.
    """
    if lesson_id is not None:
        entries = [e for e in entries if e.get("lesson_id") == lesson_id]

    by_response: dict[str, int] = {code: 0 for code in RESPONSE_TYPES}
    by_source:   dict[str, int] = {code: 0 for code in SOURCE_TYPES}
    by_student:  dict[str, int] = {}

    for e in entries:
        r = e.get("response_code", "")
        s = e.get("source_code", "")
        c = e.get("student_code", "")

        if r in by_response:
            by_response[r] += 1
        if s in by_source:
            by_source[s] += 1
        by_student[c] = by_student.get(c, 0) + 1

    substantive = by_response["C"] + by_response["P"] + by_response["I"]

    return {
        "total":          len(entries),
        "by_response":    by_response,
        "by_source":      by_source,
        "by_student":     by_student,
        "no_response":    by_response["NR"],
        "no_opportunity": by_response["NO"],
        "substantive":    substantive,
    }


# ---------------------------------------------------------------------------
# Internal helper (not part of public API; tested directly)
# ---------------------------------------------------------------------------

def _save_lesson_record() -> None:
    """
    Finalise the current lesson draft and append it to lesson_records.
    Resets lesson_active and clears the draft for the next lesson.
    Called when the teacher clicks 'End Lesson'.
    """
    import copy
    draft = copy.deepcopy(dict(st.session_state.get("lesson_draft", {})))
    draft["ended_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if "lesson_records" not in st.session_state:
        st.session_state["lesson_records"] = []

    st.session_state["lesson_records"].append(draft)
    st.session_state["lesson_active"] = False
    # Keep attendance pre-filled for the next lesson (teacher convenience)
    # but clear metadata fields so the teacher types them fresh
    st.session_state["lesson_draft"] = {
        "attendance": copy.deepcopy(draft.get("attendance", {})),
    }
    role = st.session_state.get("active_role", "unknown")
    if role not in {"teacher", "school_admin", "demo_reviewer"}:
        role = "unknown"
    st.session_state["audit_log"] = log_event(
        st.session_state.get("audit_log", []),
        action=ACTION_LESSON_ENDED,
        actor_role=role,
        entity_type=ENTITY_LESSON,
    )


def build_lesson_summary(lesson_records: list) -> pd.DataFrame:
    """
    Convert a list of lesson record dicts into a tidy summary DataFrame.

    Parameters
    ----------
    lesson_records : list of dict
        Each dict has keys: date, class, subject, title, objective,
        attendance (dict of code→status), started_at, ended_at.

    Returns
    -------
    pd.DataFrame with one row per lesson.
    Columns: date, class, subject, title, n_present, n_late, n_absent, total.
    """
    rows = []
    for rec in lesson_records:
        att = rec.get("attendance", {})
        n_present = sum(1 for v in att.values() if v in ("Present", "حاضر"))
        n_late    = sum(1 for v in att.values() if v in ("Late",    "متأخر"))
        n_absent  = sum(1 for v in att.values() if v in ("Absent",  "غائب"))
        rows.append(
            {
                "date":      rec.get("date", ""),
                "class":     rec.get("class", ""),
                "subject":   rec.get("subject", ""),
                "title":     rec.get("title", ""),
                "objective": rec.get("objective", ""),
                "n_present": n_present,
                "n_late":    n_late,
                "n_absent":  n_absent,
                "total":     n_present + n_late + n_absent,
                "started_at": rec.get("started_at", ""),
                "ended_at":   rec.get("ended_at",   ""),
            }
        )
    return pd.DataFrame(rows)
