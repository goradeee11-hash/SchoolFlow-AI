"""
pages/interventions.py
-----------------------
Student Interventions & Recommendations — SchoolFlow AI (Task 7).

What this page does
-------------------
1. Auto-Flags  — scan all students × skills; surface those where
   academic evidence (≥2 assessments, low mastery) suggests
   the teacher may want to consider additional support.
2. Create Intervention — teacher reviews a flag, edits the reason
   and proposed action, sets MTSS tier, then saves it as "Proposed".
3. Manage Interventions — teacher can view all interventions,
   update status (Proposed → Approved → In Progress → Completed),
   set MTSS tier, add notes.
4. Progress Tracking — after an intervention is In Progress,
   the teacher can record post-intervention assessment checkpoints
   and see a before/after comparison.

Design rules
------------
* Teacher is ALWAYS the decision-maker — nothing is auto-approved or
  auto-started.
* Participation data alone NEVER triggers a flag.
* MTSS tiers describe support intensity, NOT permanent student identity.
* No diagnosis or clinical judgement is produced.
* No data is fabricated when absent — N/A is shown.
* Bilingual (AR / EN) throughout; re-uses shared.i18n.T().
* Re-uses existing shared.styles CSS classes; no new global colours.
* Does NOT modify: lesson_records, participation_log, clean, summary,
  skill_definitions, skill_assessments, or any pre-existing state keys.
* Only writes to: interventions, intervention_checkpoints,
  intervention_student_code.
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

from shared.i18n import T, is_arabic, text_dir
from shared.html_utils import escape_html
from shared.streamlit_compat import full_width
from shared.audit import (
    ACTION_CHECKPOINT_ADDED,
    ACTION_INTERVENTION_CREATED,
    ACTION_INTERVENTION_UPDATED,
    ENTITY_CHECKPOINT,
    ENTITY_INTERVENTION,
    log_event,
)
from shared.interventions import (
    new_intervention,
    update_intervention,
    add_intervention,
    replace_intervention,
    get_intervention,
    student_interventions,
    active_interventions,
    flag_students_for_intervention,
    new_progress_checkpoint,
    intervention_checkpoints,
    compare_before_after,
    timestamp_sort_key,
    INTERVENTION_STATUSES,
    MTSS_TIERS,
    SUGGESTED_ACTIVITIES,
)
from shared.time_utils import format_timestamp_riyadh


# ---------------------------------------------------------------------------
# Public entry point — called from app.py router
# ---------------------------------------------------------------------------

def render() -> None:
    """Render the Interventions & Recommendations page."""
    _IS_AR = is_arabic()
    _DIR   = text_dir()

    # ── Page header ───────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="sf-section-header" style="direction:{_DIR};">
          <div class="sf-section-num">🛟</div>
          <div class="sf-section-title">
            {T("Student Interventions &amp; Recommendations",
               "التدخلات والتوصيات للطلاب")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Guard: data must be loaded ────────────────────────────────────────
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

    # Ensure all keys are initialised
    for key in ("interventions", "intervention_checkpoints",
                "skill_definitions", "skill_assessments"):
        if st.session_state.get(key) is None:
            st.session_state[key] = []

    interventions     = st.session_state["interventions"]
    checkpoints       = st.session_state["intervention_checkpoints"]
    skill_defs        = st.session_state["skill_definitions"]
    skill_ass         = st.session_state["skill_assessments"]

    student_codes = summary["Student code"].tolist()
    name_map: dict[str, str] = {}
    if has_name and "Student name" in summary.columns:
        name_map = dict(zip(summary["Student code"], summary["Student name"]))

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_labels = [
        T("🔍 Suggested Flags",      "🔍 الإشارات المقترحة"),
        T("➕ Create Intervention",  "➕ إنشاء تدخل"),
        T("📋 Manage Interventions", "📋 إدارة التدخلات"),
        T("📈 Progress Tracking",    "📈 متابعة التقدم"),
    ]
    tab1, tab2, tab3, tab4 = st.tabs(tab_labels)

    with tab1:
        _render_flags(_DIR, skill_defs, skill_ass, interventions,
                      student_codes, name_map)
    with tab2:
        _render_create(_DIR, skill_defs, skill_ass, interventions,
                       student_codes, name_map)
    with tab3:
        _render_manage(_DIR, interventions, checkpoints,
                       student_codes, name_map)
    with tab4:
        _render_progress(_DIR, interventions, checkpoints,
                         student_codes, name_map)


# ---------------------------------------------------------------------------
# Tab 1 — Suggested Flags
# ---------------------------------------------------------------------------

def _render_flags(
    _DIR: str,
    skill_defs: list[dict],
    skill_ass: list[dict],
    interventions: list[dict],
    student_codes: list[str],
    name_map: dict[str, str],
) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.5rem;">
          <div class="sf-card-header-icon">🔍</div>
          <div class="sf-card-title">
            {T("Automatically Suggested Flags", "الإشارات المقترحة تلقائيًا")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        T(
            "These flags are based on academic assessment data only "
            "(≥2 assessments, low mastery). "
            "No flag uses participation data alone. "
            "The teacher reviews and decides — nothing is applied automatically.",
            "هذه الإشارات مبنية على بيانات التقييم الأكاديمي فقط "
            "(تقييمان أو أكثر، مستوى إتقان منخفض). "
            "لا تعتمد أي إشارة على المشاركة الصفية وحدها. "
            "المعلم يراجع ويقرر — لا شيء يُطبَّق تلقائيًا.",
        )
    )

    if not skill_defs:
        st.info(
            T(
                "No skill definitions found. "
                "Define skills in the Skills & Progress page first.",
                "لا توجد تعريفات مهارات. "
                "عرِّف المهارات في صفحة المهارات والتحصيل أولاً.",
            )
        )
        return

    flags = flag_students_for_intervention(
        student_codes=student_codes,
        skill_definitions=skill_defs,
        assessment_records=skill_ass,
        existing_interventions=interventions,
    )

    if not flags:
        st.success(
            T(
                "✅ No flags at this time. "
                "Either all assessed skills show adequate mastery, "
                "or insufficient assessment data exists.",
                "✅ لا توجد إشارات في الوقت الحالي. "
                "إما أن جميع المهارات المقيَّمة تُظهر إتقانًا كافيًا، "
                "أو أن بيانات التقييم غير كافية بعد.",
            )
        )
        return

    st.markdown(
        f"<div style='font-size:0.82rem;color:#102B4E;direction:{_DIR};margin-bottom:0.6rem;'>"
        + T(
            f"<strong>{len(flags)} flag(s)</strong> found — review below and "
            "use 'Create Intervention' tab to act on any.",
            f"<strong>{len(flags)} إشارة</strong> — راجعها أدناه "
            "واستخدم تبويب 'إنشاء تدخل' للتصرف.",
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    for flag in flags:
        _render_flag_card(flag, name_map, _DIR)


def _render_flag_card(flag: dict, name_map: dict[str, str], _DIR: str) -> None:
    code = flag["student_code"]
    display = f"{code} — {name_map[code]}" if code in name_map else code
    ml = flag["mastery_level"]
    ml_ar = flag.get("mastery_level_ar", ml)
    if ml == "Beginning":
        badge_color = "#dc2626"; badge_bg = "rgba(220,38,38,0.08)"
    else:  # Emerging
        badge_color = "#D4A017"; badge_bg = "rgba(212,160,23,0.10)"

    trend = flag.get("trend", "N/A")
    trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️"}.get(trend, "—")

    st.markdown(
        f"""
        <div class="sf-card" style="direction:{_DIR};margin-bottom:0.75rem;
             border-left:4px solid {badge_color};">
          <div style="display:flex;justify-content:space-between;
                      flex-wrap:wrap;gap:0.4rem;align-items:flex-start;">
            <div>
              <strong>{escape_html(display)}</strong>
              <span style="margin-left:8px;font-size:0.80rem;color:#435F76;">
                {T("Skill:", "المهارة:")} {escape_html(flag['skill_name'])}
              </span>
            </div>
            <span style="background:{badge_bg};color:#102B4E;
                         border:1px solid {badge_color}33;
                         border-radius:20px;padding:2px 10px;
                         font-size:0.76rem;font-weight:700;">
              {T(ml, ml_ar)}
            </span>
          </div>
          <div style="display:flex;gap:1.5rem;margin-top:0.4rem;font-size:0.80rem;
                      color:#102B4E;flex-wrap:wrap;">
            <span>{T("Assessments:", "التقييمات:")}
              <strong>{flag['assessment_count']}</strong></span>
            <span>{T("Mean:", "المتوسط:")}
              <strong>{flag['mean_pct']:.1f}%</strong></span>
            <span>{T("Latest:", "الأخير:")}
              <strong>{flag['latest_pct']:.1f}%</strong></span>
            <span>{T("Trend:", "الاتجاه:")}
              <strong>{trend_icon} {escape_html(trend)}</strong></span>
          </div>
          <div style="font-size:0.76rem;color:#435F76;margin-top:0.35rem;">
            {T("Suggested starting point:", "نقطة انطلاق مقترحة:")}
            <em>{escape_html(flag['suggested_action'] or T("—", "—"))}</em>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Tab 2 — Create Intervention
# ---------------------------------------------------------------------------

def _render_create(
    _DIR: str,
    skill_defs: list[dict],
    skill_ass: list[dict],
    interventions: list[dict],
    student_codes: list[str],
    name_map: dict[str, str],
) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.5rem;">
          <div class="sf-card-header-icon">➕</div>
          <div class="sf-card-title">
            {T("Create New Intervention", "إنشاء تدخل جديد")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        T(
            "Review the suggested reason and action, edit as needed, "
            "then save. The intervention will be saved as 'Proposed' — "
            "you approve it in the Manage tab.",
            "راجع السبب والإجراء المقترح وعدِّلهما عند الحاجة، ثم احفظ. "
            "يُحفظ التدخل بحالة 'مقترح' — تُوافق عليه في تبويب الإدارة.",
        )
    )

    student_opts = [
        f"{c} — {name_map[c]}" if c in name_map else c
        for c in student_codes
    ]

    # Honour pre-selection from other pages
    pre = st.session_state.get("intervention_student_code", "")
    default_idx = 0
    if pre in student_codes:
        default_idx = student_codes.index(pre)

    c1, c2 = st.columns(2)
    with c1:
        chosen_disp = st.selectbox(
            T("Student", "الطالب"),
            student_opts,
            index=default_idx,
            key="int_create_student",
        )
        chosen_code = student_codes[student_opts.index(chosen_disp)]
        st.session_state["intervention_student_code"] = chosen_code

    # Skill selector — show only skills this student has assessments for first
    skill_opts_all = {
        f"{s['id']}  —  {s['name']}": s["id"] for s in skill_defs
    }
    # If no skill_defs, allow free-text entry
    if not skill_opts_all:
        with c2:
            st.warning(
                T(
                    "Define skills in the Skills & Progress page first.",
                    "عرِّف المهارات في صفحة المهارات والتحصيل أولاً.",
                )
            )
        return

    with c2:
        chosen_skill_disp = st.selectbox(
            T("Skill", "المهارة"),
            list(skill_opts_all.keys()),
            key="int_create_skill",
        )
        chosen_skill_id = skill_opts_all[chosen_skill_disp]

    # Look up skill name
    skill_obj = next((s for s in skill_defs if s["id"] == chosen_skill_id), None)
    skill_name = skill_obj["name"] if skill_obj else chosen_skill_id

    # Pull pre-computed mastery for this student × skill
    from shared.skills import student_assessments, compute_skill_mastery
    ass = student_assessments(skill_ass, chosen_code, skill_id=chosen_skill_id)
    mastery = compute_skill_mastery(ass)

    # Show evidence summary
    ml    = mastery["mastery_level"]
    ml_ar = mastery.get("mastery_level_ar")
    ml_disp = T(ml, ml_ar) if ml else T("N/A (insufficient data)", "غير متاح (بيانات غير كافية)")
    _ev_color = "#6B7280"
    if ml == "Beginning":
        _ev_color = "#dc2626"
    elif ml == "Emerging":
        _ev_color = "#D4A017"
    elif ml == "Secure":
        _ev_color = "#16a34a"
    elif ml == "Developing":
        _ev_color = "#2563eb"

    st.markdown(
        f"""
        <div style="background:var(--sf-surface-raised);border:1px solid #A9C0D5;border-radius:9px;
                    padding:0.6rem 1rem;margin:0.5rem 0;font-size:0.82rem;
                    direction:{_DIR};">
          <strong>{T("Evidence at this time:", "الأدلة المتاحة حاليًا:")}</strong>
          &nbsp;{T("Assessments:", "التقييمات:")} <strong>{mastery['count']}</strong>
          &nbsp;·&nbsp;{T("Mean:", "المتوسط:")}
          <strong>{f"{mastery['mean_pct']:.1f}%" if mastery['mean_pct'] is not None else "N/A"}</strong>
          &nbsp;·&nbsp;{T("Mastery:", "الإتقان:")}
          <strong style="color:{_ev_color};">{ml_disp}</strong>
          &nbsp;·&nbsp;{T("Trend:", "الاتجاه:")} <strong>{mastery['trend']}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if mastery["count"] < 2:
        st.warning(
            T(
                "⚠️ Fewer than 2 assessments recorded for this skill. "
                "You may still create an intervention, but the evidence "
                "is limited. Consider recording more assessments first.",
                "⚠️ أقل من تقييمين مسجَّلَين لهذه المهارة. "
                "يمكنك إنشاء تدخل، لكن الأدلة محدودة. "
                "فكِّر في تسجيل المزيد من التقييمات أولاً.",
            )
        )

    # Pre-fill reason and action from suggestion (teacher edits)
    suggested_actions = SUGGESTED_ACTIVITIES.get(ml or "", [])
    suggested_action_text = suggested_actions[0] if suggested_actions else ""
    reason_template = (
        f"Student {chosen_code} — skill '{skill_name}' — "
        f"mean: {mastery['mean_pct']:.1f}% — "
        f"mastery: {ml or 'N/A'}"
    ) if mastery["mean_pct"] is not None else (
        f"Student {chosen_code} — skill '{skill_name}' (manual intervention)"
    )

    reason_val = st.text_area(
        T(
            "Reason for intervention (edit before saving)",
            "سبب التدخل (عدِّله قبل الحفظ)",
        ),
        value=reason_template,
        height=80,
        key="int_reason",
    )
    action_val = st.text_area(
        T(
            "Proposed action / strategy (edit before saving)",
            "الإجراء / الاستراتيجية المقترحة (عدِّلها قبل الحفظ)",
        ),
        value=suggested_action_text,
        height=80,
        key="int_action",
    )

    tier_opts = {f"{v[0]}": k for k, v in MTSS_TIERS.items()}
    tier_labels_ar = {k: v[1] for k, v in MTSS_TIERS.items()}
    tier_display = [
        T(v[0], v[1]) for k, v in MTSS_TIERS.items()
    ]
    c3, c4 = st.columns(2)
    with c3:
        chosen_tier_disp = st.selectbox(
            T("MTSS Tier (optional — teacher decides)", "مستوى MTSS (اختياري — المعلم يقرر)"),
            tier_display,
            key="int_tier",
            help=T(
                "MTSS tiers describe support intensity — not a permanent student label.",
                "مستويات MTSS تصف شدة الدعم — وليست هوية ثابتة للطالب.",
            ),
        )
        chosen_tier = list(MTSS_TIERS.keys())[tier_display.index(chosen_tier_disp)]

    with c4:
        int_start = st.date_input(
            T("Proposed start date", "تاريخ البدء المقترح"),
            value=date.today(),
            key="int_start_date",
        )

    notes_val = st.text_input(
        T("Initial notes (optional)", "ملاحظات أولية (اختياري)"),
        key="int_notes",
    )

    if st.button(
        T("💾 Save as Proposed", "💾 حفظ كمقترح"),
        type="primary",
        key="btn_save_intervention",
    ):
        try:
            rec = new_intervention(
                student_code=chosen_code,
                skill_id=chosen_skill_id,
                skill_name=skill_name,
                reason=reason_val,
                proposed_action=action_val,
                evidence_snapshot=mastery,
                mtss_tier=chosen_tier,
                start_date=str(int_start),
                teacher_notes=notes_val,
            )
            st.session_state["interventions"] = add_intervention(
                st.session_state["interventions"], rec
            )
            role = st.session_state.get("active_role", "unknown")
            if role not in {"teacher", "school_admin", "demo_reviewer"}:
                role = "unknown"
            st.session_state["audit_log"] = log_event(
                st.session_state.get("audit_log", []),
                action=ACTION_INTERVENTION_CREATED,
                actor_role=role,
                entity_type=ENTITY_INTERVENTION,
            )
            st.success(
                T(
                    f"✅ Intervention saved for {chosen_code} / '{skill_name}'. "
                    "Review and approve it in the Manage tab.",
                    f"✅ تم حفظ التدخل للطالب {chosen_code} / '{skill_name}'. "
                    "راجعه وافق عليه في تبويب الإدارة.",
                )
            )
            st.rerun()
        except ValueError as e:
            st.error(str(e))


# ---------------------------------------------------------------------------
# Tab 3 — Manage Interventions
# ---------------------------------------------------------------------------

def _render_manage(
    _DIR: str,
    interventions: list[dict],
    checkpoints: list[dict],
    student_codes: list[str],
    name_map: dict[str, str],
) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.5rem;">
          <div class="sf-card-header-icon">📋</div>
          <div class="sf-card-title">
            {T("Manage Interventions", "إدارة التدخلات")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not interventions:
        st.info(
            T(
                "No interventions recorded yet. "
                "Use the 'Create Intervention' tab to add one.",
                "لا توجد تدخلات مسجَّلة بعد. "
                "استخدم تبويب 'إنشاء تدخل' لإضافة واحد.",
            )
        )
        return

    # ── Filter controls ────────────────────────────────────────────────
    fc1, fc2 = st.columns(2)
    with fc1:
        all_students = ["— " + T("All students", "جميع الطلاب") + " —"] + student_codes
        filter_student = st.selectbox(
            T("Filter by student", "تصفية بالطالب"),
            all_students,
            key="int_filter_student",
        )
    with fc2:
        all_statuses = ["— " + T("All statuses", "جميع الحالات") + " —"] + INTERVENTION_STATUSES
        filter_status = st.selectbox(
            T("Filter by status", "تصفية بالحالة"),
            all_statuses,
            key="int_filter_status",
        )

    filtered = list(interventions)
    if not filter_student.startswith("—"):
        filtered = [r for r in filtered if r["student_code"] == filter_student]
    if not filter_status.startswith("—"):
        filtered = [r for r in filtered if r["status"] == filter_status]
    # Sort: most recently updated first
    filtered = sorted(
        filtered,
        key=lambda r: timestamp_sort_key(r.get("updated_at", "")),
        reverse=True,
    )

    st.markdown(
        f"<div style='font-size:0.80rem;color:#435F76;margin-bottom:0.5rem;'>"
        + T(f"Showing {len(filtered)} of {len(interventions)} intervention(s).",
            f"عرض {len(filtered)} من {len(interventions)} تدخل.")
        + "</div>",
        unsafe_allow_html=True,
    )

    for rec in filtered:
        _render_intervention_card(rec, name_map, _DIR)


STATUS_COLORS = {
    "Proposed":    ("#6B7280", "rgba(107,114,128,0.08)"),
    "Approved":    ("#2563eb", "rgba(37,99,235,0.08)"),
    "In Progress": ("#D4A017", "rgba(212,160,23,0.08)"),
    "Completed":   ("#16a34a", "rgba(22,163,74,0.08)"),
    "Dismissed":   ("#9CA3AF", "rgba(156,163,175,0.06)"),
}

STATUS_AR = {
    "Proposed":    "مقترح",
    "Approved":    "موافق عليه",
    "In Progress": "جارٍ التنفيذ",
    "Completed":   "مكتمل",
    "Dismissed":   "مرفوض",
}


def _render_intervention_card(
    rec: dict,
    name_map: dict[str, str],
    _DIR: str,
) -> None:
    code    = rec["student_code"]
    display = f"{code} — {name_map[code]}" if code in name_map else code
    status  = rec["status"]
    color, bg = STATUS_COLORS.get(status, ("#6B7280", "var(--sf-surface-raised)"))
    tier_en, tier_ar = MTSS_TIERS.get(rec["mtss_tier"], ("Not set", "غير محدد"))
    tier_label = T(tier_en, tier_ar)

    with st.expander(
        f"{'✅' if status == 'Completed' else '🔵' if status == 'In Progress' else '📌'} "
        f"{escape_html(display)}  ·  {escape_html(rec['skill_name'])}  "
        f"[{T(status, STATUS_AR.get(status, status))}]",
        expanded=False,
    ):
        # Evidence snapshot
        snap = rec.get("evidence_snapshot", {})
        pre_mean = snap.get("mean_pct")
        st.markdown(
            f"""
            <div style="background:{bg};border:1px solid {color}33;
                        border-radius:8px;padding:0.5rem 0.9rem;
                        font-size:0.80rem;direction:{_DIR};margin-bottom:0.5rem;">
              <strong>{T("Evidence at creation:", "الأدلة وقت الإنشاء:")}</strong>
              &nbsp;{T("Assessments:", "التقييمات:")} {escape_html(snap.get('count', 'N/A'))}
              &nbsp;·&nbsp;{T("Mean:", "المتوسط:")}
                {f"{pre_mean:.1f}%" if pre_mean is not None else "N/A"}
              &nbsp;·&nbsp;{T("Mastery:", "الإتقان:")} {escape_html(snap.get('mastery_level') or "N/A")}
              &nbsp;·&nbsp;{T("Trend:", "الاتجاه:")} {escape_html(snap.get('trend', 'N/A'))}
              &nbsp;·&nbsp;{T("MTSS:", "MTSS:")} {tier_label}
            </div>
            <div style="font-size:0.80rem;color:#102B4E;direction:{_DIR};margin-bottom:0.4rem;">
              <strong>{T("Reason:", "السبب:")}</strong> {escape_html(rec['reason'] or T("—","—"))}
            </div>
            <div style="font-size:0.80rem;color:#102B4E;direction:{_DIR};">
              <strong>{T("Proposed Action:", "الإجراء المقترح:")}</strong>
              {escape_html(rec['proposed_action'] or T("—","—"))}
            </div>
            """,
            unsafe_allow_html=True,
        )
        created_at = format_timestamp_riyadh(rec.get("created_at"))
        updated_at = format_timestamp_riyadh(rec.get("updated_at"))
        st.caption(
            T(
                f"Created: {created_at} · Updated: {updated_at}",
                f"تاريخ الإنشاء: {created_at} · آخر تحديث: {updated_at}",
            )
        )
        if rec.get("teacher_notes"):
            st.markdown(
                f'<div style="font-size:0.78rem;color:#435F76;direction:{_DIR};">'
                f'{T("Notes:", "ملاحظات:")} {escape_html(rec["teacher_notes"])}</div>',
                unsafe_allow_html=True,
            )

        # ── Status update controls ───────────────────────────────────────
        st.markdown(f"**{T('Update Status', 'تحديث الحالة')}**")
        sc1, sc2, sc3 = st.columns([2, 2, 2])
        with sc1:
            new_status = st.selectbox(
                T("Status", "الحالة"),
                INTERVENTION_STATUSES,
                index=INTERVENTION_STATUSES.index(status),
                key=f"status_{rec['id']}",
            )
        with sc2:
            tier_display = [T(v[0], v[1]) for v in MTSS_TIERS.values()]
            new_tier = st.selectbox(
                T("MTSS Tier", "مستوى MTSS"),
                tier_display,
                index=rec["mtss_tier"],
                key=f"tier_{rec['id']}",
                help=T(
                    "MTSS tiers describe support intensity — not a permanent label.",
                    "مستويات MTSS تصف شدة الدعم — وليست هوية ثابتة.",
                ),
            )
            new_tier_val = list(MTSS_TIERS.keys())[tier_display.index(new_tier)]
        with sc3:
            new_notes = st.text_input(
                T("Add/update notes", "أضف/حدِّث ملاحظات"),
                value=rec.get("teacher_notes", ""),
                key=f"notes_{rec['id']}",
            )

        if st.button(
            T("💾 Save Changes", "💾 حفظ التغييرات"),
            key=f"save_{rec['id']}",
        ):
            updated_values = {
                "status": new_status,
                "mtss_tier": new_tier_val,
                "teacher_notes": new_notes,
            }
            changed_fields = [
                field for field, value in updated_values.items()
                if rec.get(field) != value
            ]
            updated = update_intervention(
                rec,
                status=new_status,
                mtss_tier=new_tier_val,
                teacher_notes=new_notes,
            )
            try:
                st.session_state["interventions"] = replace_intervention(
                    st.session_state["interventions"], updated
                )
                if changed_fields:
                    role = st.session_state.get("active_role", "unknown")
                    if role not in {"teacher", "school_admin", "demo_reviewer"}:
                        role = "unknown"
                    st.session_state["audit_log"] = log_event(
                        st.session_state.get("audit_log", []),
                        action=ACTION_INTERVENTION_UPDATED,
                        actor_role=role,
                        entity_type=ENTITY_INTERVENTION,
                        changed_fields=changed_fields,
                    )
                st.success(T("✅ Saved.", "✅ تم الحفظ."))
                st.rerun()
            except ValueError as e:
                st.error(str(e))


# ---------------------------------------------------------------------------
# Tab 4 — Progress Tracking
# ---------------------------------------------------------------------------

def _render_progress(
    _DIR: str,
    interventions: list[dict],
    checkpoints: list[dict],
    student_codes: list[str],
    name_map: dict[str, str],
) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.5rem;">
          <div class="sf-card-header-icon">📈</div>
          <div class="sf-card-title">
            {T("Post-Intervention Progress", "التقدم بعد التدخل")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        T(
            "Record assessment checkpoints after an intervention is in progress, "
            "then compare results to the evidence at the time of intervention creation.",
            "سجّل نتائج التقييم بعد بدء التدخل، ثم قارنها بالأدلة "
            "وقت إنشاء التدخل.",
        )
    )

    # Only show In Progress and Completed interventions
    trackable = [
        r for r in interventions
        if r["status"] in {"In Progress", "Completed"}
    ]

    if not trackable:
        st.info(
            T(
                "No interventions in 'In Progress' or 'Completed' status yet. "
                "Change an intervention's status in the Manage tab first.",
                "لا توجد تدخلات بحالة 'جارٍ التنفيذ' أو 'مكتمل' بعد. "
                "غيِّر حالة تدخل في تبويب الإدارة أولاً.",
            )
        )
        return

    # Selector
    int_opts = {
        f"{r['student_code']} / {r['skill_name']} [{r['status']}]": r["id"]
        for r in trackable
    }
    chosen_disp = st.selectbox(
        T("Select intervention", "اختر التدخل"),
        list(int_opts.keys()),
        key="progress_int_sel",
    )
    chosen_id  = int_opts[chosen_disp]
    chosen_rec = get_intervention(interventions, chosen_id)
    if not chosen_rec:
        st.error(T("Intervention not found.", "التدخل غير موجود."))
        return

    code = chosen_rec["student_code"]

    # ── Before/After comparison ────────────────────────────────────────
    post_checks = intervention_checkpoints(checkpoints, chosen_id)
    comparison  = compare_before_after(chosen_rec.get("evidence_snapshot", {}), post_checks)

    _render_before_after(comparison, _DIR)

    # ── Add checkpoint form ────────────────────────────────────────────
    st.markdown(f"**{T('Record New Checkpoint', 'تسجيل نقطة تقدم جديدة')}**")
    cc1, cc2, cc3 = st.columns([2, 2, 2])
    with cc1:
        cp_score = st.number_input(
            T("Score", "الدرجة"), min_value=0.0, value=0.0,
            step=0.5, key="cp_score",
        )
    with cc2:
        cp_max = st.number_input(
            T("Max score", "الدرجة الكاملة"), min_value=0.5, value=10.0,
            step=0.5, key="cp_max",
        )
    with cc3:
        cp_date = st.date_input(
            T("Date", "التاريخ"), value=date.today(), key="cp_date",
        )
    cp_notes = st.text_input(
        T("Notes (optional)", "ملاحظات (اختياري)"), key="cp_notes",
    )

    if st.button(
        T("➕ Add Checkpoint", "➕ إضافة نقطة تقدم"),
        type="primary",
        key="btn_add_checkpoint",
    ):
        if cp_score > cp_max:
            st.error(
                T("Score cannot exceed maximum.", "لا يمكن أن تتجاوز الدرجة الحد الأقصى.")
            )
        else:
            cp = new_progress_checkpoint(
                intervention_id=chosen_id,
                student_code=code,
                skill_id=chosen_rec["skill_id"],
                score=cp_score,
                max_score=cp_max,
                date=str(cp_date),
                notes=cp_notes,
            )
            st.session_state["intervention_checkpoints"] = checkpoints + [cp]
            role = st.session_state.get("active_role", "unknown")
            if role not in {"teacher", "school_admin", "demo_reviewer"}:
                role = "unknown"
            st.session_state["audit_log"] = log_event(
                st.session_state.get("audit_log", []),
                action=ACTION_CHECKPOINT_ADDED,
                actor_role=role,
                entity_type=ENTITY_CHECKPOINT,
            )
            st.success(
                T(
                    f"✅ Checkpoint recorded: {cp_score}/{cp_max} "
                    f"({round(cp_score/cp_max*100,1)}%)",
                    f"✅ تم تسجيل نقطة التقدم: {cp_score}/{cp_max} "
                    f"({round(cp_score/cp_max*100,1)}%)",
                )
            )
            st.rerun()

    # ── Checkpoint history table ───────────────────────────────────────
    if post_checks:
        st.markdown(
            f"**{T('Checkpoint History', 'سجل نقاط التقدم')}** "
            f"({len(post_checks)} {T('records','سجل')})"
        )
        rows = []
        for c in post_checks:
            pct = round(c["score"] / c["max_score"] * 100, 1) if c["max_score"] else 0
            rows.append({
                T("Date",       "التاريخ"):    c.get("date", ""),
                T("Score",      "الدرجة"):     f"{c['score']}/{c['max_score']}",
                T("Percentage", "النسبة"):     f"{pct}%",
                T("Notes",      "ملاحظات"):    c.get("notes", ""),
            })
        st.markdown('<div class="sf-card">', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(rows), **full_width(), hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)


def _render_before_after(comparison: dict, _DIR: str) -> None:
    """Render a before/after comparison card."""
    pre   = comparison["pre_mean_pct"]
    post  = comparison["post_mean_pct"]
    delta = comparison["delta_pct"]
    direction = comparison["direction"]

    if direction == "improved":
        dir_icon = "📈"
    elif direction == "declined":
        dir_icon = "📉"
    elif direction == "stable":
        dir_icon = "➡️"
    else:
        dir_icon = "—"

    pre_str   = f"{pre:.1f}%"   if pre   is not None else T("N/A", "غير متاح")
    post_str  = f"{post:.1f}%"  if post  is not None else T("N/A", "غير متاح")
    delta_str = (
        f"{'+' if delta and delta >= 0 else ''}{delta:.1f}%"
        if delta is not None else T("N/A", "غير متاح")
    )
    dir_label = T(direction, {
        "improved": "تحسُّن",
        "declined": "تراجع",
        "stable":   "مستقر",
        "N/A":      "غير متاح",
    }.get(direction, direction))

    suffix = ""
    if not comparison["sufficient_data"]:
        suffix = (
            f'<div style="font-size:0.76rem;color:#435F76;margin-top:0.3rem;">'
            + T(
                "No post-intervention checkpoints yet — record one below.",
                "لا توجد نقاط تقدم بعد التدخل بعد — سجّل واحدة أدناه.",
            )
            + "</div>"
        )

    st.markdown(
        f"""
        <div class="sf-card" style="direction:{_DIR};margin-bottom:0.8rem;">
          <div style="font-weight:700;font-size:0.88rem;margin-bottom:0.4rem;">
            {T("Before / After Comparison", "مقارنة قبل / بعد")}
          </div>
          <div style="display:flex;gap:2rem;flex-wrap:wrap;font-size:0.82rem;color:#102B4E;">
            <div>
              {T("Before (at creation):", "قبل (وقت الإنشاء):")}
              <strong>{pre_str}</strong>
              <span style="font-size:0.76rem;color:#435F76;">
                ({comparison['pre_count']} {T("assessments","تقييمات")})
              </span>
            </div>
            <div>
              {T("After (checkpoints):", "بعد (نقاط التقدم):")}
              <strong>{post_str}</strong>
              <span style="font-size:0.76rem;color:#435F76;">
                ({comparison['post_count']} {T("checkpoints","نقاط")})
              </span>
            </div>
            <div>
              {T("Change:", "التغيير:")}
              <strong style="color:#102B4E;">{dir_icon} {delta_str}</strong>
            </div>
            <div>
              {T("Direction:", "الاتجاه:")}
              <strong style="color:#102B4E;">{dir_label}</strong>
            </div>
          </div>
          {suffix}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if comparison["sufficient_data"]:
        st.caption(
            T(
                "⚠️ This comparison is informational only. "
                "No diagnosis or classification is made from this data.",
                "⚠️ هذه المقارنة معلوماتية فقط. "
                "لا يُستخلص أي تشخيص أو تصنيف من هذه البيانات.",
            )
        )
