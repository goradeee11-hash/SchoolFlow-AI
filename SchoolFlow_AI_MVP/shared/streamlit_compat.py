"""Compatibility helpers for Streamlit widget APIs."""

from functools import lru_cache
from importlib.metadata import version

from packaging.version import Version


@lru_cache(maxsize=1)
def _supports_stretch_width() -> bool:
    # Dataframes support the "stretch" width from Streamlit 1.49.
    return Version(version("streamlit")) >= Version("1.49.0")


def full_width() -> dict[str, str | bool]:
    if _supports_stretch_width():
        return {"width": "stretch"}
    return {"use_container_width": True}
