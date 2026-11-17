"""Provider interface for fixed, synthetic teaching examples."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Protocol


TEMPLATES = {
    "lesson": "In Arabic, prepare a short fictional lesson plan on fractions for a generic class.",
    "bloom": "In Arabic, give six generic questions about fractions, one for each Bloom level.",
    "gagne": "In Arabic, outline the nine Gagne instructional events for a fictional fractions lesson.",
}
_DEFAULT_MODEL = "gemini-2.5-flash"


class SyntheticProvider(Protocol):
    def generate(self, template_id: str) -> str: ...


def _gemini_config() -> tuple[str | None, str]:
    try:
        import streamlit as st
        section = st.secrets.get("gemini", {})
        return section.get("api_key"), section.get("model", _DEFAULT_MODEL)
    except (ImportError, FileNotFoundError):
        return None, _DEFAULT_MODEL


def _reserve_request() -> None:
    """Reserve an attempt across local processes; fail closed if storage fails."""
    location = os.environ.get("LOCALAPPDATA")
    if not location:
        raise RuntimeError("quota_unavailable")
    try:
        directory = Path(location) / "SchoolFlowAI"
        directory.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(directory / "gemini-demo-quota.sqlite3", timeout=5) as db:
            db.execute("CREATE TABLE IF NOT EXISTS attempts (requested_at REAL NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            minute = db.execute(
                "SELECT COUNT(*) FROM attempts WHERE requested_at >= ?", (now - 60,)
            ).fetchone()[0]
            day = db.execute(
                "SELECT COUNT(*) FROM attempts WHERE requested_at >= ?", (now - 86400,)
            ).fetchone()[0]
            if minute >= 5 or day >= 20:
                raise RuntimeError("local_rate_limit")
            db.execute("INSERT INTO attempts (requested_at) VALUES (?)", (now,))
    except (OSError, sqlite3.Error):
        raise RuntimeError("quota_unavailable") from None


class GeminiProvider:
    def generate(self, template_id: str) -> str:
        prompt = TEMPLATES.get(template_id)
        if prompt is None:
            raise RuntimeError("invalid_template")
        key, model = _gemini_config()
        if not key:
            raise RuntimeError("no_key")
        try:
            from google import genai
            from google.genai import errors, types
            import httpx2
        except ImportError:
            raise RuntimeError("no_package") from None

        _reserve_request()
        try:
            client = genai.Client(
                api_key=key,
                http_options=types.HttpOptions(
                    timeout=15000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=512,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            text = response.text
        except errors.APIError as error:
            if error.code == 429:
                raise RuntimeError("rate_limit") from None
            if error.code in (401, 403):
                raise RuntimeError("bad_key") from None
            raise RuntimeError("api_error") from None
        except (httpx2.TransportError, OSError):
            raise RuntimeError("connection_error") from None
        except ValueError:
            raise RuntimeError("api_error") from None
        if not text or not text.strip():
            raise RuntimeError("empty_response")
        return text.strip()


class OpenAIProvider:
    def generate(self, template_id: str) -> str:
        prompt = TEMPLATES.get(template_id)
        if prompt is None:
            raise RuntimeError("invalid_template")
        from assistant.llm_client import call_llm
        return call_llm(prompt)


_PROVIDERS: dict[str, type[SyntheticProvider]] = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
}


def generate_synthetic_template(template_id: str, provider: str = "gemini") -> str:
    provider_class = _PROVIDERS.get(provider)
    if provider_class is None:
        raise RuntimeError("unsupported_provider")
    if os.environ.get("SCHOOLFLOW_SHARED_DEMO") == "1" and provider != "gemini":
        raise RuntimeError("shared_demo_disabled")
    return provider_class().generate(template_id)
