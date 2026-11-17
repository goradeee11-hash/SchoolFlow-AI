"""
shared/bloom.py
---------------
Bloom's Taxonomy (Revised) question classification logic for SchoolFlow AI
(Task 8).

Design rules
------------
* No Streamlit imports — fully testable offline.
* Six levels: Remember, Understand, Apply, Analyze, Evaluate, Create.
  (Revised Bloom's Taxonomy — Anderson & Krathwohl 2001.)
* The classifier uses weighted keyword + pattern matching, not pure keyword
  lookup.  It evaluates the TASK DEMAND of the question, not just surface
  words.
* The classifier is SUGGESTIVE only — the teacher always has final authority.
* When no AI model is available the classifier uses rule-based heuristics;
  it is transparent about this limitation.
* Arabic and English are both supported.
* No fixed distribution or quota is imposed on any teacher or lesson.
* Classification is NOT a judgement of question quality.
* When confidence is low (< LOW_CONFIDENCE_THRESHOLD), the suggestion is
  labelled "Low confidence" and the teacher is encouraged to review.

Bloom level data
----------------
Each level is represented by:
    id    : str  — internal slug ("remember", "understand", …)
    name_en: str  — English display name
    name_ar: str  — Arabic display name
    description_en: str  — brief description
    description_ar: str  — Arabic description
    color  : str  — hex colour used in UI badges
    order  : int  — 1 (lowest) → 6 (highest)

Question record
---------------
    id           : str  — unique identifier
    text         : str  — question text (any language)
    bloom_level  : str  — level id (teacher-confirmed or manually set)
    suggested_level: str | None — classifier suggestion (may differ from bloom_level)
    confidence   : float | None — 0.0–1.0 classifier confidence (None if unavailable)
    suggestion_reason: str — human-readable explanation of the suggestion
    confirmed_by_teacher: bool — True once teacher has confirmed/edited
    lesson_id    : str  — optional link to lesson record
    skill_id     : str  — optional link to skill definition
    subject      : str  — optional subject tag
    grade        : str  — optional grade tag
    tags         : list[str] — optional free tags
    created_at   : str  — ISO timestamp
    updated_at   : str  — ISO timestamp
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Confidence threshold below which a suggestion is marked "Low confidence".
LOW_CONFIDENCE_THRESHOLD = 0.40

#: Bloom's Revised Taxonomy levels — ordered lowest to highest.
BLOOM_LEVELS = [
    {
        "id":             "remember",
        "name_en":        "Remember",
        "name_ar":        "التذكر",
        "description_en": "Recall facts, definitions, or basic concepts.",
        "description_ar": "استرجاع الحقائق والتعريفات والمفاهيم الأساسية.",
        "color":          "#B7D957",
        "order":          1,
    },
    {
        "id":             "understand",
        "name_en":        "Understand",
        "name_ar":        "الفهم",
        "description_en": "Explain, summarise, or interpret information.",
        "description_ar": "الشرح والتلخيص وتفسير المعلومات.",
        "color":          "#B7D957",
        "order":          2,
    },
    {
        "id":             "apply",
        "name_en":        "Apply",
        "name_ar":        "التطبيق",
        "description_en": "Use knowledge in a new situation or solve a problem.",
        "description_ar": "استخدام المعرفة في موقف جديد أو حل مشكلة.",
        "color":          "#B7D957",
        "order":          3,
    },
    {
        "id":             "analyze",
        "name_en":        "Analyze",
        "name_ar":        "التحليل",
        "description_en": "Break down, compare, or examine relationships.",
        "description_ar": "التجزئة والمقارنة وفحص العلاقات.",
        "color":          "#B7D957",
        "order":          4,
    },
    {
        "id":             "evaluate",
        "name_en":        "Evaluate",
        "name_ar":        "التقييم",
        "description_en": "Judge, critique, or justify based on criteria.",
        "description_ar": "الحكم والنقد والتبرير وفق معايير.",
        "color":          "#B7D957",
        "order":          5,
    },
    {
        "id":             "create",
        "name_en":        "Create",
        "name_ar":        "الإبداع",
        "description_en": "Design, produce, or construct something new.",
        "description_ar": "التصميم والإنتاج وبناء شيء جديد.",
        "color":          "#B7D957",
        "order":          6,
    },
]

LEVEL_IDS = [lvl["id"] for lvl in BLOOM_LEVELS]
LEVEL_BY_ID = {lvl["id"]: lvl for lvl in BLOOM_LEVELS}

# ---------------------------------------------------------------------------
# Rule-based classifier
# ---------------------------------------------------------------------------
#
# Architecture: each level has a list of (pattern, weight) tuples.
# Patterns are matched against the lower-cased question text.
# Scores are summed per level; the level with the highest score wins.
# Confidence = winning_score / (winning_score + second_score + ε).
#
# This is intentionally heuristic — it covers the most common question
# structures in English and Arabic without pretending to be an AI model.

_EN_PATTERNS: dict[str, list[tuple[str, float]]] = {
    "remember": [
        (r"\bwhat is\b",         1.0),
        (r"\bwhat are\b",        0.9),
        (r"\bwho is\b",          1.0),
        (r"\bwhen did\b",        1.0),
        (r"\bwhere is\b",        0.9),
        (r"\bname the\b",        1.1),
        (r"\blist the\b",        1.0),
        (r"\bdefine\b",          1.2),
        (r"\brecall\b",          1.1),
        (r"\bstate the\b",       1.0),
        (r"\bidentif(y|ies)\b",  0.8),
        (r"\bwrite down\b",      0.9),
        (r"\bwhich of these\b",  0.8),
        (r"\bmatch\b",           0.7),
        (r"\bspell\b",           1.1),
    ],
    "understand": [
        (r"\bexplain\b",         1.2),
        (r"\bdescribe\b",        1.0),
        (r"\bsummar(ise|ize)\b", 1.2),
        (r"\bparaphrase\b",      1.2),
        (r"\bin your own words\b",1.3),
        (r"\bwhat does .{0,30} mean\b", 1.1),
        (r"\binterpret\b",       1.1),
        (r"\billustrate\b",      0.9),
        (r"\bclassif(y|ies)\b",  0.8),
        (r"\bgive an example\b", 1.0),
        (r"\bhow would you describe\b", 1.1),
        (r"\bdistinguish between\b", 0.9),
        (r"\bwhat is the main idea\b", 1.1),
        (r"\bwhy is .{0,30} important\b", 0.9),
    ],
    "apply": [
        (r"\buse\b",             0.7),
        (r"\bapply\b",           1.2),
        (r"\bsolve\b",           1.1),
        (r"\bcalculate\b",       1.1),
        (r"\bcompute\b",         1.0),
        (r"\bdemonstrate\b",     1.0),
        (r"\bshow how\b",        1.0),
        (r"\bconstruct\b",       0.8),
        (r"\bwrite a .{0,30} using\b", 1.0),
        (r"\bwhat would happen if\b", 0.9),
        (r"\bhow would you use\b", 1.0),
        (r"\bpredict\b",         0.8),
        (r"\bchange .{0,20} to\b", 0.8),
        (r"\bgive an example of .{0,20} in real life\b", 1.1),
    ],
    "analyze": [
        (r"\banalyse\b",         1.2),
        (r"\banalyze\b",         1.2),
        (r"\bcompare\b",         1.1),
        (r"\bcontrast\b",        1.1),
        (r"\bcompare and contrast\b", 1.4),
        (r"\bbreak down\b",      1.1),
        (r"\bexamine\b",         1.0),
        (r"\bwhy do(es)?\b",     0.8),
        (r"\bwhat is the relationship\b", 1.2),
        (r"\bhow does .{0,30} affect\b", 1.1),
        (r"\bwhat are the causes\b", 1.1),
        (r"\bwhat are the effects\b", 1.1),
        (r"\bdifferentiate\b",   1.2),
        (r"\bdistinction between\b", 1.0),
        (r"\binfer\b",           1.0),
        (r"\bdeduce\b",          1.1),
        (r"\bwhich evidence\b",  1.0),
    ],
    "evaluate": [
        (r"\bevaluat(e|ion)\b",  1.2),
        (r"\bjudge\b",           1.2),
        (r"\bjustify\b",         1.2),
        (r"\bdo you agree\b",    1.3),
        (r"\bdo you think\b",    0.9),
        (r"\bwhat is your opinion\b", 1.2),
        (r"\bcritici(se|ze)\b",  1.2),
        (r"\bwhich is better\b", 1.1),
        (r"\bwhich is best\b",   1.1),
        (r"\brecommend\b",       1.0),
        (r"\bdefend\b",          1.1),
        (r"\brate\b",            0.8),
        (r"\brank\b",            0.9),
        (r"\bpriori(tise|tize)\b", 1.0),
        (r"\bto what extent\b",  1.3),
        (r"\bwould you support\b", 1.1),
    ],
    "create": [
        (r"\bcreate\b",          1.3),
        (r"\bdesign\b",          1.2),
        (r"\bwrite a\b",                                                 1.0),
        (r"\bwrite\b.{0,30}\b(story|poem|essay|letter|report|plan|proposal)\b", 1.5),
        (r"\bcompose\b",         1.2),
        (r"\bdevelop\b",         1.0),
        (r"\bplan\b",            1.0),
        (r"\bpropose\b",         1.0),
        (r"\binvent\b",          1.3),
        (r"\bimagine\b",         1.0),
        (r"\bformulat(e|ing)\b", 1.1),
        (r"\bgenerate\b",        1.0),
        (r"\bconstruct a .{0,30} that\b", 1.1),
        (r"\bproduce\b",         1.0),
        (r"\bput together\b",    0.9),
    ],
}

_AR_PATTERNS: dict[str, list[tuple[str, float]]] = {
    "remember": [
        (r"ما هو\b",              1.0),
        (r"ما هي\b",              1.0),
        (r"عرِّف\b",              1.2),
        (r"اذكر\b",               1.1),
        (r"اكتب\b",               0.7),
        (r"من هو\b",              1.0),
        (r"متى\b",                0.9),
        (r"أين\b",                0.8),
        (r"سمِّ\b",               1.1),
        (r"حدِّد\b",              0.8),
        (r"تعريف\b",              1.0),
        (r"ما معنى\b",            1.1),
    ],
    "understand": [
        (r"اشرح\b",               1.2),
        (r"وضِّح\b",              1.1),
        (r"لخِّص\b",              1.2),
        (r"بكلماتك الخاصة\b",   1.3),
        (r"أعطِ مثالاً\b",       1.0),
        (r"ما الفرق بين\b",      0.9),
        (r"صف\b",                 1.0),
        (r"ما المقصود\b",         1.1),
        (r"ما الفكرة الرئيسية\b", 1.1),
        (r"كيف تصف\b",           1.1),
        (r"اقرأ.*وأجب\b",        0.8),
    ],
    "apply": [
        (r"طبِّق\b",              1.2),
        (r"استخدم\b",             1.0),
        (r"حلّ\b",                1.1),
        (r"احسب\b",               1.1),
        (r"بيِّن كيف\b",          1.0),
        (r"اكتب.*باستخدام\b",    1.0),
        (r"ماذا سيحدث لو\b",     0.9),
        (r"توقَّع\b",             0.9),
        (r"استنتج\b",             0.9),
        (r"مثِّل\b",              0.9),
    ],
    "analyze": [
        (r"حلِّل\b",              1.2),
        (r"قارن\b",               1.2),
        (r"ما أوجه التشابه\b",   1.2),
        (r"ما أوجه الاختلاف\b",  1.2),
        (r"ما العلاقة\b",         1.2),
        (r"ما أسباب\b",           1.1),
        (r"ما نتائج\b",           1.1),
        (r"لماذا\b",              0.8),
        (r"ما الذي يدل\b",       1.0),
        (r"استنتج من\b",          1.1),
        (r"فرِّق بين\b",          1.1),
    ],
    "evaluate": [
        (r"قيِّم\b",              1.2),
        (r"احكم\b",               1.2),
        (r"برِّر\b",              1.2),
        (r"هل توافق\b",           1.3),
        (r"ما رأيك\b",            1.2),
        (r"أيهما أفضل\b",         1.1),
        (r"انتقد\b",              1.2),
        (r"ما مدى\b",             1.1),
        (r"اقترح.*وعلِّل\b",     1.1),
        (r"هل يمكن الاعتماد\b",  1.0),
        (r"رتِّب.*حسب الأهمية\b", 1.0),
    ],
    "create": [
        (r"أنشئ\b",               1.3),
        (r"صمِّم\b",              1.2),
        (r"اكتب قصة\b",           1.3),
        (r"اكتب مقالة\b",         1.2),
        (r"ضع خطة\b",             1.2),
        (r"اقترح\b",              1.0),
        (r"ابتكر\b",              1.3),
        (r"أنتج\b",               1.1),
        (r"خطِّط\b",              1.0),
        (r"اكتب نص\b",            1.1),
        (r"تخيَّل\b",             1.0),
        (r"اقترح حلاً جديداً\b",  1.2),
    ],
}


def _score_question(text: str) -> dict[str, float]:
    """
    Compute a raw score for each Bloom level for the given question text.

    Both English and Arabic patterns are applied to the same text
    (mixed-language questions are supported).

    Returns
    -------
    dict mapping level_id → float score (sum of matched pattern weights).
    """
    t = text.lower()
    scores: dict[str, float] = {lid: 0.0 for lid in LEVEL_IDS}
    for level_id, patterns in _EN_PATTERNS.items():
        for pattern, weight in patterns:
            if re.search(pattern, t, re.IGNORECASE):
                scores[level_id] += weight
    for level_id, patterns in _AR_PATTERNS.items():
        for pattern, weight in patterns:
            if re.search(pattern, t):
                scores[level_id] += weight
    return scores


def suggest_bloom_level(text: str) -> dict:
    """
    Suggest a Bloom's Taxonomy level for the given question text.

    Parameters
    ----------
    text : Question text (English, Arabic, or mixed).

    Returns
    -------
    dict:
        "suggested_level"  : str  — level id ("remember" … "create")
        "confidence"       : float — 0.0–1.0
        "low_confidence"   : bool
        "reason"           : str  — human-readable English explanation
        "reason_ar"        : str  — Arabic explanation
        "scores"           : dict — raw scores per level (for transparency)
        "classifier_type"  : str  — "rule_based" (always, until AI is integrated)

    Rules enforced
    --------------
    * Returns "remember" with confidence=0.0 when text is empty.
    * "low_confidence" is True when confidence < LOW_CONFIDENCE_THRESHOLD.
    * classifier_type is always "rule_based" in this implementation.
      When an AI model is integrated, this field will switch to "ai_model".
    * This function is SUGGESTIVE only — the teacher decides the final level.
    """
    text = text.strip()
    if not text:
        return {
            "suggested_level": "remember",
            "confidence":      0.0,
            "low_confidence":  True,
            "reason":          "No question text provided.",
            "reason_ar":       "لم يُدخَل نص السؤال.",
            "scores":          {lid: 0.0 for lid in LEVEL_IDS},
            "classifier_type": "rule_based",
        }

    scores = _score_question(text)
    total  = sum(scores.values())

    if total == 0.0:
        # No patterns matched — default to "remember" (lowest, safest)
        return {
            "suggested_level": "remember",
            "confidence":      0.0,
            "low_confidence":  True,
            "reason":          (
                "No matching patterns found. "
                "The question may be short, general, or use unusual phrasing. "
                "Please classify manually."
            ),
            "reason_ar":       (
                "لم تُطابق أي أنماط. "
                "قد يكون السؤال قصيرًا أو عامًا أو يستخدم صياغة غير معتادة. "
                "يُرجى التصنيف اليدوي."
            ),
            "scores":          scores,
            "classifier_type": "rule_based",
        }

    # Sort levels by score descending
    sorted_levels = sorted(scores.items(), key=lambda x: -x[1])
    best_id, best_score   = sorted_levels[0]
    second_id, second_score = sorted_levels[1]

    # Confidence = best_score / (best + second + ε) — penalised for near ties
    epsilon    = 0.001
    confidence = round(best_score / (best_score + second_score + epsilon), 3)

    low_conf = confidence < LOW_CONFIDENCE_THRESHOLD

    # Build reason
    lvl     = LEVEL_BY_ID[best_id]
    top_pct = round(best_score / total * 100, 1)

    matched_patterns = []
    for pattern, weight in (_EN_PATTERNS[best_id] + _AR_PATTERNS.get(best_id, [])):
        if re.search(pattern, text.lower()):
            matched_patterns.append(pattern.strip(r"\b").replace(r"\b", ""))

    pattern_note = (
        f" Key indicators: {', '.join(matched_patterns[:3])}."
        if matched_patterns else ""
    )
    conf_note = (
        " (Low confidence — please review.)"
        if low_conf else ""
    )
    conf_note_ar = (
        " (ثقة منخفضة — يُرجى المراجعة.)"
        if low_conf else ""
    )

    reason = (
        f"This question most closely matches '{lvl['name_en']}' "
        f"({top_pct:.0f}% of matched indicators).{pattern_note}"
        f" Second candidate: '{LEVEL_BY_ID[second_id]['name_en']}'.{conf_note}"
    )
    reason_ar = (
        f"هذا السؤال يتوافق بشكل أكبر مع مستوى '{lvl['name_ar']}' "
        f"({top_pct:.0f}% من المؤشرات المتطابقة)."
        f" المستوى الثاني المحتمل: '{LEVEL_BY_ID[second_id]['name_ar']}'.{conf_note_ar}"
    )

    return {
        "suggested_level": best_id,
        "confidence":      confidence,
        "low_confidence":  low_conf,
        "reason":          reason,
        "reason_ar":       reason_ar,
        "scores":          scores,
        "classifier_type": "rule_based",
    }


# ---------------------------------------------------------------------------
# Question record helpers
# ---------------------------------------------------------------------------

def new_question(
    text: str,
    bloom_level: str,
    confirmed_by_teacher: bool = False,
    suggested_level: str | None = None,
    confidence: float | None = None,
    suggestion_reason: str = "",
    lesson_id: str = "",
    skill_id: str = "",
    subject: str = "",
    grade: str = "",
    tags: list[str] | None = None,
    _now: str | None = None,
    _id: str | None = None,
) -> dict:
    """
    Build a new question record.

    Parameters
    ----------
    text                 : Question text (required, non-empty).
    bloom_level          : Teacher-confirmed Bloom level id.
    confirmed_by_teacher : True if the teacher explicitly set/confirmed the level.
    suggested_level      : Classifier suggestion (may differ from bloom_level).
    confidence           : Classifier confidence 0.0–1.0 (None if no suggestion).
    suggestion_reason    : Human-readable reason from the classifier.
    lesson_id            : Optional link to a lesson record.
    skill_id             : Optional link to a skill definition.
    subject              : Optional subject tag.
    grade                : Optional grade tag.
    tags                 : Optional free-text tags.
    _now                 : ISO timestamp override (for testing).
    _id                  : ID override (for testing).

    Raises
    ------
    ValueError if text is empty or bloom_level is not a valid level id.
    """
    text = text.strip()
    if not text:
        raise ValueError("Question text must not be empty.")
    if bloom_level not in LEVEL_IDS:
        raise ValueError(
            f"bloom_level must be one of {LEVEL_IDS}. Got {bloom_level!r}."
        )

    ts = _now if _now is not None else datetime.now(timezone.utc).isoformat()
    return {
        "id":                   _id if _id is not None else uuid.uuid4().hex[:12],
        "text":                 text,
        "bloom_level":          bloom_level,
        "confirmed_by_teacher": confirmed_by_teacher,
        "suggested_level":      suggested_level,
        "confidence":           confidence,
        "suggestion_reason":    suggestion_reason,
        "lesson_id":            lesson_id,
        "skill_id":             skill_id,
        "subject":              subject.strip(),
        "grade":                grade.strip(),
        "tags":                 list(tags) if tags else [],
        "created_at":           ts,
        "updated_at":           ts,
    }


def update_question(
    record: dict,
    bloom_level: str | None = None,
    confirmed_by_teacher: bool | None = None,
    text: str | None = None,
    lesson_id: str | None = None,
    skill_id: str | None = None,
    subject: str | None = None,
    grade: str | None = None,
    tags: list[str] | None = None,
    _now: str | None = None,
) -> dict:
    """
    Return a new dict that is a copy of *record* with the requested fields updated.
    Does NOT mutate the original.

    Raises ValueError if bloom_level is invalid or text becomes empty.
    """
    if bloom_level is not None and bloom_level not in LEVEL_IDS:
        raise ValueError(
            f"bloom_level must be one of {LEVEL_IDS}. Got {bloom_level!r}."
        )
    if bloom_level is not None and confirmed_by_teacher is not True:
        raise ValueError(
            "Changing bloom_level requires confirmed_by_teacher=True."
        )
    if text is not None and not text.strip():
        raise ValueError("Question text must not be empty.")

    updated = dict(record)
    if bloom_level is not None:
        updated["bloom_level"] = bloom_level
        updated["confirmed_by_teacher"] = True   # explicit level change = teacher confirmed
    if confirmed_by_teacher is not None:
        updated["confirmed_by_teacher"] = confirmed_by_teacher
    if text is not None:
        updated["text"] = text.strip()
    if lesson_id is not None:
        updated["lesson_id"] = lesson_id
    if skill_id is not None:
        updated["skill_id"] = skill_id
    if subject is not None:
        updated["subject"] = subject.strip()
    if grade is not None:
        updated["grade"] = grade.strip()
    if tags is not None:
        updated["tags"] = list(tags)

    ts = _now if _now is not None else datetime.now(timezone.utc).isoformat()
    updated["updated_at"] = ts
    return updated


# ---------------------------------------------------------------------------
# Question library store helpers
# ---------------------------------------------------------------------------

def add_question(library: list[dict], question: dict) -> list[dict]:
    """Return a new list with the question appended. Does not mutate input."""
    return library + [question]


def remove_question(library: list[dict], question_id: str) -> list[dict]:
    """Return a new list with the question removed. No error if not found."""
    return [q for q in library if q["id"] != question_id]


def get_question(library: list[dict], question_id: str) -> dict | None:
    """Return the question with the given id, or None."""
    for q in library:
        if q["id"] == question_id:
            return q
    return None


def replace_question(library: list[dict], updated: dict) -> list[dict]:
    """Return a new list where the question with the same id is replaced.

    A changed Bloom level must already be explicitly confirmed by a teacher.
    """
    new_list = []
    found = False
    for q in library:
        if q["id"] == updated["id"]:
            if (
                q.get("bloom_level") != updated.get("bloom_level")
                and updated.get("confirmed_by_teacher") is not True
            ):
                raise ValueError(
                    "Changing bloom_level requires confirmed_by_teacher=True."
                )
            new_list.append(updated)
            found = True
        else:
            new_list.append(q)
    if not found:
        raise ValueError(f"Question id {updated['id']!r} not found.")
    return new_list


def filter_questions(
    library: list[dict],
    bloom_level: str = "",
    lesson_id: str = "",
    skill_id: str = "",
    subject: str = "",
    grade: str = "",
    confirmed_only: bool = False,
) -> list[dict]:
    """
    Return questions from *library* matching the given filters.
    Empty string means "any" (no filter applied for that field).
    """
    result = library
    if bloom_level:
        result = [q for q in result if q["bloom_level"] == bloom_level]
    if lesson_id:
        result = [q for q in result if q.get("lesson_id") == lesson_id]
    if skill_id:
        result = [q for q in result if q.get("skill_id") == skill_id]
    if subject:
        result = [q for q in result if q.get("subject") == subject]
    if grade:
        result = [q for q in result if q.get("grade") == grade]
    if confirmed_only:
        result = [q for q in result if q.get("confirmed_by_teacher")]
    return result


# ---------------------------------------------------------------------------
# Distribution summary
# ---------------------------------------------------------------------------

def bloom_distribution(library: list[dict]) -> dict[str, int]:
    """
    Count questions per Bloom level in the library.

    Returns
    -------
    dict mapping level_id → count (all 6 levels always present, 0 if none).
    """
    counts = {lid: 0 for lid in LEVEL_IDS}
    for q in library:
        lid = q.get("bloom_level", "")
        if lid in counts:
            counts[lid] += 1
    return counts
