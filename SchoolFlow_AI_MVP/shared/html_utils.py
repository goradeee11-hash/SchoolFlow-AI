"""Helpers for safely displaying untrusted text in HTML."""

from html import escape


def escape_html(value: object) -> str:
    """Escape a value for insertion into HTML text or a quoted attribute."""
    return escape(str(value), quote=True)
