import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date

st.set_page_config(page_title="SchoolFlow AI", page_icon="📘", layout="wide")
st.title("SchoolFlow AI")
st.caption("نسخة تجريبية أولى — لمعلم واحد — رفع Excel ثم إعداد ملخص وتقارير")

st.info(
    "تنبيه: ابدأ ببيانات تجريبية أو بيانات مصرح باستخدامها. "
    "لا ترفع بيانات طلاب حقيقية قبل موافقة المدرسة واعتماد ضوابط الخصوصية."
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REQUIRED = [
    "Student code", "Week", "Days scheduled", "Days attended",
    "Tasks set", "Tasks completed", "Quiz score / 10",
    "Observation", "Next step",
]
OPTIONAL_NAME_COL = "Student name"   # Phase 3: used if present in the sheet

NUMERIC_COLS = [
    "Week", "Days scheduled", "Days attended",
    "Tasks set", "Tasks completed", "Quiz score / 10",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Phase 2 – Validation
# ---------------------------------------------------------------------------

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

        # Missing required numeric cells
        for col in ["Days scheduled", "Days attended", "Tasks set", "Tasks completed"]:
            if pd.isna(row[col]):
                issues.append({
                    "Student code": code, "Week": week_label,
                    "Column": col, "Issue": "قيمة مفقودة / Missing value",
                })

        # Quiz score: distinguish missing from zero
        if pd.isna(row["Quiz score / 10"]):
            issues.append({
                "Student code": code, "Week": week_label,
                "Column": "Quiz score / 10",
                "Issue": "درجة الاختبار غير مسجلة / Quiz score not recorded",
            })

        # Logical: attended > scheduled
        sched = row["Days scheduled"]
        att = row["Days attended"]
        if pd.notna(sched) and pd.notna(att) and att > sched:
            issues.append({
                "Student code": code, "Week": week_label,
                "Column": "Days attended",
                "Issue": f"الحضور ({att:g}) أكبر من المجدول ({sched:g}) / Attended > Scheduled",
            })

        # Logical: completed > set
        t_set = row["Tasks set"]
        t_done = row["Tasks completed"]
        if pd.notna(t_set) and pd.notna(t_done) and t_done > t_set:
            issues.append({
                "Student code": code, "Week": week_label,
                "Column": "Tasks completed",
                "Issue": f"المهام المنجزة ({t_done:g}) أكبر من المعيّنة ({t_set:g}) / Completed > Set",
            })

    return pd.DataFrame(issues, columns=["Student code", "Week", "Column", "Issue"])


# ---------------------------------------------------------------------------
# Phase 1 + core calculations
# ---------------------------------------------------------------------------

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

    # Drop rows with no student code or no week — these cannot be attributed
    df = df.dropna(subset=["Student code", "Week"])
    df["Week"] = df["Week"].astype(int)

    summary = []
    for student, g in df.groupby("Student code", sort=True):
        # Use the student name from the most recent row if the column exists
        if has_name:
            name_val = safe_text(g.sort_values("Week").iloc[-1].get(OPTIONAL_NAME_COL, ""))
            display_name = name_val if name_val else student
        else:
            display_name = student

        # Sum only non-NaN values (rows where that column was present)
        scheduled = g["Days scheduled"].sum(min_count=1)
        attended  = g["Days attended"].sum(min_count=1)
        tasks     = g["Tasks set"].sum(min_count=1)
        completed = g["Tasks completed"].sum(min_count=1)
        scores    = g["Quiz score / 10"].dropna()  # NaN = not recorded, kept out

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


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def make_workbook(clean, summary, weekly):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        clean.to_excel(writer,   sheet_name="Validated data",    index=False)
        summary.to_excel(writer, sheet_name="Student summaries", index=False)
        weekly.to_excel(writer,  sheet_name="Weekly summary",    index=False)
    out.seek(0)
    return out


# ---------------------------------------------------------------------------
# Phase 3 – Parent messages
# ---------------------------------------------------------------------------

def parent_message(row, language):
    code     = row["Student code"]
    name     = row.get("Student name", code) or code   # Phase 3
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


# ---------------------------------------------------------------------------
# UI — Step 1: Upload
# ---------------------------------------------------------------------------

st.subheader("1) ارفع ملف متابعة الطلاب")
uploaded = st.file_uploader("اختر ملف Excel بصيغة .xlsx", type=["xlsx"])

if uploaded:
    # Phase 1 fix: read sheet names from a fresh stream; never reuse a spent pointer
    try:
        xls = pd.ExcelFile(fresh_bytes(uploaded))
    except Exception as e:
        st.error(f"تعذر فتح الملف: {e}")
        st.stop()

    default_idx = xls.sheet_names.index("Weekly tracking") if "Weekly tracking" in xls.sheet_names else 0
    sheet = st.selectbox("اختر ورقة البيانات", xls.sheet_names, index=default_idx)

    try:
        # Phase 1 fix: fresh stream for the actual data read
        raw = pd.read_excel(fresh_bytes(uploaded), sheet_name=sheet, header=4)
    except Exception as e:
        st.error(f"تعذر قراءة الورقة: {e}")
        st.stop()

    raw.columns = [str(c).strip() for c in raw.columns]

    missing_cols = [c for c in REQUIRED if c not in raw.columns]
    has_name = OPTIONAL_NAME_COL in raw.columns   # Phase 3

    if missing_cols:
        st.error("الأعمدة التالية غير موجودة في الملف: " + "، ".join(missing_cols))
        st.write("الأعمدة التي وجدناها:", list(raw.columns))
        st.stop()

    cols_to_load = REQUIRED + ([OPTIONAL_NAME_COL] if has_name else [])
    data = raw[cols_to_load].dropna(how="all")
    st.success(f"تمت قراءة {len(data)} سجل من ورقة: **{sheet}**"
               + (" (عمود الاسم موجود ✓)" if has_name else " (عمود الاسم غير موجود — سيُستخدم الرمز)"))
    st.write("معاينة أول 10 سجلات:", data.head(10))

    # ------------------------------------------------------------------
    # Phase 2 – Validation panel
    # ------------------------------------------------------------------
    st.subheader("2) مراجعة جودة البيانات")
    issues = validate(data)
    if issues.empty:
        st.success("لا توجد مشكلات في البيانات — جميع القيم المطلوبة موجودة ومنطقية.")
    else:
        st.warning(f"⚠️ وُجدت {len(issues)} مشكلة في البيانات. راجعها قبل المتابعة.")
        st.dataframe(issues, use_container_width=True, hide_index=True)
        st.caption(
            "ملاحظة: الصفوف التي بها مشكلات لن تُحذف تلقائيًا. "
            "قيمة صفر (0) ≠ قيمة مفقودة (فارغة). "
            "راجع البيانات في Excel أولاً إذا أردت تصحيحها."
        )

    if st.button("تحليل البيانات وإنشاء التقارير", type="primary"):
        clean, summary, weekly = build_outputs(data, has_name)
        st.session_state["clean"]    = clean
        st.session_state["summary"]  = summary
        st.session_state["weekly"]   = weekly
        st.session_state["has_name"] = has_name
        st.success("اكتمل التحليل. راجع النتائج قبل استخدامها.")

# ---------------------------------------------------------------------------
# UI — Steps 3–6: Results (only shown after analysis)
# ---------------------------------------------------------------------------

if "summary" in st.session_state:
    clean    = st.session_state["clean"]
    summary  = st.session_state["summary"]
    weekly   = st.session_state["weekly"]
    has_name = st.session_state.get("has_name", False)

    st.divider()

    # Step 3 – Overview metrics
    st.subheader("3) ملخص المعلم")
    c1, c2, c3 = st.columns(3)
    c1.metric("عدد الطلاب",  len(summary))
    c2.metric("عدد الأسابيع", int(clean["Week"].nunique()))
    c3.metric("عدد السجلات",  len(clean))

    # Step 4 – Weekly summary
    st.subheader("4) ملخص أسبوعي للفصل")
    st.dataframe(weekly, use_container_width=True, hide_index=True)

    # Step 5 – Student summary
    st.subheader("5) ملخص كل طالب")
    st.dataframe(summary, use_container_width=True, hide_index=True)

    # Phase 5 – Per-student weekly detail drill-down
    st.subheader("6) تفاصيل أسبوعية لطالب محدد")
    student_options = summary["Student code"].tolist()
    if has_name:
        label_map = dict(zip(summary["Student code"], summary["Student name"]))
        student_options_labels = [f"{c} — {label_map[c]}" for c in student_options]
    else:
        student_options_labels = student_options

    selected_label = st.selectbox("اختر الطالب", student_options_labels)
    selected_code  = student_options[student_options_labels.index(selected_label)]
    student_rows   = clean[clean["Student code"] == selected_code].sort_values("Week")
    detail_cols    = ["Week", "Days scheduled", "Days attended",
                      "Tasks set", "Tasks completed", "Quiz score / 10",
                      "Observation", "Next step"]
    if has_name and OPTIONAL_NAME_COL in student_rows.columns:
        detail_cols = [OPTIONAL_NAME_COL] + detail_cols
    st.dataframe(student_rows[detail_cols], use_container_width=True, hide_index=True)

    # Step 7 – Parent messages
    st.subheader("7) إنشاء رسائل أولياء الأمور")
    language = st.radio("لغة الرسالة", ["English", "العربية"], horizontal=True)
    for _, row in summary.iterrows():
        label = row["Student name"] if has_name else row["Student code"]
        with st.expander(f"رسالة الطالب: {label}"):
            st.text_area(
                "راجع الرسالة قبل إرسالها",
                parent_message(row, language),
                height=210,
                key=f"msg_{row['Student code']}_{language}",
            )

    # Step 8 – Download
    st.subheader("8) تنزيل النتائج")
    workbook = make_workbook(clean, summary, weekly)
    st.download_button(
        "تنزيل ملف التقارير Excel",
        data=workbook,
        file_name="SchoolFlow_AI_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.caption(
        "هذه نسخة أولية: لا ترسل رسائل تلقائيًا، ولا تستبدل مراجعة المعلم. "
        "يجب التحقق من دقة البيانات والقوالب مع منتصر قبل اعتمادها."
    )
