"""
pages/bloom_questions.py
-------------------------
Bloom's Taxonomy & Smart Question Classification — SchoolFlow AI (Task 8).

What this page does
-------------------
1. Classify Question — teacher types a question; the rule-based classifier
   suggests a Bloom level with a reason. Teacher accepts, edits, or ignores.
2. Question Library  — browse, filter, and re-use all saved questions.
3. Distribution      — visual bar chart of questions across the 6 levels.

Design rules
------------
* Teacher always has final classification authority.
* The classifier is transparently described as rule-based (not AI).
* No fixed distribution or quota is imposed.
* Classification is NOT a judgement of question quality.
* Bilingual (AR / EN) throughout.
* Re-uses existing shared.styles CSS classes.
* Only writes to: question_library.
"""

from __future__ import annotations

import streamlit as st

if __name__ == "__main__":
    st.switch_page("app.py")

import pandas as pd

import sys
import os
_HERE    = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_HERE)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from shared.i18n import T, is_arabic, text_dir
from shared.html_utils import escape_html
from shared.streamlit_compat import full_width
from shared.bloom import (
    BLOOM_LEVELS,
    LEVEL_IDS,
    LEVEL_BY_ID,
    LOW_CONFIDENCE_THRESHOLD,
    suggest_bloom_level,
    new_question,
    update_question,
    add_question,
    remove_question,
    replace_question,
    filter_questions,
    bloom_distribution,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render() -> None:
    """Render the Bloom's Taxonomy & Question Classification page."""
    _IS_AR = is_arabic()
    _DIR   = text_dir()

    st.markdown(
        f"""
        <div class="sf-section-header" style="direction:{_DIR};">
          <div class="sf-section-num">🧠</div>
          <div class="sf-section-title">
            {T("Bloom&#39;s Taxonomy &amp; Question Classification",
               "تصنيف الأسئلة وفق مستويات بلوم")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Ensure library key is initialised
    if st.session_state.get("question_library") is None:
        st.session_state["question_library"] = []
    library = st.session_state["question_library"]

    tab_labels = [
        T("🔍 Classify Question",  "🔍 تصنيف سؤال"),
        T("📚 Question Library",   "📚 مكتبة الأسئلة"),
        T("📊 Distribution",       "📊 توزيع المستويات"),
    ]
    tab1, tab2, tab3 = st.tabs(tab_labels)

    with tab1:
        _render_classify(_DIR, library)
    with tab2:
        _render_library(_DIR, library)
    with tab3:
        _render_distribution(_DIR, library)


# ---------------------------------------------------------------------------
# Tab 1 — Classify Question
# ---------------------------------------------------------------------------

def _render_classify(_DIR: str, library: list[dict]) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.5rem;">
          <div class="sf-card-header-icon">🔍</div>
          <div class="sf-card-title">
            {T("Classify a Question", "تصنيف سؤال")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        T(
            "Type a question. The classifier will suggest a Bloom level based on "
            "the task demand — not just keywords. "
            "You have full control to accept, change, or ignore the suggestion.",
            "اكتب السؤال. سيقترح المصنِّف مستوى بلوم بناءً على المطلوب من الطالب، "
            "لا مجرد الكلمات المفتاحية. "
            "لك الحرية الكاملة في قبول الاقتراح أو تعديله أو تجاهله.",
        )
    )

    # Classifier type disclaimer
    st.markdown(
        f"""
        <div style="background:rgba(255,255,255,0.06);border:1px solid rgba(212,160,23,0.45);
                    border-radius:8px;padding:0.5rem 0.9rem;font-size:0.78rem;
                    color:#102B4E;direction:{_DIR};margin-bottom:0.6rem;">
          ⚙️ <strong>{T("Rule-based classifier", "مصنِّف يعتمد القواعد")}</strong>
          &nbsp;—&nbsp;
          {T(
              "No live AI model is connected. Suggestions are based on linguistic "
              "patterns (English &amp; Arabic). Accuracy is limited — always review.",
              "لا يوجد نموذج ذكاء اصطناعي متصل. الاقتراحات مبنية على الأنماط اللغوية "
              "(عربي وإنجليزي). الدقة محدودة — راجع دائمًا.",
          )}
        </div>
        """,
        unsafe_allow_html=True,
    )

    q_text = st.text_area(
        T("Question text", "نص السؤال"),
        placeholder=T(
            "e.g. Compare the causes and effects of the water cycle.",
            "مثال: قارن بين أسباب دورة المياه ونتائجها.",
        ),
        height=100,
        key="bloom_q_text",
    )

    # Optional metadata
    with st.expander(T("Optional: Link to lesson / skill", "اختياري: ربط بحصة / مهارة"), expanded=False):
        mc1, mc2 = st.columns(2)
        with mc1:
            q_subject = st.text_input(
                T("Subject", "المادة"), key="bloom_q_subject",
                placeholder=T("e.g. English", "مثال: اللغة الإنجليزية"),
            )
            q_grade = st.text_input(
                T("Grade", "الصف"), key="bloom_q_grade",
                placeholder=T("e.g. Grade 5", "مثال: الصف الخامس"),
            )
        with mc2:
            lesson_records = st.session_state.get("lesson_records") or []
            lesson_opts = ["— " + T("No lesson link", "بدون ربط بحصة") + " —"] + [
                f"{r.get('title', '')} ({r.get('date', '')})"
                for r in lesson_records
            ]
            lesson_sel = st.selectbox(
                T("Lesson (optional)", "الحصة (اختياري)"),
                lesson_opts, key="bloom_q_lesson",
            )
            lesson_id = ""
            if not lesson_sel.startswith("—") and lesson_records:
                idx = lesson_opts.index(lesson_sel) - 1
                lesson_id = lesson_records[idx].get("lesson_id", "")

            skill_defs = st.session_state.get("skill_definitions") or []
            skill_opts = ["— " + T("No skill link", "بدون ربط بمهارة") + " —"] + [
                f"{s['id']} — {s['name']}" for s in skill_defs
            ]
            skill_sel = st.selectbox(
                T("Skill (optional)", "المهارة (اختياري)"),
                skill_opts, key="bloom_q_skill",
            )
            skill_id = ""
            if not skill_sel.startswith("—") and skill_defs:
                idx = skill_opts.index(skill_sel) - 1
                skill_id = skill_defs[idx]["id"]

    if st.session_state.get("bloom_suggestion_text") != q_text.strip():
        st.session_state.pop("bloom_suggestion", None)
        st.session_state.pop("bloom_suggestion_text", None)

    # ── Suggest button ─────────────────────────────────────────────────
    if st.button(
        T("🔍 Suggest Bloom Level", "🔍 اقتراح مستوى بلوم"),
        key="btn_bloom_suggest",
        type="primary",
    ):
        if not q_text.strip():
            st.warning(T("Please enter a question first.", "أدخل السؤال أولاً."))
        else:
            st.session_state["bloom_suggestion"] = suggest_bloom_level(q_text)
            st.session_state["bloom_suggestion_text"] = q_text.strip()
            st.session_state.pop("bloom_level_select", None)

    # ── Show suggestion ────────────────────────────────────────────────
    suggestion = st.session_state.get("bloom_suggestion")
    if suggestion and q_text.strip():
        sugg_id   = suggestion["suggested_level"]
        sugg_lvl  = LEVEL_BY_ID[sugg_id]
        conf      = suggestion["confidence"]
        low_conf  = suggestion["low_confidence"]
        reason    = suggestion["reason_ar"] if is_arabic() else suggestion["reason"]

        badge_color  = sugg_lvl["color"]
        conf_pct     = f"{conf * 100:.0f}%"
        conf_label   = T(f"Confidence: {conf_pct}", f"درجة الثقة: {conf_pct}")

        if low_conf:
            conf_style = "color:#102B4E;font-weight:700;"
        else:
            conf_style = "color:#102B4E;font-weight:700;"

        st.markdown(
            f"""
            <div style="background:var(--sf-surface-raised);border:1px solid {badge_color}55;
                        border-left:4px solid {badge_color};
                        border-radius:9px;padding:0.6rem 1rem;
                        direction:{_DIR};margin:0.5rem 0;">
              <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;">
                <strong>{T("Suggestion:", "الاقتراح:")}</strong>
                <span style="background:{badge_color}22;color:#102B4E;
                             border:1px solid {badge_color}55;border-radius:20px;
                             padding:2px 10px;font-size:0.80rem;font-weight:700;">
                  {T(sugg_lvl['name_en'], sugg_lvl['name_ar'])}
                </span>
                <span style="{conf_style};font-size:0.80rem;">{conf_label}</span>
                {"<span style='color:#102B4E;font-size:0.76rem;'>⚠️ " + T("Low confidence","ثقة منخفضة") + "</span>" if low_conf else ""}
              </div>
              <div style="font-size:0.78rem;color:#102B4E;margin-top:0.3rem;">
                {escape_html(reason)}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Level selector — teacher can override
        level_display = [
            T(lvl["name_en"], lvl["name_ar"]) for lvl in BLOOM_LEVELS
        ]
        default_idx = LEVEL_IDS.index(sugg_id)
        chosen_disp = st.selectbox(
            T(
                "Accept suggestion or choose a different level:",
                "اقبل الاقتراح أو اختر مستوى آخر:",
            ),
            level_display,
            index=default_idx,
            key="bloom_level_select",
        )
        chosen_id  = LEVEL_IDS[level_display.index(chosen_disp)]
        confirmed  = (chosen_id == sugg_id)
        teacher_confirmed = True  # any selectbox choice = teacher decision

        # Warn if overriding
        if chosen_id != sugg_id:
            st.caption(
                T(
                    f"You chose '{T(LEVEL_BY_ID[chosen_id]['name_en'], LEVEL_BY_ID[chosen_id]['name_ar'])}' "
                    f"instead of the suggested '{T(sugg_lvl['name_en'], sugg_lvl['name_ar'])}'. "
                    "Your choice will be saved.",
                    f"اخترتَ '{T(LEVEL_BY_ID[chosen_id]['name_en'], LEVEL_BY_ID[chosen_id]['name_ar'])}' "
                    f"بدلاً من المقترح '{T(sugg_lvl['name_en'], sugg_lvl['name_ar'])}'. "
                    "سيُحفظ اختيارك.",
                )
            )

        if st.button(
            T("💾 Save Question", "💾 حفظ السؤال"),
            type="primary",
            key="btn_bloom_save",
        ):
            q = new_question(
                text=q_text,
                bloom_level=chosen_id,
                confirmed_by_teacher=teacher_confirmed,
                suggested_level=sugg_id,
                confidence=conf,
                suggestion_reason=reason,
                lesson_id=lesson_id,
                skill_id=skill_id,
                subject=q_subject,
                grade=q_grade,
            )
            st.session_state["question_library"] = add_question(
                st.session_state["question_library"], q
            )
            st.session_state.pop("bloom_suggestion", None)
            st.session_state.pop("bloom_suggestion_text", None)
            st.success(
                T(
                    f"✅ Question saved at level '{T(LEVEL_BY_ID[chosen_id]['name_en'], LEVEL_BY_ID[chosen_id]['name_ar'])}'.",
                    f"✅ تم حفظ السؤال في مستوى '{T(LEVEL_BY_ID[chosen_id]['name_en'], LEVEL_BY_ID[chosen_id]['name_ar'])}'.",
                )
            )
            st.rerun()

    # ── Save without suggestion (manual) ──────────────────────────────
    if not suggestion or not q_text.strip():
        if q_text.strip():
            st.markdown(f"**{T('Or classify manually:', 'أو صنِّف يدويًا:')}**")
            level_display = [T(lvl["name_en"], lvl["name_ar"]) for lvl in BLOOM_LEVELS]
            man_disp = st.selectbox(
                T("Choose Bloom level", "اختر مستوى بلوم"),
                level_display,
                key="bloom_manual_level",
            )
            man_id = LEVEL_IDS[level_display.index(man_disp)]
            if st.button(
                T("💾 Save (manual)", "💾 حفظ (يدوي)"),
                key="btn_bloom_manual_save",
            ):
                q = new_question(
                    text=q_text,
                    bloom_level=man_id,
                    confirmed_by_teacher=True,
                    lesson_id=lesson_id,
                    skill_id=skill_id,
                    subject=q_subject,
                    grade=q_grade,
                )
                st.session_state["question_library"] = add_question(
                    st.session_state["question_library"], q
                )
                st.success(
                    T(
                        f"✅ Question saved at level '{T(LEVEL_BY_ID[man_id]['name_en'], LEVEL_BY_ID[man_id]['name_ar'])}'.",
                        f"✅ تم حفظ السؤال في مستوى '{T(LEVEL_BY_ID[man_id]['name_en'], LEVEL_BY_ID[man_id]['name_ar'])}'.",
                    )
                )
                st.rerun()

    # ── Level reference card ───────────────────────────────────────────
    with st.expander(
        T("📖 Bloom's Level Reference", "📖 مرجع مستويات بلوم"),
        expanded=False,
    ):
        for lvl in BLOOM_LEVELS:
            st.markdown(
                f'<div style="direction:{_DIR};padding:0.25rem 0;font-size:0.82rem;">'
                f'<span style="background:{lvl["color"]}22;color:#102B4E;'
                f'border:1px solid {lvl["color"]}55;border-radius:16px;'
                f'padding:1px 9px;font-weight:700;font-size:0.76rem;'
                f'margin-right:8px;">{T(lvl["name_en"], lvl["name_ar"])}</span>'
                f'{T(lvl["description_en"], lvl["description_ar"])}</div>',
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Tab 2 — Question Library
# ---------------------------------------------------------------------------

def _render_library(_DIR: str, library: list[dict]) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.5rem;">
          <div class="sf-card-header-icon">📚</div>
          <div class="sf-card-title">
            {T("Question Library", "مكتبة الأسئلة")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not library:
        st.info(
            T(
                "No questions saved yet. Use the 'Classify Question' tab to add questions.",
                "لا توجد أسئلة محفوظة بعد. استخدم تبويب 'تصنيف سؤال' لإضافة أسئلة.",
            )
        )
        return

    # ── Filters ────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns(3)
    level_all = "— " + T("All levels", "جميع المستويات") + " —"
    level_opts = [level_all] + [
        T(lvl["name_en"], lvl["name_ar"]) for lvl in BLOOM_LEVELS
    ]
    with fc1:
        filter_level_disp = st.selectbox(
            T("Filter by level", "تصفية بالمستوى"),
            level_opts, key="lib_filter_level",
        )
        filter_level = ""
        if not filter_level_disp.startswith("—"):
            for lvl in BLOOM_LEVELS:
                if T(lvl["name_en"], lvl["name_ar"]) == filter_level_disp:
                    filter_level = lvl["id"]
                    break
    with fc2:
        filter_subject = st.text_input(
            T("Filter by subject", "تصفية بالمادة"), key="lib_filter_subject",
        )
    with fc3:
        filter_confirmed = st.toggle(
            T("Teacher-confirmed only", "المؤكَّد من المعلم فقط"),
            key="lib_filter_confirmed",
        )

    filtered = filter_questions(
        library,
        bloom_level=filter_level,
        subject=filter_subject.strip(),
        confirmed_only=filter_confirmed,
    )

    st.markdown(
        f"<div style='font-size:0.80rem;color:#435F76;margin-bottom:0.4rem;'>"
        + T(f"Showing {len(filtered)} of {len(library)} question(s).",
            f"عرض {len(filtered)} من {len(library)} سؤال.")
        + "</div>",
        unsafe_allow_html=True,
    )

    for q in filtered:
        _render_question_row(q, _DIR)


def _render_question_row(q: dict, _DIR: str) -> None:
    lvl    = LEVEL_BY_ID.get(q["bloom_level"], BLOOM_LEVELS[0])
    color  = lvl["color"]
    sugg   = q.get("suggested_level")
    sugg_mismatch = sugg and sugg != q["bloom_level"]
    confirmed_badge = (
        ' <span style="font-size:0.70rem;color:#102B4E;">✓ ' +
        T("confirmed", "مؤكَّد") + "</span>"
        if q.get("confirmed_by_teacher") else ""
    )

    with st.expander(
        f"[{T(lvl['name_en'], lvl['name_ar'])}]  "
        f"{escape_html(q['text'][:80])}{'…' if len(q['text']) > 80 else ''}",
        expanded=False,
    ):
        st.markdown(
            f'<div style="direction:{_DIR};font-size:0.82rem;">'
            f'<span style="background:{color}22;color:#102B4E;border:1px solid {color}55;'
            f'border-radius:16px;padding:2px 9px;font-weight:700;font-size:0.76rem;">'
            f'{T(lvl["name_en"], lvl["name_ar"])}</span>'
            f'{confirmed_badge}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="direction:{_DIR};font-size:0.84rem;color:#102B4E;'
            f'margin:0.4rem 0;">{escape_html(q["text"])}</div>',
            unsafe_allow_html=True,
        )
        meta = []
        if q.get("subject"):
            meta.append(T(f"Subject: {q['subject']}", f"المادة: {q['subject']}"))
        if q.get("grade"):
            meta.append(T(f"Grade: {q['grade']}", f"الصف: {q['grade']}"))
        if q.get("skill_id"):
            meta.append(T(f"Skill: {q['skill_id']}", f"المهارة: {q['skill_id']}"))
        if meta:
            st.markdown(
                f'<div style="font-size:0.76rem;color:#435F76;direction:{_DIR};">'
                f"{escape_html(' · '.join(meta))}</div>",
                unsafe_allow_html=True,
            )
        if sugg_mismatch:
            sugg_lvl = LEVEL_BY_ID[sugg]
            st.caption(
                T(
                    f"Note: classifier suggested '{sugg_lvl['name_en']}' — "
                    "teacher set a different level.",
                    f"ملاحظة: اقترح المصنِّف '{sugg_lvl['name_ar']}' — "
                    "غيَّر المعلم المستوى.",
                )
            )

        # ── Edit level ─────────────────────────────────────────────────
        level_display = [T(l["name_en"], l["name_ar"]) for l in BLOOM_LEVELS]
        cur_idx = LEVEL_IDS.index(q["bloom_level"])
        new_disp = st.selectbox(
            T("Change level", "تغيير المستوى"),
            level_display,
            index=cur_idx,
            key=f"lib_edit_level_{q['id']}",
        )
        new_id = LEVEL_IDS[level_display.index(new_disp)]

        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                T("💾 Save level change", "💾 حفظ التغيير"),
                key=f"lib_save_{q['id']}",
            ):
                updated = update_question(
                    q, bloom_level=new_id, confirmed_by_teacher=True
                )
                st.session_state["question_library"] = replace_question(
                    st.session_state["question_library"], updated
                )
                st.success(T("✅ Saved.", "✅ تم الحفظ."))
                st.rerun()
        with c2:
            if st.button(
                T("🗑 Remove", "🗑 حذف"),
                key=f"lib_del_{q['id']}",
            ):
                st.session_state["question_library"] = remove_question(
                    st.session_state["question_library"], q["id"]
                )
                st.rerun()


# ---------------------------------------------------------------------------
# Tab 3 — Distribution
# ---------------------------------------------------------------------------

def _render_distribution(_DIR: str, library: list[dict]) -> None:
    st.markdown(
        f"""
        <div class="sf-card-header" style="direction:{_DIR};margin-bottom:0.5rem;">
          <div class="sf-card-header-icon">📊</div>
          <div class="sf-card-title">
            {T("Question Distribution by Bloom Level",
               "توزيع الأسئلة على مستويات بلوم")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        T(
            "This is a descriptive view only. "
            "No target distribution or quota is applied.",
            "هذا عرض وصفي فقط. "
            "لا توجد نسبة مستهدفة أو حصة ثابتة.",
        )
    )

    dist = bloom_distribution(library)
    total = sum(dist.values())

    if total == 0:
        st.info(
            T(
                "No questions saved yet.",
                "لا توجد أسئلة محفوظة بعد.",
            )
        )
        return

    # Build SVG bar chart
    svg = _build_distribution_svg(dist, total, _DIR)
    st.markdown(svg, unsafe_allow_html=True)

    # Table
    rows = []
    for lvl in BLOOM_LEVELS:
        cnt = dist[lvl["id"]]
        pct = round(cnt / total * 100, 1) if total else 0
        rows.append({
            T("Level", "المستوى"):       T(lvl["name_en"], lvl["name_ar"]),
            T("Questions", "أسئلة"):     cnt,
            T("Percentage", "النسبة"):   f"{pct}%",
        })

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(rows), **full_width(), hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _build_distribution_svg(dist: dict[str, int], total: int, _DIR: str) -> str:
    """Build a horizontal bar SVG chart for Bloom level distribution."""
    if total == 0:
        return ""

    W, H = 540, 220
    pad_l, pad_r, pad_t, pad_b = 110, 60, 15, 15
    bar_area_w = W - pad_l - pad_r
    n = len(BLOOM_LEVELS)
    row_h = (H - pad_t - pad_b) / n
    bar_h = row_h * 0.55
    max_count = max(dist.values()) or 1

    bars = ""
    labels = ""
    values = ""
    for i, lvl in enumerate(BLOOM_LEVELS):
        cnt   = dist[lvl["id"]]
        y     = pad_t + i * row_h + (row_h - bar_h) / 2
        bar_w = max(2, bar_area_w * cnt / max_count)
        color = lvl["color"]
        name  = lvl["name_ar"] if _DIR == "rtl" else lvl["name_en"]

        bars   += (
            f'<rect x="{pad_l}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'rx="4" fill="{color}" opacity="0.85"/>'
        )
        labels += (
            f'<text x="{pad_l - 6}" y="{y + bar_h / 2 + 4:.1f}" '
            f'text-anchor="end" font-size="11" fill="#102B4E">{name}</text>'
        )
        pct = round(cnt / total * 100, 1) if total else 0
        values += (
            f'<text x="{pad_l + bar_w + 5:.1f}" y="{y + bar_h / 2 + 4:.1f}" '
            f'font-size="10" fill="#435F76">{cnt} ({pct}%)</text>'
        )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;max-width:{W}px;height:auto;display:block;'
        f'margin:0.5rem 0;">'
        f'{bars}{labels}{values}'
        f'</svg>'
    )
