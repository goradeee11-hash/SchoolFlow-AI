"""
make_sample.py
--------------
Generates sample_data.xlsx — a synthetic workbook with FAKE DATA ONLY.

Structure:
- Sheet name : "Weekly tracking"
- Rows 1-4  : Title / metadata (not data)
- Row 5     : Column headers  →  pandas reads with header=4
- Rows 6+   : Data (5 fake students × 4 weeks = 20 rows)

Intentional data-quality issues for validation testing:
  S02 / Week 3  → Quiz score missing (None / NaN)
  S03 / Week 2  → Days attended (6) > Days scheduled (5)
  S04 / Week 1  → Tasks completed (5) > Tasks set (3)
  S05 / Week 3  → Quiz score = 0.0  (genuine zero, NOT missing)
"""

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
import os

wb = Workbook()
ws = wb.active
ws.title = "Weekly tracking"

# ── Rows 1-4: title / metadata ─────────────────────────────────────────────
ws["A1"] = "SchoolFlow AI — Sample Workbook (FAKE DATA ONLY)"
ws["A1"].font = Font(bold=True, size=14)
ws["A2"] = "Class: 3B  |  Teacher: Montaser  |  Term: 1"
ws["A3"] = "IMPORTANT: All student names, codes, and scores are fictitious."
ws["A3"].font = Font(italic=True, color="FF0000")
ws["A4"] = ""   # blank spacer row

# ── Row 5: column headers ───────────────────────────────────────────────────
headers = [
    "Student code", "Student name", "Week",
    "Days scheduled", "Days attended",
    "Tasks set", "Tasks completed",
    "Quiz score / 10",
    "Observation", "Next step",
]
header_fill = PatternFill("solid", fgColor="4F81BD")
header_font = Font(bold=True, color="FFFFFF")
for col, h in enumerate(headers, start=1):
    cell = ws.cell(row=5, column=col, value=h)
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = Alignment(horizontal="center")

# ── Data rows (rows 6-25) ───────────────────────────────────────────────────
# (code, name, week, days_sched, days_att, tasks_set, tasks_done, quiz, obs, next_step)
rows = [
    # S01 Ahmed — clean data
    ("S01", "Ahmed Al-Farsi",  1, 5, 5, 3, 3, 8.0,  "Active participant",            "Continue reading tasks"),
    ("S01", "Ahmed Al-Farsi",  2, 5, 4, 3, 3, 7.5,  "Good effort",                   "Work on vocabulary"),
    ("S01", "Ahmed Al-Farsi",  3, 5, 5, 3, 3, 9.0,  "Excellent week",                "Extend to chapter 3"),
    ("S01", "Ahmed Al-Farsi",  4, 5, 5, 3, 2, 8.0,  "Missed one task",               "Follow up on task 3"),

    # S02 Nour — Week 3 quiz score intentionally MISSING
    ("S02", "Nour Saleh",      1, 5, 5, 3, 3, 7.0,  "Steady progress",               "Review notes"),
    ("S02", "Nour Saleh",      2, 5, 4, 3, 2, 6.5,  "Needs support",                 "Extra reading"),
    ("S02", "Nour Saleh",      3, 5, 5, 3, 3, None, "Quiz not taken — absent",       "Reschedule quiz"),
    ("S02", "Nour Saleh",      4, 5, 5, 3, 3, 7.0,  "Improved",                      "Maintain pace"),

    # S03 Rami — Week 2: Days attended 6 > Days scheduled 5
    ("S03", "Rami Hassan",     1, 5, 5, 4, 4, 8.5,  "Very engaged",                  "Advanced exercises"),
    ("S03", "Rami Hassan",     2, 5, 6, 4, 4, 9.0,  "ERROR: attended > scheduled",   "Correct record"),
    ("S03", "Rami Hassan",     3, 5, 5, 4, 3, 8.0,  "Good",                          "Focus on writing"),
    ("S03", "Rami Hassan",     4, 5, 4, 4, 4, 8.5,  "Strong finish",                 "Prepare for test"),

    # S04 Lina — Week 1: Tasks completed 5 > Tasks set 3
    ("S04", "Lina Khalid",     1, 5, 5, 3, 5, 7.0,  "ERROR: completed > set",        "Verify task count"),
    ("S04", "Lina Khalid",     2, 5, 5, 3, 3, 6.0,  "On track",                      "More practice"),
    ("S04", "Lina Khalid",     3, 5, 4, 3, 2, 5.5,  "Struggling",                    "One-to-one session"),
    ("S04", "Lina Khalid",     4, 5, 5, 3, 3, 7.0,  "Recovering",                    "Continue support"),

    # S05 Omar — Week 3: Quiz score = 0.0 (genuine zero, NOT missing)
    ("S05", "Omar Bakr",       1, 5, 5, 2, 2, 6.0,  "Quiet but working",             "Encourage participation"),
    ("S05", "Omar Bakr",       2, 5, 3, 2, 1, 5.0,  "Low attendance",                "Attendance check"),
    ("S05", "Omar Bakr",       3, 5, 5, 2, 2, 0.0,  "Scored zero — quiz recorded",   "Revision needed"),
    ("S05", "Omar Bakr",       4, 5, 5, 2, 2, 4.0,  "Slow improvement",              "Extra support"),
]

for r_idx, row_data in enumerate(rows, start=6):
    for c_idx, value in enumerate(row_data, start=1):
        ws.cell(row=r_idx, column=c_idx, value=value)

# Auto-size columns
for col in ws.columns:
    max_len = 0
    for cell in col:
        try:
            max_len = max(max_len, len(str(cell.value or "")))
        except Exception:
            pass
    ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 42)

script_dir = os.path.dirname(os.path.abspath(__file__))
out_path = os.path.join(script_dir, "sample_data.xlsx")
wb.save(out_path)
print(f"Saved: {out_path}")
print(f"Rows: {len(rows)} data rows across 5 students x 4 weeks")
print("Intentional issues: S02/W3 missing quiz | S03/W2 att>sched | S04/W1 done>set | S05/W3 score=0")
