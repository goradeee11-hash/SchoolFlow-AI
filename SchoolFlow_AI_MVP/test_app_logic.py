"""
test_app_logic.py
-----------------
Headless test of SchoolFlow AI core logic against sample_data.xlsx.
Runs without Streamlit — tests file reading, validation, and calculations.
"""

import sys
import os
import pandas as pd
from io import BytesIO

# ── Import canonical logic from app_logic (same module used by the live UI) ─
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from app_logic import (
    REQUIRED, OPTIONAL_NAME_COL, NUMERIC_COLS,
    validate, build_outputs, make_workbook,
)

# ── Test run ────────────────────────────────────────────────────────────────
PASS = "  PASS"
FAIL = "  FAIL"

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"{status}  {label}" + (f"  [{detail}]" if detail else ""))
    return condition

errors = 0

print("\n=== SchoolFlow AI - Headless Logic Test ===\n")

# 1. Read the sample workbook
sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data.xlsx")
if not os.path.exists(sample_path):
    print(f"{FAIL}  sample_data.xlsx not found at {sample_path}")
    sys.exit(1)

with open(sample_path, "rb") as f:
    file_bytes = f.read()

# Phase 1: fresh BytesIO on each read
xls = pd.ExcelFile(BytesIO(file_bytes))
errors += 0 if check("Sheet 'Weekly tracking' exists", "Weekly tracking" in xls.sheet_names,
                      str(xls.sheet_names)) else 1

raw = pd.read_excel(BytesIO(file_bytes), sheet_name="Weekly tracking", header=4)
raw.columns = [str(c).strip() for c in raw.columns]

missing_cols = [c for c in REQUIRED if c not in raw.columns]
errors += 0 if check("All required columns present", not missing_cols,
                      "missing: " + str(missing_cols) if missing_cols else "") else 1

has_name = OPTIONAL_NAME_COL in raw.columns
errors += 0 if check("Optional 'Student name' column present", has_name) else 1

cols_to_load = REQUIRED + ([OPTIONAL_NAME_COL] if has_name else [])
data = raw[cols_to_load].dropna(how="all")
errors += 0 if check("20 data rows loaded", len(data) == 20, f"got {len(data)}") else 1

# Phase 2: Validation
print("\n--- Validation ---")
issues = validate(data)
errors += 0 if check("Validation returns a DataFrame", isinstance(issues, pd.DataFrame)) else 1
errors += 0 if check("Exactly 3 issues detected", len(issues) == 3,
                      f"got {len(issues)}: {issues['Issue'].tolist() if not issues.empty else []}") else 1

# Check specific expected issues
has_missing_quiz = issues["Issue"].str.contains("not recorded", case=False).any() if not issues.empty else False
has_att_gt_sched  = issues["Issue"].str.contains("Attended.*Scheduled", case=False).any() if not issues.empty else False
has_done_gt_set   = issues["Issue"].str.contains("Completed.*Set",       case=False).any() if not issues.empty else False
errors += 0 if check("Flags missing quiz score (S02/W3)",  has_missing_quiz) else 1
errors += 0 if check("Flags attended > scheduled (S03/W2)", has_att_gt_sched) else 1
errors += 0 if check("Flags completed > set (S04/W1)",      has_done_gt_set) else 1

# Zero vs missing: S05/W3 score=0.0 must NOT appear as a missing-quiz issue
s05_issues = issues[issues["Student code"] == "S05"] if not issues.empty else pd.DataFrame()
zero_flagged_as_missing = s05_issues["Issue"].str.contains("not recorded", case=False).any() if not s05_issues.empty else False
errors += 0 if check("Zero score (S05/W3) NOT flagged as missing", not zero_flagged_as_missing) else 1

# Phase 3 & core: build_outputs
print("\n--- Calculations ---")
clean, summary, _weekly_out = build_outputs(data, has_name)
errors += 0 if check("5 students in summary", len(summary) == 5, f"got {len(summary)}") else 1
errors += 0 if check("Student name column in summary", "Student name" in summary.columns) else 1

# Check S05/W3 zero score is counted in mean (not skipped as missing)
s05 = summary[summary["Student code"] == "S05"].iloc[0]
s05_mean = s05["Mean quiz / 10"]
s05_weeks = s05["Quiz weeks recorded"]
errors += 0 if check("S05 has 4 quiz weeks recorded (0.0 counts)", s05_weeks == 4,
                      f"got {s05_weeks}") else 1
errors += 0 if check("S05 mean includes zero (expected 3.75)", s05_mean == 3.75,
                      f"got {s05_mean}") else 1

# S02 has only 3 quiz weeks (W3 was missing)
s02 = summary[summary["Student code"] == "S02"].iloc[0]
errors += 0 if check("S02 has 3 quiz weeks recorded (W3 missing excluded)", s02["Quiz weeks recorded"] == 3,
                      f"got {s02['Quiz weeks recorded']}") else 1

# Names in messages
errors += 0 if check("S01 display name is 'Ahmed Al-Farsi'",
                      summary[summary["Student code"]=="S01"].iloc[0]["Student name"] == "Ahmed Al-Farsi") else 1

# Weekly aggregation
print("\n--- Weekly summary ---")
weekly = clean.groupby("Week", sort=True).agg(
    **{"Mean quiz / 10": ("Quiz score / 10", "mean")}
).reset_index()
errors += 0 if check("4 weeks in weekly summary", len(weekly) == 4, f"got {len(weekly)}") else 1

# Excel export
print("\n--- Excel export ---")
wb_bytes = make_workbook(clean, summary, weekly).read()  # app_logic returns BytesIO
errors += 0 if check("Workbook bytes non-empty", len(wb_bytes) > 0, f"{len(wb_bytes)} bytes") else 1
wb_check = pd.ExcelFile(BytesIO(wb_bytes))
expected_sheets = {"Validated data", "Student summaries", "Weekly summary"}
errors += 0 if check("All 3 output sheets present",
                      expected_sheets.issubset(set(wb_check.sheet_names)),
                      str(wb_check.sheet_names)) else 1

# Summary
print("=" * 44)
if errors == 0:
    print("  ALL TESTS PASSED")
else:
    print(f"  {errors} TEST(S) FAILED - see FAIL lines above")
print("=" * 44)
sys.exit(errors)
