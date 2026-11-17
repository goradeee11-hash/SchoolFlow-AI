"""
shared/skills.py
----------------
Pure-Python logic for the Skills & Academic Progress Tracking system.

Design rules
------------
* No Streamlit imports — all functions are fully testable offline.
* Academic attainment is SEPARATE from class participation.
  - Skill mastery is computed only from explicit assessment scores.
  - Participation response codes (C/P/I) are shown as contextual evidence,
    never converted into an academic grade or mastery level.
* No grade or mastery level is inferred from a single assessment.
* When fewer than MIN_ASSESSMENTS_FOR_MASTERY assessments exist for a skill,
  mastery is reported as None (displayed as N/A).
* Mastery levels are computed from numeric scores only; they are NOT fixed
  student labels and change as more data is added.
* No MTSS tier is assigned from this module.

Data structures
---------------
Skill definition (dict):
    id          : str  — unique slug (e.g. "inference")
    name        : str  — display name (e.g. "Reading Inference")
    subject     : str  — e.g. "English Language"
    grade       : str  — e.g. "Grade 5"
    description : str  — optional free text
    objectives  : list[str]  — optional learning objectives

Skill assessment record (dict):
    skill_id      : str   — references skill definition id
    student_code  : str
    lesson_id     : str   — links to lesson_records (optional, may be "")
    date          : str   — ISO date string (YYYY-MM-DD)
    score         : float — numeric score (0.0 – max_score)
    max_score     : float — maximum possible score for this assessment
    notes         : str   — optional teacher notes (no auto-inference)
    created_at    : str   — ISO timestamp
"""

from __future__ import annotations

import math
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from numbers import Real

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimum number of assessments required before reporting a mastery level.
#: Below this threshold we return None (shown as N/A).
MIN_ASSESSMENTS_FOR_MASTERY = 2

#: Mastery level thresholds (percentage of max_score, inclusive lower bound).
#: These are interpretive bands — not fixed student labels.
MASTERY_BANDS = [
    (80.0, "Secure",      "راسخ"),
    (60.0, "Developing",  "في تطور"),
    (40.0, "Emerging",    "بدايات"),
    (0.0,  "Beginning",   "بداية"),
]

# ---------------------------------------------------------------------------
# Skill definition helpers
# ---------------------------------------------------------------------------

def make_skill_id(name: str) -> str:
    """
    Generate a URL-safe slug from a skill name.

    >>> make_skill_id("Reading Inference")
    'reading_inference'
    """
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "skill"


def new_skill(
    name: str,
    subject: str = "",
    grade: str = "",
    description: str = "",
    objectives: list[str] | None = None,
    skill_id: str | None = None,
) -> dict:
    """
    Build a new skill definition dict.

    Parameters
    ----------
    name        : Display name (required, non-empty).
    subject     : Subject area (e.g. "English Language").
    grade       : Grade level (e.g. "Grade 5").
    description : Optional description.
    objectives  : Optional list of learning objective strings.
    skill_id    : Override auto-generated id (must be unique in the store).

    Raises
    ------
    ValueError if name is empty.
    """
    name = name.strip()
    if not name:
        raise ValueError("Skill name must not be empty.")
    return {
        "id":          skill_id or make_skill_id(name),
        "name":        name,
        "subject":     subject.strip(),
        "grade":       grade.strip(),
        "description": description.strip(),
        "objectives":  list(objectives) if objectives else [],
    }


def add_skill(skill_definitions: list[dict], skill: dict) -> list[dict]:
    """
    Return a new list with the skill appended.
    Raises ValueError if a skill with the same id already exists.
    """
    existing_ids = {s["id"] for s in skill_definitions}
    if skill["id"] in existing_ids:
        raise ValueError(
            f"A skill with id {skill['id']!r} already exists. "
            "Choose a different name or provide an explicit skill_id."
        )
    return skill_definitions + [skill]


def remove_skill(skill_definitions: list[dict], skill_id: str) -> list[dict]:
    """Return a new list with the skill removed (no error if not found)."""
    return [s for s in skill_definitions if s["id"] != skill_id]


def get_skill(skill_definitions: list[dict], skill_id: str) -> dict | None:
    """Return the skill definition with the given id, or None."""
    for s in skill_definitions:
        if s["id"] == skill_id:
            return s
    return None


def resolve_participation_skill_id(
    entry: dict,
    skill_definitions: list[dict],
) -> str | None:
    """Resolve a participation link without rewriting legacy records."""
    skill_map = {
        skill["id"]: skill
        for skill in skill_definitions
        if isinstance(skill, dict)
        and isinstance(skill.get("id"), str)
        and skill["id"].strip()
    }
    if not isinstance(entry, dict):
        return None
    recorded_id = entry.get("skill_id")
    if recorded_id not in (None, ""):
        if not isinstance(recorded_id, str):
            return None
        skill_id = recorded_id.strip()
        return skill_id if skill_id in skill_map else None

    legacy_name = entry.get("skill")
    if not isinstance(legacy_name, str) or not legacy_name.strip():
        return None
    normalized_name = legacy_name.strip().casefold()
    matches = [
        skill["id"]
        for skill in skill_map.values()
        if isinstance(skill.get("name"), str)
        and skill["name"].strip().casefold() == normalized_name
    ]
    return matches[0] if len(matches) == 1 else None


def skills_for_subject_grade(
    skill_definitions: list[dict],
    subject: str = "",
    grade: str = "",
) -> list[dict]:
    """
    Filter skill definitions by subject and/or grade.
    Empty string means "any" (no filter applied for that field).
    """
    result = skill_definitions
    if subject:
        result = [s for s in result if s.get("subject", "") == subject]
    if grade:
        result = [s for s in result if s.get("grade", "") == grade]
    return result


# ---------------------------------------------------------------------------
# Assessment record helpers
# ---------------------------------------------------------------------------

def _validated_assessment_scores(score: object, max_score: object) -> tuple[float, float]:
    values = []
    for value, name in ((score, "score"), (max_score, "max_score")):
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a finite number.")
        try:
            number = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a finite number.") from exc
        if not math.isfinite(number):
            raise ValueError(f"{name} must be a finite number.")
        values.append(number)

    score, max_score = values
    if max_score <= 0:
        raise ValueError("max_score must be greater than 0.")
    if score < 0:
        raise ValueError("score must be >= 0.")
    if score > max_score:
        raise ValueError("score must not exceed max_score.")
    return score, max_score


def new_assessment(
    skill_id: str,
    student_code: str,
    score: float,
    max_score: float,
    date: str = "",
    lesson_id: str = "",
    notes: str = "",
    _now: str | None = None,
) -> dict:
    """
    Build a new skill assessment record.

    Parameters
    ----------
    skill_id     : References a skill definition id.
    student_code : Student identifier.
    score        : Numeric score achieved.
    max_score    : Maximum possible score (must be > 0).
    date         : ISO date string; defaults to today.
    lesson_id    : Optional lesson_id link (from lesson_records).
    notes        : Optional teacher notes — no inference made from this.
    _now         : ISO timestamp override (for testing).

    Raises
    ------
    ValueError if scores are non-finite or outside the valid range.
    """
    score, max_score = _validated_assessment_scores(score, max_score)

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    return {
        "id":           uuid.uuid4().hex,
        "skill_id":     skill_id,
        "student_code": student_code,
        "score":        float(score),
        "max_score":    float(max_score),
        "date":         date,
        "lesson_id":    lesson_id,
        "notes":        notes.strip(),
        "created_at":   _now if _now is not None else datetime.now(timezone.utc).isoformat(),
    }


def student_assessments(
    assessment_records: list[dict],
    student_code: str,
    skill_id: str = "",
) -> list[dict]:
    """
    Return all assessment records for a student, optionally filtered by skill.
    Results are sorted by date ascending (oldest first).
    """
    result = [
        r for r in assessment_records
        if r.get("student_code") == student_code
    ]
    if skill_id:
        result = [r for r in result if r.get("skill_id") == skill_id]
    return sorted(result, key=lambda r: r.get("date", ""))


# ---------------------------------------------------------------------------
# Mastery calculation — academic attainment only
# ---------------------------------------------------------------------------

def compute_skill_mastery(
    assessments: list[dict],
) -> dict:
    """
    Compute mastery statistics from a list of assessment records for ONE
    student × ONE skill.

    Parameters
    ----------
    assessments : List of assessment dicts (all for the same student + skill).
                  Must be pre-filtered by caller.

    Returns
    -------
    dict with keys:
        "count"          : int   — number of assessments
        "mean_pct"       : float | None — mean percentage score (0–100), or None
        "latest_pct"     : float | None — most recent percentage score, or None
        "trend"          : str   — "improving" / "declining" / "stable" / "N/A"
        "mastery_level"  : str | None — band name in English, or None if < MIN
        "mastery_level_ar": str | None — band name in Arabic, or None if < MIN
        "needs_support"  : bool  — True when mastery_level in {"Beginning", "Emerging"}
        "scores_pct"     : list[float] — chronological percentage scores
        "dates"          : list[str]   — corresponding dates

    Rules enforced
    --------------
    * mastery_level is None when count < MIN_ASSESSMENTS_FOR_MASTERY.
    * No single assessment triggers a mastery classification.
    * Trend requires ≥ 2 assessments; computed from first to last percentage.
    * "needs_support" is False when mastery_level is None (insufficient data).
    """
    validated_assessments = []
    for record in assessments:
        if not isinstance(record, dict):
            raise ValueError("each assessment record must be a dict.")
        score, max_score = _validated_assessment_scores(
            record.get("score"), record.get("max_score")
        )
        validated_assessments.append((record, score, max_score))

    n = len(validated_assessments)
    if n == 0:
        return {
            "count": 0,
            "mean_pct": None,
            "latest_pct": None,
            "trend": "N/A",
            "mastery_level": None,
            "mastery_level_ar": None,
            "needs_support": False,
            "scores_pct": [],
            "dates": [],
        }

    sorted_ass = sorted(
        validated_assessments,
        key=lambda item: item[0].get("date", ""),
    )

    scores_pct = [
        round(score / max_score * 100, 1)
        for _, score, max_score in sorted_ass
    ]
    dates = [record.get("date", "") for record, _, _ in sorted_ass]

    mean_pct   = round(sum(scores_pct) / n, 1)
    latest_pct = scores_pct[-1]

    # Trend (requires ≥ 2 assessments)
    if n < 2:
        trend = "N/A"
    else:
        delta = scores_pct[-1] - scores_pct[0]
        if delta >= 5.0:
            trend = "improving"
        elif delta <= -5.0:
            trend = "declining"
        else:
            trend = "stable"

    # Mastery level (requires MIN_ASSESSMENTS_FOR_MASTERY)
    if n < MIN_ASSESSMENTS_FOR_MASTERY:
        mastery_en = None
        mastery_ar = None
    else:
        mastery_en = mastery_ar = None
        for threshold, band_en, band_ar in MASTERY_BANDS:
            if mean_pct >= threshold:
                mastery_en = band_en
                mastery_ar = band_ar
                break

    needs_support = mastery_en in {"Beginning", "Emerging"} if mastery_en else False

    return {
        "count":            n,
        "mean_pct":         mean_pct,
        "latest_pct":       latest_pct,
        "trend":            trend,
        "mastery_level":    mastery_en,
        "mastery_level_ar": mastery_ar,
        "needs_support":    needs_support,
        "scores_pct":       scores_pct,
        "dates":            dates,
    }


def student_skills_summary(
    student_code: str,
    skill_definitions: list[dict],
    assessment_records: list[dict],
    participation_log: list[dict],
) -> list[dict]:
    """
    Build a per-skill progress summary for one student.

    For each skill that has at least one assessment OR participation entry:
    - Compute mastery from assessment records.
    - Count participation evidence per response code (contextual only).
    - Return structured rows suitable for display.

    Parameters
    ----------
    student_code      : Student identifier.
    skill_definitions : Full list of skill definition dicts.
    assessment_records: Full list of assessment record dicts.
    participation_log : Full list of participation entry dicts.

    Returns
    -------
    list[dict], one entry per relevant skill, with keys:
        "skill_id"         : str | None
        "skill_name"       : str
        "skill_linked"     : bool
        "subject"          : str
        "grade"            : str
        "mastery"          : dict (from compute_skill_mastery)
        "participation_c"  : int  — Correct participation entries
        "participation_p"  : int  — Partial participation entries
        "participation_i"  : int  — Incorrect participation entries
        "participation_nr" : int  — No Response entries
        "participation_no" : int  — No Opportunity entries
        "has_assessments"  : bool
        "has_participation": bool

    Rules
    -----
    * Participation counts are NEVER used to compute mastery.
    * A skill with only participation evidence (no assessments) shows mastery=None.
    """
    # Find all skill_ids relevant to this student
    assessed_ids = {
        r["skill_id"] for r in assessment_records
        if r.get("student_code") == student_code
    }
    skill_map = {s["id"]: s for s in skill_definitions}
    participation_by_skill: dict[str, list[dict]] = {}
    unlinked_participation: dict[str, list[dict]] = {}
    unlinked_labels: dict[str, str] = {}
    for entry in participation_log:
        if entry.get("student_code") != student_code:
            continue
        skill_id = resolve_participation_skill_id(entry, skill_definitions)
        if skill_id is not None:
            participation_by_skill.setdefault(skill_id, []).append(entry)
            continue
        legacy_name = entry.get("skill")
        if isinstance(legacy_name, str) and legacy_name.strip():
            label = legacy_name.strip()
            label_key = label.casefold()
            unlinked_labels.setdefault(label_key, label)
            unlinked_participation.setdefault(label_key, []).append(entry)

    # Participation contributes context only and never creates skill definitions.
    all_relevant_ids = assessed_ids | (set(participation_by_skill) & set(skill_map))

    rows = []

    for sid in sorted(all_relevant_ids):
        skill = skill_map.get(sid, {"id": sid, "name": sid, "subject": "", "grade": ""})
        ass = student_assessments(assessment_records, student_code, skill_id=sid)
        mastery = compute_skill_mastery(ass)

        # Participation breakdown (contextual, not used for mastery)
        part_entries = participation_by_skill.get(sid, [])
        counts = {"C": 0, "P": 0, "I": 0, "NR": 0, "NO": 0}
        for e in part_entries:
            rc = e.get("response_code", "")
            if rc in counts:
                counts[rc] += 1

        rows.append({
            "skill_id":          sid,
            "skill_name":        skill.get("name", sid),
            "skill_linked":      sid in skill_map,
            "subject":           skill.get("subject", ""),
            "grade":             skill.get("grade", ""),
            "mastery":           mastery,
            "participation_c":   counts["C"],
            "participation_p":   counts["P"],
            "participation_i":   counts["I"],
            "participation_nr":  counts["NR"],
            "participation_no":  counts["NO"],
            "has_assessments":   len(ass) > 0,
            "has_participation": len(part_entries) > 0,
        })

    # Keep unmatched legacy labels visible without treating them as skill IDs.
    for label_key in sorted(unlinked_participation):
        name = unlinked_labels[label_key]
        part_entries = unlinked_participation[label_key]
        counts = {"C": 0, "P": 0, "I": 0, "NR": 0, "NO": 0}
        for e in part_entries:
            rc = e.get("response_code", "")
            if rc in counts:
                counts[rc] += 1

        rows.append({
            "skill_id":          None,
            "skill_name":        name,
            "skill_linked":      False,
            "subject":           "",
            "grade":             "",
            "mastery":           compute_skill_mastery([]),
            "participation_c":   counts["C"],
            "participation_p":   counts["P"],
            "participation_i":   counts["I"],
            "participation_nr":  counts["NR"],
            "participation_no":  counts["NO"],
            "has_assessments":   False,
            "has_participation": len(part_entries) > 0,
        })

    return rows


def class_skills_overview(
    student_codes: list[str],
    skill_definitions: list[dict],
    assessment_records: list[dict],
) -> pd.DataFrame:
    """
    Build a class-level overview DataFrame: one row per student × skill,
    showing count of assessments and mean mastery percentage.

    Returns empty DataFrame if no assessments exist.
    Participation is NOT included (this is academic data only).
    """
    if not assessment_records or not skill_definitions:
        return pd.DataFrame(columns=[
            "Student code", "Skill", "Assessments", "Mean %",
            "Latest %", "Trend", "Mastery Level",
        ])

    skill_map = {s["id"]: s["name"] for s in skill_definitions}
    rows = []
    for code in student_codes:
        for skill in skill_definitions:
            ass = student_assessments(assessment_records, code, skill_id=skill["id"])
            if not ass:
                continue
            m = compute_skill_mastery(ass)
            rows.append({
                "Student code":  code,
                "Skill":         skill["name"],
                "Assessments":   m["count"],
                "Mean %":        m["mean_pct"],
                "Latest %":      m["latest_pct"],
                "Trend":         m["trend"],
                "Mastery Level": m["mastery_level"] or "N/A",
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "Student code", "Skill", "Assessments", "Mean %",
        "Latest %", "Trend", "Mastery Level",
    ])
