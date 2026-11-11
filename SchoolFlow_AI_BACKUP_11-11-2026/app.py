import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date

st.set_page_config(
    page_title="SchoolFlow AI",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===========================================================================
# CSS — Dashboard Design
# Palette: Dark Green #1B5E4A | Gold #D4A017 | White #FFFFFF | Light #F5F6FA
# ===========================================================================
st.markdown("""
<style>
/* ── Fonts ───────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Cairo', 'Inter', 'Segoe UI', system-ui, sans-serif;
}

/* ── App background ──────────────────────────────────────────────────── */
.stApp { background-color: #F5F6FA; }

/* ── Hide Streamlit chrome ───────────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* ── Sidebar — dark green ────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1B5E4A 0%, #154a38 100%) !important;
    border-left: none !important;
}
[data-testid="stSidebar"] * { color: #ffffff !important; }
[data-testid="stSidebarNav"] { display: none; }

/* ── Top bar ─────────────────────────────────────────────────────────── */
.sf-topbar {
    background: #ffffff;
    border-bottom: 1px solid #E8EBF0;
    padding: 0.5rem 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.2rem;
    direction: rtl;
}
.sf-topbar-date {
    display: flex; align-items: center; gap: 0.4rem;
    font-size: 0.82rem; color: #6B7280; font-weight: 500;
}
.sf-topbar-actions {
    display: flex; align-items: center; gap: 0.6rem;
}
.sf-topbar-icon {
    width: 32px; height: 32px;
    border-radius: 8px; border: 1px solid #E8EBF0;
    background: #F5F6FA;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.9rem; cursor: pointer;
}
.sf-lang-btn {
    padding: 3px 12px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 700;
    cursor: pointer;
}
.sf-lang-ar {
    background: #1B5E4A; color: #ffffff;
    border: 1px solid #1B5E4A;
}
.sf-lang-en {
    background: transparent; color: #6B7280;
    border: 1px solid #E8EBF0;
    margin-right: 4px;
}

/* ── Hero banner ─────────────────────────────────────────────────────── */
.sf-hero {
    background: linear-gradient(135deg, #1B5E4A 0%, #2E7D5A 55%, #1a5240 100%);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    direction: rtl;
    position: relative;
    overflow: hidden;
}
.sf-hero::before {
    content: '';
    position: absolute;
    top: -40px; left: -40px;
    width: 200px; height: 200px;
    background: rgba(212,160,23,0.08);
    border-radius: 50%;
}
.sf-hero::after {
    content: '';
    position: absolute;
    bottom: -60px; right: 30%;
    width: 280px; height: 280px;
    background: rgba(255,255,255,0.04);
    border-radius: 50%;
}
.sf-hero-text { position: relative; z-index: 2; }
.sf-hero-greeting {
    font-size: 0.85rem; color: #D4A017;
    font-weight: 600; margin-bottom: 0.3rem;
    display: flex; align-items: center; gap: 0.4rem;
}
.sf-hero-title {
    font-size: 1.7rem; font-weight: 900;
    color: #ffffff; line-height: 1.25;
    margin-bottom: 0.5rem;
}
.sf-hero-subtitle {
    font-size: 0.88rem; color: rgba(255,255,255,0.80);
    line-height: 1.6; max-width: 420px;
}
.sf-hero-badge {
    position: relative; z-index: 2;
    background: rgba(212,160,23,0.18);
    border: 1px solid rgba(212,160,23,0.45);
    border-radius: 12px;
    padding: 0.7rem 1.2rem;
    text-align: center;
    min-width: 130px;
}
.sf-hero-badge-icon { font-size: 2rem; }
.sf-hero-badge-text {
    font-size: 0.75rem; color: #D4A017;
    font-weight: 600; margin-top: 0.3rem;
}

/* ── Metric cards ─────────────────────────────────────────────────────── */
.sf-metrics-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 1.4rem;
    direction: rtl;
}
.sf-metric-card {
    background: #ffffff;
    border-radius: 14px;
    border: 1px solid #E8EBF0;
    padding: 1.1rem 1.2rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05);
    display: flex;
    align-items: flex-start;
    gap: 0.85rem;
    direction: rtl;
}
.sf-metric-icon {
    width: 44px; height: 44px;
    border-radius: 11px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.3rem; flex-shrink: 0;
}
.sf-icon-green  { background: rgba(27,94,74,0.10); }
.sf-icon-gold   { background: rgba(212,160,23,0.12); }
.sf-icon-blue   { background: rgba(59,130,246,0.10); }
.sf-icon-purple { background: rgba(124,92,216,0.10); }
.sf-metric-body { flex: 1; }
.sf-metric-label { font-size: 0.76rem; color: #9CA3AF; font-weight: 600; margin-bottom: 0.2rem; }
.sf-metric-value { font-size: 1.65rem; font-weight: 900; color: #1A2B3C; line-height: 1; }
.sf-metric-sub   { font-size: 0.75rem; color: #6B7280; margin-top: 0.25rem; }
.sf-metric-badge-up   { color: #16a34a; font-weight: 700; font-size: 0.75rem; }
.sf-metric-badge-warn { color: #D4A017; font-weight: 700; font-size: 0.75rem; }

/* ── Two-column section ──────────────────────────────────────────────── */
.sf-two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.2rem;
    margin-bottom: 1.4rem;
}
.sf-two-col-wide { grid-template-columns: 3fr 2fr; }

/* ── White cards ─────────────────────────────────────────────────────── */
.sf-card {
    background: #ffffff;
    border-radius: 14px;
    border: 1px solid #E8EBF0;
    padding: 1.3rem 1.4rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05);
    direction: rtl;
}
.sf-card-header {
    display: flex; align-items: center; gap: 0.55rem;
    margin-bottom: 1rem;
    padding-bottom: 0.7rem;
    border-bottom: 1px solid #F0F1F5;
    direction: rtl;
}
.sf-card-header-icon {
    width: 30px; height: 30px;
    border-radius: 8px;
    background: rgba(27,94,74,0.10);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.95rem;
}
.sf-card-title {
    font-size: 0.92rem; font-weight: 700; color: #1A2B3C;
}

/* ── Section headers ─────────────────────────────────────────────────── */
.sf-section-header {
    display: flex; align-items: center; gap: 0.6rem;
    margin: 1.6rem 0 0.85rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #E8EBF0;
    direction: rtl;
}
.sf-section-num {
    background: #1B5E4A; color: #D4A017;
    width: 28px; height: 28px;
    border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.80rem; font-weight: 700; flex-shrink: 0;
}
.sf-section-title { font-size: 0.98rem; font-weight: 700; color: #1A2B3C; }

/* ── Observations list ───────────────────────────────────────────────── */
.sf-obs-item {
    display: flex; align-items: flex-start; gap: 0.7rem;
    padding: 0.6rem 0;
    border-bottom: 1px solid #F5F6FA;
    direction: rtl;
}
.sf-obs-item:last-child { border-bottom: none; }
.sf-obs-code {
    background: #1B5E4A; color: #ffffff;
    font-size: 0.72rem; font-weight: 700;
    padding: 2px 8px; border-radius: 5px;
    flex-shrink: 0; margin-top: 1px;
}
.sf-obs-text { font-size: 0.82rem; color: #374151; line-height: 1.5; }
.sf-obs-empty { font-size: 0.85rem; color: #6B7280; text-align: center; padding: 1rem 0; }

/* ── Quick actions grid ──────────────────────────────────────────────── */
.sf-quick-grid {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
}
.sf-quick-btn {
    background: #F5F6FA;
    border: 1px solid #E8EBF0;
    border-radius: 11px;
    padding: 0.85rem 1rem;
    display: flex; align-items: center; gap: 0.7rem;
    cursor: pointer; transition: all 0.18s ease;
    direction: rtl;
    text-decoration: none;
}
.sf-quick-btn:hover { background: #EEF8F4; border-color: #1B5E4A; }
.sf-quick-icon {
    width: 36px; height: 36px; border-radius: 9px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem; flex-shrink: 0;
}
.sf-qi-green  { background: rgba(27,94,74,0.10); }
.sf-qi-gold   { background: rgba(212,160,23,0.12); }
.sf-qi-blue   { background: rgba(59,130,246,0.10); }
.sf-qi-purple { background: rgba(124,92,216,0.10); }
.sf-quick-label {
    font-size: 0.82rem; font-weight: 700; color: #1A2B3C;
    line-height: 1.3;
}
.sf-quick-sub { font-size: 0.72rem; color: #9CA3AF; }

/* ── Upload card ─────────────────────────────────────────────────────── */
.sf-upload-area {
    background: #ffffff;
    border: 2px dashed #C5D8D1;
    border-radius: 14px;
    padding: 1.5rem 1.8rem;
    text-align: center;
    transition: border-color 0.2s;
}
.sf-upload-area:hover { border-color: #1B5E4A; }

/* ── Status pills ────────────────────────────────────────────────────── */
.sf-pill-ok {
    background: rgba(22,163,74,0.10); color: #166534;
    border: 1px solid rgba(22,163,74,0.25);
    border-radius: 20px; padding: 3px 12px;
    font-size: 0.79rem; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}
.sf-pill-warn {
    background: rgba(212,160,23,0.10); color: #92400e;
    border: 1px solid rgba(212,160,23,0.30);
    border-radius: 20px; padding: 3px 12px;
    font-size: 0.79rem; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}

/* ── Buttons ─────────────────────────────────────────────────────────── */
div.stButton > button[kind="primary"] {
    background: linear-gradient(90deg, #1B5E4A, #236b56) !important;
    color: #ffffff !important; border: none !important;
    border-radius: 9px !important; font-weight: 700 !important;
    font-size: 0.92rem !important; padding: 0.55rem 1.6rem !important;
    box-shadow: 0 3px 12px rgba(27,94,74,0.28) !important;
    font-family: 'Cairo', sans-serif !important;
}
div.stButton > button[kind="primary"]:hover {
    background: linear-gradient(90deg, #154a38, #1B5E4A) !important;
    transform: translateY(-1px) !important;
}
div.stButton > button {
    border-radius: 9px !important;
    font-family: 'Cairo', sans-serif !important;
}
div.stDownloadButton > button {
    background: linear-gradient(90deg, #D4A017, #e6b52a) !important;
    color: #1A2B3C !important; border: none !important;
    border-radius: 9px !important; font-weight: 700 !important;
    font-size: 0.92rem !important; padding: 0.55rem 1.6rem !important;
    box-shadow: 0 3px 12px rgba(212,160,23,0.28) !important;
    font-family: 'Cairo', sans-serif !important;
}
div.stDownloadButton > button:hover {
    background: linear-gradient(90deg, #b8880f, #D4A017) !important;
    transform: translateY(-1px) !important;
}

/* ── Dataframe ───────────────────────────────────────────────────────── */
.stDataFrame {
    border-radius: 10px !important;
    border: 1px solid #E8EBF0 !important;
}

/* ── Selectbox / inputs ──────────────────────────────────────────────── */
.stSelectbox > div > div { border-radius: 9px !important; }
.stFileUploader > div   { border-radius: 9px !important; }
.stTextArea > div > div > textarea {
    border-radius: 9px !important;
    font-family: 'Cairo', 'Inter', sans-serif !important;
    font-size: 0.87rem !important;
}

/* ── Global text contrast on light main canvas ──────────────────────── */
[data-testid="stMain"] {
    color: #1F2937 !important;
}
[data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] h1,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] h2,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] h3,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] h4,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] h5,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] h6,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] li,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] td,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] th,
[data-testid="stMain"] label,
[data-testid="stMain"] [data-testid="stCaptionContainer"],
[data-testid="stMain"] .stCaption {
    color: #263238 !important;
    -webkit-text-fill-color: #263238 !important;
}
[data-testid="stMain"] [data-testid="stDataFrame"] {
    color: #263238 !important;
}
[data-testid="stMain"] [data-testid="stDataFrame"] * {
    color: #263238 !important;
    -webkit-text-fill-color: #263238 !important;
}
.sf-metric-label, .sf-quick-sub, .sf-obs-empty, .stCaption {
    color: #4B5563 !important;
}
[data-testid="stMain"] input,
[data-testid="stMain"] textarea,
[data-testid="stMain"] select {
    color: #1F2937 !important;
    -webkit-text-fill-color: #1F2937 !important;
}

/* ── Chat input — high contrast on desktop and mobile ───────────────── */
[data-testid="stChatInput"] {
    background: #202824 !important;
    border: 1px solid #527568 !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.16) !important;
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] textarea:focus {
    background: #202824 !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    caret-color: #D4A017 !important;
    font-family: 'Cairo', 'Inter', sans-serif !important;
    font-size: 0.95rem !important;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: #D1D5DB !important;
    -webkit-text-fill-color: #D1D5DB !important;
    opacity: 1 !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #D4A017 !important;
    box-shadow: 0 0 0 2px rgba(212,160,23,0.22) !important;
}
[data-testid="stChatInput"] button {
    background: #1B5E4A !important;
    color: #FFFFFF !important;
    border-radius: 9px !important;
}
[data-testid="stChatInput"] button svg {
    fill: #FFFFFF !important;
    color: #FFFFFF !important;
}

/* ── Chat message bubbles — force readable text on mobile/desktop ────── */
/* Streamlit chat messages can inherit theme text colors; force every text
   node in the message body to a dark color with full opacity. */
[data-testid="stChatMessage"],
.stChatMessage {
    background: #FFFFFF !important;
    border: 1px solid #D9E1E7 !important;
    border-radius: 12px !important;
    padding: 0.85rem 1rem !important;
    margin: 0.55rem 0 !important;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"],
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] *,
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] span,
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li,
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] strong,
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] em,
[data-testid="stChatMessage"] [data-testid="stCaptionContainer"],
[data-testid="stChatMessage"] [data-testid="stCaptionContainer"] *,
.stChatMessage [data-testid="stMarkdownContainer"],
.stChatMessage [data-testid="stMarkdownContainer"] *,
.stChatMessage p,
.stChatMessage span,
.stChatMessage li,
.stChatMessage strong,
.stChatMessage em {
    color: #17212B !important;
    -webkit-text-fill-color: #17212B !important;
    opacity: 1 !important;
    text-shadow: none !important;
}
[data-testid="stChatMessage"] a,
.stChatMessage a {
    color: #126B50 !important;
    -webkit-text-fill-color: #126B50 !important;
}
[data-testid="stChatMessage"] code,
[data-testid="stChatMessage"] pre,
.stChatMessage code,
.stChatMessage pre {
    background: #F1F5F3 !important;
    color: #17212B !important;
    -webkit-text-fill-color: #17212B !important;
}
/* ── Expander ────────────────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: #ffffff !important;
    border: 1px solid #E8EBF0 !important;
    border-radius: 9px !important;
    font-weight: 700 !important; color: #1A2B3C !important;
    font-family: 'Cairo', sans-serif !important;
}
.streamlit-expanderContent {
    background: #FAFBFC !important;
    border: 1px solid #E8EBF0 !important;
    border-top: none !important;
    border-radius: 0 0 9px 9px !important;
}

/* ── Divider ─────────────────────────────────────────────────────────── */
.sf-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #D4A01755, transparent);
    margin: 1.6rem 0; border: none;
}

/* ── Footer ──────────────────────────────────────────────────────────── */
.sf-footer {
    text-align: center; padding: 1.4rem 1rem 2rem;
    margin-top: 2.5rem; border-top: 1px solid #E8EBF0;
    color: #9CA3AF; font-size: 0.76rem; direction: rtl;
}
.sf-footer strong { color: #1B5E4A; }

/* ── Caption ─────────────────────────────────────────────────────────── */
.stCaption { color: #9CA3AF !important; font-size: 0.78rem !important; }

/* ── Sidebar nav item active ─────────────────────────────────────────── */
.sf-nav-item-active {
    background: #D4A017 !important;
    color: #1A2B3C !important;
    border-radius: 9px;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)

# ===========================================================================
# Constants  (unchanged)
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
# Helpers  (unchanged)
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
# Phase 2 – Validation  (unchanged)
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
# Phase 1 + core calculations  (unchanged)
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
# Export  (unchanged)
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
# Phase 3 – Parent messages  (unchanged)
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


# ===========================================================================
# Helper: build SVG bar chart from weekly data
# ===========================================================================

def _build_weekly_svg(weekly_df: pd.DataFrame) -> str:
    """Generate a compact SVG bar+line chart for weekly attendance & task rates."""
    weeks = weekly_df["Week"].tolist()
    n = len(weeks)
    if n == 0:
        return ""

    # Extract numeric rates
    def parse_pct(s):
        try:
            return float(str(s).replace("%", "").strip())
        except Exception:
            return 0.0

    att_rates  = [parse_pct(r) for r in weekly_df["Attendance rate"].tolist()]
    task_rates = [parse_pct(r) for r in weekly_df["Task completion"].tolist()]

    W, H = 340, 180
    pad_l, pad_r, pad_t, pad_b = 30, 15, 15, 40
    chart_w = W - pad_l - pad_r
    chart_h = H - pad_t - pad_b

    bar_w = max(10, int(chart_w / n * 0.5))
    slot_w = chart_w / n

    def x_center(i):
        return pad_l + slot_w * i + slot_w / 2

    def y_val(v, min_v=50):
        clamped = max(min_v, min(v, 110))
        return pad_t + chart_h * (1 - (clamped - min_v) / (110 - min_v))

    # Y-axis grid lines
    grid_lines = ""
    for tick in [60, 70, 80, 90, 100]:
        y = y_val(tick)
        grid_lines += (
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W - pad_r}" y2="{y:.1f}" '
            f'stroke="#E8EBF0" stroke-width="1"/>'
            f'<text x="{pad_l - 4}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="9" fill="#9CA3AF">{tick}%</text>'
        )

    # Bars (green — attendance)
    bars = ""
    for i, v in enumerate(att_rates):
        x = x_center(i) - bar_w / 2
        y = y_val(v)
        bh = (H - pad_b) - y
        bars += (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{max(2,bh):.1f}" '
            f'rx="3" fill="#1B5E4A" opacity="0.85"/>'
        )

    # Line (gold — task completion)
    pts = " ".join(f"{x_center(i):.1f},{y_val(v):.1f}" for i, v in enumerate(task_rates))
    line_path = f'<polyline points="{pts}" fill="none" stroke="#D4A017" stroke-width="2.5" stroke-linejoin="round"/>'
    dots = "".join(
        f'<circle cx="{x_center(i):.1f}" cy="{y_val(v):.1f}" r="4" fill="#D4A017" stroke="#fff" stroke-width="1.5"/>'
        for i, v in enumerate(task_rates)
    )

    # X-axis labels
    x_labels = "".join(
        f'<text x="{x_center(i):.1f}" y="{H - pad_b + 14}" text-anchor="middle" '
        f'font-size="9" fill="#6B7280">الأسبوع {w}</text>'
        for i, w in enumerate(weeks)
    )

    # Legend
    legend = (
        f'<rect x="{pad_l}" y="{H - 10}" width="10" height="8" rx="2" fill="#1B5E4A" opacity="0.85"/>'
        f'<text x="{pad_l + 13}" y="{H - 3}" font-size="8.5" fill="#6B7280">نسبة الحضور</text>'
        f'<line x1="{pad_l + 80}" y1="{H - 6}" x2="{pad_l + 93}" y2="{H - 6}" '
        f'stroke="#D4A017" stroke-width="2.5"/>'
        f'<circle cx="{pad_l + 87}" cy="{H - 6}" r="3" fill="#D4A017"/>'
        f'<text x="{pad_l + 96}" y="{H - 3}" font-size="8.5" fill="#6B7280">إنجاز المهام</text>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;display:block;">'
        f'{grid_lines}{bars}{line_path}{dots}{x_labels}{legend}'
        f'</svg>'
    )


# ===========================================================================
# Language initialisation  (must run before sidebar renders)
# ===========================================================================

if "ui_lang" not in st.session_state:
    st.session_state["ui_lang"] = "en"   # English is the default

_L = st.session_state["ui_lang"]   # "en" | "ar"
_IS_AR = (_L == "ar")
_DIR   = "rtl" if _IS_AR else "ltr"

# Translation helper — T(english, arabic)
def T(en: str, ar: str) -> str:      # noqa: N802  (short name intentional)
    return ar if _IS_AR else en

# ===========================================================================
# UI — Sidebar
# ===========================================================================
with st.sidebar:
    # Logo block
    _sub = (
        "منصة ذكية لمساعدة المعلمين<br>وإدارة متابعة الطلاب"
        if _IS_AR else
        "Smart platform for teachers<br>and student tracking"
    )
    st.markdown(f"""
    <div style="text-align:center; padding: 1.2rem 0.5rem 1rem;">
      <div style="width:60px;height:60px;background:#D4A017;border-radius:14px;
                  display:inline-flex;align-items:center;justify-content:center;
                  font-size:1.8rem;margin-bottom:0.6rem;">🎓</div>
      <div style="font-size:1.1rem;font-weight:900;color:#ffffff;
                  font-family:'Cairo',sans-serif;">SchoolFlow AI</div>
      <div style="font-size:0.72rem;color:rgba(255,255,255,0.65);
                  margin-top:0.2rem;line-height:1.5;font-family:'Cairo',sans-serif;">
        {_sub}
      </div>
    </div>
    <hr style="border-color:rgba(255,255,255,0.12);margin:0 0 0.8rem;"/>
    """, unsafe_allow_html=True)

    # ── Language toggle ───────────────────────────────────────────────────
    _lang_col_en, _lang_col_ar = st.columns(2)
    with _lang_col_en:
        if st.button(
            "🌐 English" if not _IS_AR else "English",
            key="lang_en",
            use_container_width=True,
            type="primary" if not _IS_AR else "secondary",
        ):
            st.session_state["ui_lang"] = "en"
            st.rerun()
    with _lang_col_ar:
        if st.button(
            "عربي 🌐" if _IS_AR else "عربي",
            key="lang_ar",
            use_container_width=True,
            type="primary" if _IS_AR else "secondary",
        ):
            st.session_state["ui_lang"] = "ar"
            st.rerun()

    st.markdown('<hr style="border-color:rgba(255,255,255,0.12);margin:0.6rem 0 0.8rem;"/>', unsafe_allow_html=True)

    # Navigation
    nav_items = [
        ("🏠", T("Dashboard",          "لوحة التحكم"),        "dashboard"),
        ("📤", T("Upload Student Data", "رفع بيانات الطلاب"),  "upload"),
        ("📊", T("Performance Analysis","تحليل الأداء"),        "analysis"),
        ("📋", T("Student Reports",     "تقارير الطلاب"),       "reports"),
        ("✉",  T("Parent Messages",     "رسائل أولياء الأمور"),"messages"),
        ("⚙",  T("Project Settings",   "إعدادات المشروع"),    "settings"),
    ]

    current_page = st.session_state.get("page", "dashboard")

    for icon, label, key in nav_items:
        is_active = (current_page == key)
        if st.button(
            f"{icon}  {label}",
            key=f"nav_{key}",
            use_container_width=True,
        ):
            st.session_state["page"] = key
            st.rerun()

    # User block
    _user_dir = "rtl" if _IS_AR else "ltr"
    _user_name = "أ. منتصر" if _IS_AR else "T. Montaser"
    _user_role = "معلم لغة إنجليزية" if _IS_AR else "English Language Teacher"
    _user_init = "م" if _IS_AR else "M"
    st.markdown(f"""
    <hr style="border-color:rgba(255,255,255,0.12);margin:1.2rem 0 0.8rem;"/>
    <div style="display:flex;align-items:center;gap:0.7rem;padding:0.5rem 0.3rem;
                direction:{_user_dir};">
      <div style="width:38px;height:38px;background:#D4A017;border-radius:50%;
                  display:flex;align-items:center;justify-content:center;
                  font-size:1rem;font-weight:900;color:#1A2B3C;flex-shrink:0;">{_user_init}</div>
      <div>
        <div style="font-size:0.85rem;font-weight:700;color:#fff;
                    font-family:'Cairo',sans-serif;">{_user_name}</div>
        <div style="font-size:0.72rem;color:rgba(255,255,255,0.60);
                    font-family:'Cairo',sans-serif;">{_user_role}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ===========================================================================
# UI — Main content
# ===========================================================================

# ── Top bar ──────────────────────────────────────────────────────────────
_today_fmt = date.today().strftime("%A, %d %B %Y")
if _IS_AR:
    _days_map = {"Monday":"الاثنين","Tuesday":"الثلاثاء","Wednesday":"الأربعاء",
                 "Thursday":"الخميس","Friday":"الجمعة","Saturday":"السبت","Sunday":"الأحد"}
    _mon_map  = {"January":"يناير","February":"فبراير","March":"مارس","April":"أبريل",
                 "May":"مايو","June":"يونيو","July":"يوليو","August":"أغسطس",
                 "September":"سبتمبر","October":"أكتوبر","November":"نوفمبر","December":"ديسمبر"}
    for _en, _ar in {**_days_map, **_mon_map}.items():
        _today_fmt = _today_fmt.replace(_en, _ar)

_topbar_dir = "rtl" if _IS_AR else "ltr"
st.markdown(f"""
<div class="sf-topbar" style="direction:{_topbar_dir};">
  <div class="sf-topbar-date">📅 {_today_fmt}</div>
  <div class="sf-topbar-actions">
    <div class="sf-topbar-icon">❓</div>
    <div class="sf-topbar-icon">🔔</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Hero Banner ───────────────────────────────────────────────────────────
_hero_greeting = T("👋 Welcome to", "👋 مرحبًا بك في")
_hero_subtitle  = T(
    "Transform your student data into actionable insights,<br>"
    "smart reports, and effective parent communication.",
    "حوّل بيانات طلابك إلى رؤى عملية، وتقارير ذكية،<br>وتواصل فعّال مع أولياء الأمور."
)
_hero_dir = "rtl" if _IS_AR else "ltr"
st.markdown(f"""
<div class="sf-hero" style="direction:{_hero_dir};">
  <div class="sf-hero-text">
    <div class="sf-hero-greeting">{_hero_greeting}</div>
    <div class="sf-hero-title">SchoolFlow AI</div>
    <div class="sf-hero-subtitle">{_hero_subtitle}</div>
  </div>
  <div class="sf-hero-badge">
    <div class="sf-hero-badge-icon">📚</div>
    <div class="sf-hero-badge-text">MVP v0.1</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Privacy notice ────────────────────────────────────────────────────────
_priv_title = T("Privacy Notice", "تنبيه الخصوصية")
_priv_body  = T(
    "Start with sample or authorised data. Do not upload real student data "
    "without school consent and approved privacy controls.",
    "ابدأ ببيانات تجريبية أو بيانات مصرح باستخدامها. "
    "لا ترفع بيانات طلاب حقيقية قبل موافقة المدرسة واعتماد ضوابط الخصوصية."
)
_priv_dir = "rtl" if _IS_AR else "ltr"
st.markdown(f"""
<div style="background:rgba(212,160,23,0.08);border:1px solid rgba(212,160,23,0.35);
            border-right:4px solid #D4A017;border-radius:9px;
            padding:0.6rem 1rem;font-size:0.82rem;color:#78530a;
            margin-bottom:1.2rem;direction:{_priv_dir};display:flex;gap:0.5rem;align-items:flex-start;">
  <span>⚠️</span>
  <span><strong>{_priv_title}:</strong> {_priv_body}</span>
</div>
""", unsafe_allow_html=True)

# ── KPI cards (dynamic after analysis, placeholder before) ────────────────
if "summary" in st.session_state:
    _sum  = st.session_state["summary"]
    _cln  = st.session_state["clean"]
    _n_s  = len(_sum)
    _n_w  = int(_cln["Week"].nunique())
    _n_r  = len(_cln)
    # Compute aggregate rates
    def _avg_pct(col):
        vals = []
        for v in _sum[col]:
            try:
                vals.append(float(str(v).replace("%","").strip()))
            except Exception:
                pass
        return f"{sum(vals)/len(vals):.1f}%" if vals else "N/A"
    _att_avg  = _avg_pct("Attendance")
    _task_avg = _avg_pct("Task completion")
    _scores   = _sum["Mean quiz / 10"].dropna()
    _quiz_avg = f"{_scores.mean():.1f} / 10" if len(_scores) else "N/A"
else:
    _n_s = "—"; _n_w = "—"; _n_r = "—"
    _att_avg = "—"; _task_avg = "—"; _quiz_avg = "—"

_kpi_dir = "rtl" if _IS_AR else "ltr"
st.markdown(f"""
<div class="sf-metrics-row" style="direction:{_kpi_dir};">
  <div class="sf-metric-card">
    <div class="sf-metric-icon sf-icon-green">👥</div>
    <div class="sf-metric-body">
      <div class="sf-metric-label">{T("Students","عدد الطلاب")}</div>
      <div class="sf-metric-value">{_n_s}</div>
      <div class="sf-metric-sub">{T(f"Total records: {_n_r}", f"إجمالي السجلات: {_n_r}")}</div>
    </div>
  </div>
  <div class="sf-metric-card">
    <div class="sf-metric-icon sf-icon-blue">📅</div>
    <div class="sf-metric-body">
      <div class="sf-metric-label">{T("Attendance Rate","نسبة الحضور")}</div>
      <div class="sf-metric-value">{_att_avg}</div>
      <div class="sf-metric-sub">{T(f"Class avg · {_n_w} weeks", f"متوسط الفصل · {_n_w} أسبوع")}</div>
    </div>
  </div>
  <div class="sf-metric-card">
    <div class="sf-metric-icon sf-icon-gold">✅</div>
    <div class="sf-metric-body">
      <div class="sf-metric-label">{T("Task Completion","إنجاز المهام")}</div>
      <div class="sf-metric-value">{_task_avg}</div>
      <div class="sf-metric-sub">{T("Whole-class average","متوسط الفصل الكامل")}</div>
    </div>
  </div>
  <div class="sf-metric-card">
    <div class="sf-metric-icon sf-icon-purple">🏆</div>
    <div class="sf-metric-body">
      <div class="sf-metric-label">{T("Mean Quiz Score","متوسط الاختبارات")}</div>
      <div class="sf-metric-value">{_quiz_avg}</div>
      <div class="sf-metric-sub">{T("Recorded scores average","معدّل الدرجات المسجّلة")}</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Dashboard: weekly chart + observations (only when data is ready) ──────
if "summary" in st.session_state:
    clean    = st.session_state["clean"]
    summary  = st.session_state["summary"]
    weekly   = st.session_state["weekly"]
    has_name = st.session_state.get("has_name", False)
    issues_stored = st.session_state.get("issues", pd.DataFrame())

    # Build SVG chart
    svg_chart = _build_weekly_svg(weekly)

    # Observations HTML
    if issues_stored.empty:
        obs_html = f'<div class="sf-obs-empty">✅ {T("No issues — all data is clean","لا توجد ملاحظات — البيانات سليمة")}</div>'
    else:
        rows_html = ""
        for _, r in issues_stored.iterrows():
            rows_html += (
                f'<div class="sf-obs-item">'
                f'<span class="sf-obs-code">{r["Student code"]}</span>'
                f'<span class="sf-obs-text">{r["Week"]}: {r["Issue"]}</span>'
                f'</div>'
            )
        obs_html = rows_html

    _dash_dir = "rtl" if _IS_AR else "ltr"
    _chart_title = T("Weekly Class Performance","تطور الأداء الأسبوعي للفصل")
    _obs_title   = T("Key Observations","أبرز الملاحظات")
    st.markdown(f"""
    <div class="sf-two-col sf-two-col-wide" style="direction:{_dash_dir};">
      <div class="sf-card">
        <div class="sf-card-header">
          <div class="sf-card-header-icon">📊</div>
          <div class="sf-card-title">{_chart_title}</div>
        </div>
        {svg_chart}
      </div>
      <div class="sf-card">
        <div class="sf-card-header">
          <div class="sf-card-header-icon">⚠</div>
          <div class="sf-card-title">{_obs_title}</div>
        </div>
        {obs_html}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Quick actions row
    workbook_ready = make_workbook(clean, summary, weekly)
    col_q1, col_q2, col_q3, col_q4 = st.columns(4)
    with col_q1:
        st.download_button(
            T("📥 Export Excel Report","📥 تصدير تقرير Excel"),
            data=workbook_ready,
            file_name="SchoolFlow_AI_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col_q2:
        if st.button(T("📋 Student Reports","📋 عرض تقارير الطلاب"), use_container_width=True):
            st.session_state["page"] = "reports"
    with col_q3:
        if st.button(T("✉ Parent Messages","✉ رسائل أولياء الأمور"), use_container_width=True):
            st.session_state["page"] = "messages"
    with col_q4:
        if st.button(T("📤 Upload New File","📤 رفع ملف جديد"), use_container_width=True):
            st.session_state["page"] = "upload"

    st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)

# ===========================================================================
# UI — Step 1: Upload
# ===========================================================================
_sec1_title = T(
    "Upload Student Tracking File · رفع ملف متابعة الطلاب",
    "رفع ملف متابعة الطلاب · Upload Student Tracking File"
)
st.markdown(f"""
<div class="sf-section-header">
  <div class="sf-section-num">1</div>
  <div class="sf-section-title">{_sec1_title}</div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="sf-upload-area">', unsafe_allow_html=True)
uploaded = st.file_uploader(
    T("Drag and drop an Excel file (.xlsx) here, or click to choose",
      "اسحب ملف Excel (.xlsx) وأفلته هنا، أو انقر للاختيار"),
    type=["xlsx"],
    label_visibility="visible",
)
st.markdown('</div>', unsafe_allow_html=True)

if uploaded:
    try:
        xls = pd.ExcelFile(fresh_bytes(uploaded))
    except Exception as e:
        st.error(T(f"Could not open file: {e}", f"تعذر فتح الملف: {e}"))
        st.stop()

    col_sheet, col_info = st.columns([2, 3])
    with col_sheet:
        default_idx = xls.sheet_names.index("Weekly tracking") if "Weekly tracking" in xls.sheet_names else 0
        sheet = st.selectbox(
            T("📋 Select data sheet", "📋 اختر ورقة البيانات"),
            xls.sheet_names, index=default_idx,
        )
    with col_info:
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption(T(f"Available sheets: {', '.join(xls.sheet_names)}",
                     f"الأوراق المتاحة: {', '.join(xls.sheet_names)}"))

    try:
        raw = pd.read_excel(fresh_bytes(uploaded), sheet_name=sheet, header=4)
    except Exception as e:
        st.error(T(f"Could not read sheet: {e}", f"تعذر قراءة الورقة: {e}"))
        st.stop()

    raw.columns = [str(c).strip() for c in raw.columns]
    missing_cols = [c for c in REQUIRED if c not in raw.columns]
    has_name = OPTIONAL_NAME_COL in raw.columns

    if missing_cols:
        st.error(
            T("The following columns are missing: ", "الأعمدة التالية غير موجودة في الملف: ")
            + ", ".join(missing_cols)
        )
        st.write(T("Columns found:", "الأعمدة التي وجدناها:"), list(raw.columns))
        st.stop()

    cols_to_load = REQUIRED + ([OPTIONAL_NAME_COL] if has_name else [])
    data = raw[cols_to_load].dropna(how="all")

    name_status = (
        T("✓ Name column present", "✓ عمود الاسم موجود")
        if has_name else
        T("Student code will be used", "سيُستخدم رمز الطالب")
    )
    st.markdown(
        f'<span class="sf-pill-ok">✓ {T(f"Loaded {len(data)} records from", f"تمت القراءة — {len(data)} سجل من")} "{sheet}" · {name_status}</span>',
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    with st.expander(T("👁 Preview first 10 records", "👁 معاينة أول 10 سجلات"), expanded=False):
        st.dataframe(data.head(10), use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------------
    # Step 2 – Validation
    # -----------------------------------------------------------------------
    _sec2_title = T(
        "Data Quality Check · مراجعة جودة البيانات",
        "مراجعة جودة البيانات · Data Quality Check"
    )
    st.markdown(f"""
    <div class="sf-section-header">
      <div class="sf-section-num">2</div>
      <div class="sf-section-title">{_sec2_title}</div>
    </div>
    """, unsafe_allow_html=True)

    issues = validate(data)
    if issues.empty:
        st.markdown(
            f'<span class="sf-pill-ok">✓ {T("No issues — all required values present and valid","لا توجد مشكلات — جميع القيم المطلوبة موجودة ومنطقية")}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<span class="sf-pill-warn">⚠ {T(f"{len(issues)} data issues found — review before continuing", f"وُجدت {len(issues)} مشكلة في البيانات — راجعها قبل المتابعة")}</span>',
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="sf-card">', unsafe_allow_html=True)
        st.dataframe(issues, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.caption(
            T(
                "Note: rows with issues are NOT removed automatically. "
                "Zero (0) ≠ missing (blank). Fix data in Excel first if needed.",
                "ملاحظة: الصفوف التي بها مشكلات لن تُحذف تلقائيًا. "
                "قيمة صفر (0) ≠ قيمة مفقودة (فارغة). "
                "راجع البيانات في Excel أولاً إذا أردت تصحيحها."
            )
        )

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button(T("⚡  Analyse Data & Generate Reports", "⚡  تحليل البيانات وإنشاء التقارير"), type="primary"):
        clean, summary, weekly = build_outputs(data, has_name)
        st.session_state["clean"]    = clean
        st.session_state["summary"]  = summary
        st.session_state["weekly"]   = weekly
        st.session_state["has_name"] = has_name
        st.session_state["issues"]   = issues   # store for dashboard
        st.success(T("✅  Analysis complete. Review results below.", "✅  اكتمل التحليل بنجاح. راجع النتائج أدناه."))

# ===========================================================================
# UI — Steps 3–8: Results
# ===========================================================================

if "summary" in st.session_state:
    clean    = st.session_state["clean"]
    summary  = st.session_state["summary"]
    weekly   = st.session_state["weekly"]
    has_name = st.session_state.get("has_name", False)

    st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)

    # Step 3 – Teacher overview
    _s3 = T("Teacher Dashboard · ملخص المعلم", "ملخص المعلم · Teacher Dashboard")
    st.markdown(f"""
    <div class="sf-section-header">
      <div class="sf-section-num">3</div>
      <div class="sf-section-title">{_s3}</div>
    </div>
    """, unsafe_allow_html=True)

    # Step 4 – Weekly summary
    _s4 = T("Weekly Class Summary · الملخص الأسبوعي للفصل", "الملخص الأسبوعي للفصل · Weekly Class Summary")
    st.markdown(f"""
    <div class="sf-section-header">
      <div class="sf-section-num">4</div>
      <div class="sf-section-title">{_s4}</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.dataframe(weekly, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Step 5 – Student summary
    _s5 = T("Student Summary · ملخص كل طالب", "ملخص كل طالب · Student Summary")
    st.markdown(f"""
    <div class="sf-section-header">
      <div class="sf-section-num">5</div>
      <div class="sf-section-title">{_s5}</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Step 6 – Per-student drill-down
    _s6 = T("Student Weekly Drill-Down · تفاصيل أسبوعية لطالب محدد",
            "تفاصيل أسبوعية لطالب محدد · Student Weekly Drill-Down")
    st.markdown(f"""
    <div class="sf-section-header">
      <div class="sf-section-num">6</div>
      <div class="sf-section-title">{_s6}</div>
    </div>
    """, unsafe_allow_html=True)

    student_options = summary["Student code"].tolist()
    if has_name:
        label_map = dict(zip(summary["Student code"], summary["Student name"]))
        student_options_labels = [f"{c} — {label_map[c]}" for c in student_options]
    else:
        student_options_labels = student_options

    selected_label = st.selectbox(T("🎓 Select student", "🎓 اختر الطالب"), student_options_labels)
    selected_code  = student_options[student_options_labels.index(selected_label)]
    student_rows   = clean[clean["Student code"] == selected_code].sort_values("Week")
    detail_cols    = ["Week", "Days scheduled", "Days attended",
                      "Tasks set", "Tasks completed", "Quiz score / 10",
                      "Observation", "Next step"]
    if has_name and OPTIONAL_NAME_COL in student_rows.columns:
        detail_cols = [OPTIONAL_NAME_COL] + detail_cols

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    st.dataframe(student_rows[detail_cols], use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Step 7 – Parent messages
    _s7 = T("Parent Messages · رسائل أولياء الأمور", "رسائل أولياء الأمور · Parent Messages")
    st.markdown(f"""
    <div class="sf-section-header">
      <div class="sf-section-num">7</div>
      <div class="sf-section-title">{_s7}</div>
    </div>
    """, unsafe_allow_html=True)

    col_lang, _ = st.columns([2, 4])
    with col_lang:
        language = st.radio(T("🌐 Message language", "🌐 لغة الرسالة"), ["English", "العربية"], horizontal=True)

    st.markdown("<br>", unsafe_allow_html=True)

    for _, row in summary.iterrows():
        label = row["Student name"] if has_name else row["Student code"]
        _exp_label = T(f"✉  Message for: {label}", f"✉  رسالة الطالب: {label}")
        with st.expander(_exp_label):
            st.text_area(
                T("Review before sending — راجع الرسالة قبل إرسالها",
                  "راجع الرسالة قبل إرسالها — Review before sending"),
                parent_message(row, language),
                height=210,
                key=f"msg_{row['Student code']}_{language}",
            )

    # Step 8 – Download
    _s8 = T("Download Reports · تنزيل النتائج", "تنزيل النتائج · Download Reports")
    st.markdown(f"""
    <div class="sf-section-header">
      <div class="sf-section-num">8</div>
      <div class="sf-section-title">{_s8}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sf-card">', unsafe_allow_html=True)
    col_dl, col_note = st.columns([2, 4])
    with col_dl:
        workbook = make_workbook(clean, summary, weekly)
        st.download_button(
            T("📥  Download Excel Reports File","📥  تنزيل ملف التقارير Excel"),
            data=workbook,
            file_name="SchoolFlow_AI_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col_note:
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption(
            T("File contains 3 sheets: Validated data · Student summaries · Weekly summary",
              "الملف يحتوي على 3 أوراق: البيانات المُتحقق منها · ملخص الطلاب · الملخص الأسبوعي")
        )
    st.markdown('</div>', unsafe_allow_html=True)

    st.caption(
        T(
            "This is an early version: no automatic messaging, no replacement for teacher review. "
            "Verify data accuracy and message templates with Montaser before use.",
            "هذه نسخة أولية: لا ترسل رسائل تلقائيًا، ولا تستبدل مراجعة المعلم. "
            "يجب التحقق من دقة البيانات والقوالب مع منتصر قبل اعتمادها."
        )
    )

# ===========================================================================
# UI — SchoolFlow AI Assistant (Section 9)
# ===========================================================================
st.markdown('<hr class="sf-divider"/>', unsafe_allow_html=True)
_s9_title = T("SchoolFlow AI Assistant · المساعد الذكي",
              "SchoolFlow AI Assistant · المساعد الذكي")
st.markdown(f"""
<div class="sf-section-header">
  <div class="sf-section-num">9</div>
  <div class="sf-section-title">{_s9_title}</div>
</div>
""", unsafe_allow_html=True)

# ── Import assistant modules ─────────────────────────────────────────────
import sys as _sys, os as _os
_assistant_dir = _os.path.dirname(__file__)
if _assistant_dir not in _sys.path:
    _sys.path.insert(0, _assistant_dir)

_ASSISTANT_ERR = ""   # safe default; overwritten only if import fails
try:
    from assistant.intent_router import route as _route
    from assistant.llm_client import get_mode as _get_mode
    _ASSISTANT_READY = True
except Exception as _e:
    _ASSISTANT_READY = False
    _ASSISTANT_ERR   = str(_e)

# ── Session state for chat ───────────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "assistant_mode" not in st.session_state:
    st.session_state["assistant_mode"] = "offline"

# ── Mode indicator ────────────────────────────────────────────────────────
if _ASSISTANT_READY:
    _mode = _get_mode()
    st.session_state["assistant_mode"] = _mode
    _mode_txt = (
        T("● Connected to OpenAI", "● متصل بـ OpenAI")
        if _mode == "online" else
        T("● Offline Mode — Fallback", "● وضع محلي — Offline")
    )
else:
    _mode_txt = T("● Assistant load error", "● خطأ في تحميل المساعد")

# ── Assistant header ──────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:linear-gradient(90deg,#1B5E4A,#236b56);
            border-radius:12px 12px 0 0;padding:0.7rem 1.2rem;
            display:flex;align-items:center;gap:0.6rem;
            direction:{'rtl' if _IS_AR else 'ltr'};">
  <span style="font-size:1.2rem;">🤖</span>
  <div>
    <div style="color:#fff;font-weight:700;font-size:0.95rem;">SchoolFlow AI Assistant</div>
    <div style="font-size:0.72rem;color:rgba(255,255,255,0.75);">{_mode_txt}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Chat history (native st.chat_message — no DOM conflict) ──────────────
_chat_container = st.container()
with _chat_container:
    history = st.session_state["chat_history"]
    if not history:
        with st.chat_message("assistant"):
            st.markdown(
                T(
                    "Hello! I'm SchoolFlow AI Assistant 🎓\n\n"
                    "Upload your data file first, then ask me about student performance.\n\n"
                    "Type **help** to see all available commands.",
                    "مرحبًا! أنا مساعد SchoolFlow AI 🎓\n\n"
                    "ارفع ملف البيانات أولاً ثم اسألني عن أداء الطلاب.\n\n"
                    "اكتب **مساعدة** لعرض الأوامر المتاحة."
                )
            )
    else:
        for _msg in history:
            _role    = _msg.get("role", "bot")
            _content = _msg.get("content", "")
            _ts_str  = _msg.get("ts", "")
            _st_role = "user" if _role == "user" else "assistant"
            with st.chat_message(_st_role):
                st.markdown(_content)
                if _ts_str:
                    st.caption(_ts_str)

# ── Clear button ─────────────────────────────────────────────────────────
if st.session_state["chat_history"]:
    if st.button(T("🗑 Clear chat", "🗑 مسح المحادثة"), key="clear_chat"):
        st.session_state["chat_history"] = []
        st.rerun()

# ── Quick-command chips ──────────────────────────────────────────────────
_chip_label = T("Quick commands:", "أوامر سريعة:")
st.markdown(
    f'<div style="direction:{"rtl" if _IS_AR else "ltr"};margin:0.5rem 0 0.4rem;">'
    f'<span style="font-size:0.78rem;color:#9CA3AF;font-weight:600;">{_chip_label}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# Bilingual chip pairs — (english_command, arabic_command, display_label)
_chips_def = [
    ("class analysis",        "تحليل الفصل",         T("Class Analysis",    "تحليل الفصل")),
    ("show at-risk students", "من يحتاج متابعة؟",    T("At-Risk Students",  "من يحتاج متابعة؟")),
    ("data issues",           "مشكلات البيانات",      T("Data Issues",       "مشكلات البيانات")),
    ("list students",         "قائمة الطلاب",         T("List Students",     "قائمة الطلاب")),
    ("explain",               "اشرح النتائج",         T("Explain Results",   "اشرح النتائج")),
    ("help",                  "مساعدة",                T("Help",              "مساعدة")),
]
_chip_cols = st.columns(len(_chips_def))
for _i, (_col, (_cmd_en, _cmd_ar, _label)) in enumerate(zip(_chip_cols, _chips_def)):
    with _col:
        if st.button(_label, key=f"chip_{_i}", use_container_width=True):
            from datetime import datetime as _dt2
            _ts2  = _dt2.now().strftime("%H:%M")
            _chip = _cmd_ar   # always send Arabic command to the router (patterns cover both)
            st.session_state["chat_history"].append(
                {"role": "user", "content": _label, "ts": _ts2}
            )
            if _ASSISTANT_READY:
                try:
                    _r = _route(_chip, lang=_L)
                    st.session_state["chat_history"].append(
                        {"role": "bot" if _r.get("ok") else "error",
                         "content": _r.get("response", ""), "ts": _ts2}
                    )
                except Exception as _ex2:
                    st.session_state["chat_history"].append(
                        {"role": "error", "content": str(_ex2), "ts": _ts2}
                    )
            st.rerun()

# ── Chat input (native Streamlit — React-safe) ────────────────────────────
_placeholder = T(
    "Example: report S01 | at-risk students | help",
    "مثال: تقرير S01 | من يحتاج متابعة؟ | مساعدة",
)
_user_msg = st.chat_input(_placeholder)

if _user_msg and _user_msg.strip():
    from datetime import datetime as _dt
    _ts = _dt.now().strftime("%H:%M")

    st.session_state["chat_history"].append({
        "role": "user", "content": _user_msg.strip(), "ts": _ts,
    })

    if not _ASSISTANT_READY:
        _bot_text = T(f"⚠️ Assistant failed to load: {_ASSISTANT_ERR}",
                      f"⚠️ تعذر تحميل المساعد: {_ASSISTANT_ERR}")
        _bot_role = "error"
    else:
        try:
            _result   = _route(_user_msg.strip(), lang=_L)
            _bot_text = _result.get("response", T("No response.", "لا توجد إجابة."))
            _bot_role = "bot" if _result.get("ok") else "error"
        except Exception as _ex:
            _bot_text = T(f"⚠️ Unexpected error: {_ex}", f"⚠️ خطأ غير متوقع: {_ex}")
            _bot_role = "error"

    st.session_state["chat_history"].append({
        "role": _bot_role, "content": _bot_text, "ts": _ts,
    })
    st.rerun()

# ===========================================================================
# Footer
# ===========================================================================
_footer_sub = T(
    "Smart platform for teachers and student tracking management",
    "منصة ذكية لمساعدة المعلمين وإدارة متابعة الطلاب"
)
_footer_note = T(
    "For trial use only — Not for production use without data governance approval",
    "للاستخدام التجريبي فقط — Not for production use without data governance approval"
)
st.markdown(f"""
<div class="sf-footer">
  <strong>SchoolFlow AI</strong> &nbsp;·&nbsp; MVP v0.1 Beta &nbsp;·&nbsp;
  {_footer_sub}<br>
  <span>{_footer_note}</span>
</div>
""", unsafe_allow_html=True)
