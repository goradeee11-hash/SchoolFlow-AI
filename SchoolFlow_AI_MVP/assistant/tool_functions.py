"""
tool_functions.py
-----------------
Wrappers that read from st.session_state and call the existing app.py
logic functions.  No calculations are performed here — all numbers come
from the functions that were already tested (validate, build_outputs,
make_workbook, parent_message).

Every function returns a plain dict:
    {"ok": True,  "data": <value>, "message": <human-readable str>}
    {"ok": False, "message": <reason>}
"""

from __future__ import annotations
import pandas as pd


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_state(key, default=None):
    """Safe import of streamlit only at call time (avoids import-time side-effects)."""
    import streamlit as st
    return st.session_state.get(key, default)


def _require_analysis() -> dict | None:
    """Return an error dict if analysis has not been run yet, else None."""
    if _get_state("summary") is None:
        return {
            "ok": False,
            "message": (
                "لم يتم تحليل البيانات بعد.\n"
                "ارفع ملف Excel أولاً ثم اضغط «تحليل البيانات»."
            ),
        }
    return None


# Sentinel returned when multiple students match a query — callers must
# check for this object and return a disambiguation message to the user.
class _Ambiguous:
    """Holds all matches so the caller can present a clear choice."""
    def __init__(self, matches: list[tuple[str, str]]):
        # matches: list of (student_code, display_name)
        self.matches = matches

    def message_ar(self, query: str) -> str:
        lines = [f"وجدت {len(self.matches)} طلاب يطابقون «{query}»:"]
        for code, name in self.matches:
            lines.append(f"  • **{code}** — {name}")
        lines.append("\nيرجى تحديد رمز الطالب بدقة. مثال: `تقرير S01`")
        return "\n".join(lines)

    def message_en(self, query: str) -> str:
        lines = [f"Found {len(self.matches)} students matching \"{query}\":"]
        for code, name in self.matches:
            lines.append(f"  • **{code}** — {name}")
        lines.append("\nPlease specify the exact student code. Example: `report S01`")
        return "\n".join(lines)

    def message(self, query: str, lang: str = "ar") -> str:
        return self.message_en(query) if lang == "en" else self.message_ar(query)


def _find_student(
    code_or_name: str,
) -> tuple[str | None, pd.Series | None] | tuple[None, "_Ambiguous"]:
    """
    Look up a student by code or name.

    Priority:
      1. Exact code match  → (code, row)          — always safe, return immediately
      2. Exact name match  → (code, row)           — safe if unique
      3. Partial name match → disambiguate if >1   → (None, _Ambiguous) if multiple
      4. Partial code match → disambiguate if >1   → (None, _Ambiguous) if multiple

    Returns:
        (code, Series)      — unique match found
        (None, _Ambiguous)  — multiple matches; caller must ask user to clarify
        (None, None)        — no match at all
    """
    summary: pd.DataFrame = _get_state("summary", pd.DataFrame())
    if summary.empty:
        return None, None

    q = code_or_name.strip().lower()

    def _display(row) -> str:
        return str(row.get("Student name", row["Student code"]) or row["Student code"])

    # ── 1. Exact code match ────────────────────────────────────────────────
    exact_code = summary[summary["Student code"].str.lower() == q]
    if not exact_code.empty:
        row = exact_code.iloc[0]
        return row["Student code"], row

    # ── 2. Exact name match ────────────────────────────────────────────────
    if "Student name" in summary.columns:
        exact_name = summary[summary["Student name"].str.lower() == q]
        if len(exact_name) == 1:
            row = exact_name.iloc[0]
            return row["Student code"], row
        if len(exact_name) > 1:
            return None, _Ambiguous(
                [(r["Student code"], _display(r)) for _, r in exact_name.iterrows()]
            )

    # ── 3. Partial name match ──────────────────────────────────────────────
    if "Student name" in summary.columns:
        partial_name = summary[
            summary["Student name"].str.lower().str.contains(q, na=False)
        ]
        if len(partial_name) == 1:
            row = partial_name.iloc[0]
            return row["Student code"], row
        if len(partial_name) > 1:
            return None, _Ambiguous(
                [(r["Student code"], _display(r)) for _, r in partial_name.iterrows()]
            )

    # ── 4. Partial code match ──────────────────────────────────────────────
    partial_code = summary[
        summary["Student code"].str.lower().str.contains(q, na=False)
    ]
    if len(partial_code) == 1:
        row = partial_code.iloc[0]
        return row["Student code"], row
    if len(partial_code) > 1:
        return None, _Ambiguous(
            [(r["Student code"], _display(r)) for _, r in partial_code.iterrows()]
        )

    return None, None


def _ambiguous_error(result, query: str, lang: str = "ar") -> dict | None:
    """
    If result is an _Ambiguous object, return an error dict with a
    disambiguation message.  Otherwise return None (caller continues normally).
    """
    if isinstance(result, _Ambiguous):
        return {"ok": False, "message": result.message(query, lang=lang)}
    return None


# ---------------------------------------------------------------------------
# Internal: bilingual _require_analysis
# ---------------------------------------------------------------------------

def _require_analysis_lang(lang: str = "ar") -> dict | None:
    """Like _require_analysis but with bilingual message."""
    if _get_state("summary") is None:
        if lang == "en":
            msg = (
                "No analysis data found.\n"
                "Please upload an Excel file and click **Analyse Data** first."
            )
        else:
            msg = (
                "لم يتم تحليل البيانات بعد.\n"
                "ارفع ملف Excel أولاً ثم اضغط «تحليل البيانات»."
            )
        return {"ok": False, "message": msg}
    return None


# ---------------------------------------------------------------------------
# Tool 1 – Class analysis overview
# ---------------------------------------------------------------------------

def get_class_analysis(lang: str = "ar") -> dict:
    """Return a narrative summary of the whole class."""
    err = _require_analysis_lang(lang)
    if err:
        return err

    summary: pd.DataFrame = _get_state("summary")
    weekly: pd.DataFrame  = _get_state("weekly")
    clean: pd.DataFrame   = _get_state("clean")

    n_students = len(summary)
    n_weeks    = int(clean["Week"].nunique())
    n_records  = len(clean)

    def avg_pct(col):
        vals = []
        for v in summary[col]:
            try:
                vals.append(float(str(v).replace("%", "").strip()))
            except Exception:
                pass
        return f"{sum(vals)/len(vals):.1f}%" if vals else "N/A"

    att  = avg_pct("Attendance")
    task = avg_pct("Task completion")
    scores = summary["Mean quiz / 10"].dropna()
    quiz_na = "N/A" if lang == "en" else "غير متاح"
    quiz = f"{scores.mean():.2f}/10" if len(scores) else quiz_na

    latest_week = weekly.iloc[-1] if not weekly.empty else None
    last_att  = latest_week["Attendance rate"]  if latest_week is not None else "—"
    last_task = latest_week["Task completion"]  if latest_week is not None else "—"

    if lang == "en":
        msg = (
            f"📊 **Class Summary — {n_students} students · {n_weeks} weeks · {n_records} records**\n\n"
            f"- Mean attendance: **{att}**\n"
            f"- Mean task completion: **{task}**\n"
            f"- Mean quiz score: **{quiz}**\n"
            f"- Latest week — attendance: **{last_att}** · tasks: **{last_task}**"
        )
    else:
        msg = (
            f"📊 **ملخص الفصل — {n_students} طلاب · {n_weeks} أسابيع · {n_records} سجل**\n\n"
            f"- متوسط الحضور: **{att}**\n"
            f"- متوسط إنجاز المهام: **{task}**\n"
            f"- متوسط الاختبارات: **{quiz}**\n"
            f"- آخر أسبوع مسجّل — حضور: **{last_att}** · مهام: **{last_task}**"
        )
    return {"ok": True, "data": summary, "message": msg}


# ---------------------------------------------------------------------------
# Tool 2 – Find at-risk students
# ---------------------------------------------------------------------------

def find_at_risk_students(lang: str = "ar") -> dict:
    """Return students with attendance < 80% OR task completion < 70%."""
    err = _require_analysis_lang(lang)
    if err:
        return err

    summary: pd.DataFrame = _get_state("summary")
    at_risk = []

    for _, row in summary.iterrows():
        reasons = []
        try:
            att_val = float(str(row["Attendance"]).replace("%", "").strip())
            if att_val < 80:
                r_txt = (
                    f"low attendance ({row['Attendance']})"
                    if lang == "en" else
                    f"حضور منخفض ({row['Attendance']})"
                )
                reasons.append(r_txt)
        except Exception:
            pass
        try:
            task_val = float(str(row["Task completion"]).replace("%", "").strip())
            if task_val < 70:
                r_txt = (
                    f"low task completion ({row['Task completion']})"
                    if lang == "en" else
                    f"إنجاز مهام منخفض ({row['Task completion']})"
                )
                reasons.append(r_txt)
        except Exception:
            pass
        if reasons:
            name = row.get("Student name", row["Student code"])
            at_risk.append({"student": name, "code": row["Student code"], "reasons": reasons})

    if not at_risk:
        msg = (
            "✅ All students are within acceptable thresholds (attendance ≥ 80%, tasks ≥ 70%)."
            if lang == "en" else
            "✅ جميع الطلاب ضمن المعدلات المقبولة (حضور ≥ 80%، مهام ≥ 70%)."
        )
    else:
        if lang == "en":
            lines = [f"⚠️ **{len(at_risk)} student(s) need follow-up:**\n"]
        else:
            lines = [f"⚠️ **{len(at_risk)} طالب يحتاج متابعة:**\n"]
        for s in at_risk:
            lines.append(f"- **{s['student']}** ({s['code']}): {' · '.join(s['reasons'])}")
        msg = "\n".join(lines)

    return {"ok": True, "data": at_risk, "message": msg}


# ---------------------------------------------------------------------------
# Tool 3 – Single student report
# ---------------------------------------------------------------------------

def get_student_report(code_or_name: str, lang: str = "ar") -> dict:
    """Return a detailed report for one student."""
    err = _require_analysis_lang(lang)
    if err:
        return err

    code, row = _find_student(code_or_name)

    # Disambiguation: multiple students matched
    amb = _ambiguous_error(row, code_or_name, lang=lang)
    if amb:
        return amb

    if row is None:
        if lang == "en":
            msg = (
                f"No student found with name or code \"{code_or_name}\".\n"
                f"Check the exact code or ask for **list students**."
            )
        else:
            msg = (
                f"لم أجد طالباً بالاسم أو الرمز «{code_or_name}».\n"
                f"تحقق من الرمز الصحيح أو اطلب «قائمة الطلاب»."
            )
        return {"ok": False, "message": msg}

    name   = row.get("Student name", code)
    weeks  = row["Weeks recorded"]
    att    = row["Attendance"]
    att_s  = row["Attendance attended/scheduled"]
    task   = row["Task completion"]
    task_s = row["Tasks completed/set"]
    quiz   = row["Mean quiz / 10"]
    quiz_w = row["Quiz weeks recorded"]

    if lang == "en":
        obs  = row["Latest observation"] or "No observation recorded."
        step = row["Next step"] or "Next step not yet determined."
        quiz_str = (
            f"{quiz}/10 (from {quiz_w} quiz(zes))" if pd.notna(quiz) else "Not recorded"
        )
        msg = (
            f"📋 **Student Report: {name} ({code})**\n\n"
            f"- Weeks recorded: **{weeks}**\n"
            f"- Attendance: **{att}** ({att_s})\n"
            f"- Task completion: **{task}** ({task_s})\n"
            f"- Mean quiz score: **{quiz_str}**\n"
            f"- Latest observation: {obs}\n"
            f"- Next step: {step}"
        )
    else:
        obs  = row["Latest observation"] or "لا توجد ملاحظة مسجّلة"
        step = row["Next step"] or "لم تُحدَّد الخطوة القادمة"
        quiz_str = (
            f"{quiz}/10 (من {quiz_w} اختبار)" if pd.notna(quiz) else "غير مسجّل"
        )
        msg = (
            f"📋 **تقرير الطالب: {name} ({code})**\n\n"
            f"- الأسابيع المسجّلة: **{weeks}**\n"
            f"- الحضور: **{att}** ({att_s})\n"
            f"- إنجاز المهام: **{task}** ({task_s})\n"
            f"- متوسط الاختبارات: **{quiz_str}**\n"
            f"- آخر ملاحظة: {obs}\n"
            f"- الخطوة القادمة: {step}"
        )
    return {"ok": True, "data": row.to_dict(), "message": msg}


# ---------------------------------------------------------------------------
# Tool 4 – Student weekly record
# ---------------------------------------------------------------------------

def get_student_weekly(code_or_name: str, lang: str = "ar") -> dict:
    """Return the week-by-week record for one student."""
    err = _require_analysis_lang(lang)
    if err:
        return err

    code, row = _find_student(code_or_name)

    amb = _ambiguous_error(row, code_or_name, lang=lang)
    if amb:
        return amb

    if row is None:
        msg = (
            f"No student found with name or code \"{code_or_name}\"."
            if lang == "en" else
            f"لم أجد طالباً بالاسم أو الرمز «{code_or_name}»."
        )
        return {"ok": False, "message": msg}

    clean: pd.DataFrame = _get_state("clean")
    student_rows = clean[clean["Student code"] == code].sort_values("Week")
    display_name = row.get("Student name", code)

    if lang == "en":
        lines = [f"📅 **Weekly Record: {display_name} ({code})**\n"]
        for _, wr in student_rows.iterrows():
            quiz_v = wr["Quiz score / 10"]
            quiz_s = f"{quiz_v:g}/10" if pd.notna(quiz_v) else "not recorded"
            # Guard NaN on numeric fields before :g format
            att_d  = f"{wr['Days attended']:g}"   if pd.notna(wr["Days attended"])   else "—"
            att_s  = f"{wr['Days scheduled']:g}"  if pd.notna(wr["Days scheduled"])  else "—"
            task_c = f"{wr['Tasks completed']:g}" if pd.notna(wr["Tasks completed"]) else "—"
            task_s = f"{wr['Tasks set']:g}"       if pd.notna(wr["Tasks set"])       else "—"
            lines.append(
                f"- Week {int(wr['Week'])}: attendance {att_d}/{att_s}"
                f" · tasks {task_c}/{task_s}"
                f" · quiz {quiz_s}"
            )
    else:
        lines = [f"📅 **السجل الأسبوعي للطالب: {display_name} ({code})**\n"]
        for _, wr in student_rows.iterrows():
            quiz_v = wr["Quiz score / 10"]
            quiz_s = f"{quiz_v:g}/10" if pd.notna(quiz_v) else "غير مسجّل"
            att_d  = f"{wr['Days attended']:g}"   if pd.notna(wr["Days attended"])   else "—"
            att_s  = f"{wr['Days scheduled']:g}"  if pd.notna(wr["Days scheduled"])  else "—"
            task_c = f"{wr['Tasks completed']:g}" if pd.notna(wr["Tasks completed"]) else "—"
            task_s = f"{wr['Tasks set']:g}"       if pd.notna(wr["Tasks set"])       else "—"
            lines.append(
                f"- الأسبوع {int(wr['Week'])}: حضور {att_d}/{att_s}"
                f" · مهام {task_c}/{task_s}"
                f" · اختبار {quiz_s}"
            )

    return {"ok": True, "data": student_rows, "message": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Tool 5 – Draft parent message
# ---------------------------------------------------------------------------

def draft_parent_message(code_or_name: str, language: str = "العربية", lang: str = "ar") -> dict:
    """Draft a parent message for review (never sends automatically)."""
    err = _require_analysis_lang(lang)
    if err:
        return err

    code, row = _find_student(code_or_name)

    amb = _ambiguous_error(row, code_or_name, lang=lang)
    if amb:
        return amb

    if row is None:
        msg = (
            f"No student found with name or code \"{code_or_name}\"."
            if lang == "en" else
            f"لم أجد طالباً بالاسم أو الرمز «{code_or_name}»."
        )
        return {"ok": False, "message": msg}

    try:
        import sys, os
        app_dir = os.path.dirname(os.path.dirname(__file__))
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)
        from app_logic import parent_message as _pm
        pm_lang = "English" if language.lower() in ("english", "en", "إنجليزي", "انجليزي") else "العربية"
        text = _pm(row, pm_lang)
    except Exception as e:
        msg = (
            f"Error preparing message: {e}" if lang == "en"
            else f"خطأ في إعداد الرسالة: {e}"
        )
        return {"ok": False, "message": msg}

    name = row.get("Student name", code)
    if lang == "en":
        msg = (
            f"✉ **Draft Parent Message: {name}**\n"
            f"*(For review only — will NOT be sent automatically)*\n\n"
            f"```\n{text}\n```"
        )
    else:
        msg = (
            f"✉ **مسودة رسالة ولي أمر: {name}**\n"
            f"*(للمراجعة فقط — لن تُرسَل تلقائياً)*\n\n"
            f"```\n{text}\n```"
        )
    return {"ok": True, "data": text, "message": msg}


# ---------------------------------------------------------------------------
# Tool 6 – Data quality issues
# ---------------------------------------------------------------------------

def get_data_issues(lang: str = "ar") -> dict:
    """Return the stored validation issues."""
    err = _require_analysis_lang(lang)
    if err:
        return err

    issues: pd.DataFrame = _get_state("issues", pd.DataFrame())
    if issues.empty:
        msg = (
            "✅ No data quality issues found."
            if lang == "en" else
            "✅ لا توجد مشكلات في البيانات."
        )
        return {"ok": True, "data": issues, "message": msg}

    if lang == "en":
        lines = [f"⚠️ **{len(issues)} data issue(s) found:**\n"]
    else:
        lines = [f"⚠️ **{len(issues)} مشكلة في البيانات:**\n"]
    for _, r in issues.iterrows():
        lines.append(f"- **{r['Student code']}** | {r['Week']} | {r['Column']}: {r['Issue']}")
    return {"ok": True, "data": issues, "message": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Tool 7 – Weekly class summary for a specific week
# ---------------------------------------------------------------------------

def get_week_summary(week_num: int | str, lang: str = "ar") -> dict:
    """Return stats for a specific week number."""
    err = _require_analysis_lang(lang)
    if err:
        return err

    weekly: pd.DataFrame = _get_state("weekly")
    try:
        wn = int(week_num)
    except (ValueError, TypeError):
        msg = (
            f"Invalid week number: \"{week_num}\"." if lang == "en"
            else f"رقم الأسبوع غير صحيح: «{week_num}»."
        )
        return {"ok": False, "message": msg}

    row = weekly[weekly["Week"] == wn]
    if row.empty:
        available = weekly["Week"].tolist()
        if lang == "en":
            msg = f"No data found for week {wn}. Available weeks: {available}"
        else:
            msg = f"لا توجد بيانات للأسبوع {wn}. الأسابيع المتاحة: {available}"
        return {"ok": False, "message": msg}

    r = row.iloc[0]
    if lang == "en":
        msg = (
            f"📅 **Week {wn} Summary**\n\n"
            f"- Attendance: **{r['Attendance rate']}** ({r['Attended days']:g}/{r['Scheduled days']:g} days)\n"
            f"- Task completion: **{r['Task completion']}** ({r['Tasks completed']:g}/{r['Tasks set']:g})\n"
            f"- Mean quiz score: **{r['Mean quiz / 10']:.2f}/10**"
        )
    else:
        msg = (
            f"📅 **ملخص الأسبوع {wn}**\n\n"
            f"- الحضور: **{r['Attendance rate']}** ({r['Attended days']:g}/{r['Scheduled days']:g} يوم)\n"
            f"- إنجاز المهام: **{r['Task completion']}** ({r['Tasks completed']:g}/{r['Tasks set']:g})\n"
            f"- متوسط الاختبارات: **{r['Mean quiz / 10']:.2f}/10**"
        )
    return {"ok": True, "data": r.to_dict(), "message": msg}


# ---------------------------------------------------------------------------
# Tool 8 – List all students
# ---------------------------------------------------------------------------

def list_students(lang: str = "ar") -> dict:
    """Return the list of student codes and names."""
    err = _require_analysis_lang(lang)
    if err:
        return err

    summary: pd.DataFrame = _get_state("summary")
    header = "👥 **Student List:**\n" if lang == "en" else "👥 **قائمة الطلاب:**\n"
    lines = [header]
    for _, row in summary.iterrows():
        name = row.get("Student name", row["Student code"])
        lines.append(f"- **{row['Student code']}** — {name}")
    return {
        "ok": True,
        "data": summary[["Student code", "Student name"]].to_dict("records"),
        "message": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Tool 9 – Excel download trigger message
# ---------------------------------------------------------------------------

def trigger_excel_download(lang: str = "ar") -> dict:
    """Remind the teacher to use the download button (no file created here)."""
    err = _require_analysis_lang(lang)
    if err:
        return err

    if lang == "en":
        msg = (
            "📥 **Download Reports File**\n\n"
            "The file is ready. Go to section **8 — Download Reports** "
            "and click the **Download Excel Reports File** button.\n\n"
            "The file contains three sheets:\n"
            "1. **Validated data** — checked records\n"
            "2. **Student summaries** — per-student summary\n"
            "3. **Weekly summary** — class-level weekly stats"
        )
    else:
        msg = (
            "📥 **تنزيل ملف التقارير**\n\n"
            "الملف جاهز للتنزيل. انتقل إلى القسم رقم **8 — تنزيل النتائج** "
            "واضغط زر «تنزيل ملف التقارير Excel».\n\n"
            "الملف يحتوي على ثلاث أوراق:\n"
            "1. **Validated data** — البيانات المُتحقق منها\n"
            "2. **Student summaries** — ملخص الطلاب\n"
            "3. **Weekly summary** — الملخص الأسبوعي"
        )
    return {"ok": True, "data": None, "message": msg}


# ---------------------------------------------------------------------------
# Tool 10 – Explain analysis results
# ---------------------------------------------------------------------------

def explain_results(lang: str = "ar") -> dict:
    """Produce a narrative explanation of the analysis for the teacher."""
    err = _require_analysis_lang(lang)
    if err:
        return err

    summary: pd.DataFrame = _get_state("summary")
    issues: pd.DataFrame  = _get_state("issues", pd.DataFrame())
    at_risk_result = find_at_risk_students(lang=lang)

    top_student = None
    best_score  = -1.0
    for _, row in summary.iterrows():
        score = row["Mean quiz / 10"]
        if pd.notna(score) and float(score) > best_score:
            best_score  = float(score)
            top_student = row.get("Student name", row["Student code"])

    issue_count   = len(issues)
    at_risk_count = len(at_risk_result.get("data", []))
    n_students    = len(summary)

    if lang == "en":
        msg = f"🔍 **Analysis Results Explained**\n\nData analysed for **{n_students} student(s)**.\n\n"
        if top_student:
            msg += f"🏆 Highest mean quiz score: **{top_student}** ({best_score:.2f}/10)\n\n"
        if at_risk_count:
            msg += f"⚠️ **{at_risk_count} student(s)** need follow-up (low attendance or task completion).\n"
        else:
            msg += "✅ All students are within acceptable thresholds.\n"
        if issue_count:
            msg += (
                f"📋 **{issue_count} data quality issue(s)** found "
                "(unrecorded scores or illogical values). "
                "See section **Data Quality Check** for details.\n"
            )
        else:
            msg += "📋 Clean data — no quality issues.\n"
        msg += "\nType **at-risk students** or **report [student code]** for details."
    else:
        msg = f"🔍 **شرح نتائج التحليل**\n\nتم تحليل بيانات **{n_students} طالب**.\n\n"
        if top_student:
            msg += f"🏆 أعلى متوسط اختبارات: **{top_student}** ({best_score:.2f}/10)\n\n"
        if at_risk_count:
            msg += f"⚠️ **{at_risk_count} طالب** يحتاج متابعة (حضور أو مهام منخفضة).\n"
        else:
            msg += "✅ جميع الطلاب ضمن المعدلات المقبولة.\n"
        if issue_count:
            msg += (
                f"📋 وُجدت **{issue_count} مشكلة** في جودة البيانات "
                "(درجات غير مسجّلة أو قيم غير منطقية). "
                "راجع قسم «مراجعة جودة البيانات» للتفاصيل.\n"
            )
        else:
            msg += "📋 بيانات نظيفة — لا مشكلات في جودة البيانات.\n"
        msg += "\nاكتب «من يحتاج متابعة» أو «تقرير [اسم الطالب]» للحصول على تفاصيل."

    return {"ok": True, "data": None, "message": msg}
