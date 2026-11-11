"""
app_logic.py
------------
Pure Python logic for SchoolFlow AI — no Streamlit imports.
Both app.py and the test suite import from here.
"""

import pandas as pd
from io import BytesIO

# ===========================================================================
# Constants
# ===========================================================================
REQUIRED = [
    "Student code", "Week", "Days scheduled", "Days attended",
    "Tasks set", "Tasks completed", "Quiz score / 10",
    "Observation", "Next step",
]
OPTIONAL_NAME_COL = "Student name"

NUMERIC_COLS = [
    "Week", "Days scheduled", "Days attended",
    "Tasks set", "Tasks completed", "Quiz score / 10",
]

# ===========================================================================
# Helpers
# ===========================================================================

def pct(n, d):
    return (n / d * 100) if d else 0.0


def safe_text(v):
    if pd.isna(v):
        return ""
    return str(v).strip()


def fresh_bytes(uploaded) -> BytesIO:
    """
    Return a fresh BytesIO stream from the uploaded file object.
    Calling this before every pd.read_excel / pd.ExcelFile call avoids
    the stream-exhaustion bug that occurs on Streamlit reruns.
    """
    return BytesIO(uploaded.getvalue())


# ===========================================================================
# Phase 2 – Validation
# ===========================================================================

def validate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a DataFrame of issues.  Each row is one flagged cell/row.
    Columns: Student code, Week, Column, Issue
    This function does NOT modify df; it only reports problems.
    """
    issues = []

    numeric_temp = df.copy()
    for c in NUMERIC_COLS:
        numeric_temp[c] = pd.to_numeric(numeric_temp[c], errors="coerce")

    for idx, row in numeric_temp.iterrows():
        code = safe_text(row.get("Student code")) or f"row {idx + 1}"
        week = row.get("Week")
        week_label = f"Week {int(week)}" if pd.notna(week) else "Week ?"

        for col in ["Days scheduled", "Days attended", "Tasks set", "Tasks completed"]:
            if pd.isna(row[col]):
                issues.append({
                    "Student code": code, "Week": week_label,
                    "Column": col, "Issue": "قيمة مفقودة / Missing value",
                })

        if pd.isna(row["Quiz score / 10"]):
            issues.append({
                "Student code": code, "Week": week_label,
                "Column": "Quiz score / 10",
                "Issue": "درجة الاختبار غير مسجلة / Quiz score not recorded",
            })

        sched = row["Days scheduled"]
        att = row["Days attended"]
        if pd.notna(sched) and pd.notna(att) and att > sched:
            issues.append({
                "Student code": code, "Week": week_label,
                "Column": "Days attended",
                "Issue": f"الحضور ({att:g}) أكبر من المجدول ({sched:g}) / Attended > Scheduled",
            })

        t_set = row["Tasks set"]
        t_done = row["Tasks completed"]
        if pd.notna(t_set) and pd.notna(t_done) and t_done > t_set:
            issues.append({
                "Student code": code, "Week": week_label,
                "Column": "Tasks completed",
                "Issue": f"المهام المنجزة ({t_done:g}) أكبر من المعيّنة ({t_set:g}) / Completed > Set",
            })

    return pd.DataFrame(issues, columns=["Student code", "Week", "Column", "Issue"])


# ===========================================================================
# Phase 1 + core calculations
# ===========================================================================

def build_outputs(df: pd.DataFrame, has_name: bool):
    """
    Build clean data, per-student summary, and weekly summary.
    Missing numeric values are NOT filled with zero; they remain NaN so that
    percentages are computed only from present values, and the validation step
    has already informed Montaser about every missing cell.
    Zero scores are preserved as 0.0, distinct from NaN (not recorded).
    """
    df = df.copy()
    for c in NUMERIC_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Student code"] = df["Student code"].astype(str).str.strip()

    df = df.dropna(subset=["Student code", "Week"])
    df["Week"] = df["Week"].astype(int)

    summary = []
    for student, g in df.groupby("Student code", sort=True):
        if has_name:
            name_val = safe_text(g.sort_values("Week").iloc[-1].get(OPTIONAL_NAME_COL, ""))
            display_name = name_val if name_val else student
        else:
            display_name = student

        scheduled = g["Days scheduled"].sum(min_count=1)
        attended  = g["Days attended"].sum(min_count=1)
        tasks     = g["Tasks set"].sum(min_count=1)
        completed = g["Tasks completed"].sum(min_count=1)
        scores    = g["Quiz score / 10"].dropna()

        latest = g.sort_values("Week").iloc[-1]

        summary.append({
            "Student code": student,
            "Student name": display_name,
            "Weeks recorded": int(g["Week"].nunique()),
            "Attendance": f"{pct(attended, scheduled):.1f}%" if pd.notna(scheduled) and scheduled > 0 else "N/A",
            "Attendance attended/scheduled": f"{attended:g}/{scheduled:g}" if pd.notna(scheduled) else "N/A",
            "Task completion": f"{pct(completed, tasks):.1f}%" if pd.notna(tasks) and tasks > 0 else "N/A",
            "Tasks completed/set": f"{completed:g}/{tasks:g}" if pd.notna(tasks) else "N/A",
            "Mean quiz / 10": round(float(scores.mean()), 2) if len(scores) else None,
            "Quiz weeks recorded": int(len(scores)),
            "Latest observation": safe_text(latest.get("Observation", "")),
            "Next step": safe_text(latest.get("Next step", "")),
        })

    summary_df = pd.DataFrame(summary)

    weekly = df.groupby("Week", sort=True).agg(
        **{
            "Attended days":  ("Days attended", "sum"),
            "Scheduled days": ("Days scheduled", "sum"),
            "Tasks completed": ("Tasks completed", "sum"),
            "Tasks set":       ("Tasks set", "sum"),
            "Mean quiz / 10":  ("Quiz score / 10", "mean"),
        }
    ).reset_index()
    weekly["Attendance rate"] = weekly.apply(
        lambda r: f"{pct(r['Attended days'], r['Scheduled days']):.1f}%", axis=1
    )
    weekly["Task completion"] = weekly.apply(
        lambda r: f"{pct(r['Tasks completed'], r['Tasks set']):.1f}%", axis=1
    )
    weekly["Mean quiz / 10"] = weekly["Mean quiz / 10"].round(2)

    return df, summary_df, weekly


# ===========================================================================
# Export
# ===========================================================================

def make_workbook(clean, summary, weekly):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        clean.to_excel(writer,   sheet_name="Validated data",    index=False)
        summary.to_excel(writer, sheet_name="Student summaries", index=False)
        weekly.to_excel(writer,  sheet_name="Weekly summary",    index=False)
    out.seek(0)
    return out


# ===========================================================================
# Phase 3 – Parent messages
# ===========================================================================

def parent_message(row, language):
    code     = row["Student code"]
    name     = row.get("Student name", code) or code
    attend   = row["Attendance"]
    complete = row["Task completion"]
    score    = row["Mean quiz / 10"]
    obs      = row["Latest observation"] or ("No observation was provided."
                                              if language == "English"
                                              else "لم تُسجَّل ملاحظة.")
    step     = row["Next step"] or ("The next learning step will be agreed by the teacher."
                                     if language == "English"
                                     else "ستُحدَّد الخطوة القادمة مع المعلم.")
    score_en = f"{score}/10" if pd.notna(score) else "not recorded"
    score_ar = f"{score}/10" if pd.notna(score) else "غير مسجل"

    if language == "English":
        return (
            f"Hello,\n\n"
            f"Here is {name}'s learning update.\n"
            f"Attendance: {attend}.  Task completion: {complete}.  "
            f"Mean quiz score: {score_en}.\n\n"
            f"Teacher observation: {obs}\n"
            f"Next step: {step}\n\n"
            "Please contact the teacher if you would like to discuss this update.\n\n"
            "Thank you."
        )
    return (
        f"مرحبًا،\n\n"
        f"هذا ملخص متابعة الطالب ({name}).\n"
        f"الحضور: {attend}.  إنجاز المهام: {complete}.  "
        f"متوسط الاختبارات: {score_ar}.\n\n"
        f"ملاحظة المعلم: {obs}\n"
        f"الخطوة القادمة: {step}\n\n"
        "يرجى التواصل مع المعلم إذا رغبتم في مناقشة هذا التقرير.\n\n"
        "شكرًا لتعاونكم."
    )
