"""
shared/i18n.py
--------------
Bilingual (Arabic / English) helpers for SchoolFlow AI.

Usage in app.py and future pages:
    from shared.i18n import T, get_lang, is_arabic, text_dir

Design notes
------------
* get_lang()   reads st.session_state["ui_lang"] on every call — this is
  safe because Streamlit re-runs the entire script on each interaction,
  so module-level caching would behave identically, but a function call
  is clearer and avoids subtle ordering bugs.
* T() replicates the exact same logic as the original T() defined inline
  in app.py lines 631-632 — no behaviour change.
* Callers may still compute local aliases for performance-sensitive loops:
      _IS_AR = is_arabic()
      _DIR   = text_dir()
  exactly as app.py does today.
"""

from __future__ import annotations

_DEFAULT_LANG = "en"
_SUPPORTED_LANGS = frozenset({"en", "ar"})


def get_lang() -> str:
    """Return the current UI language: 'en' or 'ar'.

    Reads st.session_state['ui_lang'] and accepts only supported languages.
    Falls back to English when Streamlit or an active session is unavailable,
    or when the stored value is invalid. Unexpected errors are not suppressed.
    """
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:
        if exc.name != "streamlit":
            raise
        return _DEFAULT_LANG

    try:
        language = st.session_state.get("ui_lang", _DEFAULT_LANG)
    except (AttributeError, RuntimeError):
        return _DEFAULT_LANG
    return language if isinstance(language, str) and language in _SUPPORTED_LANGS else _DEFAULT_LANG


def is_arabic() -> bool:
    """Return True when the current UI language is Arabic."""
    return get_lang() == "ar"


def text_dir() -> str:
    """Return CSS direction string: 'rtl' for Arabic, 'ltr' otherwise."""
    return "rtl" if is_arabic() else "ltr"


def translate_column_labels(
    columns: list[str],
    arabic_labels: dict[str, str],
) -> list[str]:
    """Translate known display-only column labels while preserving unknown labels."""
    if not is_arabic():
        return list(columns)
    return [arabic_labels.get(column, column) for column in columns]


def T(en: str, ar: str) -> str:  # noqa: N802  (short name intentional)
    """Return *ar* when UI language is Arabic, *en* otherwise.

    Drop-in replacement for the T() defined inline in app.py.
    Usage is identical:
        T("Upload", "رفع")
    """
    return ar if is_arabic() else en
