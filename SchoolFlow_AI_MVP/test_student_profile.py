"""
test_student_profile.py
-----------------------
Offline unit tests for pages/student_profile.py.

Tests cover:
  - build_student_profile() with various data combinations
  - _summarise_student_participation()
  - Navigation and routing checks in app.py
  - profile_student_code key in init_state()

No Streamlit runtime is required; streamlit is stubbed identically to
test_assistant.py / test_lesson_workspace.py.
"""

import sys, os, types, unittest
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Stub streamlit
# ---------------------------------------------------------------------------
_state: dict = {}

class _FakeSecrets(dict):
    def get(self, key, default=None):
        return default

def _noop(*a, **kw): pass
def _noop_ctx(*a, **kw):
    import contextlib
    return contextlib.nullcontext()

class _FakeST(types.ModuleType):
    session_state = _state
    secrets       = _FakeSecrets()
    set_page_config = staticmethod(_noop)
    markdown        = staticmethod(_noop)
    title           = staticmethod(_noop)
    caption         = staticmethod(_noop)
    info            = staticmethod(_noop)
    success         = staticmethod(_noop)
    warning         = staticmethod(_noop)
    error           = staticmethod(_noop)
    write           = staticmethod(_noop)
    divider         = staticmethod(_noop)
    subheader       = staticmethod(_noop)
    stop            = staticmethod(_noop)
    rerun           = staticmethod(_noop)
    text_input      = staticmethod(lambda *a, **kw: kw.get("value", ""))
    text_area       = staticmethod(lambda *a, **kw: kw.get("value", ""))
    selectbox       = staticmethod(
        lambda *a, **kw: (kw.get("options") or (a[1] if len(a) > 1 else [""]))[0]
    )
    radio           = staticmethod(lambda *a, **kw: "English")
    button          = staticmethod(lambda *a, **kw: False)
    download_button = staticmethod(lambda *a, **kw: False)
    file_uploader   = staticmethod(lambda *a, **kw: None)
    dataframe       = staticmethod(_noop)
    expander        = staticmethod(_noop_ctx)
    container       = staticmethod(_noop_ctx)
    toggle          = staticmethod(lambda *a, **kw: False)
    columns         = staticmethod(lambda n, **kw: [
        type("Col", (), {
            "markdown": _noop, "caption": _noop,
            "button": lambda *a, **kw: False,
            "selectbox": lambda *a, **kw:
                (kw.get("options") or (a[1] if len(a) > 1 else [""]))[0],
            "text_input": lambda *a, **kw: kw.get("value", ""),
            "__enter__": lambda s: s, "__exit__": lambda s, *a: None,
        })()
        for _ in range(n if isinstance(n, int) else len(n))
    ])
    metric          = staticmethod(_noop)
    spinner         = staticmethod(_noop_ctx)
    cache_data      = staticmethod(lambda f=None, **kw: f if f else lambda g: g)
    class _FakeSidebar:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def markdown(self, *a, **kw): pass
        def button(self, *a, **kw): return False
    sidebar = _FakeSidebar()

sys.modules["streamlit"] = _FakeST("streamlit")

# ---------------------------------------------------------------------------
# 2. Patch sys.path
# ---------------------------------------------------------------------------
HERE    = os.path.dirname(__file__)
APP_DIR = HERE
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# ---------------------------------------------------------------------------
# 3. Import functions under test
# ---------------------------------------------------------------------------
from pages.student_profile import build_student_profile, _summarise_student_participation

# ---------------------------------------------------------------------------
# 4. Test fixtures
# ---------------------------------------------------------------------------

def _make_summary(codes=("S01", "S02"), with_name=True):
    rows = []
    names = {"S01": "Ahmed Al-Farsi", "S02": "Sara Hassan",
             "S03": "Omar Noor", "S04": "Lina Ziad", "S05": "Yusuf Abbas"}
    for c in codes:
        rows.append({
            "Student code": c,
            "Student name": names.get(c, c) if with_name else c,
            "Weeks recorded": 4,
            "Attendance": "80.0%",
            "Attendance attended/scheduled": "16/20",
            "Task completion": "90.0%",
            "Tasks completed/set": "18/20",
            "Mean quiz / 10": 7.5,
            "Quiz weeks recorded": 4,
            "Latest observation": "Good progress",
            "Next step": "Focus on inference",
        })
    return pd.DataFrame(rows)


def _make_clean(codes=("S01", "S02")):
    rows = []
    for c in codes:
        for w in range(1, 5):
            rows.append({
                "Student code": c,
                "Week": w,
                "Days scheduled": 5,
                "Days attended": 4,
                "Tasks set": 3,
                "Tasks completed": 3,
                "Quiz score / 10": 7.0 + w * 0.5,
                "Observation": f"Week {w} obs",
                "Next step": "Continue",
            })
    return pd.DataFrame(rows)


def _make_part_entry(code, rc, lid="L1", skill="", name="", skill_id=""):
    from pages.lesson_workspace import build_participation_entry
    entry = build_participation_entry(
        student_code=code, student_name=name,
        lesson_id=lid, question="Q1",
        response_code=rc, source_code="TS",
        skill_id=skill_id, _now="2026-11-13T08:00:00",
    )
    if skill:
        entry.pop("skill_id")
        entry["skill"] = skill
    return entry


def _make_lesson_record(att: dict) -> dict:
    return {
        "class": "5B", "subject": "English", "title": "Reading",
        "objective": "...", "date": "2026-11-13",
        "started_at": "2026-11-13T08:00:00",
        "ended_at":   "2026-11-13T08:45:00",
        "lesson_id":  "LID-001",
        "attendance": att,
    }


# ---------------------------------------------------------------------------
# 5. Tests — build_student_profile()
# ---------------------------------------------------------------------------
class TestBuildStudentProfile(unittest.TestCase):

    def _profile(self, code="S01", with_name=True, part_log=None, lessons=None):
        return build_student_profile(
            student_code=code,
            summary_df=_make_summary(with_name=with_name),
            clean_df=_make_clean(),
            participation_log=part_log or [],
            lesson_records=lessons or [],
            has_name=with_name,
            skill_definitions=[
                {"id": "inference", "name": "Inference"},
                {"id": "vocabulary", "name": "Vocabulary"},
            ],
        )

    def test_01_found_true_for_known_student(self):
        p = self._profile("S01")
        self.assertTrue(p["found"])

    def test_02_found_false_for_unknown_student(self):
        p = self._profile("S99")
        self.assertFalse(p["found"])

    def test_03_student_code_preserved(self):
        p = self._profile("S01")
        self.assertEqual(p["student_code"], "S01")

    def test_04_student_name_set_when_has_name(self):
        p = self._profile("S01", with_name=True)
        self.assertIn("Ahmed", p["student_name"])

    def test_05_student_name_empty_when_no_name_col(self):
        p = self._profile("S01", with_name=False)
        # When no name column, build_outputs puts code as name; profile strips it
        self.assertEqual(p["student_name"], "")

    def test_06_weekly_rows_count(self):
        p = self._profile("S01")
        self.assertEqual(len(p["weekly_rows"]), 4)

    def test_07_weekly_rows_sorted_by_week(self):
        p = self._profile("S01")
        weeks = [r["Week"] for r in p["weekly_rows"]]
        self.assertEqual(weeks, sorted(weeks))

    def test_08_attendance_pct_present(self):
        p = self._profile("S01")
        self.assertIn("%", p["attendance_pct"])

    def test_09_mean_quiz_not_none(self):
        p = self._profile("S01")
        self.assertIsNotNone(p["mean_quiz"])

    def test_10_no_grade_key_in_profile(self):
        """Profile must not contain grade / score / ranking keys."""
        p = self._profile("S01")
        for bad in ("grade", "ranking", "rank", "final_score"):
            self.assertNotIn(bad, p,
                msg=f"Profile must not contain key '{bad}'")

    def test_11_participation_zero_when_empty_log(self):
        p = self._profile("S01", part_log=[])
        self.assertEqual(p["participation"]["total"], 0)
        self.assertEqual(p["participation"]["substantive"], 0)

    def test_12_participation_counts_entries(self):
        log = [
            _make_part_entry("S01", "C"),
            _make_part_entry("S01", "NR"),
            _make_part_entry("S02", "P"),  # different student — not counted
        ]
        p = self._profile("S01", part_log=log)
        self.assertEqual(p["participation"]["total"], 2)

    def test_13_nr_not_added_to_substantive(self):
        log = [_make_part_entry("S01", "NR")]
        p = self._profile("S01", part_log=log)
        self.assertEqual(p["participation"]["no_response"], 1)
        self.assertEqual(p["participation"]["substantive"], 0)

    def test_14_no_not_added_to_substantive(self):
        log = [_make_part_entry("S01", "NO")]
        p = self._profile("S01", part_log=log)
        self.assertEqual(p["participation"]["no_opportunity"], 1)
        self.assertEqual(p["participation"]["substantive"], 0)

    def test_15_skills_aggregated(self):
        log = [
            _make_part_entry("S01", "C", skill="Inference"),
            _make_part_entry("S01", "P", skill="Inference"),
            _make_part_entry("S01", "C", skill="Vocabulary"),
        ]
        p = self._profile("S01", part_log=log)
        self.assertEqual(p["skills"]["inference"], 2)
        self.assertEqual(p["skills"]["vocabulary"], 1)

    def test_16_skills_empty_when_no_skill_entries(self):
        log = [_make_part_entry("S01", "C", skill="")]
        p = self._profile("S01", part_log=log)
        self.assertEqual(p["skills"], {})

    def test_new_skill_id_displays_definition_name(self):
        entry = _make_part_entry("S01", "C", skill_id="inference")
        p = self._profile("S01", part_log=[entry])
        self.assertEqual(p["skills"], {"inference": 1})
        self.assertNotIn("skill", entry)

    def test_unknown_legacy_skill_remains_separately_unlinked(self):
        entry = _make_part_entry("S01", "C", skill="Mystery")
        original = dict(entry)
        p = self._profile("S01", part_log=[entry])
        self.assertEqual(p["skills"], {})
        self.assertEqual(p["unlinked_skills"], {"Mystery": 1})
        self.assertEqual(entry, original)

    def test_17_lesson_attendance_counts_present(self):
        lessons = [
            _make_lesson_record({"S01": "Present", "S02": "Absent"}),
            _make_lesson_record({"S01": "Late",    "S02": "Present"}),
        ]
        p = self._profile("S01", lessons=lessons)
        self.assertEqual(p["lessons_present"], 2)
        self.assertEqual(p["lessons_absent"],  0)
        self.assertEqual(p["lessons_total"],   2)

    def test_18_lesson_attendance_counts_absent(self):
        lessons = [
            _make_lesson_record({"S01": "Absent"}),
            _make_lesson_record({"S01": "Absent"}),
        ]
        p = self._profile("S01", lessons=lessons)
        self.assertEqual(p["lessons_absent"],  2)
        self.assertEqual(p["lessons_present"], 0)

    def test_19_absent_arabic_counted(self):
        lessons = [_make_lesson_record({"S01": "غائب"})]
        p = self._profile("S01", lessons=lessons)
        self.assertEqual(p["lessons_absent"], 1)

    def test_20_lessons_zero_when_no_records(self):
        p = self._profile("S01", lessons=[])
        self.assertEqual(p["lessons_total"], 0)

    def test_21_does_not_mutate_summary_df(self):
        df = _make_summary()
        before = df.shape
        build_student_profile("S01", df, _make_clean(), [], [])
        self.assertEqual(df.shape, before)

    def test_22_does_not_mutate_participation_log(self):
        log = [_make_part_entry("S01", "C")]
        before = list(log)
        build_student_profile("S01", _make_summary(), _make_clean(), log, [])
        self.assertEqual(log, before)


# ---------------------------------------------------------------------------
# 6. Tests — _summarise_student_participation()
# ---------------------------------------------------------------------------
class TestSummariseStudentParticipation(unittest.TestCase):

    def _e(self, code, rc, lid="L1", sk=""):
        return _make_part_entry(code, rc, lid=lid, skill=sk)

    def test_23_empty_log(self):
        s = _summarise_student_participation("S01", [])
        self.assertEqual(s["total"], 0)
        self.assertEqual(s["no_response"], 0)
        self.assertEqual(s["no_opportunity"], 0)

    def test_24_counts_only_matching_student(self):
        log = [self._e("S01", "C"), self._e("S02", "P")]
        s = _summarise_student_participation("S01", log)
        self.assertEqual(s["total"], 1)

    def test_25_nr_distinct_from_incorrect(self):
        log = [self._e("S01", "NR")]
        s = _summarise_student_participation("S01", log)
        self.assertEqual(s["no_response"], 1)
        self.assertEqual(s["by_response"]["I"], 0)

    def test_26_no_distinct_from_failure(self):
        log = [self._e("S01", "NO")]
        s = _summarise_student_participation("S01", log)
        self.assertEqual(s["no_opportunity"], 1)
        self.assertEqual(s["by_response"]["I"],  0)
        self.assertEqual(s["by_response"]["NR"], 0)

    def test_27_substantive_c_p_i_only(self):
        log = [
            self._e("S01", "C"), self._e("S01", "P"), self._e("S01", "I"),
            self._e("S01", "NR"), self._e("S01", "NO"),
        ]
        s = _summarise_student_participation("S01", log)
        self.assertEqual(s["substantive"], 3)

    def test_28_lesson_ids_unique(self):
        log = [
            self._e("S01", "C", lid="L1"),
            self._e("S01", "C", lid="L1"),  # duplicate lid
            self._e("S01", "C", lid="L2"),
        ]
        s = _summarise_student_participation("S01", log)
        self.assertEqual(len(s["lesson_ids"]), 2)

    def test_29_no_grade_in_summary_keys(self):
        s = _summarise_student_participation("S01", [])
        for bad in ("grade", "score", "average", "mean"):
            self.assertNotIn(bad, s)


# ---------------------------------------------------------------------------
# 7. Tests — Navigation and routing in app.py
# ---------------------------------------------------------------------------
class TestStudentProfileAppWiring(unittest.TestCase):

    def _src(self):
        path = os.path.join(HERE, "app.py")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_30_nav_entry_exists(self):
        self.assertIn("student_profile", self._src())

    def test_31_nav_bilingual(self):
        src = self._src()
        self.assertIn("Student Profile", src)
        self.assertIn("ملف الطالب",      src)

    def test_32_router_calls_sp_render(self):
        self.assertIn("_sp_render()", self._src())

    def test_33_profile_student_code_in_state(self):
        """shared/state.py must initialise profile_student_code."""
        path = os.path.join(HERE, "shared", "state.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("profile_student_code", src)


# ---------------------------------------------------------------------------
# 8. Tests — found=False profile is complete (no KeyError)
# ---------------------------------------------------------------------------
class TestProfileNotFound(unittest.TestCase):

    def test_34_not_found_has_all_keys(self):
        p = build_student_profile(
            "UNKNOWN",
            _make_summary(),
            _make_clean(),
            [], [],
        )
        self.assertFalse(p["found"])
        for key in ("student_code", "student_name", "attendance_pct",
                    "task_pct", "mean_quiz", "weekly_rows",
                    "participation", "skills",
                    "lessons_present", "lessons_absent", "lessons_total"):
            self.assertIn(key, p, msg=f"Missing key: {key}")

    def test_35_not_found_weekly_rows_empty(self):
        p = build_student_profile("X", _make_summary(), _make_clean(), [], [])
        self.assertEqual(p["weekly_rows"], [])

    def test_36_not_found_participation_zero(self):
        p = build_student_profile("X", _make_summary(), _make_clean(), [], [])
        self.assertEqual(p["participation"]["total"], 0)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== SchoolFlow AI — Student Profile Tests ===\n")
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = None
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestBuildStudentProfile))
    suite.addTests(loader.loadTestsFromTestCase(TestSummariseStudentParticipation))
    suite.addTests(loader.loadTestsFromTestCase(TestStudentProfileAppWiring))
    suite.addTests(loader.loadTestsFromTestCase(TestProfileNotFound))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print()
    total = result.testsRun
    if result.wasSuccessful():
        print("=" * 46)
        print(f"  ALL {total} STUDENT PROFILE TESTS PASSED")
        print("=" * 46)
    else:
        print(f"FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}")
        raise SystemExit(1)
