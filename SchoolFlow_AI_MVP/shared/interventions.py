"""
shared/interventions.py
------------------------
Pure-Python logic for the Student Interventions & Recommendations system
(SchoolFlow AI — Task 7).

Design rules
------------
* No Streamlit imports — all functions are fully testable offline.
* The teacher is ALWAYS the decision-maker.  This module only:
    - Flags skills that may need attention (based on academic data).
    - Proposes intervention records for teacher review.
    - Tracks status through a teacher-controlled lifecycle.
    - Never automatically approves, starts, or completes anything.
* Academic evidence gate:
    - A flag/proposal is only raised when there are ≥ MIN_ASSESSMENTS_FOR_FLAG
      assessment records for the skill (default: 2 — same as mastery threshold).
    - Participation data alone NEVER triggers a flag.
    - A declining trend alone does NOT trigger a flag unless mastery is also low.
* MTSS tiers describe support intensity, NOT permanent student identity:
    - Tier 1 — Universal classroom support (whole-class strategy).
    - Tier 2 — Targeted small-group support.
    - Tier 3 — Intensive individual support.
    - Tier 0 is used when no MTSS assignment is yet made (teacher decides).
* No diagnosis or clinical judgement is produced.
* When data is absent, N/A / None is returned — nothing is fabricated.
* Intervention status lifecycle (teacher-controlled only):
    Proposed → Approved → In Progress → Completed
    Any status can also be set to Dismissed by the teacher.

Intervention record (dict)
--------------------------
    id               : str   — unique identifier (auto-generated UUID-style)
    student_code     : str
    skill_id         : str   — references skill definition id
    skill_name       : str   — display name snapshot
    reason           : str   — teacher-written or auto-suggested reason (editable)
    proposed_action  : str   — suggested activity / strategy (teacher editable)
    mtss_tier        : int   — 0 = unset, 1/2/3 = tier (teacher sets)
    status           : str   — "Proposed" | "Approved" | "In Progress"
                               | "Completed" | "Dismissed"
    start_date       : str   — ISO date (YYYY-MM-DD), set when teacher approves
    end_date         : str   — ISO date (optional, teacher sets)
    teacher_notes    : str   — free-text notes
    created_at       : str   — ISO timestamp
    updated_at       : str   — ISO timestamp
    evidence_snapshot: dict  — mastery/trend at time of creation (read-only after)

Progress checkpoint (dict)
--------------------------
    intervention_id  : str
    student_code     : str
    skill_id         : str
    date             : str   — ISO date
    score            : float
    max_score        : float
    notes            : str
    created_at       : str
"""

from __future__ import annotations

from copy import deepcopy

import uuid
from datetime import datetime, timezone

from shared.time_utils import timestamp_sort_key

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimum assessments before a skill may be flagged for intervention.
#: Below this, we do not raise any flag (insufficient evidence).
MIN_ASSESSMENTS_FOR_FLAG = 2

#: Mastery bands that qualify as needing potential support.
SUPPORT_MASTERY_LEVELS = {"Beginning", "Emerging"}

#: Valid status values — ordered by lifecycle.
INTERVENTION_STATUSES = ["Proposed", "Approved", "In Progress", "Completed", "Dismissed"]

#: MTSS tier descriptions.
MTSS_TIERS = {
    0: ("Not set",          "غير محدد"),
    1: ("Tier 1 — Universal","المستوى 1 — دعم عام"),
    2: ("Tier 2 — Targeted", "المستوى 2 — دعم موجَّه"),
    3: ("Tier 3 — Intensive","المستوى 3 — دعم مكثَّف"),
}

#: Suggested activities keyed by mastery level.
#: These are STARTING POINTS only — the teacher always edits before approving.
SUGGESTED_ACTIVITIES: dict[str, list[str]] = {
    "Beginning": [
        "One-to-one teacher modelling of the skill",
        "Structured scaffolding worksheet with worked examples",
        "Daily 5-minute targeted practice with immediate feedback",
    ],
    "Emerging": [
        "Small-group re-teaching with guided practice",
        "Partner reading or peer explanation activity",
        "Targeted homework task with teacher check-in",
    ],
    "Developing": [
        "Independent practice with self-assessment checklist",
        "Extension task at current level before moving on",
    ],
    "Secure": [],   # No intervention suggested for Secure mastery
}


# ---------------------------------------------------------------------------
# Identifier generation
# ---------------------------------------------------------------------------

def _new_id() -> str:
    """Return a short unique identifier based on UUID4."""
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Intervention record creation
# ---------------------------------------------------------------------------

def new_intervention(
    student_code: str,
    skill_id: str,
    skill_name: str,
    reason: str,
    proposed_action: str,
    evidence_snapshot: dict | None = None,
    mtss_tier: int = 0,
    start_date: str = "",
    end_date: str = "",
    teacher_notes: str = "",
    _now: str | None = None,
    _id: str | None = None,
) -> dict:
    """
    Build a new intervention record.

    Parameters
    ----------
    student_code    : Student identifier.
    skill_id        : Skill definition id this intervention targets.
    skill_name      : Human-readable skill name (snapshot at creation).
    reason          : Why this intervention is proposed (teacher-editable text).
    proposed_action : Suggested activity or strategy (teacher-editable).
    evidence_snapshot: Mastery dict at creation time (from compute_skill_mastery).
    mtss_tier       : 0 = not yet set by teacher; 1/2/3 = MTSS tier.
    start_date      : ISO date string; empty until teacher approves.
    end_date        : ISO date string; optional.
    teacher_notes   : Free-text notes.
    _now            : ISO timestamp override (for testing).
    _id             : ID override (for testing).

    Returns
    -------
    dict — intervention record.

    Rules enforced
    --------------
    * Status is always initialised to "Proposed" — teacher must act to change it.
    * mtss_tier must be 0, 1, 2, or 3.
    * student_code and skill_id must be non-empty strings.
    """
    student_code = student_code.strip()
    skill_id     = skill_id.strip()
    if not student_code:
        raise ValueError("student_code must not be empty.")
    if not skill_id:
        raise ValueError("skill_id must not be empty.")
    if mtss_tier not in MTSS_TIERS:
        raise ValueError(f"mtss_tier must be one of {list(MTSS_TIERS.keys())}.")

    ts = _now if _now is not None else datetime.now(timezone.utc).isoformat()
    return {
        "id":                _id if _id is not None else _new_id(),
        "student_code":      student_code,
        "skill_id":          skill_id,
        "skill_name":        skill_name.strip(),
        "reason":            reason.strip(),
        "proposed_action":   proposed_action.strip(),
        "mtss_tier":         mtss_tier,
        "status":            "Proposed",
        "start_date":        start_date.strip(),
        "end_date":          end_date.strip(),
        "teacher_notes":     teacher_notes.strip(),
        "created_at":        ts,
        "updated_at":        ts,
        "evidence_snapshot": (
            deepcopy(evidence_snapshot) if evidence_snapshot is not None else {}
        ),
    }


def update_intervention(
    record: dict,
    status: str | None = None,
    mtss_tier: int | None = None,
    proposed_action: str | None = None,
    reason: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    teacher_notes: str | None = None,
    _now: str | None = None,
) -> dict:
    """
    Return a NEW dict that is a copy of *record* with the requested fields updated.
    Does NOT mutate the original record.

    Parameters
    ----------
    status          : New status value (must be in INTERVENTION_STATUSES).
    mtss_tier       : New MTSS tier (0–3).
    proposed_action : Updated proposed action text.
    reason          : Updated reason text.
    start_date      : Updated start date string.
    end_date        : Updated end date string.
    teacher_notes   : Updated notes.
    _now            : Timestamp override for testing.

    Raises
    ------
    ValueError for invalid status or mtss_tier values.
    """
    if status is not None and status not in INTERVENTION_STATUSES:
        raise ValueError(
            f"status must be one of {INTERVENTION_STATUSES}. Got {status!r}."
        )
    if mtss_tier is not None and mtss_tier not in MTSS_TIERS:
        raise ValueError(
            f"mtss_tier must be one of {list(MTSS_TIERS.keys())}."
        )

    updated = dict(record)
    if "evidence_snapshot" in updated:
        updated["evidence_snapshot"] = deepcopy(updated["evidence_snapshot"])
    if status is not None:
        updated["status"] = status
    if mtss_tier is not None:
        updated["mtss_tier"] = mtss_tier
    if proposed_action is not None:
        updated["proposed_action"] = proposed_action.strip()
    if reason is not None:
        updated["reason"] = reason.strip()
    if start_date is not None:
        updated["start_date"] = start_date.strip()
    if end_date is not None:
        updated["end_date"] = end_date.strip()
    if teacher_notes is not None:
        updated["teacher_notes"] = teacher_notes.strip()

    ts = _now if _now is not None else datetime.now(timezone.utc).isoformat()
    updated["updated_at"] = ts
    return updated


# ---------------------------------------------------------------------------
# Intervention store helpers
# ---------------------------------------------------------------------------

def add_intervention(
    interventions: list[dict],
    record: dict,
) -> list[dict]:
    """
    Return a new list with the intervention appended.
    Raises ValueError if an active (non-Dismissed, non-Completed) intervention
    already exists for the same student_code × skill_id.
    """
    for existing in interventions:
        if (
            existing["student_code"] == record["student_code"]
            and existing["skill_id"] == record["skill_id"]
            and existing["status"] not in {"Completed", "Dismissed"}
        ):
            raise ValueError(
                f"An active intervention for student '{record['student_code']}' "
                f"and skill '{record['skill_id']}' already exists "
                f"(status: {existing['status']!r}). "
                "Complete or dismiss it before adding a new one."
            )
    return interventions + [record]


def replace_intervention(
    interventions: list[dict],
    updated_record: dict,
) -> list[dict]:
    """
    Return a new list where the record with the same id as *updated_record*
    is replaced. Raises ValueError if not found or if evidence_snapshot changes.
    Does NOT mutate the input list.
    """
    new_list = []
    found = False
    for rec in interventions:
        if rec["id"] == updated_record["id"]:
            has_original_snapshot = "evidence_snapshot" in rec
            has_updated_snapshot = "evidence_snapshot" in updated_record
            if (
                has_original_snapshot != has_updated_snapshot
                or (
                    has_original_snapshot
                    and rec["evidence_snapshot"] != updated_record["evidence_snapshot"]
                )
            ):
                raise ValueError(
                    "evidence_snapshot cannot be changed after intervention creation."
                )
            replacement = dict(updated_record)
            if has_original_snapshot:
                replacement["evidence_snapshot"] = deepcopy(
                    rec["evidence_snapshot"]
                )
            new_list.append(replacement)
            found = True
        else:
            new_list.append(rec)
    if not found:
        raise ValueError(
            f"Intervention id {updated_record['id']!r} not found."
        )
    return new_list


def get_intervention(interventions: list[dict], intervention_id: str) -> dict | None:
    """Return the intervention with the given id, or None."""
    for rec in interventions:
        if rec["id"] == intervention_id:
            return rec
    return None


def student_interventions(
    interventions: list[dict],
    student_code: str,
    status_filter: list[str] | None = None,
) -> list[dict]:
    """
    Return all interventions for a student, optionally filtered by status list.
    Sorted by created_at descending (most recent first).
    """
    result = [r for r in interventions if r["student_code"] == student_code]
    if status_filter:
        result = [r for r in result if r["status"] in status_filter]
    return sorted(
        result,
        key=lambda r: timestamp_sort_key(r.get("created_at", "")),
        reverse=True,
    )


def active_interventions(interventions: list[dict]) -> list[dict]:
    """Return all interventions with status not in {Completed, Dismissed}."""
    return [r for r in interventions if r["status"] not in {"Completed", "Dismissed"}]


# ---------------------------------------------------------------------------
# Auto-flag logic — academic data only
# ---------------------------------------------------------------------------

def flag_students_for_intervention(
    student_codes: list[str],
    skill_definitions: list[dict],
    assessment_records: list[dict],
    existing_interventions: list[dict],
) -> list[dict]:
    """
    Scan all students × skills and return a list of FLAG dicts for cases
    where the data suggests a student may benefit from additional support.

    A flag is raised ONLY when ALL of the following are true:
      1. ≥ MIN_ASSESSMENTS_FOR_FLAG assessment records exist for this student × skill.
      2. The computed mastery_level is in SUPPORT_MASTERY_LEVELS
         (i.e. "Beginning" or "Emerging").
      3. No active (non-Completed, non-Dismissed) intervention already exists
         for this student × skill.

    Participation data is NOT used here.

    Parameters
    ----------
    student_codes         : List of all student codes to scan.
    skill_definitions     : Full list of skill definition dicts.
    assessment_records    : Full list of assessment record dicts.
    existing_interventions: Existing intervention records to avoid duplicates.

    Returns
    -------
    list[dict], each with keys:
        "student_code"      : str
        "skill_id"          : str
        "skill_name"        : str
        "mastery_level"     : str  — "Beginning" | "Emerging"
        "mastery_level_ar"  : str
        "mean_pct"          : float
        "latest_pct"        : float
        "trend"             : str
        "assessment_count"  : int
        "suggested_action"  : str  — first item from SUGGESTED_ACTIVITIES (starting point)
        "reason_template"   : str  — suggested reason text (teacher edits before saving)
        "already_has_active": bool — always False here (filtered out above)
    """
    from shared.skills import student_assessments, compute_skill_mastery

    # Build quick lookup of active interventions per (student, skill)
    active_pairs: set[tuple[str, str]] = {
        (r["student_code"], r["skill_id"])
        for r in existing_interventions
        if r["status"] not in {"Completed", "Dismissed"}
    }

    flags = []
    for code in student_codes:
        for skill in skill_definitions:
            sid = skill["id"]
            if (code, sid) in active_pairs:
                continue  # active intervention already exists

            ass = student_assessments(assessment_records, code, skill_id=sid)
            if len(ass) < MIN_ASSESSMENTS_FOR_FLAG:
                continue  # insufficient data

            m = compute_skill_mastery(ass)
            if m["mastery_level"] not in SUPPORT_MASTERY_LEVELS:
                continue  # mastery is adequate (or None)

            suggested = SUGGESTED_ACTIVITIES.get(m["mastery_level"], [""])[0]
            reason_template = (
                f"Student {code} has completed {m['count']} assessment(s) "
                f"for skill '{skill['name']}' "
                f"with a mean score of {m['mean_pct']:.1f}% "
                f"(mastery level: {m['mastery_level']})."
            )

            flags.append({
                "student_code":       code,
                "skill_id":           sid,
                "skill_name":         skill["name"],
                "mastery_level":      m["mastery_level"],
                "mastery_level_ar":   m["mastery_level_ar"],
                "mean_pct":           m["mean_pct"],
                "latest_pct":         m["latest_pct"],
                "trend":              m["trend"],
                "assessment_count":   m["count"],
                "suggested_action":   suggested,
                "reason_template":    reason_template,
                "already_has_active": False,
            })

    return flags


# ---------------------------------------------------------------------------
# Progress checkpoint helpers
# ---------------------------------------------------------------------------

def new_progress_checkpoint(
    intervention_id: str,
    student_code: str,
    skill_id: str,
    score: float,
    max_score: float,
    date: str = "",
    notes: str = "",
    _now: str | None = None,
) -> dict:
    """
    Build a post-intervention progress checkpoint record.

    Parameters
    ----------
    intervention_id : Links to the intervention this checkpoint monitors.
    student_code    : Student identifier.
    skill_id        : Skill definition id.
    score           : Score achieved.
    max_score       : Maximum possible score (must be > 0).
    date            : ISO date string (defaults to today).
    notes           : Optional teacher notes.
    _now            : Timestamp override (for testing).

    Raises
    ------
    ValueError if max_score <= 0, score < 0, or score > max_score.
    """
    if max_score <= 0:
        raise ValueError("max_score must be > 0.")
    if score < 0:
        raise ValueError("score must be >= 0.")
    if score > max_score:
        raise ValueError("score must not exceed max_score.")
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    return {
        "id":              uuid.uuid4().hex,
        "intervention_id": intervention_id,
        "student_code":    student_code,
        "skill_id":        skill_id,
        "date":            date,
        "score":           float(score),
        "max_score":       float(max_score),
        "notes":           notes.strip(),
        "created_at":      _now if _now is not None else datetime.now(timezone.utc).isoformat(),
    }


def intervention_checkpoints(
    checkpoints: list[dict],
    intervention_id: str,
) -> list[dict]:
    """Return checkpoints for a given intervention, sorted by date ascending."""
    result = [c for c in checkpoints if c.get("intervention_id") == intervention_id]
    return sorted(result, key=lambda c: c.get("date", ""))


def compare_before_after(
    evidence_snapshot: dict,
    post_checkpoints: list[dict],
) -> dict:
    """
    Compare the mastery evidence at intervention creation time vs post-checkpoints.

    Parameters
    ----------
    evidence_snapshot : The mastery dict stored when the intervention was created.
    post_checkpoints  : Checkpoint records added during/after the intervention.

    Returns
    -------
    dict:
        "pre_mean_pct"   : float | None
        "pre_count"      : int
        "post_mean_pct"  : float | None
        "post_count"     : int
        "delta_pct"      : float | None — post_mean_pct − pre_mean_pct
        "direction"      : str — "improved" | "declined" | "stable" | "N/A"
        "sufficient_data": bool — True when post_count >= 1

    Rules
    -----
    * Never fabricates data — returns None when values are absent.
    * No diagnostic conclusion is drawn — just the numeric comparison.
    """
    pre_mean  = evidence_snapshot.get("mean_pct")
    pre_count = evidence_snapshot.get("count", 0)

    if not post_checkpoints:
        return {
            "pre_mean_pct":    pre_mean,
            "pre_count":       pre_count,
            "post_mean_pct":   None,
            "post_count":      0,
            "delta_pct":       None,
            "direction":       "N/A",
            "sufficient_data": False,
        }

    pcts = []
    for c in post_checkpoints:
        if c["max_score"] > 0:
            pcts.append(round(c["score"] / c["max_score"] * 100, 1))

    post_mean = round(sum(pcts) / len(pcts), 1) if pcts else None

    if pre_mean is not None and post_mean is not None:
        delta = round(post_mean - pre_mean, 1)
        if delta >= 5.0:
            direction = "improved"
        elif delta <= -5.0:
            direction = "declined"
        else:
            direction = "stable"
    else:
        delta     = None
        direction = "N/A"

    return {
        "pre_mean_pct":    pre_mean,
        "pre_count":       pre_count,
        "post_mean_pct":   post_mean,
        "post_count":      len(post_checkpoints),
        "delta_pct":       delta,
        "direction":       direction,
        "sufficient_data": len(post_checkpoints) >= 1,
    }
