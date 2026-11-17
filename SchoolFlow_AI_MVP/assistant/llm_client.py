"""
llm_client.py
-------------
Thin wrapper around an LLM provider (currently OpenAI).
Designed so that:

1. The app works 100% offline when no API key is configured.
2. Adding an OpenAI key later enables richer natural language understanding
   without changing any other file.
3. Only the teacher's query and optional caller-supplied summary are sent.
   The caller must not include student identifiers or sensitive data.

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
    "teaching assistant. Help teachers plan lessons, activities and questions, "
    "including Bloom's taxonomy and the nine Gagne instructional events. "
    "Help interpret only the performance information supplied to you. "
    "You never invent grades, attendance figures, or student names. "
    "When information is missing, say so clearly. Recommendations require "
    "teacher review and must not claim to access records you have not received. "
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
    except (ImportError, FileNotFoundError):
        pass

    # Fall back to environment variable
    return os.environ.get("OPENAI_API_KEY") or None


def _resolve_model() -> str:
    try:
        import streamlit as st
        return st.secrets.get("openai", {}).get("model", _DEFAULT_MODEL)
    except (ImportError, FileNotFoundError):
        pass
    return os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------

def is_online() -> bool:
    """Return True only if an API key is available AND openai package is importable."""
    if os.environ.get("SCHOOLFLOW_SHARED_DEMO") == "1":
        return False
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
    if os.environ.get("SCHOOLFLOW_SHARED_DEMO") == "1":
        raise RuntimeError("shared_demo_disabled")
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
        content = response.choices[0].message.content if response.choices else None
        if not content or not content.strip():
            raise RuntimeError("empty_response")
        return content.strip()
    except openai.AuthenticationError:
        raise RuntimeError("bad_key")
    except openai.RateLimitError:
        raise RuntimeError("rate_limit")
    except openai.APIConnectionError:
        raise RuntimeError("connection_error")
    except openai.APIError as e:
        raise RuntimeError("api_error") from e


# ---------------------------------------------------------------------------
# Safe wrapper used by the router
# ---------------------------------------------------------------------------

def try_llm_enhance(user_message: str, context_summary: str = "") -> str:
    """Call the provider; configuration and connection failures remain explicit."""
    return call_llm(user_message, context_summary)
