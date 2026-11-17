"""
test_shared.py
--------------
Unit tests for the shared/ package (Task 1 — SchoolFlow AI).

Tests are headless: streamlit is stubbed so no browser or server is needed.
Run with:
    python test_shared.py

All 9 tests cover:
  shared/styles.py  — inject_css()
  shared/i18n.py    — T(), get_lang(), is_arabic(), text_dir()
  shared/state.py   — init_state()
"""

import sys
import os
import types
import unittest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# 1.  Stub streamlit before any import touches it
# ---------------------------------------------------------------------------
_injected_html: list = []

class _FakeSecrets(dict):
    def get(self, key, default=None):
        return default

_state: dict = {}

def _fake_markdown(html, **kw):
    _injected_html.append(html)

class _FakeST(types.ModuleType):
    session_state = _state
    secrets       = _FakeSecrets()

    @staticmethod
    def markdown(html, **kw):
        _injected_html.append(html)

    @staticmethod
    def set_page_config(**kw):
        pass

sys.modules["streamlit"] = _FakeST("streamlit")

# ---------------------------------------------------------------------------
# 2.  Patch sys.path so shared/ resolves
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ---------------------------------------------------------------------------
# 3.  Import the modules under test
# ---------------------------------------------------------------------------
from shared.styles import (  # noqa: E402
    ACCENT_LIME, PRIMARY_NAVY, WHITE, inject_css, _CSS,
)
from shared.html_utils import escape_html           # noqa: E402
from shared.i18n   import (  # noqa: E402
    T, get_lang, is_arabic, text_dir, translate_column_labels,
)
from shared.state  import init_state                # noqa: E402
from shared.streamlit_compat import full_width, _supports_stretch_width  # noqa: E402


# ---------------------------------------------------------------------------
# 4.  Test classes
# ---------------------------------------------------------------------------

class TestStreamlitCompatibility(unittest.TestCase):
    def tearDown(self):
        _supports_stretch_width.cache_clear()

    def test_full_width_supports_both_old_and_new_streamlit(self):
        for streamlit_version, expected in (
            ("1.40.0", {"use_container_width": True}),
            ("1.48.0", {"use_container_width": True}),
            ("1.49.0", {"width": "stretch"}),
            ("1.67.0", {"width": "stretch"}),
        ):
            with self.subTest(streamlit_version=streamlit_version):
                _supports_stretch_width.cache_clear()
                with patch("shared.streamlit_compat.version", return_value=streamlit_version):
                    self.assertEqual(full_width(), expected)


class TestStyles(unittest.TestCase):

    def setUp(self):
        sys.modules["streamlit"] = _FakeST("streamlit")
        _injected_html.clear()
        _state.pop("ui_lang", None)

    def test_01_inject_css_does_not_raise(self):
        """inject_css() must complete without raising any exception."""
        try:
            inject_css()
        except Exception as e:
            self.fail(f"inject_css() raised {type(e).__name__}: {e}")

    def test_02_inject_css_inserts_style_tag(self):
        """inject_css() must pass HTML containing a <style> tag to st.markdown."""
        inject_css()
        self.assertTrue(
            any("<style>" in h for h in _injected_html),
            msg="Expected a <style> tag in the injected HTML"
        )

    def test_css_uses_the_approved_brand_palette(self):
        self.assertEqual(PRIMARY_NAVY, "#102B4E")
        self.assertEqual(ACCENT_LIME, "#B7D957")
        self.assertEqual(WHITE, "#FFFFFF")
        self.assertIn("#102B4E", _CSS)
        self.assertIn("#B7D957", _CSS)
        self.assertIn("#FFFFFF", _CSS)
        self.assertNotIn("#1B5E4A", _CSS)
        self.assertIn("background: #EAF4FA !important;", _CSS)
        self.assertIn("color: #102B4E !important;", _CSS)
        self.assertNotIn("#C7E83E", _CSS)
        self.assertIn("--sf-border: #A9C0D5;", _CSS)

    def test_global_theme_uses_contrasting_light_surfaces(self):
        self.assertIn(".stApp { background-color: #EAF4FA !important;", _CSS)
        self.assertIn("--sf-surface: #D7E8F2;", _CSS)
        self.assertIn("--sf-surface-raised: #C8DFEC;", _CSS)
        self.assertIn(".sf-card {\n    background: var(--sf-surface);", _CSS)
        self.assertIn("--sf-logo-panel: #EAF4FA;", _CSS)
        self.assertIn("color: #FFFFFF !important;", _CSS)
        self.assertIn('[data-testid="stFormSubmitButton"] button[kind="primary"]', _CSS)
        self.assertIn('[data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"]', _CSS)
        self.assertIn('[data-testid="stAlertContainer"]', _CSS)
        self.assertIn('[data-testid="stTextInputRootElement"]', _CSS)
        self.assertIn('[data-testid="stSidebar"] [data-testid="stImage"] {\n    background: var(--sf-logo-panel);', _CSS)
        self.assertIn(".sf-hero-logo {\n    background: var(--sf-logo-panel);", _CSS)
        self.assertIn(".st-key-sf-login-brand [data-testid=\"stImage\"] {\n    background: transparent;", _CSS)

    def test_shared_main_styles_also_cover_chat_layout(self):
        self.assertIn('main#stMain [data-testid="stSelectbox"]', _CSS)
        self.assertNotIn('[data-testid="stMain"]', _CSS)

    def test_fonts_are_local_system_fallbacks(self):
        self.assertNotIn("fonts.googleapis.com", _CSS)
        self.assertIn("Noto Sans Arabic", _CSS)
        with open(os.path.join(HERE, "app.py"), encoding="utf-8") as f:
            self.assertNotIn("fonts.googleapis.com", f.read())

    def test_brand_logo_asset_is_used_in_app_shell(self):
        light_logo = os.path.join(
            HERE, "assets", "schoolflow_ai_logo_light_background.png"
        )
        transparent_logo = os.path.join(
            HERE, "assets", "schoolflow_ai_logo_transparent.png"
        )
        for logo_path in (light_logo, transparent_logo):
            with open(logo_path, "rb") as logo:
                self.assertEqual(logo.read(8), b"\x89PNG\r\n\x1a\n")

        with open(os.path.join(HERE, "app.py"), encoding="utf-8") as f:
            source = f.read()
        self.assertIn("page_icon=_LOGO_TRANSPARENT_PATH", source)
        self.assertIn("st.image(_LOGO_LIGHT_PATH, width=300)", source)
        self.assertIn("st.image(_LOGO_TRANSPARENT_PATH, width=190)", source)
        self.assertIn('key="sf-login-brand"', source)
        self.assertIn('class="sf-hero-logo"', source)
        self.assertIn("_LOGO_DATA_URI", source)
        self.assertIn("data:image/png;base64,", source)
        self.assertIn("@media (max-width: 768px)", _CSS)

    def test_login_language_selector_is_available_before_authentication(self):
        with open(os.path.join(HERE, "app.py"), encoding="utf-8") as f:
            source = f.read()
        login_gate = source.index('if not st.session_state.get("_supabase_user_id"):')
        login_stop = source.index("        st.stop()", login_gate)
        language_controls = source.index('with st.container(key="sf-login-language")')
        self.assertLess(login_gate, language_controls)
        self.assertLess(language_controls, login_stop)
        self.assertIn('key="login_lang_en"', source[login_gate:login_stop])
        self.assertIn('key="login_lang_ar"', source[login_gate:login_stop])
        self.assertIn('st.session_state["ui_lang"] = "en"', source[login_gate:login_stop])
        self.assertIn('st.session_state["ui_lang"] = "ar"', source[login_gate:login_stop])

    def test_arabic_injection_sets_rtl_dataframe_direction(self):
        _state["ui_lang"] = "ar"
        inject_css()
        self.assertTrue(
            any('[data-testid="stDataFrame"]' in html and "direction: rtl;" in html
                for html in _injected_html)
        )


class TestHtmlUtils(unittest.TestCase):

    def test_escape_html_encodes_markup_and_quotes(self):
        self.assertEqual(
            escape_html('<img src="x" onerror="run()"> &'),
            "&lt;img src=&quot;x&quot; onerror=&quot;run()&quot;&gt; &amp;",
        )

    def test_escape_html_stringifies_non_string_values(self):
        self.assertEqual(escape_html(42), "42")


class TestI18n(unittest.TestCase):

    def setUp(self):
        sys.modules["streamlit"] = _FakeST("streamlit")

    def _set_lang(self, lang: str):
        _state["ui_lang"] = lang

    def test_04_get_lang_default(self):
        """get_lang() returns 'en' when ui_lang is not set."""
        _state.pop("ui_lang", None)
        self.assertEqual(get_lang(), "en")

    def test_invalid_language_values_fall_back_to_english(self):
        for language in ("fr", None, [], {}):
            with self.subTest(language=language):
                _state["ui_lang"] = language
                self.assertEqual(get_lang(), "en")
                self.assertFalse(is_arabic())
                self.assertEqual(text_dir(), "ltr")

    def test_missing_streamlit_falls_back_to_english(self):
        sys.modules["streamlit"] = None
        try:
            self.assertEqual(get_lang(), "en")
        finally:
            sys.modules["streamlit"] = _FakeST("streamlit")

    def test_unexpected_session_state_error_is_not_suppressed(self):
        class BrokenState:
            def get(self, *args, **kwargs):
                raise ValueError("unexpected state failure")

        streamlit_stub = _FakeST("streamlit")
        streamlit_stub.session_state = BrokenState()
        sys.modules["streamlit"] = streamlit_stub
        with self.assertRaisesRegex(ValueError, "unexpected state failure"):
            get_lang()

    def test_05_T_returns_english(self):
        """T(en, ar) returns English string when ui_lang == 'en'."""
        self._set_lang("en")
        self.assertEqual(T("hello", "مرحبا"), "hello")

    def test_06_T_returns_arabic(self):
        """T(en, ar) returns Arabic string when ui_lang == 'ar'."""
        self._set_lang("ar")
        self.assertEqual(T("hello", "مرحبا"), "مرحبا")

    def test_07_is_arabic_true_and_false(self):
        """is_arabic() reflects current ui_lang correctly."""
        self._set_lang("ar")
        self.assertTrue(is_arabic())
        self._set_lang("en")
        self.assertFalse(is_arabic())

    def test_08_text_dir(self):
        """text_dir() returns 'rtl' for Arabic and 'ltr' for English."""
        self._set_lang("ar")
        self.assertEqual(text_dir(), "rtl")
        self._set_lang("en")
        self.assertEqual(text_dir(), "ltr")

    def test_column_labels_follow_language_and_preserve_unknowns(self):
        labels = {"Week": "الأسبوع"}
        self._set_lang("en")
        self.assertEqual(
            translate_column_labels(["Week", "Custom"], labels),
            ["Week", "Custom"],
        )
        self._set_lang("ar")
        self.assertEqual(
            translate_column_labels(["Week", "Custom"], labels),
            ["الأسبوع", "Custom"],
        )

    def test_main_dashboard_section_titles_are_not_mixed_language(self):
        with open(os.path.join(HERE, "app.py"), encoding="utf-8") as f:
            source = f.read()
        for mixed_title in (
            "Upload Student Tracking File · رفع ملف متابعة الطلاب",
            "Data Quality Check · مراجعة جودة البيانات",
            "Teacher Dashboard · ملخص المعلم",
            "Weekly Class Summary · الملخص الأسبوعي للفصل",
            "Student Summary · ملخص كل طالب",
            "Review before sending — راجع الرسالة قبل إرسالها",
            "Download Reports · تنزيل النتائج",
        ):
            self.assertNotIn(mixed_title, source)

    def test_dashboard_displays_localized_table_and_chart_labels(self):
        with open(os.path.join(HERE, "app.py"), encoding="utf-8") as f:
            source = f.read()
        self.assertIn('"Student code": "رمز الطالب"', source)
        self.assertIn("_localized_dataframe(weekly)", source)
        self.assertIn("_localized_dataframe(summary)", source)
        self.assertIn("_build_weekly_svg(weekly, arabic=_IS_AR)", source)
        self.assertIn('week_label = "الأسبوع" if arabic else "Week"', source)


class TestState(unittest.TestCase):

    def setUp(self):
        sys.modules["streamlit"] = _FakeST("streamlit")
        _state.clear()

    def test_09_init_state_sets_all_defaults(self):
        """init_state() populates all expected keys with correct default values."""
        init_state()
        self.assertIn("ui_lang", _state)
        self.assertEqual(_state["ui_lang"], "en")

        self.assertIn("page", _state)
        self.assertEqual(_state["page"], "dashboard")

        self.assertIn("online_ai_enabled", _state)
        self.assertEqual(_state["online_ai_enabled"], False)

        self.assertIn("chat_history", _state)
        self.assertIsInstance(_state["chat_history"], list)
        self.assertEqual(_state["chat_history"], [])

        self.assertIn("assistant_mode", _state)
        self.assertEqual(_state["assistant_mode"], "offline")
        self.assertIn("audit_log", _state)
        self.assertEqual(_state["audit_log"], [])

    def test_10_init_state_does_not_overwrite(self):
        """init_state() must NOT overwrite values already in session_state."""
        _state["ui_lang"] = "ar"
        _state["online_ai_enabled"] = True
        _state["chat_history"] = [{"role": "user", "content": "hi"}]

        init_state()

        self.assertEqual(_state["ui_lang"], "ar",
            msg="ui_lang must not be reset to 'en'")
        self.assertEqual(_state["online_ai_enabled"], True,
            msg="online_ai_enabled must not be reset to False")
        self.assertEqual(len(_state["chat_history"]), 1,
            msg="chat_history must not be cleared")

    def test_11_init_state_no_data_keys(self):
        """init_state() must NOT touch clean/summary/weekly/has_name/issues."""
        init_state()
        for key in ("clean", "summary", "weekly", "has_name", "issues"):
            self.assertNotIn(key, _state,
                msg=f"init_state() must not initialise '{key}'")

    def test_12_chat_history_is_independent_list(self):
        """Each call with empty state produces a fresh independent list."""
        init_state()
        h1 = _state["chat_history"]
        _state.clear()
        init_state()
        h2 = _state["chat_history"]
        h1.append("x")
        self.assertEqual(h2, [],
            msg="chat_history lists from different calls must be independent")


# ---------------------------------------------------------------------------
# 5.  Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== SchoolFlow AI shared/ Tests ===\n")
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = None   # preserve definition order
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestStyles))
    suite.addTests(loader.loadTestsFromTestCase(TestHtmlUtils))
    suite.addTests(loader.loadTestsFromTestCase(TestI18n))
    suite.addTests(loader.loadTestsFromTestCase(TestState))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print()
    total = result.testsRun
    if result.wasSuccessful():
        print("=" * 44)
        print(f"  ALL {total} SHARED TESTS PASSED")
        print("=" * 44)
    else:
        print(f"FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}")
        raise SystemExit(1)
