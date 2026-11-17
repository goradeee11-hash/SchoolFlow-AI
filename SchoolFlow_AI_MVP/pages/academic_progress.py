"""
pages/academic_progress.py
--------------------------
Skills & Academic Progress Tracking — SchoolFlow AI (Task 6).

What this page does
-------------------
1. Skill Definitions — teacher defines skills linked to subject/grade.
2. Skill Assessments  — teacher records per-student assessment scores
   for a specific skill (not participation — real scored evidence).
3. Progress View      — per-student skill mastery timeline, trend, and
   class-level overview.

Design rules
------------
* Academic attainment is COMPLETELY SEPARATE from participation.
  - Mastery is computed from assessment scores only.
  - Participation evidence is shown as optional context, never as a grade.
* No mastery level is assigned from a single assessment (N/A displayed).
* When data is absent, N/A is shown — nothing is fabricated.
* Bilingual (AR / EN) throughout; re-uses shared.i18n.T().
* Re-uses existing shared.styles CSS classes; no new global colours.
* Does NOT modify: lesson_records, participation_log, clean, summary,
  or any other pre-existing session_state keys.
* Only writes to: skill_definitions, skill_assessments,
  skill_progress_student_code (new navigation shortcut).
"""

from __future__ import annotations

import streamlit as st

if __name__ == "__main__":
    st.switch_page("app.py")

import pandas as pd
from datetime import date

import sys
import os
_HERE    = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_HERE)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from shared.i18n   import T, is_arabic, text_dir
from shared.html_utils import escape_html
from shared.streamlit_compat import full_width
from shared.audit import (
    ACTION_ASSESSMENT_CREATED,
    ACTION_SKILL_CREATED,
    ACTION_SKILL_REMOVED,
    ENTITY_ASSESSMENT,
    ENTITY_SKILL,
    log_event,
)
from shared.skills import (
    new_skill, add_skill, remove_skill, get_skill, skills_for_subject_grade,
    new_assessment, student_assessments,
    compute_skill_mastery, student_skills_summary, class_skills_overview,
    MIN_ASSESSMENTS_FOR_MASTERY, MASTERY_BANDS,
)
from shared.styles import PRIMARY_NAVY, WHITE


# ---------------------------------------------------------------------------
# Public entry point — called from app.py router
# ---------------------------------------------------------------------------

def render() -> None:
    """Render the Skills & Academic Progress page."""
    _IS_AR = is_arabic()
    _DIR   = text_dir()

    # ── Page header ───────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="sf-section-header" style="direction:{_DIR};">
          <div class="sf-section-num">🎯</div>
          <div class="sf-section-title">
            {T("Skills &amp; Academic Progress", "المهارات والتحصيل الأكاديمي")}
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
    has_name = st.session_state.get("has_name", False)
    participation_log = st.session_state.get("participation_log", [])

    # Ensure skills keys are initialised
    if "skill_definitions" not in st.session_state or st.session_state["skill_definitions"] is None:
        st.session_state["skill_definitions"] = []
    if "skill_assessments" not in st.session_state or st.session_state["skill_assessments"] is None:
        st.session_state["skill_assessments"] = []

    skill_defs = st.session_state["skill_definitions"]
    skill_ass  = st.session_state["skill_assessments"]

    student_codes = summary["Student code"].tolist()
    name_map: dict[str, str] = {}
    if has_name and "Student name" in summary.columns:
        name_map = dict(zip(summary["Student code"], summary["Student name"]))

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_labels = [
        T("📚 Skill Definitions",    "📚 تعريف المهارات"),
        T("📝 Record Assessment",    "📝 تسجيل التقييم"),
        T("📊 Student Progress",     "📊 تقدم الطالب"),
        T("🏫 Class Overview",       "🏫 نظرة عامة على الفصل"),
    ]
    tab1, tab2, tab3, tab4 = st.tabs(tab_labels)

    with tab1:
        _render_skill_definitions(_DIR, skill_defs)

    with tab2:
        _render_record_assessment(_DIR, skill_defs, skill_ass, student_codes, name_map)

    with tab3:
        _render_student_progress(_DIR, skill_defs, skill_ass, participation_log,
                                  student_codes, name_map)

    with tab4:
        _render_class_overview(_DIR, skill_defs, skill_ass, student_codes)


# ---------------------------------------------------------------------------
# Tab 1 — Skill Definitions
# ---------------------------------------------------------------------------

def _render_skill_definitions(_DIR: str, skill_defs: list[dict]) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.6rem;">
          <div class="sf-card-header-icon">📚</div>
          <div class="sf-card-title">
            {T("Define Teaching Skills", "تعريف المهارات التعليمية")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        T(
            "Define the skills you assess in your class. "
            "Link each skill to a subject and grade for easy filtering.",
            "عرِّف المهارات التي تقيّمها في فصلك. "
            "اربط كل مهارة بمادة ومرحلة دراسية لتسهيل التصفية.",
        )
    )

    # ── Add new skill form ─────────────────────────────────────────────
    with st.expander(T("➕ Add New Skill", "➕ إضافة مهارة جديدة"), expanded=len(skill_defs) == 0):
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            sk_name = st.text_input(
                T("Skill Name *", "اسم المهارة *"),
                placeholder=T("e.g. Reading Inference", "مثال: الاستنتاج من النص"),
                key="sk_name_input",
            )
        with c2:
            sk_subject = st.text_input(
                T("Subject", "المادة"),
                placeholder=T("e.g. English Language", "مثال: اللغة الإنجليزية"),
                key="sk_subject_input",
            )
        with c3:
            sk_grade = st.text_input(
                T("Grade", "الصف"),
                placeholder=T("e.g. Grade 5", "مثال: الصف الخامس"),
                key="sk_grade_input",
            )
        sk_desc = st.text_input(
            T("Description (optional)", "الوصف (اختياري)"),
            placeholder=T(
                "Brief description of what this skill covers",
                "وصف مختصر لما تغطيه هذه المهارة",
            ),
            key="sk_desc_input",
        )
        sk_obj_text = st.text_area(
            T(
                "Learning Objectives (one per line, optional)",
                "أهداف التعلم (هدف في كل سطر، اختياري)",
            ),
            height=80,
            placeholder=T(
                "e.g.\nIdentify the main idea\nInfer meaning from context",
                "مثال:\nتحديد الفكرة الرئيسية\nاستنتاج المعنى من السياق",
            ),
            key="sk_obj_input",
        )

        if st.button(T("Add Skill", "إضافة المهارة"), type="primary", key="btn_add_skill"):
            if not sk_name.strip():
                st.error(T("Skill name is required.", "اسم المهارة مطلوب."))
            else:
                objectives = [
                    ln.strip()
                    for ln in sk_obj_text.splitlines()
                    if ln.strip()
                ]
                try:
                    skill = new_skill(
                        name=sk_name,
                        subject=sk_subject,
                        grade=sk_grade,
                        description=sk_desc,
                        objectives=objectives,
                    )
                    st.session_state["skill_definitions"] = add_skill(skill_defs, skill)
                    role = st.session_state.get("active_role", "unknown")
                    if role not in {"teacher", "school_admin", "demo_reviewer"}:
                        role = "unknown"
                    st.session_state["audit_log"] = log_event(
                        st.session_state.get("audit_log", []),
                        action=ACTION_SKILL_CREATED,
                        actor_role=role,
                        entity_type=ENTITY_SKILL,
                    )
                    st.success(
                        T(
                            f"✅ Skill '{sk_name}' added.",
                            f"✅ تمت إضافة المهارة '{sk_name}'.",
                        )
                    )
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    # ── Existing skills list ───────────────────────────────────────────
    if not skill_defs:
        st.info(
            T(
                "No skills defined yet. Add your first skill above.",
                "لا توجد مهارات محددة بعد. أضف مهارتك الأولى أعلاه.",
            )
        )
        return

    st.markdown(
        f"**{T(f'{len(skill_defs)} skill(s) defined', f'{len(skill_defs)} مهارة معرَّفة')}**"
    )
    for sk in skill_defs:
        with st.container():
            col_info, col_del = st.columns([8, 1])
            with col_info:
                badge = (
                    f'<span style="background:{PRIMARY_NAVY};color:{WHITE};padding:2px 8px;'
                    f'border-radius:5px;font-size:0.76rem;font-weight:700;'
                    f'margin-right:6px;">{escape_html(sk["id"])}</span>'
                )
                detail = []
                if sk.get("subject"):
                    detail.append(T(sk["subject"], sk["subject"]))
                if sk.get("grade"):
                    detail.append(T(sk["grade"], sk["grade"]))
                detail_str = " · ".join(detail)
                objs_html = ""
                if sk.get("objectives"):
                    items = "".join(
                        f"<li>{escape_html(o)}</li>" for o in sk["objectives"]
                    )
                    objs_html = f'<ul style="margin:0.3rem 0 0 1.2rem;font-size:0.78rem;color:#102B4E;">{items}</ul>'
                st.markdown(
                    f'<div style="direction:{text_dir()};padding:0.4rem 0;">'
                    f'{badge}<strong>{escape_html(sk["name"])}</strong>'
                    + (f' &nbsp;<span style="font-size:0.78rem;color:#435F76;">{escape_html(detail_str)}</span>' if detail_str else "")
                    + (f'<div style="font-size:0.80rem;color:#435F76;margin-top:0.2rem;">{escape_html(sk["description"])}</div>' if sk.get("description") else "")
                    + objs_html
                    + "</div>",
                    unsafe_allow_html=True,
                )
            with col_del:
                if st.button(
                    "🗑",
                    key=f"del_skill_{sk['id']}",
                    help=T(f"Remove skill '{sk['name']}'", f"حذف مهارة '{sk['name']}'"),
                ):
                    st.session_state["skill_definitions"] = remove_skill(
                        st.session_state["skill_definitions"], sk["id"]
                    )
                    role = st.session_state.get("active_role", "unknown")
                    if role not in {"teacher", "school_admin", "demo_reviewer"}:
                        role = "unknown"
                    st.session_state["audit_log"] = log_event(
                        st.session_state.get("audit_log", []),
                        action=ACTION_SKILL_REMOVED,
                        actor_role=role,
                        entity_type=ENTITY_SKILL,
                    )
                    st.rerun()


# ---------------------------------------------------------------------------
# Tab 2 — Record Assessment
# ---------------------------------------------------------------------------

def _render_record_assessment(
    _DIR: str,
    skill_defs: list[dict],
    skill_ass: list[dict],
    student_codes: list[str],
    name_map: dict[str, str],
) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.6rem;">
          <div class="sf-card-header-icon">📝</div>
          <div class="sf-card-title">
            {T("Record Skill Assessment", "تسجيل تقييم مهارة")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        T(
            "Record a scored assessment for a specific student and skill. "
            "Participation in class is NOT an assessment — only enter deliberate, "
            "scored evidence here.",
            "سجّل تقييمًا بدرجة لطالب محدد ومهارة معينة. "
            "المشاركة الصفية ليست تقييمًا — أدخل هنا الأدلة الموثَّقة بدرجات فعلية فقط.",
        )
    )

    if not skill_defs:
        st.warning(
            T(
                "⚠️ Please define at least one skill first (Skill Definitions tab).",
                "⚠️ يرجى تعريف مهارة واحدة على الأقل أولاً (تبويب تعريف المهارات).",
            )
        )
        return

    # Build skill options
    skill_opts = {f"{s['id']}  —  {s['name']}": s["id"] for s in skill_defs}
    student_opts = [
        f"{c} — {name_map[c]}" if c in name_map else c
        for c in student_codes
    ]

    c1, c2 = st.columns(2)
    with c1:
        chosen_student_disp = st.selectbox(
            T("Student", "الطالب"),
            student_opts,
            key="ass_student_sel",
        )
        chosen_code = student_codes[student_opts.index(chosen_student_disp)]

    with c2:
        chosen_skill_disp = st.selectbox(
            T("Skill", "المهارة"),
            list(skill_opts.keys()),
            key="ass_skill_sel",
        )
        chosen_skill_id = skill_opts[chosen_skill_disp]

    c3, c4, c5 = st.columns([2, 2, 2])
    with c3:
        score_val = st.number_input(
            T("Score achieved", "الدرجة المحققة"),
            min_value=0.0,
            value=0.0,
            step=0.5,
            key="ass_score",
        )
    with c4:
        max_val = st.number_input(
            T("Maximum score", "الدرجة الكاملة"),
            min_value=0.5,
            value=10.0,
            step=0.5,
            key="ass_max",
        )
    with c5:
        ass_date = st.date_input(
            T("Assessment date", "تاريخ التقييم"),
            value=date.today(),
            key="ass_date",
        )

    ass_notes = st.text_input(
        T("Notes (optional)", "ملاحظات (اختياري)"),
        placeholder=T(
            "e.g. formal test, worksheet, oral reading check",
            "مثال: اختبار رسمي، ورقة عمل، قراءة شفهية",
        ),
        key="ass_notes",
    )

    if st.button(
        T("Save Assessment", "حفظ التقييم"),
        type="primary",
        key="btn_save_assessment",
    ):
        if score_val > max_val:
            st.error(
                T(
                    "Score cannot exceed the maximum score.",
                    "لا يمكن أن تتجاوز الدرجة الحد الأقصى.",
                )
            )
        else:
            rec = new_assessment(
                skill_id=chosen_skill_id,
                student_code=chosen_code,
                score=score_val,
                max_score=max_val,
                date=str(ass_date),
                notes=ass_notes,
            )
            st.session_state["skill_assessments"] = skill_ass + [rec]
            role = st.session_state.get("active_role", "unknown")
            if role not in {"teacher", "school_admin", "demo_reviewer"}:
                role = "unknown"
            st.session_state["audit_log"] = log_event(
                st.session_state.get("audit_log", []),
                action=ACTION_ASSESSMENT_CREATED,
                actor_role=role,
                entity_type=ENTITY_ASSESSMENT,
            )
            pct = round(score_val / max_val * 100, 1)
            st.success(
                T(
                    f"✅ Assessment saved: {chosen_code} — {score_val}/{max_val} "
                    f"({pct}%) on skill '{chosen_skill_id}'.",
                    f"✅ تم حفظ التقييم: {chosen_code} — {score_val}/{max_val} "
                    f"({pct}%) في مهارة '{chosen_skill_id}'.",
                )
            )
            st.rerun()

    # ── Recent assessments table ───────────────────────────────────────
    if skill_ass:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f"**{T('Recent Assessments', 'آخر التقييمات')}** "
            f"({T(f'{len(skill_ass)} total', f'الإجمالي: {len(skill_ass)}')})"
        )
        # Build display rows (most recent first)
        display_rows = []
        for r in reversed(skill_ass[-30:]):
            sk = get_skill(skill_defs, r.get("skill_id", ""))
            sk_name = sk["name"] if sk else r.get("skill_id", "")
            pct = round(r["score"] / r["max_score"] * 100, 1) if r["max_score"] else 0
            display_rows.append({
                T("Date", "التاريخ"):         r.get("date", ""),
                T("Student", "الطالب"):       r.get("student_code", ""),
                T("Skill", "المهارة"):        sk_name,
                T("Score", "الدرجة"):         f"{r['score']}/{r['max_score']}",
                T("Percentage", "النسبة"):    f"{pct}%",
                T("Notes", "ملاحظات"):        r.get("notes", ""),
            })
        st.markdown('<div class="sf-card">', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(display_rows), **full_width(), hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.caption(
            T(
                "⚠️ These are recorded assessment scores — not participation grades.",
                "⚠️ هذه درجات تقييمات مسجّلة — وليست درجات مشاركة.",
            )
        )


# ---------------------------------------------------------------------------
# Tab 3 — Student Progress
# ---------------------------------------------------------------------------

def _render_student_progress(
    _DIR: str,
    skill_defs: list[dict],
    skill_ass: list[dict],
    participation_log: list[dict],
    student_codes: list[str],
    name_map: dict[str, str],
) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.6rem;">
          <div class="sf-card-header-icon">📊</div>
          <div class="sf-card-title">
            {T("Student Skill Progress", "تقدم مهارات الطالب")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Honour navigation shortcut from Student Profile
    pre = st.session_state.get("skill_progress_student_code", "")
    default_idx = 0
    if pre in student_codes:
        default_idx = student_codes.index(pre)

    student_opts = [
        f"{c} — {name_map[c]}" if c in name_map else c
        for c in student_codes
    ]
    sel_col, _ = st.columns([3, 5])
    with sel_col:
        chosen_disp = st.selectbox(
            T("Select student", "اختر الطالب"),
            student_opts,
            index=default_idx,
            key="sp_student_sel",
        )
    chosen_code = student_codes[student_opts.index(chosen_disp)]
    st.session_state["skill_progress_student_code"] = chosen_code

    # Build student summary
    summary_rows = student_skills_summary(
        student_code=chosen_code,
        skill_definitions=skill_defs,
        assessment_records=skill_ass,
        participation_log=participation_log,
    )

    if not summary_rows:
        st.info(
            T(
                "No skill data available for this student yet. "
                "Add skill definitions and record assessments, or run a lesson "
                "with skill tags in the participation log.",
                "لا توجد بيانات مهارات لهذا الطالب بعد. "
                "أضف تعريفات للمهارات وسجّل التقييمات، أو شغّل حصة مع وسم المهارات "
                "في سجل المشاركة.",
            )
        )
        return

    # ── Skill cards ────────────────────────────────────────────────────
    for row in summary_rows:
        m = row["mastery"]
        _render_skill_card(row, m, _DIR)

    # ── Disclaimer + link to Interventions ────────────────────────────
    st.caption(
        T(
            "⚠️ Mastery levels are computed from assessment scores only. "
            f"At least {MIN_ASSESSMENTS_FOR_MASTERY} assessments are required before "
            "a mastery level is shown. Participation evidence is contextual only.",
            f"⚠️ تُحتسب مستويات الإتقان من درجات التقييم فقط. "
            f"يلزم {MIN_ASSESSMENTS_FOR_MASTERY} تقييمات على الأقل قبل عرض مستوى الإتقان. "
            "المشاركة الصفية بيانات سياقية فقط.",
        )
    )
    if st.button(
        T("🛟 View / Create Interventions for this student",
          "🛟 عرض / إنشاء تدخلات لهذا الطالب"),
        key=f"ap_link_interventions_{chosen_code}",
    ):
        st.session_state["intervention_student_code"] = chosen_code
        st.session_state["page"] = "interventions"
        st.rerun()


def _render_skill_card(row: dict, m: dict, _DIR: str) -> None:
    """Render a single skill progress card."""
    skill_name = row["skill_name"]
    if row.get("skill_linked") is False:
        skill_name = T(
            f"Unlinked skill: {skill_name}",
            f"مهارة غير مرتبطة: {skill_name}",
        )
    subject    = row.get("subject", "")
    grade      = row.get("grade", "")

    # Mastery badge colour
    mastery_en = m.get("mastery_level")
    mastery_ar = m.get("mastery_level_ar")
    mastery_label = (
        T(mastery_en, mastery_ar) if mastery_en else T("N/A", "غير متاح")
    )
    if mastery_en == "Secure":
        badge_color = "#16a34a"; badge_bg = "rgba(22,163,74,0.10)"
    elif mastery_en == "Developing":
        badge_color = "#2563eb"; badge_bg = "rgba(37,99,235,0.10)"
    elif mastery_en == "Emerging":
        badge_color = "#D4A017"; badge_bg = "rgba(212,160,23,0.12)"
    elif mastery_en == "Beginning":
        badge_color = "#dc2626"; badge_bg = "rgba(220,38,38,0.10)"
    else:
        badge_color = "#6B7280"; badge_bg = "rgba(107,114,128,0.10)"

    # Trend icon
    trend = m.get("trend", "N/A")
    trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️"}.get(trend, "—")
    trend_label = {
        "improving": T("Improving", "في تحسن"),
        "declining": T("Needs attention", "يحتاج متابعة"),
        "stable":    T("Stable", "مستقر"),
        "N/A":       T("N/A", "غير متاح"),
    }.get(trend, "—")

    # Scores SVG sparkline
    scores = m.get("scores_pct", [])
    dates  = m.get("dates", [])
    sparkline = _build_sparkline(scores)

    # Participation context (not academic)
    part_total = (
        row["participation_c"]
        + row["participation_p"]
        + row["participation_i"]
        + row["participation_nr"]
        + row["participation_no"]
    )
    part_html = ""
    if part_total > 0:
        part_html = (
            f'<div style="font-size:0.76rem;color:#435F76;margin-top:0.5rem;'
            f'direction:{_DIR};">'
            f'<em>{T("Class participation (context only, not a grade):", "المشاركة الصفية (سياق فقط، ليست تقييمًا):")}</em> '
            f'C:{row["participation_c"]} P:{row["participation_p"]} '
            f'I:{row["participation_i"]} NR:{row["participation_nr"]} '
            f'NO:{row["participation_no"]}'
            f'</div>'
        )

    # Assessment count
    ass_count = m.get("count", 0)
    if ass_count < MIN_ASSESSMENTS_FOR_MASTERY and ass_count > 0:
        mastery_note = T(
            f"({ass_count}/{MIN_ASSESSMENTS_FOR_MASTERY} assessments — more needed for mastery level)",
            f"({ass_count}/{MIN_ASSESSMENTS_FOR_MASTERY} تقييمات — يلزم المزيد لتحديد مستوى الإتقان)",
        )
    elif ass_count == 0:
        mastery_note = T(
            "(No assessments recorded — only participation data available)",
            "(لا توجد تقييمات مسجّلة — البيانات المتاحة من المشاركة فقط)",
        )
    else:
        mastery_note = ""

    # Mean / latest pct
    mean_str   = f"{m['mean_pct']:.1f}%" if m["mean_pct"] is not None else T("N/A", "غير متاح")
    latest_str = f"{m['latest_pct']:.1f}%" if m["latest_pct"] is not None else T("N/A", "غير متاح")

    detail_line = []
    if subject:
        detail_line.append(subject)
    if grade:
        detail_line.append(grade)
    detail_str = " · ".join(detail_line)

    st.markdown(
        f"""
        <div class="sf-card" style="direction:{_DIR};margin-bottom:0.9rem;">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;
                      flex-wrap:wrap;gap:0.5rem;">
            <div>
              <span style="font-weight:700;font-size:0.95rem;color:{PRIMARY_NAVY};">{escape_html(skill_name)}</span>
              {f'<span style="font-size:0.76rem;color:#435F76;margin-left:8px;">{escape_html(detail_str)}</span>' if detail_str else ''}
            </div>
            <span style="background:{badge_bg};color:#102B4E;
                         border:1px solid {badge_color}33;
                         border-radius:20px;padding:2px 12px;
                         font-size:0.78rem;font-weight:700;white-space:nowrap;">
              {mastery_label}
            </span>
          </div>
          <div style="display:flex;gap:2rem;margin-top:0.5rem;flex-wrap:wrap;">
            <div style="font-size:0.82rem;color:#102B4E;">
              {T("Assessments:", "التقييمات:")} <strong>{ass_count}</strong>
            </div>
            <div style="font-size:0.82rem;color:#102B4E;">
              {T("Mean:", "المتوسط:")} <strong>{mean_str}</strong>
            </div>
            <div style="font-size:0.82rem;color:#102B4E;">
              {T("Latest:", "الأخير:")} <strong>{latest_str}</strong>
            </div>
            <div style="font-size:0.82rem;color:#102B4E;">
              {T("Trend:", "الاتجاه:")} <strong>{trend_icon} {trend_label}</strong>
            </div>
          </div>
          {f'<div style="font-size:0.75rem;color:#435F76;margin-top:0.3rem;">{mastery_note}</div>' if mastery_note else ''}
          {sparkline}
          {part_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _build_sparkline(scores: list[float]) -> str:
    """Build a small SVG sparkline for a list of percentage scores."""
    if len(scores) < 2:
        if len(scores) == 1:
            return (
                f'<div style="font-size:0.76rem;color:#435F76;margin-top:0.4rem;">'
                f'Score: {scores[0]:.1f}%</div>'
            )
        return ""

    W, H = 220, 48
    pad_l, pad_r, pad_t, pad_b = 6, 6, 6, 6
    chart_w = W - pad_l - pad_r
    chart_h = H - pad_t - pad_b
    n = len(scores)

    def xp(i):
        return pad_l + i * chart_w / (n - 1)

    def yp(v):
        clamped = max(0, min(v, 100))
        return pad_t + chart_h * (1 - clamped / 100)

    pts = " ".join(f"{xp(i):.1f},{yp(v):.1f}" for i, v in enumerate(scores))
    dots = "".join(
        f'<circle cx="{xp(i):.1f}" cy="{yp(v):.1f}" r="3" fill="#B7D957" '
        f'stroke="#102B4E" stroke-width="1"><title>{v:.1f}%</title></circle>'
        for i, v in enumerate(scores)
    )
    # Dashed 60% reference line
    ref_y = yp(60)
    ref_line = (
        f'<line x1="{pad_l}" y1="{ref_y:.1f}" x2="{W - pad_r}" y2="{ref_y:.1f}" '
        f'stroke="#A9C0D5" stroke-width="1" stroke-dasharray="3,3"/>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:220px;height:48px;display:block;margin-top:0.4rem;">'
        f'{ref_line}'
        f'<polyline points="{pts}" fill="none" stroke="#102B4E" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'{dots}'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# Tab 4 — Class Overview
# ---------------------------------------------------------------------------

def _render_class_overview(
    _DIR: str,
    skill_defs: list[dict],
    skill_ass: list[dict],
    student_codes: list[str],
) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.6rem;">
          <div class="sf-card-header-icon">🏫</div>
          <div class="sf-card-title">
            {T("Class Skills Overview", "نظرة عامة على مهارات الفصل")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        T(
            "Academic attainment only — based on recorded assessment scores. "
            "Participation is excluded from this view.",
            "التحصيل الأكاديمي فقط — مبني على درجات التقييمات المسجّلة. "
            "المشاركة الصفية مستبعدة من هذه النظرة.",
        )
    )

    overview_df = class_skills_overview(
        student_codes=student_codes,
        skill_definitions=skill_defs,
        assessment_records=skill_ass,
    )

    if overview_df.empty:
        st.info(
            T(
                "No assessment data available yet. "
                "Record assessments in the 'Record Assessment' tab.",
                "لا توجد بيانات تقييم بعد. "
                "سجّل التقييمات في تبويب 'تسجيل التقييم'.",
            )
        )
        return

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.dataframe(
        overview_df,
        **full_width(),
        hide_index=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Needs support highlight ────────────────────────────────────────
    beginning_rows = overview_df[overview_df["Mastery Level"].isin(["Beginning", "Emerging"])]
    if not beginning_rows.empty:
        st.markdown(
            f"""
            <div style="background:rgba(220,38,38,0.12);border:1px solid rgba(220,38,38,0.45);
                        border-radius:9px;padding:0.6rem 1rem;font-size:0.82rem;
                        color:#102B4E;margin-top:0.8rem;direction:{_DIR};">
              <strong>
                {T("Skills needing more practice:", "مهارات تحتاج مزيدًا من التدريب:")}
              </strong><br>
              {", ".join(
                  f"{escape_html(r['Student code'])} / {escape_html(r['Skill'])}"
                  for _, r in beginning_rows.iterrows()
              )}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Clear progress highlight ───────────────────────────────────────
    improving_rows = overview_df[overview_df["Trend"] == "improving"]
    if not improving_rows.empty:
        st.markdown(
            f"""
            <div style="background:rgba(22,163,74,0.12);border:1px solid rgba(22,163,74,0.45);
                        border-radius:9px;padding:0.6rem 1rem;font-size:0.82rem;
                        color:#102B4E;margin-top:0.5rem;direction:{_DIR};">
              <strong>
                {T("Clear progress:", "تقدم واضح:")}
              </strong>
              📈 {", ".join(
                  f"{escape_html(r['Student code'])} / {escape_html(r['Skill'])}"
                  for _, r in improving_rows.iterrows()
              )}
            </div>
            """,
            unsafe_allow_html=True,
        )
