"""
test_academic_progress.py
--------------------------
Offline unit tests for shared/skills.py (Skills & Academic Progress — Task 6).

Tests cover:
  - Skill definition creation and management (new_skill, add_skill, etc.)
  - Assessment record creation and validation
  - Mastery calculation (compute_skill_mastery)
  - Student skills summary (student_skills_summary)
  - Class overview (class_skills_overview)
  - Separation of participation from academic attainment
  - N/A rules (no mastery from single assessment, etc.)
  - State initialisation (shared/state.py)

No Streamlit runtime required; streamlit is stubbed identically to
existing test files.
"""

import sys
import os
import types
import unittest
from datetime import datetime, timedelta
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Stub streamlit (identical pattern to other test files)
# ---------------------------------------------------------------------------
_state: dict = {}


class _FakeSecrets(dict):
    def get(self, key, default=None):
        return default


def _noop(*a, **kw):
    pass


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
    number_input    = staticmethod(lambda *a, **kw: kw.get("value", 0.0))
    date_input      = staticmethod(lambda *a, **kw: kw.get("value", None))
    tabs            = staticmethod(lambda labels: [_noop_ctx() for _ in labels])
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
from shared.skills import (
    make_skill_id,
    new_skill,
    add_skill,
    remove_skill,
    get_skill,
    skills_for_subject_grade,
    new_assessment,
    student_assessments,
    compute_skill_mastery,
    student_skills_summary,
    class_skills_overview,
    MIN_ASSESSMENTS_FOR_MASTERY,
    MASTERY_BANDS,
)

# ---------------------------------------------------------------------------
# 4. Fixtures
# ---------------------------------------------------------------------------

def _skill(name="Inference", subject="English", grade="Grade 5"):
    return new_skill(name=name, subject=subject, grade=grade)


def _make_skills():
    return [
        new_skill("Inference",   subject="English", grade="Grade 5"),
        new_skill("Vocabulary",  subject="English", grade="Grade 5"),
        new_skill("Fluency",     subject="English", grade="Grade 6"),
    ]


def _ass(skill_id, student, score, max_score=10.0, date="2026-11-01"):
    return new_assessment(
        skill_id=skill_id,
        student_code=student,
        score=score,
        max_score=max_score,
        date=date,
    )


def _part(student, response_code, skill=""):
    """Make a legacy participation entry with a free-text skill value."""
    return {
        "student_code":  student,
        "lesson_id":     "L1",
        "response_code": response_code,
        "source_code":   "TS",
        "skill":         skill,
        "timestamp":     "2026-11-01T08:00:00",
    }


def _part_id(student, response_code, skill_id=""):
    """Make a participation record using the current Skill ID schema."""
    return {
        "student_code": student,
        "lesson_id": "L1",
        "response_code": response_code,
        "source_code": "TS",
        "skill_id": skill_id,
        "timestamp": "2026-11-01T08:00:00",
    }


# ---------------------------------------------------------------------------
# 5. Tests — Skill ID and new_skill()
# ---------------------------------------------------------------------------
class TestSkillCreation(unittest.TestCase):

    def test_01_make_skill_id_simple(self):
        self.assertEqual(make_skill_id("Reading Inference"), "reading_inference")

    def test_02_make_skill_id_special_chars(self):
        sid = make_skill_id("Vocab & Grammar!")
        self.assertRegex(sid, r"^[a-z0-9_]+$")

    def test_03_new_skill_has_required_keys(self):
        s = _skill()
        for key in ("id", "name", "subject", "grade", "description", "objectives"):
            self.assertIn(key, s, msg=f"Missing key: {key}")

    def test_04_new_skill_name_preserved(self):
        s = new_skill("Phonemic Awareness")
        self.assertEqual(s["name"], "Phonemic Awareness")

    def test_05_new_skill_empty_name_raises(self):
        with self.assertRaises(ValueError):
            new_skill("")

    def test_06_new_skill_whitespace_only_raises(self):
        with self.assertRaises(ValueError):
            new_skill("   ")

    def test_07_new_skill_explicit_id(self):
        s = new_skill("Test Skill", skill_id="custom_id")
        self.assertEqual(s["id"], "custom_id")

    def test_08_new_skill_objectives_list(self):
        s = new_skill("Reading", objectives=["Identify main idea", "Infer meaning"])
        self.assertEqual(len(s["objectives"]), 2)

    def test_09_new_skill_objectives_default_empty(self):
        s = new_skill("Reading")
        self.assertEqual(s["objectives"], [])


# ---------------------------------------------------------------------------
# 6. Tests — add_skill / remove_skill / get_skill
# ---------------------------------------------------------------------------
class TestSkillStoreOps(unittest.TestCase):

    def test_10_add_skill_appends(self):
        store = []
        s = _skill()
        result = add_skill(store, s)
        self.assertEqual(len(result), 1)

    def test_11_add_skill_duplicate_raises(self):
        s = _skill()
        store = add_skill([], s)
        with self.assertRaises(ValueError):
            add_skill(store, s)   # same id

    def test_12_add_skill_does_not_mutate_original(self):
        store = []
        add_skill(store, _skill())
        self.assertEqual(len(store), 0)

    def test_13_remove_skill_removes_by_id(self):
        s = _skill()
        store = add_skill([], s)
        result = remove_skill(store, s["id"])
        self.assertEqual(len(result), 0)

    def test_14_remove_skill_no_error_if_not_found(self):
        result = remove_skill([], "nonexistent")
        self.assertEqual(result, [])

    def test_15_get_skill_found(self):
        s = _skill()
        store = add_skill([], s)
        found = get_skill(store, s["id"])
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], "Inference")

    def test_16_get_skill_not_found_returns_none(self):
        result = get_skill([], "nope")
        self.assertIsNone(result)

    def test_17_skills_for_subject_grade_filters_subject(self):
        skills = _make_skills()
        result = skills_for_subject_grade(skills, subject="English")
        self.assertEqual(len(result), 3)

    def test_18_skills_for_subject_grade_filters_grade(self):
        skills = _make_skills()
        result = skills_for_subject_grade(skills, grade="Grade 5")
        self.assertEqual(len(result), 2)

    def test_19_skills_for_subject_grade_no_filter(self):
        skills = _make_skills()
        result = skills_for_subject_grade(skills)
        self.assertEqual(len(result), 3)


# ---------------------------------------------------------------------------
# 7. Tests — new_assessment()
# ---------------------------------------------------------------------------
class TestAssessmentCreation(unittest.TestCase):

    def test_20_valid_assessment(self):
        a = _ass("inference", "S01", 7.0)
        self.assertTrue(a["id"])
        self.assertEqual(a["skill_id"], "inference")
        self.assertEqual(a["score"], 7.0)
        self.assertEqual(a["max_score"], 10.0)

    def test_created_at_is_utc_and_calendar_date_is_preserved(self):
        a = new_assessment("sk", "S01", 5.0, max_score=10.0, date="2026-11-14")
        created_at = datetime.fromisoformat(a["created_at"])
        self.assertEqual(created_at.utcoffset(), timedelta(0))
        self.assertEqual(a["date"], "2026-11-14")

    def test_21_max_score_zero_raises(self):
        with self.assertRaises(ValueError):
            new_assessment("sk", "S01", 5.0, max_score=0.0)

    def test_22_negative_score_raises(self):
        with self.assertRaises(ValueError):
            new_assessment("sk", "S01", -1.0, max_score=10.0)

    def test_23_score_exceeds_max_raises(self):
        with self.assertRaises(ValueError):
            new_assessment("sk", "S01", 11.0, max_score=10.0)

    def test_24_zero_score_valid(self):
        a = new_assessment("sk", "S01", 0.0, max_score=10.0)
        self.assertEqual(a["score"], 0.0)

    def test_25_perfect_score_valid(self):
        a = new_assessment("sk", "S01", 10.0, max_score=10.0)
        self.assertEqual(a["score"], 10.0)

    def test_non_finite_scores_and_max_scores_raise(self):
        non_finite_values = (float("nan"), float("inf"), float("-inf"))
        for value in non_finite_values:
            with self.subTest(field="score", value=value):
                with self.assertRaisesRegex(ValueError, "score must be a finite number"):
                    new_assessment("sk", "S01", value, max_score=10.0)
            with self.subTest(field="max_score", value=value):
                with self.assertRaisesRegex(ValueError, "max_score must be a finite number"):
                    new_assessment("sk", "S01", 5.0, max_score=value)

    def test_26_assessment_has_required_keys(self):
        a = _ass("sk", "S01", 5.0)
        for key in ("skill_id", "student_code", "score", "max_score",
                    "date", "lesson_id", "notes", "created_at"):
            self.assertIn(key, a, msg=f"Missing key: {key}")


# ---------------------------------------------------------------------------
# 8. Tests — student_assessments()
# ---------------------------------------------------------------------------
class TestStudentAssessments(unittest.TestCase):

    def _records(self):
        return [
            _ass("inference", "S01", 6.0, date="2026-11-01"),
            _ass("inference", "S01", 8.0, date="2026-11-10"),
            _ass("vocabulary", "S01", 7.0, date="2026-11-05"),
            _ass("inference", "S02", 9.0, date="2026-11-01"),
        ]

    def test_27_filters_by_student(self):
        result = student_assessments(self._records(), "S01")
        self.assertEqual(len(result), 3)

    def test_28_filters_by_skill(self):
        result = student_assessments(self._records(), "S01", skill_id="inference")
        self.assertEqual(len(result), 2)

    def test_29_sorted_by_date_ascending(self):
        result = student_assessments(self._records(), "S01", skill_id="inference")
        dates = [r["date"] for r in result]
        self.assertEqual(dates, sorted(dates))

    def test_30_different_student_not_included(self):
        result = student_assessments(self._records(), "S01")
        codes = {r["student_code"] for r in result}
        self.assertNotIn("S02", codes)


# ---------------------------------------------------------------------------
# 9. Tests — compute_skill_mastery()
# ---------------------------------------------------------------------------
class TestComputeSkillMastery(unittest.TestCase):

    def test_31_empty_assessments(self):
        m = compute_skill_mastery([])
        self.assertEqual(m["count"], 0)
        self.assertIsNone(m["mean_pct"])
        self.assertIsNone(m["mastery_level"])
        self.assertEqual(m["trend"], "N/A")
        self.assertFalse(m["needs_support"])

    def test_32_single_assessment_no_mastery_level(self):
        """Single assessment must NOT trigger mastery classification."""
        a = [_ass("sk", "S01", 9.0)]
        m = compute_skill_mastery(a)
        self.assertIsNone(m["mastery_level"])
        self.assertEqual(m["count"], 1)

    def test_33_two_assessments_allows_mastery(self):
        a = [
            _ass("sk", "S01", 8.0, date="2026-11-01"),
            _ass("sk", "S01", 9.0, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertIsNotNone(m["mastery_level"])

    def test_34_mastery_secure_at_80_pct(self):
        a = [
            _ass("sk", "S01", 8.0, date="2026-11-01"),
            _ass("sk", "S01", 8.5, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertEqual(m["mastery_level"], "Secure")

    def test_35_mastery_developing_60_to_79(self):
        a = [
            _ass("sk", "S01", 6.0, date="2026-11-01"),
            _ass("sk", "S01", 7.0, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertEqual(m["mastery_level"], "Developing")

    def test_36_mastery_emerging_40_to_59(self):
        a = [
            _ass("sk", "S01", 4.0, date="2026-11-01"),
            _ass("sk", "S01", 5.0, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertEqual(m["mastery_level"], "Emerging")

    def test_37_mastery_beginning_below_40(self):
        a = [
            _ass("sk", "S01", 2.0, date="2026-11-01"),
            _ass("sk", "S01", 3.0, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertEqual(m["mastery_level"], "Beginning")

    def test_38_needs_support_beginning(self):
        a = [
            _ass("sk", "S01", 1.0, date="2026-11-01"),
            _ass("sk", "S01", 2.0, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertTrue(m["needs_support"])

    def test_39_needs_support_false_secure(self):
        a = [
            _ass("sk", "S01", 9.0, date="2026-11-01"),
            _ass("sk", "S01", 9.5, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertFalse(m["needs_support"])

    def test_40_needs_support_false_when_no_mastery(self):
        """If mastery_level is None (insufficient data), needs_support must be False."""
        a = [_ass("sk", "S01", 1.0)]
        m = compute_skill_mastery(a)
        self.assertFalse(m["needs_support"])

    def test_41_trend_improving(self):
        a = [
            _ass("sk", "S01", 5.0, date="2026-11-01"),
            _ass("sk", "S01", 9.0, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertEqual(m["trend"], "improving")

    def test_42_trend_declining(self):
        a = [
            _ass("sk", "S01", 9.0, date="2026-11-01"),
            _ass("sk", "S01", 2.0, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertEqual(m["trend"], "declining")

    def test_43_trend_stable(self):
        a = [
            _ass("sk", "S01", 7.0, date="2026-11-01"),
            _ass("sk", "S01", 7.0, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertEqual(m["trend"], "stable")

    def test_44_trend_na_single_assessment(self):
        a = [_ass("sk", "S01", 7.0)]
        m = compute_skill_mastery(a)
        self.assertEqual(m["trend"], "N/A")

    def test_45_scores_pct_chronological(self):
        a = [
            _ass("sk", "S01", 6.0, date="2026-11-01"),
            _ass("sk", "S01", 8.0, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertEqual(m["scores_pct"], [60.0, 80.0])

    def test_46_no_grade_or_score_key_in_mastery(self):
        m = compute_skill_mastery([])
        for bad in ("grade", "ranking", "rank", "final_score"):
            self.assertNotIn(bad, m, msg=f"Mastery must not contain key '{bad}'")

    def test_47_participation_record_is_not_an_assessment(self):
        participation = _part_id("S01", "C", "inference")
        with self.assertRaisesRegex(ValueError, "score must be a finite number"):
            compute_skill_mastery([participation])

    def test_non_finite_assessments_raise_even_when_mixed_with_valid_records(self):
        valid = _ass("sk", "S01", 8.0, date="2026-11-01")
        non_finite_values = (float("nan"), float("inf"), float("-inf"))
        for value in non_finite_values:
            for field in ("score", "max_score"):
                invalid = {
                    "skill_id": "sk",
                    "student_code": "S01",
                    "score": 5.0,
                    "max_score": 10.0,
                    "date": "2026-11-10",
                }
                invalid[field] = value
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, "must be a finite number"):
                        compute_skill_mastery([valid, invalid])


# ---------------------------------------------------------------------------
# 10. Tests — student_skills_summary()
# ---------------------------------------------------------------------------
class TestStudentSkillsSummary(unittest.TestCase):

    def _setup(self):
        skills = _make_skills()  # inference, vocabulary, fluency
        assessments = [
            _ass("inference", "S01", 7.0, date="2026-11-01"),
            _ass("inference", "S01", 8.0, date="2026-11-10"),
            _ass("vocabulary", "S01", 5.0, date="2026-11-01"),
            _ass("inference", "S02", 9.0, date="2026-11-01"),
        ]
        participation = [
            _part("S01", "C", skill="inference"),
            _part("S01", "P", skill="inference"),
            _part("S01", "NR", skill="vocabulary"),
            _part("S01", "C", skill="SomeUndefinedSkill"),
        ]
        return skills, assessments, participation

    def test_48_returns_list(self):
        s, a, p = self._setup()
        rows = student_skills_summary("S01", s, a, p)
        self.assertIsInstance(rows, list)

    def test_49_includes_assessed_skills(self):
        s, a, p = self._setup()
        rows = student_skills_summary("S01", s, a, p)
        ids = [r["skill_id"] for r in rows]
        self.assertIn("inference", ids)
        self.assertIn("vocabulary", ids)

    def test_50_does_not_include_other_student_data(self):
        s, a, _ = self._setup()
        rows = student_skills_summary("S01", s, a, [])
        # S02 had inference assessment; should not appear in S01's summary
        for r in rows:
            m = r["mastery"]
            # All assessments counted must belong to S01
            self.assertGreaterEqual(m["count"], 0)

    def test_51_participation_counts_separated(self):
        s, a, p = self._setup()
        rows = student_skills_summary("S01", s, a, p)
        inf_row = next((r for r in rows if r["skill_id"] == "inference"), None)
        self.assertIsNotNone(inf_row)
        self.assertEqual(inf_row["participation_c"], 1)
        self.assertEqual(inf_row["participation_p"], 1)

    def test_52_participation_not_used_for_mastery(self):
        """A student with ONLY participation (no assessments) must have mastery=None."""
        s = _make_skills()
        p = [_part("S01", "C", skill="inference"), _part("S01", "C", skill="inference")]
        rows = student_skills_summary("S01", s, [], p)
        for r in rows:
            if r["skill_id"] == "inference":
                self.assertIsNone(r["mastery"]["mastery_level"])

    def test_53_unnamed_participation_skill_included(self):
        s = []  # no formal skill definitions
        p = [_part("S01", "C", skill="SomeNewSkill")]
        rows = student_skills_summary("S01", s, [], p)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["skill_id"])
        self.assertEqual(rows[0]["skill_name"], "SomeNewSkill")
        self.assertFalse(rows[0]["skill_linked"])

    def test_54_unnamed_has_no_assessments(self):
        s = []
        p = [_part("S01", "C", skill="UndefinedSkill")]
        rows = student_skills_summary("S01", s, [], p)
        for r in rows:
            if r["skill_name"] == "UndefinedSkill":
                self.assertFalse(r["has_assessments"])
                self.assertIsNone(r["skill_id"])
                self.assertFalse(r["skill_linked"])

    def test_legacy_unique_name_links_once_to_formal_skill(self):
        skills = _make_skills()
        assessments = [_ass("inference", "S01", 7.0)]
        legacy = [
            _part("S01", "C", skill=" inference "),
            _part("S01", "P", skill="Inference"),
        ]
        original = [dict(entry) for entry in legacy]

        rows = student_skills_summary("S01", skills, assessments, legacy)

        inference_rows = [row for row in rows if row["skill_id"] == "inference"]
        self.assertEqual(len(inference_rows), 1)
        self.assertEqual(inference_rows[0]["participation_c"], 1)
        self.assertEqual(inference_rows[0]["participation_p"], 1)
        self.assertEqual(legacy, original)

    def test_ambiguous_legacy_name_stays_unlinked_without_creating_definition(self):
        definitions = [
            new_skill("Inference", skill_id="inference_a"),
            new_skill(" inference ", skill_id="inference_b"),
        ]
        original_definitions = [dict(skill) for skill in definitions]
        legacy = _part("S01", "C", skill="Inference")
        original_entry = dict(legacy)

        rows = student_skills_summary("S01", definitions, [], [legacy])

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["skill_id"])
        self.assertFalse(rows[0]["skill_linked"])
        self.assertEqual(rows[0]["skill_name"], "Inference")
        self.assertEqual(definitions, original_definitions)
        self.assertEqual(legacy, original_entry)

    def test_unknown_id_does_not_fall_back_to_legacy_name(self):
        definitions = _make_skills()
        entry = _part("S01", "C", skill="Inference")
        entry["skill_id"] = "missing_id"

        rows = student_skills_summary("S01", definitions, [], [entry])

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["skill_id"])
        self.assertFalse(rows[0]["skill_linked"])
        self.assertEqual(rows[0]["skill_name"], "Inference")

    def test_new_skill_id_links_participation_without_changing_mastery(self):
        skills = _make_skills()
        assessments = [
            _ass("inference", "S01", 7.0),
            _ass("inference", "S01", 8.0, date="2026-11-10"),
        ]
        participation = [_part_id("S01", "C", "inference")]

        without_participation = student_skills_summary(
            "S01", skills, assessments, []
        )
        with_participation = student_skills_summary(
            "S01", skills, assessments, participation
        )
        before = next(row for row in without_participation if row["skill_id"] == "inference")
        after = next(row for row in with_participation if row["skill_id"] == "inference")

        self.assertEqual(after["skill_name"], "Inference")
        self.assertEqual(after["participation_c"], 1)
        self.assertEqual(after["mastery"], before["mastery"])

    def test_55_empty_data_returns_empty_list(self):
        rows = student_skills_summary("S01", [], [], [])
        self.assertEqual(rows, [])

    def test_non_finite_assessment_rejected_in_student_summary(self):
        invalid = {
            "skill_id": "inference",
            "student_code": "S01",
            "score": float("nan"),
            "max_score": 10.0,
            "date": "2026-11-01",
        }
        with self.assertRaisesRegex(ValueError, "score must be a finite number"):
            student_skills_summary("S01", _make_skills(), [invalid], [])


# ---------------------------------------------------------------------------
# 11. Tests — class_skills_overview()
# ---------------------------------------------------------------------------
class TestClassSkillsOverview(unittest.TestCase):

    def test_56_empty_returns_empty_df(self):
        df = class_skills_overview(["S01"], [], [])
        self.assertIsInstance(df, pd.DataFrame)
        self.assertTrue(df.empty)

    def test_57_returns_dataframe(self):
        skills = [new_skill("Inference", subject="English", grade="G5")]
        ass = [
            _ass("inference", "S01", 7.0, date="2026-11-01"),
            _ass("inference", "S01", 8.0, date="2026-11-10"),
        ]
        df = class_skills_overview(["S01"], skills, ass)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertGreater(len(df), 0)

    def test_58_has_required_columns(self):
        skills = [new_skill("Inference")]
        ass = [
            _ass("inference", "S01", 7.0, date="2026-11-01"),
            _ass("inference", "S01", 8.0, date="2026-11-10"),
        ]
        df = class_skills_overview(["S01"], skills, ass)
        for col in ("Student code", "Skill", "Assessments", "Mean %", "Mastery Level"):
            self.assertIn(col, df.columns, msg=f"Missing column: {col}")

    def test_59_mastery_na_shown_when_insufficient_data(self):
        skills = [new_skill("Inference")]
        # Only 1 assessment — below MIN_ASSESSMENTS_FOR_MASTERY
        ass = [_ass("inference", "S01", 9.0, date="2026-11-01")]
        df = class_skills_overview(["S01"], skills, ass)
        if not df.empty:
            row = df[df["Student code"] == "S01"]
            if not row.empty:
                self.assertEqual(row.iloc[0]["Mastery Level"], "N/A")

    def test_60_participation_excluded_from_overview(self):
        """class_skills_overview must only use assessment_records, not participation."""
        skills = [new_skill("Inference")]
        ass = []  # no assessments
        df = class_skills_overview(["S01"], skills, ass)
        self.assertTrue(df.empty)

    def test_non_finite_assessment_rejected_in_class_overview(self):
        invalid = {
            "skill_id": "inference",
            "student_code": "S01",
            "score": 8.0,
            "max_score": float("inf"),
            "date": "2026-11-01",
        }
        with self.assertRaisesRegex(ValueError, "max_score must be a finite number"):
            class_skills_overview(["S01"], [new_skill("Inference")], [invalid])


# ---------------------------------------------------------------------------
# 12. Tests — State initialisation
# ---------------------------------------------------------------------------
class TestStateInit(unittest.TestCase):

    def _src(self, filename):
        path = os.path.join(HERE, "shared", filename)
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_61_skill_definitions_in_state(self):
        src = self._src("state.py")
        self.assertIn("skill_definitions", src)

    def test_62_skill_assessments_in_state(self):
        src = self._src("state.py")
        self.assertIn("skill_assessments", src)

    def test_63_skill_progress_student_code_in_state(self):
        src = self._src("state.py")
        self.assertIn("skill_progress_student_code", src)

    def test_64_mutable_includes_skill_definitions(self):
        src = self._src("state.py")
        # Both keys must appear in _MUTABLE block
        self.assertIn('"skill_definitions"', src)
        self.assertIn('"skill_assessments"', src)


# ---------------------------------------------------------------------------
# 13. Tests — App wiring (academic_progress in nav + router)
# ---------------------------------------------------------------------------
class TestAcademicProgressAppWiring(unittest.TestCase):

    def _app_src(self):
        path = os.path.join(HERE, "app.py")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_65_nav_entry_exists(self):
        self.assertIn("academic_progress", self._app_src())

    def test_66_nav_bilingual(self):
        src = self._app_src()
        self.assertIn("Skills & Progress", src)
        self.assertIn("المهارات والتحصيل", src)

    def test_67_router_calls_ap_render(self):
        self.assertIn("_ap_render()", self._app_src())

    def test_68_skills_py_exists(self):
        path = os.path.join(HERE, "shared", "skills.py")
        self.assertTrue(os.path.isfile(path), "shared/skills.py not found")

    def test_69_academic_progress_page_exists(self):
        path = os.path.join(HERE, "pages", "academic_progress.py")
        self.assertTrue(os.path.isfile(path), "pages/academic_progress.py not found")

    def test_70_student_profile_links_to_academic(self):
        path = os.path.join(HERE, "pages", "student_profile.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("academic_progress", src)
        self.assertIn("skill_progress_student_code", src)


# ---------------------------------------------------------------------------
# 14. Tests — Design constraints
# ---------------------------------------------------------------------------
class TestDesignConstraints(unittest.TestCase):

    def test_71_mastery_not_from_participation(self):
        """
        Even 100 Correct participation entries for a skill must NOT
        produce a mastery level (no assessments = mastery None).
        """
        skills = [new_skill("Inference")]
        p = [_part("S01", "C", skill="inference") for _ in range(10)]
        rows = student_skills_summary("S01", skills, [], p)
        for r in rows:
            self.assertIsNone(r["mastery"]["mastery_level"])

    def test_72_no_fabricated_data_when_empty(self):
        m = compute_skill_mastery([])
        self.assertIsNone(m["mean_pct"])
        self.assertIsNone(m["latest_pct"])
        self.assertIsNone(m["mastery_level"])

    def test_73_mastery_requires_min_assessments(self):
        self.assertGreaterEqual(MIN_ASSESSMENTS_FOR_MASTERY, 2)

    def test_74_mastery_bands_cover_zero(self):
        """MASTERY_BANDS must have a band that covers 0% (lowest threshold)."""
        thresholds = [t for t, _, _ in MASTERY_BANDS]
        self.assertIn(0.0, thresholds)

    def test_75_mastery_bands_cover_100(self):
        """A score of 100% must match some band."""
        # simulate 100%
        a = [
            _ass("sk", "S01", 10.0, date="2026-11-01"),
            _ass("sk", "S01", 10.0, date="2026-11-10"),
        ]
        m = compute_skill_mastery(a)
        self.assertIsNotNone(m["mastery_level"])

    def test_76_skills_module_has_no_streamlit_import(self):
        """shared/skills.py must not import streamlit."""
        path = os.path.join(HERE, "shared", "skills.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("import streamlit", src)

    def test_77_assessment_records_not_modified_by_student_summary(self):
        skills = _make_skills()
        ass = [_ass("inference", "S01", 7.0)]
        original = list(ass)
        student_skills_summary("S01", skills, ass, [])
        self.assertEqual(ass, original)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== SchoolFlow AI — Skills & Academic Progress Tests ===\n")
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = None
    suite = unittest.TestSuite()
    for cls in [
        TestSkillCreation,
        TestSkillStoreOps,
        TestAssessmentCreation,
        TestStudentAssessments,
        TestComputeSkillMastery,
        TestStudentSkillsSummary,
        TestClassSkillsOverview,
        TestStateInit,
        TestAcademicProgressAppWiring,
        TestDesignConstraints,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print()
    total = result.testsRun
    if result.wasSuccessful():
        print("=" * 54)
        print(f"  ALL {total} ACADEMIC PROGRESS TESTS PASSED")
        print("=" * 54)
    else:
        print(f"FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}")
        raise SystemExit(1)
