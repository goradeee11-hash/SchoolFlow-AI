"""
pages/student_profile.py
------------------------
Student Profile — a consolidated view of everything SchoolFlow AI knows
about one student, drawn from:

  * st.session_state["summary"]          — per-student summary (from app_logic)
  * st.session_state["clean"]            — weekly detail rows (from app_logic)
  * st.session_state["participation_log"]— in-lesson participation entries
  * st.session_state["lesson_records"]   — completed lesson metadata

Design rules
------------
* All data comes from existing session_state keys — nothing invented.
* Participation is NEVER mixed with academic attainment.
* No Response (NR) ≠ Incorrect.  No Opportunity (NO) ≠ failure.
* No automatic grades, rankings, or final judgements are produced.
* When data is absent, we say so explicitly rather than hiding it.
* Bilingual (AR / EN) throughout; re-uses shared.i18n.T().
* Does NOT modify any existing session_state key.
"""

from __future__ import annotations

import streamlit as st

if __name__ == "__main__":
    st.switch_page("app.py")

import pandas as pd
from datetime import datetime

import sys, os
_HERE    = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_HERE)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from shared.i18n import T, is_arabic, text_dir
from shared.html_utils import escape_html
from shared.streamlit_compat import full_width
from shared.audit import ACTION_PROFILE_VIEWED, ENTITY_STUDENT, log_event
from shared.skills import resolve_participation_skill_id
from shared.styles import PRIMARY_NAVY, WHITE

# ---------------------------------------------------------------------------
# Public pure functions — no Streamlit; fully testable
# ---------------------------------------------------------------------------

def build_student_profile(
    student_code: str,
    summary_df: pd.DataFrame,
    clean_df: pd.DataFrame,
    participation_log: list[dict],
    lesson_records: list[dict],
    has_name: bool = False,
    skill_definitions: list[dict] | None = None,
) -> dict:
    """
    Assemble all available data about one student into a single profile dict.

    Parameters
    ----------
    student_code      : The student's unique identifier (e.g. "S01").
    summary_df        : Per-student summary DataFrame from build_outputs().
    clean_df          : Weekly detail DataFrame from build_outputs().
    participation_log : List of participation entry dicts (may be empty).
    lesson_records    : List of completed lesson record dicts (may be empty).
    has_name          : Whether the "Student name" column is present.
    skill_definitions : Official skills used to resolve IDs and unique legacy names.

    Returns
    -------
    dict with keys:
        "found"            : bool — False if student_code not in summary_df
        "student_code"     : str
        "student_name"     : str  (empty if unavailable)
        "weeks_recorded"   : int
        "attendance_pct"   : str  (formatted, e.g. "85.0%") or "N/A"
        "attendance_detail": str  (e.g. "17/20") or "N/A"
        "task_pct"         : str  or "N/A"
        "task_detail"      : str  or "N/A"
        "mean_quiz"        : float | None
        "quiz_weeks"       : int
        "latest_obs"       : str
        "next_step"        : str
        "weekly_rows"      : list[dict]  — per-week detail rows, sorted by week
        "participation"    : dict (see _summarise_student_participation)
        "skills"           : dict mapping skill ID → count (may be empty)
        "unlinked_skills"  : legacy labels not matched to one official skill
        "lessons_present"  : int — lessons where this student was marked present/late
        "lessons_absent"   : int
        "lessons_total"    : int — completed lesson records this session
    """
    # ── Locate summary row ────────────────────────────────────────────────
    mask = summary_df["Student code"] == student_code
    if not mask.any():
        return {
            "found": False,
            "student_code": student_code,
            "student_name": "",
            "weeks_recorded": 0,
            "attendance_pct": "N/A",
            "attendance_detail": "N/A",
            "task_pct": "N/A",
            "task_detail": "N/A",
            "mean_quiz": None,
            "quiz_weeks": 0,
            "latest_obs": "",
            "next_step": "",
            "weekly_rows": [],
            "participation": _summarise_student_participation(student_code, []),
            "skills": {},
            "unlinked_skills": {},
            "lessons_present": 0,
            "lessons_absent": 0,
            "lessons_total": 0,
        }

    row = summary_df[mask].iloc[0]
    name = str(row.get("Student name", "")) if has_name else ""
    if name == student_code:   # build_outputs puts code as name when no name column
        name = ""

    # ── Weekly detail rows ────────────────────────────────────────────────
    student_clean = clean_df[clean_df["Student code"] == student_code].sort_values("Week")
    weekly_rows = student_clean.to_dict("records")

    # ── Participation ─────────────────────────────────────────────────────
    part = _summarise_student_participation(student_code, participation_log)

    # ── Skills from participation log ─────────────────────────────────────
    skills: dict[str, int] = {}
    unlinked_counts: dict[str, int] = {}
    unlinked_labels: dict[str, str] = {}
    for e in participation_log:
        if e.get("student_code") == student_code:
            skill_id = resolve_participation_skill_id(e, skill_definitions or [])
            if skill_id:
                skills[skill_id] = skills.get(skill_id, 0) + 1
            else:
                legacy_name = e.get("skill")
                if isinstance(legacy_name, str) and legacy_name.strip():
                    label = legacy_name.strip()
                    label_key = label.casefold()
                    unlinked_labels.setdefault(label_key, label)
                    unlinked_counts[label_key] = unlinked_counts.get(label_key, 0) + 1
    unlinked_skills = {
        unlinked_labels[key]: unlinked_counts[key]
        for key in unlinked_counts
    }

    # ── Lesson attendance from lesson_records ─────────────────────────────
    lessons_present = 0
    lessons_absent  = 0
    ABSENT_VALUES   = {"Absent", "غائب"}
    for rec in lesson_records:
        att = rec.get("attendance", {})
        status = att.get(student_code, "")
        if status in ABSENT_VALUES:
            lessons_absent += 1
        else:
            lessons_present += 1

    return {
        "found": True,
        "student_code": student_code,
        "student_name": name,
        "weeks_recorded": int(row.get("Weeks recorded", 0)),
        "attendance_pct": str(row.get("Attendance", "N/A")),
        "attendance_detail": str(row.get("Attendance attended/scheduled", "N/A")),
        "task_pct": str(row.get("Task completion", "N/A")),
        "task_detail": str(row.get("Tasks completed/set", "N/A")),
        "mean_quiz": row.get("Mean quiz / 10"),
        "quiz_weeks": int(row.get("Quiz weeks recorded", 0)),
        "latest_obs": str(row.get("Latest observation", "") or ""),
        "next_step": str(row.get("Next step", "") or ""),
        "weekly_rows": weekly_rows,
        "participation": part,
        "skills": skills,
        "unlinked_skills": unlinked_skills,
        "lessons_present": lessons_present,
        "lessons_absent": lessons_absent,
        "lessons_total": len(lesson_records),
    }


def _summarise_student_participation(
    student_code: str,
    participation_log: list[dict],
) -> dict:
    """
    Summarise participation entries for one student.

    Returns
    -------
    dict:
        "total"          : int
        "substantive"    : int  (C + P + I only)
        "no_response"    : int  (NR — opportunity given, no response; NOT Incorrect)
        "no_opportunity" : int  (NO — no opportunity; NOT a failure)
        "by_response"    : dict code → count
        "by_source"      : dict code → count
        "lesson_ids"     : list of unique lesson_ids this student appeared in
    """
    entries = [e for e in participation_log if e.get("student_code") == student_code]

    RESPONSE_CODES = ["C", "P", "I", "NR", "NO"]
    SOURCE_CODES   = ["TS", "SI", "GP"]

    by_response: dict[str, int] = {c: 0 for c in RESPONSE_CODES}
    by_source:   dict[str, int] = {c: 0 for c in SOURCE_CODES}
    lesson_ids: list[str] = []

    for e in entries:
        r = e.get("response_code", "")
        s = e.get("source_code", "")
        lid = e.get("lesson_id", "")
        if r in by_response:
            by_response[r] += 1
        if s in by_source:
            by_source[s] += 1
        if lid and lid not in lesson_ids:
            lesson_ids.append(lid)

    substantive = by_response["C"] + by_response["P"] + by_response["I"]

    return {
        "total":          len(entries),
        "substantive":    substantive,
        "no_response":    by_response["NR"],
        "no_opportunity": by_response["NO"],
        "by_response":    by_response,
        "by_source":      by_source,
        "lesson_ids":     lesson_ids,
    }


# ---------------------------------------------------------------------------
# Streamlit page renderer
# ---------------------------------------------------------------------------

def render() -> None:
    """Render the Student Profile page."""
    _IS_AR = is_arabic()
    _DIR   = text_dir()

    # ── Page header ───────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="sf-section-header" style="direction:{_DIR};">
          <div class="sf-section-num">👤</div>
          <div class="sf-section-title">
            {T("Student Profile", "ملف الطالب")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Guard: data must be loaded ─────────────────────────────────────────
    if "summary" not in st.session_state:
        st.warning(
            T(
                "⚠️ No class data loaded. Please upload the Excel file first.",
                "⚠️ لم يتم تحميل بيانات الفصل. يرجى رفع ملف Excel أولاً.",
            )
        )
        return

    summary  = st.session_state["summary"]
    clean    = st.session_state["clean"]
    has_name = st.session_state.get("has_name", False)
    participation_log = st.session_state.get("participation_log", [])
    lesson_records    = st.session_state.get("lesson_records", [])
    skill_definitions = st.session_state.get("skill_definitions") or []

    # ── Student selector ──────────────────────────────────────────────────
    student_codes = summary["Student code"].tolist()
    name_map: dict[str, str] = {}
    if has_name and "Student name" in summary.columns:
        name_map = dict(zip(summary["Student code"], summary["Student name"]))

    display_opts = [
        f"{c} — {name_map[c]}" if c in name_map else c
        for c in student_codes
    ]

    # Honour pre-selected code if set via session_state
    pre = st.session_state.get("profile_student_code", "")
    default_idx = 0
    if pre in student_codes:
        default_idx = student_codes.index(pre)

    sel_col, _ = st.columns([3, 5])
    with sel_col:
        chosen_display = st.selectbox(
            T("Select student", "اختر الطالب"),
            display_opts,
            index=default_idx,
            key="profile_selector",
        )
    chosen_code = student_codes[display_opts.index(chosen_display)]
    st.session_state["profile_student_code"] = chosen_code

    # ── Build profile ──────────────────────────────────────────────────────
    profile = build_student_profile(
        student_code=chosen_code,
        summary_df=summary,
        clean_df=clean,
        participation_log=participation_log,
        lesson_records=lesson_records,
        has_name=has_name,
        skill_definitions=skill_definitions,
    )

    if not profile["found"]:
        st.error(T(f"Student {chosen_code} not found.", f"الطالب {chosen_code} غير موجود."))
        return

    if pre != chosen_code:
        role = st.session_state.get("active_role", "unknown")
        if role not in {"teacher", "school_admin", "demo_reviewer"}:
            role = "unknown"
        st.session_state["audit_log"] = log_event(
            st.session_state.get("audit_log", []),
            action=ACTION_PROFILE_VIEWED,
            actor_role=role,
            entity_type=ENTITY_STUDENT,
        )

    _render_profile(profile, _DIR)


def _render_profile(profile: dict, _DIR: str) -> None:
    """Render all profile sections from the assembled profile dict."""
    code    = profile["student_code"]
    name    = profile["student_name"]
    display = f"{code}  —  {name}" if name else code

    # ── Hero card ─────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:{PRIMARY_NAVY};
                    border-radius:14px;padding:1.1rem 1.5rem;
                    display:flex;align-items:center;gap:1rem;
                    margin-bottom:1.2rem;direction:{_DIR};">
          <div style="width:52px;height:52px;border-radius:50%;
                      background:rgba(183,217,87,0.25);
                      display:flex;align-items:center;justify-content:center;
                      font-size:1.5rem;flex-shrink:0;">👤</div>
          <div>
            <div style="font-size:1.2rem;font-weight:900;color:{WHITE};">{escape_html(display)}</div>
            <div style="font-size:0.78rem;color:rgba(255,255,255,0.72);margin-top:0.2rem;">
              {T(f"Weeks recorded: {profile['weeks_recorded']}",
                 f"أسابيع مسجّلة: {profile['weeks_recorded']}")}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── KPI strip ─────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    _kpi(k1, "📅", T("Attendance",   "الحضور"),
         profile["attendance_pct"], profile["attendance_detail"])
    _kpi(k2, "✅", T("Task Completion","إنجاز المهام"),
         profile["task_pct"], profile["task_detail"])
    quiz_val = (f"{profile['mean_quiz']:.1f}/10"
                if profile["mean_quiz"] is not None else T("N/A","غير متاح"))
    _kpi(k3, "🏆", T("Mean Quiz","متوسط الاختبارات"),
         quiz_val, T(f"{profile['quiz_weeks']} quiz weeks",
                     f"{profile['quiz_weeks']} أسابيع اختبار"))
    _kpi(k4, "✋", T("Interactions","التفاعلات"),
         str(profile["participation"]["total"]),
         T(f"{profile['participation']['substantive']} substantive",
           f"{profile['participation']['substantive']} تفاعل فعلي"))

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Two columns: Academic detail | Participation ───────────────────────
    left, right = st.columns(2)

    with left:
        # ── Academic progress ────────────────────────────────────────────
        st.markdown(
            f"""
            <div class="sf-card-header" style="direction:{_DIR};">
              <div class="sf-card-header-icon">📊</div>
              <div class="sf-card-title">{T("Academic Progress","التقدم الأكاديمي")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        rows = profile["weekly_rows"]
        if rows:
            show_cols = ["Week", "Days scheduled", "Days attended",
                         "Tasks set", "Tasks completed", "Quiz score / 10"]
            df_weekly = pd.DataFrame(rows)
            available = [c for c in show_cols if c in df_weekly.columns]
            st.markdown('<div class="sf-card">', unsafe_allow_html=True)
            st.dataframe(df_weekly[available], **full_width(), hide_index=True)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.caption(T("No weekly records available.", "لا توجد سجلات أسبوعية."))

        # ── Observations ──────────────────────────────────────────────────
        obs  = profile["latest_obs"]
        step = profile["next_step"]
        if obs or step:
            st.markdown(
                f"""
                <div class="sf-card" style="direction:{_DIR};margin-top:0.9rem;">
                  <div class="sf-card-header">
                    <div class="sf-card-header-icon">💬</div>
                    <div class="sf-card-title">{T("Teacher Notes","ملاحظات المعلم")}</div>
                  </div>
                  <div style="font-size:0.83rem;color:#102B4E;margin-bottom:0.5rem;">
                    <strong>{T("Observation:","الملاحظة:")}</strong><br>
                    {escape_html(obs or T("—","—"))}
                  </div>
                  <div style="font-size:0.83rem;color:#102B4E;">
                    <strong>{T("Next step:","الخطوة القادمة:")}</strong><br>
                    {escape_html(step or T("—","—"))}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with right:
        # ── Participation breakdown ───────────────────────────────────────
        part = profile["participation"]
        st.markdown(
            f"""
            <div class="sf-card-header" style="direction:{_DIR};">
              <div class="sf-card-header-icon">✋</div>
              <div class="sf-card-title">{T("Participation","المشاركة")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        RESPONSE_LABELS = {
            "C":  T("Correct (C)",              "صحيح (C)"),
            "P":  T("Partially Correct (P)",    "صحيح جزئيًا (P)"),
            "I":  T("Incorrect (I)",            "غير صحيح (I)"),
            "NR": T("No Response (NR)",         "لا استجابة (NR)"),
            "NO": T("No Opportunity (NO)",      "لم تُتَح الفرصة (NO)"),
        }
        SOURCE_LABELS = {
            "TS": T("Teacher Selected","اختيار المعلم"),
            "SI": T("Student Initiated","مبادرة الطالب"),
            "GP": T("Group","مجموعة"),
        }

        if part["total"] > 0:
            st.markdown('<div class="sf-card">', unsafe_allow_html=True)
            # Response breakdown
            st.markdown(
                f"**{T('By Response','حسب الاستجابة')}**",
                unsafe_allow_html=False,
            )
            resp_rows = [
                {T("Type","النوع"): RESPONSE_LABELS[k],
                 T("Count","العدد"): v}
                for k, v in part["by_response"].items() if v > 0
            ]
            if resp_rows:
                st.dataframe(
                    pd.DataFrame(resp_rows),
                    **full_width(), hide_index=True,
                )
            # Source breakdown
            src_rows = [
                {T("Source","المصدر"): SOURCE_LABELS.get(k, k),
                 T("Count","العدد"): v}
                for k, v in part["by_source"].items() if v > 0
            ]
            if src_rows:
                st.markdown(
                    f"**{T('By Source','حسب المصدر')}**",
                    unsafe_allow_html=False,
                )
                st.dataframe(
                    pd.DataFrame(src_rows),
                    **full_width(), hide_index=True,
                )

            # Important disclaimer
            st.caption(
                T(
                    "⚠️ No Response ≠ Incorrect · No Opportunity is not a failure · "
                    "Participation ≠ Academic attainment",
                    "⚠️ لا استجابة ≠ إجابة خاطئة · لم تُتَح الفرصة ليست إخفاقًا · "
                    "المشاركة ≠ التحصيل الأكاديمي",
                )
            )
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.caption(
                T("No participation records for this student yet.",
                  "لا توجد سجلات مشاركة لهذا الطالب بعد.")
            )

        # ── Skills ────────────────────────────────────────────────────────
        skills = profile["skills"]
        if skills:
            skill_names = {
                skill["id"]: skill.get("name", skill["id"])
                for skill in skill_definitions
                if isinstance(skill.get("id"), str)
            }
            st.markdown(
                f"""
                <div class="sf-card-header" style="direction:{_DIR};margin-top:0.9rem;">
                  <div class="sf-card-header-icon">🎯</div>
                  <div class="sf-card-title">{T("Skills Practised","المهارات المُمارَسة")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            skill_rows = [
                {
                    T("Skill", "المهارة"): skill_names.get(
                        skill_id,
                        T(f"Unlinked skill ID: {skill_id}", f"معرف مهارة غير مرتبط: {skill_id}"),
                    ),
                    T("Interactions", "تفاعلات"): count,
                }
                for skill_id, count in sorted(skills.items(), key=lambda item: -item[1])
            ]
            st.markdown('<div class="sf-card">', unsafe_allow_html=True)
            st.dataframe(
                pd.DataFrame(skill_rows),
                **full_width(), hide_index=True,
            )
            st.caption(
                T("Skills are logged per interaction — not academic assessments.",
                  "المهارات مسجّلة بناءً على التفاعلات، وليست تقييمات أكاديمية.")
            )
            st.markdown("</div>", unsafe_allow_html=True)

        unlinked_skills = profile.get("unlinked_skills", {})
        if unlinked_skills:
            st.markdown(
                f"""
                <div class="sf-card-header" style="direction:{_DIR};margin-top:0.9rem;">
                  <div class="sf-card-header-icon">🔗</div>
                  <div class="sf-card-title">
                    {T("Unlinked legacy skill labels", "أسماء مهارات قديمة غير مرتبطة")}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            unlinked_rows = [
                {T("Label", "الاسم"): label, T("Interactions", "تفاعلات"): count}
                for label, count in sorted(
                    unlinked_skills.items(), key=lambda item: -item[1]
                )
            ]
            st.dataframe(
                pd.DataFrame(unlinked_rows),
                **full_width(),
                hide_index=True,
            )
            st.caption(
                T(
                    "These legacy labels do not uniquely match an official skill.",
                    "هذه الأسماء القديمة لا تطابق مهارة معتمدة واحدة بشكل فريد.",
                )
            )

        # ── Link to Academic Progress / Interventions ──────────────────────
        code = profile["student_code"]
        btn_col_a, btn_col_b = st.columns(2)
        with btn_col_a:
            if st.button(
                T("🎯 Skill Progress", "🎯 تقدم المهارات"),
                key=f"sp_link_academic_{code}",
                **full_width(),
            ):
                st.session_state["skill_progress_student_code"] = code
                st.session_state["page"] = "academic_progress"
                st.rerun()
        with btn_col_b:
            if st.button(
                T("🛟 Interventions", "🛟 التدخلات"),
                key=f"sp_link_interventions_{code}",
                **full_width(),
            ):
                st.session_state["intervention_student_code"] = code
                st.session_state["page"] = "interventions"
                st.rerun()

        # ── Lesson attendance (from lesson_records) ────────────────────────
        if profile["lessons_total"] > 0:
            st.markdown(
                f"""
                <div class="sf-card" style="direction:{_DIR};margin-top:0.9rem;">
                  <div class="sf-card-header">
                    <div class="sf-card-header-icon">📖</div>
                    <div class="sf-card-title">
                      {T("Lesson Attendance (this session)","حضور الحصص (هذه الجلسة)")}
                    </div>
                  </div>
                  <div style="display:flex;gap:1.5rem;font-size:0.88rem;
                              color:#102B4E;direction:{_DIR};">
                    <div>✅ {T("Present/Late","حاضر/متأخر")}:
                      <strong>{profile["lessons_present"]}</strong></div>
                    <div>❌ {T("Absent","غائب")}:
                      <strong>{profile["lessons_absent"]}</strong></div>
                    <div>📋 {T("Total lessons","إجمالي الحصص")}:
                      <strong>{profile["lessons_total"]}</strong></div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _kpi(col, icon: str, label: str, value: str, sub: str) -> None:
    """Render a single KPI metric card inside a Streamlit column."""
    col.markdown(
        f"""
        <div class="sf-metric-card">
          <div class="sf-metric-icon sf-icon-green">{escape_html(icon)}</div>
          <div class="sf-metric-body">
            <div class="sf-metric-label">{escape_html(label)}</div>
            <div class="sf-metric-value" style="font-size:1.3rem;">{escape_html(value)}</div>
            <div class="sf-metric-sub">{escape_html(sub)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
