"""
test_assistant.py
-----------------
Offline tests for the assistant module (no Streamlit, no API needed).
Patches st.session_state with realistic data from sample_data.xlsx,
then verifies intent routing and tool functions for 20 scenarios.
"""
import sys, os, types, unittest, pandas as pd
from io import BytesIO

# ---------------------------------------------------------------------------
# 1.  Stub streamlit before any import touches it
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

    # Page / layout calls
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
    text_input      = staticmethod(lambda *a, **kw: "")
    text_area       = staticmethod(lambda *a, **kw: "")
    selectbox       = staticmethod(lambda *a, **kw: (kw.get("options") or (a[1] if len(a) > 1 else [""]))[0])
    radio           = staticmethod(lambda *a, **kw: "English")
    button          = staticmethod(lambda *a, **kw: False)
    download_button = staticmethod(lambda *a, **kw: False)
    file_uploader   = staticmethod(lambda *a, **kw: None)
    dataframe       = staticmethod(_noop)
    expander        = staticmethod(_noop_ctx)
    container       = staticmethod(_noop_ctx)
    class _FakeSidebar:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def markdown(self, *a, **kw): pass
        def button(self, *a, **kw): return False
        def rerun(self): pass
    sidebar = _FakeSidebar()
    class _FakeCol:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def markdown(self, *a, **kw): pass
        def caption(self, *a, **kw): pass
        def button(self, *a, **kw): return False
        def download_button(self, *a, **kw): return False
        def selectbox(self, *a, **kw): return ""
        def text_input(self, *a, **kw): return ""

    @staticmethod
    def columns(n, **kw):
        count = n if isinstance(n, int) else len(n)
        return [_FakeST._FakeCol() for _ in range(count)]
    metric          = staticmethod(_noop)
    spinner         = staticmethod(_noop_ctx)
    cache_data      = staticmethod(lambda f=None, **kw: f if f else lambda g: g)

sys.modules["streamlit"] = _FakeST("streamlit")

# ---------------------------------------------------------------------------
# 2.  Patch sys.path so assistant package resolves
# ---------------------------------------------------------------------------
HERE    = os.path.dirname(__file__)
APP_DIR = HERE  # SchoolFlow_AI_MVP/
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# ---------------------------------------------------------------------------
# 3.  Load real data into fake session_state
# ---------------------------------------------------------------------------
from app_logic import (
    fresh_bytes, validate, build_outputs,
    REQUIRED, OPTIONAL_NAME_COL, NUMERIC_COLS,
)

SAMPLE = os.path.join(HERE, "sample_data.xlsx")

def _setup_state():
    """Populate _state with real analysis results from sample_data.xlsx."""
    with open(SAMPLE, "rb") as f:
        raw_bytes = f.read()

    class _FakeUpload:
        def getvalue(self): return raw_bytes

    uploaded = _FakeUpload()
    raw = pd.read_excel(fresh_bytes(uploaded), sheet_name="Weekly tracking", header=4)
    raw.columns = [str(c).strip() for c in raw.columns]
    has_name = OPTIONAL_NAME_COL in raw.columns
    cols = REQUIRED + ([OPTIONAL_NAME_COL] if has_name else [])
    data = raw[cols].dropna(how="all")

    issues = validate(data)
    clean, summary, weekly = build_outputs(data, has_name)

    _state.clear()
    _state["clean"]    = clean
    _state["summary"]  = summary
    _state["weekly"]   = weekly
    _state["has_name"] = has_name
    _state["issues"]   = issues

_setup_state()

# ---------------------------------------------------------------------------
# 4.  Import router
# ---------------------------------------------------------------------------
from assistant.intent_router import route
from assistant.llm_client    import get_mode, is_online

# ---------------------------------------------------------------------------
# 5.  Tests
# ---------------------------------------------------------------------------
class TestAssistantOffline(unittest.TestCase):

    # ── Mode ───────────────────────────────────────────────────────────────
    def test_01_mode_is_offline(self):
        """No API key → offline mode."""
        self.assertEqual(get_mode(), "offline")
        self.assertFalse(is_online())

    # ── Greetings ──────────────────────────────────────────────────────────
    def test_02_greeting_arabic(self):
        r = route("مرحبا")
        self.assertEqual(r["intent"], "greeting")
        self.assertTrue(r["ok"])

    def test_03_greeting_english(self):
        r = route("Hello")
        self.assertEqual(r["intent"], "greeting")
        self.assertTrue(r["ok"])

    # ── Help ───────────────────────────────────────────────────────────────
    def test_04_help(self):
        r = route("مساعدة")
        self.assertEqual(r["intent"], "help")
        self.assertIn("تقرير", r["response"])

    # ── Class analysis ─────────────────────────────────────────────────────
    def test_05_class_analysis_arabic(self):
        r = route("تحليل الفصل")
        self.assertEqual(r["intent"], "class_analysis")
        self.assertTrue(r["ok"])
        self.assertIn("5", r["response"])   # 5 students

    def test_06_class_analysis_english(self):
        r = route("class analysis")
        self.assertEqual(r["intent"], "class_analysis")
        self.assertTrue(r["ok"])

    # ── At-risk ────────────────────────────────────────────────────────────
    def test_07_at_risk(self):
        r = route("من يحتاج متابعة؟")
        self.assertEqual(r["intent"], "at_risk")
        self.assertTrue(r["ok"])

    def test_08_at_risk_english(self):
        r = route("show at-risk students")
        self.assertEqual(r["intent"], "at_risk")
        self.assertTrue(r["ok"])

    # ── Student report ─────────────────────────────────────────────────────
    def test_09_student_report_known(self):
        r = route("تقرير S01")
        self.assertEqual(r["intent"], "student_report")
        self.assertTrue(r["ok"])
        self.assertIn("S01", r["response"])

    def test_10_student_report_by_name(self):
        r = route("تقرير Ahmed")
        self.assertEqual(r["intent"], "student_report")
        self.assertTrue(r["ok"])
        self.assertIn("Ahmed", r["response"])

    def test_11_student_report_unknown(self):
        r = route("تقرير XYZ999")
        self.assertEqual(r["intent"], "student_report")
        self.assertFalse(r["ok"])
        self.assertIn("XYZ999", r["response"])

    # ── Weekly record ──────────────────────────────────────────────────────
    def test_12_student_weekly(self):
        r = route("سجل S02")
        self.assertEqual(r["intent"], "student_weekly")
        self.assertTrue(r["ok"])
        self.assertIn("S02", r["response"])

    # ── Parent message Arabic ──────────────────────────────────────────────
    def test_13_parent_message_arabic(self):
        r = route("رسالة ولي أمر S01")
        self.assertEqual(r["intent"], "parent_message")
        self.assertTrue(r["ok"])
        self.assertIn("مرحبًا", r["response"])

    # ── Parent message English ─────────────────────────────────────────────
    def test_14_parent_message_english(self):
        r = route("رسالة إنجليزي S01")
        self.assertEqual(r["intent"], "parent_message_en")
        self.assertTrue(r["ok"])
        self.assertIn("Hello", r["response"])

    # ── Data issues ────────────────────────────────────────────────────────
    def test_15_data_issues(self):
        r = route("مشكلات البيانات")
        self.assertEqual(r["intent"], "data_issues")
        self.assertTrue(r["ok"])
        self.assertIn("S02", r["response"])   # known issue in sample data

    # ── Week summary ───────────────────────────────────────────────────────
    def test_16_week_summary(self):
        r = route("ملخص الأسبوع 2")
        self.assertEqual(r["intent"], "week_summary")
        self.assertTrue(r["ok"])
        self.assertIn("2", r["response"])

    def test_17_week_summary_nonexistent(self):
        r = route("ملخص الأسبوع 99")
        self.assertEqual(r["intent"], "week_summary")
        self.assertFalse(r["ok"])

    # ── List students ──────────────────────────────────────────────────────
    def test_18_list_students(self):
        r = route("قائمة الطلاب")
        self.assertEqual(r["intent"], "list_students")
        self.assertTrue(r["ok"])
        self.assertIn("S01", r["response"])

    # ── Excel download reminder ────────────────────────────────────────────
    def test_19_excel_download(self):
        r = route("تنزيل Excel")
        self.assertEqual(r["intent"], "excel_download")
        self.assertTrue(r["ok"])

    # ── Explain results ────────────────────────────────────────────────────
    def test_20_explain_results(self):
        r = route("اشرح النتائج")
        self.assertEqual(r["intent"], "explain_results")
        self.assertTrue(r["ok"])

    # ── Unknown / unsupported command ──────────────────────────────────────
    def test_21_unknown_command(self):
        r = route("أرسل رسائل لجميع أولياء الأمور تلقائياً")
        self.assertEqual(r["intent"], "unknown")
        self.assertFalse(r["ok"])
        # Must NOT claim it did something
        self.assertNotIn("تم الإرسال", r["response"])

    def test_22_no_data_yet(self):
        """Responses when analysis hasn't been run."""
        _state_backup = dict(_state)
        _state.clear()
        try:
            r = route("تقرير S01")
            self.assertFalse(r["ok"])
            self.assertIn("Excel", r["response"])
        finally:
            _state.update(_state_backup)


# ---------------------------------------------------------------------------
# 6.  Adversarial & bilingual tests
# ---------------------------------------------------------------------------
class TestAdversarialAndBilingual(unittest.TestCase):
    """
    10 adversarial tests + bilingual verification.
    All rely on the same _state already loaded by _setup_state() above.
    """

    # ── Test 23: ambiguous partial name match ──────────────────────────────
    def test_23_ambiguous_partial_name(self):
        """
        If two students share a partial name, the assistant must NOT silently
        pick the first one. It must ask the teacher to clarify.
        Sample data has names like 'Ahmed Al-Farsi'.  We inject a second
        student whose name also contains 'Ahmed' to force the ambiguity path.
        """
        import pandas as pd
        backup_summary = _state["summary"].copy()
        try:
            # Add a fake second 'Ahmed' row
            extra = backup_summary.iloc[0].copy()
            extra["Student code"] = "S99"
            extra["Student name"] = "Ahmed Khalil"
            _state["summary"] = pd.concat(
                [backup_summary, extra.to_frame().T], ignore_index=True
            )
            r = route("تقرير Ahmed")
            # Must NOT return ok=True with one student's data silently
            self.assertFalse(r["ok"],
                msg="Must return ok=False when multiple students match")
            resp = r["response"]
            # Must list both matches
            self.assertIn("S01", resp)   # original Ahmed
            self.assertIn("S99", resp)   # injected Ahmed
        finally:
            _state["summary"] = backup_summary

    # ── Test 24: ambiguous partial code match (S0 matches all 5) ───────────
    def test_24_ambiguous_partial_code_s0(self):
        """
        'report S0' matches S01…S05 — must not silently return S01.
        """
        r = route("report S0")
        self.assertFalse(r["ok"],
            msg="'report S0' matches 5 students — must trigger disambiguation")
        resp = r["response"]
        # All five codes must appear in the disambiguation message
        for code in ("S01", "S02", "S03", "S04", "S05"):
            self.assertIn(code, resp,
                msg=f"Expected {code} in disambiguation list")

    # ── Test 25: nonexistent week returns available list ───────────────────
    def test_25_nonexistent_week_returns_list(self):
        r = route("ملخص الأسبوع 99")
        self.assertFalse(r["ok"])
        # Must report which weeks ARE available (sample has weeks 1-4)
        for w in ("1", "2", "3", "4"):
            self.assertIn(w, r["response"])

    # ── Test 26: 'guess grade' rejected — unknown intent ──────────────────
    def test_26_guess_grade_rejected(self):
        """Assistant must not invent or guess a grade."""
        r = route("خمّن درجة S01")
        self.assertFalse(r["ok"])
        # Must NOT claim it computed a grade
        self.assertNotIn("10", r["response"][:30])

    # ── Test 27: unsupported operation (auto-send messages) ───────────────
    def test_27_unsupported_auto_send_rejected(self):
        r = route("أرسل رسائل لجميع أولياء الأمور تلقائياً")
        self.assertEqual(r["intent"], "unknown")
        self.assertFalse(r["ok"])
        self.assertNotIn("تم الإرسال", r["response"])
        self.assertNotIn("sent", r["response"].lower())

    # ── Test 28: class analysis without data → upload prompt ──────────────
    def test_28_class_analysis_no_data(self):
        backup = dict(_state)
        _state.clear()
        try:
            r = route("تحليل الفصل")
            self.assertFalse(r["ok"])
            self.assertIn("Excel", r["response"])
        finally:
            _state.update(backup)

    # ── Test 29: English greeting response is English ──────────────────────
    def test_29_bilingual_greeting_english(self):
        r = route("Hello", lang="en")
        self.assertEqual(r["intent"], "greeting")
        self.assertTrue(r["ok"])
        resp = r["response"]
        self.assertIn("SchoolFlow", resp)
        # Must NOT be purely Arabic
        self.assertNotIn("مرحبًا", resp)

    # ── Test 30: Arabic greeting response is Arabic ────────────────────────
    def test_30_bilingual_greeting_arabic(self):
        r = route("مرحبا", lang="ar")
        self.assertEqual(r["intent"], "greeting")
        self.assertTrue(r["ok"])
        self.assertIn("مرحبًا", r["response"])

    # ── Test 31: EN and AR class analysis contain the same student count ───
    def test_31_bilingual_facts_consistent(self):
        """
        Both language responses must report the same facts (5 students).
        Translation must not alter numerical values.
        """
        r_en = route("class analysis", lang="en")
        r_ar = route("تحليل الفصل",  lang="ar")
        self.assertTrue(r_en["ok"])
        self.assertTrue(r_ar["ok"])
        # Both must contain '5' (student count)
        self.assertIn("5", r_en["response"])
        self.assertIn("5", r_ar["response"])
        # EN response must not contain Arabic-only phrases
        self.assertNotIn("طلاب", r_en["response"])
        # AR response must not contain English-only phrases
        self.assertNotIn("students", r_ar["response"])

    # ── Test 32: English help response is in English ───────────────────────
    def test_32_bilingual_help_english(self):
        r = route("help", lang="en")
        self.assertEqual(r["intent"], "help")
        self.assertTrue(r["ok"])
        resp = r["response"]
        self.assertIn("Available Commands", resp)
        self.assertIn("report S01", resp)

    # ── Test 33: English unknown response is in English ────────────────────
    def test_33_bilingual_unknown_english(self):
        r = route("please invent student grades", lang="en")
        self.assertFalse(r["ok"])
        resp = r["response"]
        self.assertIn("not currently supported", resp)
        # Must not claim it did something
        self.assertNotIn("grade", resp.lower()[:50])

    # ── Test 34: correct student data preserved — no cross-contamination ───
    def test_34_no_cross_student_contamination(self):
        """
        Report for S01 must not contain data about S02 or vice-versa.
        """
        r01 = route("report S01", lang="en")
        r02 = route("report S02", lang="en")
        self.assertTrue(r01["ok"])
        self.assertTrue(r02["ok"])
        # Each response contains its own code
        self.assertIn("S01", r01["response"])
        self.assertIn("S02", r02["response"])
        # Each response must NOT contain the other's code as the subject
        # (S02 might appear in S01's context only if it's in obs text,
        # but the report header must be unique)
        self.assertNotIn("S02", r01["response"][:60])
        self.assertNotIn("S01", r02["response"][:60])


# ---------------------------------------------------------------------------
# 7.  Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== SchoolFlow AI Assistant Tests ===\n")
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = None   # preserve definition order
    suite  = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestAssistantOffline))
    suite.addTests(loader.loadTestsFromTestCase(TestAdversarialAndBilingual))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print()
    total = result.testsRun
    if result.wasSuccessful():
        print("=" * 44)
        print(f"  ALL {total} ASSISTANT TESTS PASSED")
        print("=" * 44)
    else:
        print(f"FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}")
        raise SystemExit(1)
