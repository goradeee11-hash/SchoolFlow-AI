"""
test_bloom.py
-------------
Offline unit tests for shared/bloom.py
(Bloom's Taxonomy & Question Classification — Task 8).

Tests cover:
  - Level constants (BLOOM_LEVELS, LEVEL_IDS, LEVEL_BY_ID)
  - Rule-based classifier (suggest_bloom_level) for English and Arabic questions
  - Low-confidence detection
  - Question record creation and updates (new_question, update_question)
  - Library store operations (add_question, remove_question, etc.)
  - Filter and distribution helpers
  - Design constraints (teacher control, transparency, no fabrication)
  - State initialisation
  - App wiring

No Streamlit runtime required; streamlit is stubbed.
"""

import sys
import os
import types
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# 1. Stub streamlit
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
HERE = os.path.dirname(__file__)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ---------------------------------------------------------------------------
# 3. Import functions under test
# ---------------------------------------------------------------------------
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
    get_question,
    replace_question,
    filter_questions,
    bloom_distribution,
)


# ---------------------------------------------------------------------------
# 4. Fixtures
# ---------------------------------------------------------------------------

def _q(text="What is photosynthesis?", level="remember", confirmed=True,
       _id="q001", _now="2026-11-01T08:00:00+00:00"):
    return new_question(
        text=text,
        bloom_level=level,
        confirmed_by_teacher=confirmed,
        _id=_id,
        _now=_now,
    )


# ---------------------------------------------------------------------------
# 5. Tests — Level constants
# ---------------------------------------------------------------------------
class TestBloomConstants(unittest.TestCase):

    def test_01_six_levels_defined(self):
        self.assertEqual(len(BLOOM_LEVELS), 6)

    def test_02_level_ids_ordered(self):
        expected = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
        self.assertEqual(LEVEL_IDS, expected)

    def test_03_all_levels_have_required_keys(self):
        for lvl in BLOOM_LEVELS:
            for key in ("id", "name_en", "name_ar", "description_en",
                        "description_ar", "color", "order"):
                self.assertIn(key, lvl, msg=f"Level {lvl['id']} missing key {key}")

    def test_04_level_by_id_lookup(self):
        lvl = LEVEL_BY_ID["analyze"]
        self.assertEqual(lvl["name_en"], "Analyze")
        self.assertEqual(lvl["color"], "#B7D957")

    def test_05_remember_order_is_1(self):
        self.assertEqual(LEVEL_BY_ID["remember"]["order"], 1)

    def test_06_create_order_is_6(self):
        self.assertEqual(LEVEL_BY_ID["create"]["order"], 6)


# ---------------------------------------------------------------------------
# 6. Tests — suggest_bloom_level() — English
# ---------------------------------------------------------------------------
class TestSuggestBloomEN(unittest.TestCase):

    def _suggest(self, text):
        return suggest_bloom_level(text)

    def test_07_empty_text_returns_remember_zero_confidence(self):
        r = self._suggest("")
        self.assertEqual(r["suggested_level"], "remember")
        self.assertEqual(r["confidence"], 0.0)
        self.assertTrue(r["low_confidence"])

    def test_08_has_required_keys(self):
        r = self._suggest("Define photosynthesis.")
        for key in ("suggested_level", "confidence", "low_confidence",
                    "reason", "reason_ar", "scores", "classifier_type"):
            self.assertIn(key, r)

    def test_09_classifier_type_is_rule_based(self):
        """Must be transparent — classifier is rule-based, not AI."""
        r = self._suggest("What is water?")
        self.assertEqual(r["classifier_type"], "rule_based")

    def test_10_define_suggests_remember(self):
        r = self._suggest("Define photosynthesis.")
        self.assertEqual(r["suggested_level"], "remember")

    def test_11_explain_suggests_understand(self):
        r = self._suggest("Explain how photosynthesis works.")
        self.assertEqual(r["suggested_level"], "understand")

    def test_12_summarise_suggests_understand(self):
        r = self._suggest("Summarise the main idea of the passage.")
        self.assertEqual(r["suggested_level"], "understand")

    def test_13_solve_suggests_apply(self):
        r = self._suggest("Solve this equation using the quadratic formula.")
        self.assertEqual(r["suggested_level"], "apply")

    def test_14_compare_suggests_analyze(self):
        r = self._suggest("Compare and contrast photosynthesis and respiration.")
        self.assertEqual(r["suggested_level"], "analyze")

    def test_15_justify_suggests_evaluate(self):
        r = self._suggest("Do you agree with the author's argument? Justify your answer.")
        self.assertEqual(r["suggested_level"], "evaluate")

    def test_16_design_suggests_create(self):
        r = self._suggest("Design an experiment to test the effect of light on plant growth.")
        self.assertEqual(r["suggested_level"], "create")

    def test_17_write_story_suggests_create(self):
        r = self._suggest("Write a short story about a child who discovers a magical garden.")
        self.assertEqual(r["suggested_level"], "create")

    def test_18_confidence_between_0_and_1(self):
        r = self._suggest("Explain the water cycle.")
        self.assertGreaterEqual(r["confidence"], 0.0)
        self.assertLessEqual(r["confidence"], 1.0)

    def test_19_scores_has_all_6_levels(self):
        r = self._suggest("What is water?")
        self.assertEqual(set(r["scores"].keys()), set(LEVEL_IDS))

    def test_20_reason_is_string(self):
        r = self._suggest("What is the main idea?")
        self.assertIsInstance(r["reason"], str)
        self.assertGreater(len(r["reason"]), 0)

    def test_21_reason_ar_is_string(self):
        r = self._suggest("What is the main idea?")
        self.assertIsInstance(r["reason_ar"], str)
        self.assertGreater(len(r["reason_ar"]), 0)


# ---------------------------------------------------------------------------
# 7. Tests — suggest_bloom_level() — Arabic
# ---------------------------------------------------------------------------
class TestSuggestBloomAR(unittest.TestCase):

    def test_22_define_ar_suggests_remember(self):
        r = suggest_bloom_level("عرِّف مفهوم التمثيل الضوئي.")
        self.assertEqual(r["suggested_level"], "remember")

    def test_23_explain_ar_suggests_understand(self):
        r = suggest_bloom_level("اشرح كيف يعمل التمثيل الضوئي.")
        self.assertEqual(r["suggested_level"], "understand")

    def test_24_compare_ar_suggests_analyze(self):
        r = suggest_bloom_level("قارن بين التمثيل الضوئي والتنفس الخلوي.")
        self.assertEqual(r["suggested_level"], "analyze")

    def test_25_justify_ar_suggests_evaluate(self):
        r = suggest_bloom_level("هل توافق على هذا القرار؟ برِّر إجابتك.")
        self.assertEqual(r["suggested_level"], "evaluate")

    def test_26_design_ar_suggests_create(self):
        r = suggest_bloom_level("صمِّم تجربة لدراسة تأثير الضوء على النمو النباتي.")
        self.assertEqual(r["suggested_level"], "create")

    def test_27_story_ar_suggests_create(self):
        r = suggest_bloom_level("اكتب قصة قصيرة عن طفل يكتشف حديقة سحرية.")
        self.assertEqual(r["suggested_level"], "create")


# ---------------------------------------------------------------------------
# 8. Tests — new_question()
# ---------------------------------------------------------------------------
class TestNewQuestion(unittest.TestCase):

    def test_28_has_required_keys(self):
        q = _q()
        for key in ("id", "text", "bloom_level", "confirmed_by_teacher",
                    "suggested_level", "confidence", "suggestion_reason",
                    "lesson_id", "skill_id", "subject", "grade",
                    "tags", "created_at", "updated_at"):
            self.assertIn(key, q)

    def test_default_question_timestamps_are_utc(self):
        q = new_question("Question?", "remember")
        for field in ("created_at", "updated_at"):
            self.assertEqual(datetime.fromisoformat(q[field]).utcoffset(), timedelta(0))

    def test_29_empty_text_raises(self):
        with self.assertRaises(ValueError):
            new_question("", "remember")

    def test_30_whitespace_only_raises(self):
        with self.assertRaises(ValueError):
            new_question("   ", "remember")

    def test_31_invalid_bloom_level_raises(self):
        with self.assertRaises(ValueError):
            new_question("Question?", "memorise")

    def test_32_all_valid_levels_accepted(self):
        for lid in LEVEL_IDS:
            q = new_question("Q?", lid)
            self.assertEqual(q["bloom_level"], lid)

    def test_33_text_preserved(self):
        q = new_question("What is water?", "remember")
        self.assertEqual(q["text"], "What is water?")

    def test_34_tags_default_empty(self):
        q = new_question("Q?", "remember")
        self.assertEqual(q["tags"], [])

    def test_35_tags_stored_as_list(self):
        q = new_question("Q?", "remember", tags=["science", "water"])
        self.assertEqual(q["tags"], ["science", "water"])


# ---------------------------------------------------------------------------
# 9. Tests — update_question()
# ---------------------------------------------------------------------------
class TestUpdateQuestion(unittest.TestCase):

    def test_36_does_not_mutate_original(self):
        q = _q()
        orig_level = q["bloom_level"]
        update_question(q, bloom_level="analyze", confirmed_by_teacher=True)
        self.assertEqual(q["bloom_level"], orig_level)

    def test_37_level_updated(self):
        q = _q(level="remember")
        updated = update_question(
            q, bloom_level="evaluate", confirmed_by_teacher=True
        )
        self.assertEqual(updated["bloom_level"], "evaluate")

    def test_level_change_requires_explicit_teacher_confirmation(self):
        for confirmed in (False, True):
            with self.subTest(confirmed_before=confirmed):
                q = _q(confirmed=confirmed)
                with self.assertRaisesRegex(ValueError, "confirmed_by_teacher=True"):
                    update_question(q, bloom_level="analyze")

    def test_level_change_rejects_explicit_false_confirmation(self):
        q = _q(confirmed=True)
        with self.assertRaisesRegex(ValueError, "confirmed_by_teacher=True"):
            update_question(
                q, bloom_level="analyze", confirmed_by_teacher=False
            )

    def test_level_change_with_explicit_confirmation_is_confirmed(self):
        q = _q(confirmed=False)
        updated = update_question(
            q, bloom_level="analyze", confirmed_by_teacher=True
        )
        self.assertTrue(updated["confirmed_by_teacher"])

    def test_39_invalid_level_raises(self):
        q = _q()
        with self.assertRaises(ValueError):
            update_question(q, bloom_level="memorise")

    def test_40_empty_text_raises(self):
        q = _q()
        with self.assertRaises(ValueError):
            update_question(q, text="")

    def test_41_updated_at_changes(self):
        q = _q(_now="2026-11-01T08:00:00+00:00")
        updated = update_question(
            q, bloom_level="analyze", confirmed_by_teacher=True,
            _now="2026-11-15T10:00:00+00:00"
        )
        self.assertEqual(updated["updated_at"], "2026-11-15T10:00:00+00:00")
        self.assertEqual(q["updated_at"], "2026-11-01T08:00:00+00:00")

    def test_default_updated_at_is_utc(self):
        updated = update_question(
            _q(), bloom_level="analyze", confirmed_by_teacher=True
        )
        self.assertEqual(
            datetime.fromisoformat(updated["updated_at"]).utcoffset(),
            timedelta(0),
        )


# ---------------------------------------------------------------------------
# 10. Tests — Library store operations
# ---------------------------------------------------------------------------
class TestLibraryStore(unittest.TestCase):

    def test_42_add_appends(self):
        q = _q()
        result = add_question([], q)
        self.assertEqual(len(result), 1)

    def test_43_add_does_not_mutate_original(self):
        lib = []
        add_question(lib, _q())
        self.assertEqual(len(lib), 0)

    def test_44_remove_removes_by_id(self):
        q = _q()
        lib = add_question([], q)
        result = remove_question(lib, q["id"])
        self.assertEqual(len(result), 0)

    def test_45_remove_no_error_if_not_found(self):
        result = remove_question([], "nope")
        self.assertEqual(result, [])

    def test_46_get_question_found(self):
        q = _q()
        lib = add_question([], q)
        found = get_question(lib, q["id"])
        self.assertIsNotNone(found)

    def test_47_get_question_not_found(self):
        result = get_question([], "nope")
        self.assertIsNone(result)

    def test_48_replace_updates_record(self):
        q = _q(level="remember")
        lib = add_question([], q)
        updated = update_question(
            q, bloom_level="analyze", confirmed_by_teacher=True
        )
        new_lib = replace_question(lib, updated)
        self.assertEqual(new_lib[0]["bloom_level"], "analyze")

    def test_48b_replace_cannot_bypass_level_confirmation(self):
        q = _q(level="remember")
        library = add_question([], q)
        bypass = dict(q, bloom_level="analyze", confirmed_by_teacher=False)
        with self.assertRaisesRegex(ValueError, "confirmed_by_teacher=True"):
            replace_question(library, bypass)

    def test_49_replace_not_found_raises(self):
        q = _q(_id="x99")
        with self.assertRaises(ValueError):
            replace_question([], q)


# ---------------------------------------------------------------------------
# 11. Tests — filter_questions()
# ---------------------------------------------------------------------------
class TestFilterQuestions(unittest.TestCase):

    def _lib(self):
        return [
            new_question("Define X", "remember", subject="English", _id="q1", _now="2026-11-01T08:00:00+00:00"),
            new_question("Explain Y", "understand", confirmed_by_teacher=True,
                         subject="English", grade="Grade 5", _id="q2", _now="2026-11-01T08:00:00+00:00"),
            new_question("Compare A and B", "analyze", subject="Science", _id="q3", _now="2026-11-01T08:00:00+00:00"),
        ]

    def test_50_no_filter_returns_all(self):
        lib = self._lib()
        result = filter_questions(lib)
        self.assertEqual(len(result), 3)

    def test_51_filter_by_level(self):
        lib = self._lib()
        result = filter_questions(lib, bloom_level="analyze")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "q3")

    def test_52_filter_by_subject(self):
        lib = self._lib()
        result = filter_questions(lib, subject="English")
        self.assertEqual(len(result), 2)

    def test_53_filter_confirmed_only(self):
        lib = self._lib()
        result = filter_questions(lib, confirmed_only=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "q2")

    def test_54_filter_combined(self):
        lib = self._lib()
        result = filter_questions(lib, subject="English", bloom_level="understand")
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# 12. Tests — bloom_distribution()
# ---------------------------------------------------------------------------
class TestBloomDistribution(unittest.TestCase):

    def test_55_empty_library_all_zeros(self):
        dist = bloom_distribution([])
        for lid in LEVEL_IDS:
            self.assertEqual(dist[lid], 0)

    def test_56_counts_correctly(self):
        lib = [
            new_question("Q1", "remember", _id="q1", _now="2026-11-01T08:00:00+00:00"),
            new_question("Q2", "remember", _id="q2", _now="2026-11-01T08:00:00+00:00"),
            new_question("Q3", "analyze",  _id="q3", _now="2026-11-01T08:00:00+00:00"),
        ]
        dist = bloom_distribution(lib)
        self.assertEqual(dist["remember"], 2)
        self.assertEqual(dist["analyze"],  1)
        self.assertEqual(dist["create"],   0)

    def test_57_all_six_levels_present(self):
        dist = bloom_distribution([])
        self.assertEqual(set(dist.keys()), set(LEVEL_IDS))


# ---------------------------------------------------------------------------
# 13. Tests — Design constraints
# ---------------------------------------------------------------------------
class TestDesignConstraints(unittest.TestCase):

    def test_58_bloom_module_no_streamlit(self):
        path = os.path.join(HERE, "shared", "bloom.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("import streamlit", src)

    def test_59_low_confidence_threshold_between_0_and_1(self):
        self.assertGreater(LOW_CONFIDENCE_THRESHOLD, 0.0)
        self.assertLess(LOW_CONFIDENCE_THRESHOLD, 1.0)

    def test_60_classifier_is_rule_based_not_ai(self):
        """classifier_type must be 'rule_based' — no false AI claims."""
        r = suggest_bloom_level("What is water?")
        self.assertEqual(r["classifier_type"], "rule_based")

    def test_61_suggestion_does_not_modify_library(self):
        """suggest_bloom_level must not modify any external state."""
        lib = [_q()]
        original = list(lib)
        suggest_bloom_level("Explain photosynthesis.")
        self.assertEqual(lib, original)

    def test_62_no_quota_imposed(self):
        """The classifier and helpers must impose no fixed distribution."""
        # bloom_distribution just counts — it does not enforce ratios
        lib = [new_question("Q" + str(i), "remember", _id=f"q{i}",
                            _now="2026-11-01T08:00:00+00:00") for i in range(10)]
        dist = bloom_distribution(lib)
        self.assertEqual(dist["remember"], 10)
        # No assertion error means no quota enforced

    def test_63_classification_not_a_quality_judgement(self):
        """The question record must not contain quality / rating keys."""
        q = _q()
        for bad in ("quality", "rating", "score", "good", "bad"):
            self.assertNotIn(bad, q)


# ---------------------------------------------------------------------------
# 14. Tests — State and wiring
# ---------------------------------------------------------------------------
class TestStateAndWiring(unittest.TestCase):

    def _src(self, path):
        with open(os.path.join(HERE, path), encoding="utf-8") as f:
            return f.read()

    def test_64_question_library_in_state(self):
        self.assertIn("question_library", self._src("shared/state.py"))

    def test_65_mutable_includes_question_library(self):
        self.assertIn('"question_library"', self._src("shared/state.py"))

    def test_66_nav_entry_exists(self):
        self.assertIn("bloom_questions", self._src("app.py"))

    def test_67_nav_bilingual(self):
        src = self._src("app.py")
        self.assertIn("Bloom Questions", src)
        self.assertIn("أسئلة بلوم", src)

    def test_68_router_calls_bq_render(self):
        self.assertIn("_bq_render()", self._src("app.py"))

    def test_69_bloom_py_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(HERE, "shared", "bloom.py")))

    def test_70_bloom_questions_page_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(HERE, "pages", "bloom_questions.py")))

    def test_level_edit_page_passes_explicit_teacher_confirmation(self):
        src = self._src("pages/bloom_questions.py")
        self.assertRegex(
            src,
            r"update_question\(\s*q,\s*bloom_level=new_id,\s*"
            r"confirmed_by_teacher=True",
        )


class TestBloomQuestionInteractions(unittest.TestCase):
    def setUp(self):
        from pages import bloom_questions

        self.page = bloom_questions
        self.ui = MagicMock()
        self.ui.session_state = {
            "question_library": [],
            "lesson_records": [
                {"lesson_id": "lesson-1", "title": "Lesson", "date": "2026-01-01"}
            ],
            "skill_definitions": [{"id": "skill-1", "name": "Skill"}],
        }
        self.ui.expander.side_effect = lambda *args, **kwargs: nullcontext()
        self.ui.columns.side_effect = lambda count: [nullcontext() for _ in range(count)]
        self.ui.text_input.return_value = ""
        self.ui.selectbox.side_effect = self._select
        self.pressed = None
        self.ui.button.side_effect = lambda *args, **kwargs: kwargs.get("key") == self.pressed
        self.patches = [
            patch.object(self.page, "st", self.ui),
            patch.object(self.page, "T", lambda en, ar: en),
            patch.object(self.page, "is_arabic", lambda: False),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def _select(self, label, options, index=0, key=None, **kwargs):
        if key in {"bloom_q_lesson", "bloom_q_skill"}:
            return options[1]
        return options[index]

    def _render(self, text, pressed=None):
        self.pressed = pressed
        self.ui.text_area.return_value = text
        self.page._render_classify("ltr", self.ui.session_state["question_library"])

    def test_editing_question_invalidates_old_suggestion(self):
        self._render("Define a planet.", "btn_bloom_suggest")
        self.assertEqual(self.ui.session_state["bloom_suggestion"]["suggested_level"], "remember")
        self.ui.button.reset_mock()
        self._render("Compare two planets.")
        rendered = [call.kwargs.get("key") for call in self.ui.button.call_args_list]
        self.assertNotIn("btn_bloom_save", rendered)
        self.assertIn("btn_bloom_manual_save", rendered)

    def test_manual_question_keeps_selected_lesson_and_skill(self):
        self._render("Compare two planets.", "btn_bloom_manual_save")
        saved = self.ui.session_state["question_library"][0]
        self.assertEqual(saved["lesson_id"], "lesson-1")
        self.assertEqual(saved["skill_id"], "skill-1")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== SchoolFlow AI — Bloom's Taxonomy Tests ===\n")
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = None
    suite = unittest.TestSuite()
    for cls in [
        TestBloomConstants,
        TestSuggestBloomEN,
        TestSuggestBloomAR,
        TestNewQuestion,
        TestUpdateQuestion,
        TestLibraryStore,
        TestFilterQuestions,
        TestBloomDistribution,
        TestDesignConstraints,
        TestStateAndWiring,
        TestBloomQuestionInteractions,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print()
    total = result.testsRun
    if result.wasSuccessful():
        print("=" * 50)
        print(f"  ALL {total} BLOOM TESTS PASSED")
        print("=" * 50)
    else:
        print(f"FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}")
        raise SystemExit(1)
