"""Optional, Windows-user-protected storage for a synthetic local demo."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import tempfile

import pandas as pd

from app_logic import OPTIONAL_NAME_COL, REQUIRED, build_outputs, validate
from shared.supabase_backend import _dataframe_records, _json_safe

_HEADER = b"SchoolFlowSyntheticDemo\x00\x01"
_LIST_KEYS = (
    "lesson_records", "participation_log", "skill_definitions",
    "skill_assessments", "interventions", "intervention_checkpoints",
    "question_library",
)


class DemoStorageError(ValueError):
    """Local demo storage failed or was changed by another session."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _protect(data: bytes, *, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise DemoStorageError("Encrypted demo storage is available only on Windows.")
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = _DataBlob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    func.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    func.restype = wintypes.BOOL
    if not func(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise DemoStorageError(f"Windows data protection failed: {ctypes.WinError(ctypes.get_last_error())}")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel.LocalFree(output.pbData)


def demo_path() -> Path:
    if os.name != "nt" or not os.environ.get("LOCALAPPDATA"):
        raise DemoStorageError("Windows local application storage is unavailable.")
    return Path(os.environ["LOCALAPPDATA"]) / "SchoolFlowAI" / "synthetic-demo.dat"


def reviewer_demo_path() -> Path:
    return demo_path().with_name("synthetic-reviewer-demo.dat")


def snapshot(state) -> dict:
    """Keep only educational demo data; never save credentials, chat or audit events."""
    data = {key: _json_safe(state.get(key, [])) for key in _LIST_KEYS}
    data["lesson_draft"] = _json_safe(state.get("lesson_draft", {}))
    data["source_rows"] = (
        _dataframe_records(state["source_rows"]) if "source_rows" in state else None
    )
    return data


def snapshot_digest(data: dict) -> str:
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def restore_snapshot(state, data: dict) -> None:
    if not isinstance(data, dict) or set(data) != {*_LIST_KEYS, "lesson_draft", "source_rows"}:
        raise DemoStorageError("The saved demo workspace has an invalid structure.")
    if any(not isinstance(data[key], list) or not all(isinstance(item, dict) for item in data[key]) for key in _LIST_KEYS):
        raise DemoStorageError("The saved demo workspace contains invalid records.")
    if not isinstance(data["lesson_draft"], dict):
        raise DemoStorageError("The saved lesson draft is invalid.")
    rows = data["source_rows"]
    derived = None
    if rows is not None:
        if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
            raise DemoStorageError("The saved demo import is invalid.")
        frame = pd.DataFrame(rows)
        if any(column not in frame.columns for column in REQUIRED):
            raise DemoStorageError("The saved demo import is missing required columns.")
        issues = validate(frame)
        if not issues.empty and issues["Blocking"].any():
            raise DemoStorageError("The saved demo import contains invalid records.")
        has_name = OPTIONAL_NAME_COL in frame.columns
        clean, summary, weekly = build_outputs(frame, has_name)
        derived = (frame, clean, summary, weekly, has_name, issues)

    for key in _LIST_KEYS:
        state[key] = data[key]
    state["lesson_draft"] = data["lesson_draft"]
    state["lesson_active"] = bool(data["lesson_draft"].get("lesson_id"))
    if derived is None:
        for key in ("source_rows", "clean", "summary", "weekly", "has_name", "issues"):
            state.pop(key, None)
    else:
        for key, value in zip(
            ("source_rows", "clean", "summary", "weekly", "has_name", "issues"), derived
        ):
            state[key] = value


def load_demo(path: Path) -> tuple[dict, str] | None:
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
        if not raw.startswith(_HEADER):
            raise DemoStorageError("The local demo file has an unrecognized format; it was not changed.")
        data = json.loads(_protect(raw[len(_HEADER):], decrypt=True).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DemoStorageError(f"Could not read the encrypted demo workspace: {error}") from error
    return data, hashlib.sha256(raw).hexdigest()


def save_demo(path: Path, data: dict, expected_file_digest: str | None) -> str:
    """Encrypt and atomically save only if no other session has changed the file."""
    if os.name != "nt":
        raise DemoStorageError("Encrypted demo storage is available only on Windows.")
    import msvcrt

    try:
        restore_snapshot({}, data)
        encoded = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        raw = _HEADER + _protect(encoded)
        path.parent.mkdir(parents=True, exist_ok=True)
        with (path.parent / "synthetic-demo.lock").open("a+b") as lock:
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise DemoStorageError("Another session is saving the demo workspace; retry.") from error
            try:
                current = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
                if current != expected_file_digest:
                    raise DemoStorageError("The saved demo was changed by another session; your changes were not overwritten.")
                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
                        temp_path = Path(temp.name)
                        temp.write(raw)
                        temp.flush()
                        os.fsync(temp.fileno())
                    os.replace(temp_path, path)
                finally:
                    if temp_path is not None and temp_path.exists():
                        temp_path.unlink(missing_ok=True)
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    except (OSError, TypeError, ValueError) as error:
        if isinstance(error, DemoStorageError):
            raise
        raise DemoStorageError(f"Could not save the encrypted demo workspace: {error}") from error
    return hashlib.sha256(raw).hexdigest()
