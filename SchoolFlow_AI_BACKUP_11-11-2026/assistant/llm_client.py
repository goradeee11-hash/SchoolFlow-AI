"""
llm_client.py
-------------
Thin wrapper around an LLM provider (currently OpenAI).
Designed so that:

1. The app works 100% offline when no API key is configured.
2. Adding an OpenAI key later enables richer natural language understanding
   without changing any other file.
3. No student PII is sent to external services — only anonymised summaries
   and the teacher's own query are included in any API call.

Configuration (when ready):
    .streamlit/secrets.toml
    ─────────────────────────
    [openai]
    api_key = "sk-..."
    model   = "gpt-4o-mini"   # optional, default shown
"""

from __future__ import annotations
import os

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_MODEL   = "gpt-4o-mini"
_MAX_TOKENS      = 512
_SYSTEM_PROMPT   = (
    "You are SchoolFlow AI Assistant, a helpful bilingual (Arabic/English) "
    "teaching assistant. You help teachers analyse student performance data. "
    "You never invent grades, attendance figures, or student names. "
    "When you cannot find data, say so clearly. "
    "Respond in the same language the teacher used."
)


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------

def _resolve_api_key() -> str | None:
    """
    Look for the OpenAI API key in (in order):
    1. Streamlit secrets  (.streamlit/secrets.toml  →  [openai] api_key)
    2. Environment variable  OPENAI_API_KEY
    Returns None if neither is found.
    """
    # Try Streamlit secrets first (only works when running inside Streamlit)
    try:
        import streamlit as st
        key = st.secrets.get("openai", {}).get("api_key") or st.secrets.get("OPENAI_API_KEY")
        if key:
            return key
    except Exception:
        pass

    # Fall back to environment variable
    return os.environ.get("OPENAI_API_KEY") or None


def _resolve_model() -> str:
    try:
        import streamlit as st
        return st.secrets.get("openai", {}).get("model", _DEFAULT_MODEL)
    except Exception:
        pass
    return os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------

def is_online() -> bool:
    """Return True only if an API key is available AND openai package is importable."""
    try:
        import openai  # noqa: F401
        return bool(_resolve_api_key())
    except ImportError:
        return False


def get_mode() -> str:
    """Return 'online' or 'offline'."""
    return "online" if is_online() else "offline"


# ---------------------------------------------------------------------------
# LLM call (online path)
# ---------------------------------------------------------------------------

def call_llm(user_message: str, context_summary: str = "") -> str:
    """
    Send user_message to the LLM with an optional anonymised context.
    Returns the assistant's response text, or raises RuntimeError on failure.

    context_summary should contain only aggregate numbers (e.g.
    "5 students, 4 weeks, avg attendance 92%") — no student names/IDs.
    """
    api_key = _resolve_api_key()
    if not api_key:
        raise RuntimeError("no_key")

    try:
        import openai
    except ImportError:
        raise RuntimeError("no_package")

    client = openai.OpenAI(api_key=api_key)
    model  = _resolve_model()

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if context_summary:
        messages.append({
            "role": "system",
            "content": f"Current class data summary (anonymised): {context_summary}",
        })
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=_MAX_TOKENS,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except openai.AuthenticationError:
        raise RuntimeError("bad_key")
    except openai.RateLimitError:
        raise RuntimeError("rate_limit")
    except openai.APIConnectionError:
        raise RuntimeError("connection_error")
    except Exception as e:
        raise RuntimeError(f"api_error: {e}")


# ---------------------------------------------------------------------------
# Safe wrapper used by the router
# ---------------------------------------------------------------------------

def try_llm_enhance(user_message: str, context_summary: str = "") -> str | None:
    """
    Attempt an LLM call; return the response or None on any failure.
    Never raises — callers fall back to rule-based routing on None.
    """
    if not is_online():
        return None
    try:
        return call_llm(user_message, context_summary)
    except RuntimeError as e:
        code = str(e)
        _error_messages = {
            "no_key":           None,   # silent fallback
            "no_package":       None,
            "bad_key":          "⚠️ مفتاح OpenAI غير صحيح. يعمل المساعد بالوضع المحلي.",
            "rate_limit":       "⚠️ تجاوزت الحد المسموح به من الطلبات. يعمل المساعد بالوضع المحلي.",
            "connection_error": "⚠️ تعذر الاتصال بخادم OpenAI. يعمل المساعد بالوضع المحلي.",
        }
        if code in _error_messages:
            return _error_messages[code]    # None = silent, str = user-visible warning
        return f"⚠️ خطأ في الاتصال بالذكاء الاصطناعي: {code}. يعمل المساعد بالوضع المحلي."
    except Exception:
        return None
