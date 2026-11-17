"""
shared/gagne.py
---------------
Gagné's Nine Events of Instruction — pure Python logic for SchoolFlow AI
(Task 9).

Design rules
------------
* No Streamlit imports — fully testable offline.
* Gagné's model is treated as a FLEXIBLE GUIDE, not a rigid checklist.
  Teachers may skip, reorder, or merge events freely.
* No event's absence is treated as a failure indicator.
* Suggested activities are starting points only — always labelled as such.
* No live AI generation is claimed; suggestions are static templates.
* Bilingual (English / Arabic) content throughout.
* Integration strategy: a lightweight "Gagné plan" is stored inside
  `lesson_draft["gagne_plan"]` — a list of nine event dicts.
  This is a NEW sub-key inside the existing lesson_draft; it does NOT
  replace or alter any existing key.

Nine Events data
----------------
Each event dict (GAGNE_EVENTS) contains:
    id          : str  — internal slug ("gain_attention" … "retention_transfer")
    number      : int  — 1–9
    name_en     : str
    name_ar     : str
    description_en: str
    description_ar: str
    example_activities_en: list[str]  — suggested, teacher-editable
    example_activities_ar: list[str]

Plan event record (inside lesson_draft["gagne_plan"])
------------------------------------------------------
    event_id    : str   — references GAGNE_EVENTS id
    status      : str   — "planned" | "in_progress" | "done" | "skipped"
    notes       : str   — teacher's free-text notes
    activity    : str   — teacher-written or chosen activity description
    question_ids: list[str]  — links to question_library question ids
    skill_id    : str   — optional link to skill definition
    duration_min: int | float | None  — planned duration in minutes (optional)
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Nine Events data
# ---------------------------------------------------------------------------

GAGNE_EVENTS: list[dict] = [
    {
        "id":       "gain_attention",
        "number":   1,
        "name_en":  "Gain Attention",
        "name_ar":  "جذب الانتباه",
        "description_en": (
            "Capture students' attention and motivate engagement before instruction begins."
        ),
        "description_ar": (
            "جذب انتباه الطلاب وتحفيز تفاعلهم قبل بدء التدريس."
        ),
        "example_activities_en": [
            "Start with a surprising fact, question, or image.",
            "Show a short video clip or anecdote.",
            "Pose a puzzling problem or riddle.",
        ],
        "example_activities_ar": [
            "ابدأ بحقيقة مثيرة أو صورة لافتة.",
            "اعرض مقطعًا قصيرًا أو قصة مثيرة.",
            "اطرح لغزًا أو مشكلة مثيرة للتساؤل.",
        ],
    },
    {
        "id":       "inform_objectives",
        "number":   2,
        "name_en":  "Inform Learners of Objectives",
        "name_ar":  "توضيح أهداف التعلم",
        "description_en": (
            "Tell students what they will be able to do by the end of the lesson."
        ),
        "description_ar": (
            "أخبر الطلاب بما سيكونون قادرين على فعله في نهاية الدرس."
        ),
        "example_activities_en": [
            "Write objectives on the board using 'I can…' statements.",
            "Show a learning target list and discuss briefly.",
            "Reference the skill or concept being developed.",
        ],
        "example_activities_ar": [
            "اكتب الأهداف على السبورة بصيغة 'سأكون قادرًا على…'.",
            "اعرض قائمة الأهداف وناقشها باختصار.",
            "أشر إلى المهارة أو المفهوم الذي سيُطوَّر.",
        ],
    },
    {
        "id":       "stimulate_recall",
        "number":   3,
        "name_en":  "Stimulate Recall of Prior Learning",
        "name_ar":  "استدعاء التعلم السابق",
        "description_en": (
            "Activate students' existing knowledge to build connections with new content."
        ),
        "description_ar": (
            "تنشيط المعرفة السابقة لدى الطلاب لبناء الروابط مع المحتوى الجديد."
        ),
        "example_activities_en": [
            "Ask review questions from the previous lesson.",
            "Quick 'think-pair-share' on a related concept.",
            "Show a concept map of prior learning.",
        ],
        "example_activities_ar": [
            "اطرح أسئلة مراجعة من الدرس السابق.",
            "نشاط 'فكِّر-ناقش-شارك' حول مفهوم ذي صلة.",
            "اعرض خريطة مفاهيمية للمعرفة السابقة.",
        ],
    },
    {
        "id":       "present_content",
        "number":   4,
        "name_en":  "Present the Content",
        "name_ar":  "تقديم المحتوى",
        "description_en": (
            "Deliver the new information, concept, or skill in a clear, organised way."
        ),
        "description_ar": (
            "تقديم المعلومات أو المفهوم أو المهارة الجديدة بوضوح وتنظيم."
        ),
        "example_activities_en": [
            "Direct instruction with examples.",
            "Worked examples on the board.",
            "Demonstration of a process or procedure.",
        ],
        "example_activities_ar": [
            "تعليم مباشر مع أمثلة توضيحية.",
            "أمثلة محلولة على السبورة.",
            "توضيح عملي لإجراء أو خطوات.",
        ],
    },
    {
        "id":       "provide_guidance",
        "number":   5,
        "name_en":  "Provide Learning Guidance",
        "name_ar":  "تقديم الإرشاد التعليمي",
        "description_en": (
            "Support students in encoding and understanding the new content."
        ),
        "description_ar": (
            "مساعدة الطلاب في فهم المحتوى الجديد وترميزه."
        ),
        "example_activities_en": [
            "Provide worked examples with annotations.",
            "Use visual organisers, mnemonics, or analogies.",
            "Guided practice with teacher support.",
        ],
        "example_activities_ar": [
            "قدِّم نماذج محلولة مع تعليقات توضيحية.",
            "استخدم منظِّمات بصرية أو تشبيهات.",
            "ممارسة موجَّهة بدعم من المعلم.",
        ],
    },
    {
        "id":       "elicit_performance",
        "number":   6,
        "name_en":  "Elicit Performance (Practice)",
        "name_ar":  "استثارة أداء المتعلم",
        "description_en": (
            "Require students to practise or demonstrate the new skill or knowledge."
        ),
        "description_ar": (
            "مطالبة الطلاب بالتدرب أو إظهار المهارة أو المعرفة الجديدة."
        ),
        "example_activities_en": [
            "Independent or pair practice exercises.",
            "Quick comprehension questions.",
            "Role-play or problem-solving task.",
        ],
        "example_activities_ar": [
            "تمارين فردية أو ثنائية.",
            "أسئلة فهم سريعة.",
            "لعب أدوار أو مهمة حل مشكلة.",
        ],
    },
    {
        "id":       "provide_feedback",
        "number":   7,
        "name_en":  "Provide Feedback",
        "name_ar":  "تقديم التغذية الراجعة",
        "description_en": (
            "Give timely, specific feedback on student performance."
        ),
        "description_ar": (
            "تقديم تغذية راجعة فورية وموجَّهة على أداء الطالب."
        ),
        "example_activities_en": [
            "Correct errors and explain why.",
            "Peer feedback using a simple checklist.",
            "Whole-class feedback on common mistakes.",
        ],
        "example_activities_ar": [
            "صحِّح الأخطاء وأوضح السبب.",
            "تغذية راجعة بين الأقران بقائمة مرجعية.",
            "تغذية راجعة جماعية على الأخطاء الشائعة.",
        ],
    },
    {
        "id":       "assess_performance",
        "number":   8,
        "name_en":  "Assess Performance",
        "name_ar":  "تقييم الأداء",
        "description_en": (
            "Measure whether the learning objectives have been achieved."
        ),
        "description_ar": (
            "قياس مدى تحقيق الأهداف التعليمية."
        ),
        "example_activities_en": [
            "Exit ticket or short quiz.",
            "Oral questioning of a sample of students.",
            "Observation checklist during activity.",
        ],
        "example_activities_ar": [
            "بطاقة خروج أو اختبار قصير.",
            "أسئلة شفهية لعينة من الطلاب.",
            "قائمة مراقبة أثناء النشاط.",
        ],
    },
    {
        "id":       "retention_transfer",
        "number":   9,
        "name_en":  "Enhance Retention and Transfer",
        "name_ar":  "تعزيز الاحتفاظ ونقل التعلم",
        "description_en": (
            "Help students retain what they learned and apply it to new contexts."
        ),
        "description_ar": (
            "مساعدة الطلاب على الاحتفاظ بما تعلموه وتطبيقه في سياقات جديدة."
        ),
        "example_activities_en": [
            "Assign a spaced practice task for homework.",
            "Connect lesson content to a real-world application.",
            "Preview how this skill will be used in future lessons.",
        ],
        "example_activities_ar": [
            "أسِّس مهمة تكرار موزَّع كواجب منزلي.",
            "اربط محتوى الدرس بتطبيق في الحياة الواقعية.",
            "أشر إلى كيفية استخدام هذه المهارة في دروس قادمة.",
        ],
    },
]

EVENT_IDS   = [e["id"] for e in GAGNE_EVENTS]
EVENT_BY_ID = {e["id"]: e for e in GAGNE_EVENTS}

#: Valid plan-event status values.
PLAN_STATUSES = ["planned", "in_progress", "done", "skipped"]
MIN_DURATION_MIN = 0
MAX_DURATION_MIN = 90


# ---------------------------------------------------------------------------
# Plan construction helpers
# ---------------------------------------------------------------------------

def new_gagne_plan() -> list[dict]:
    """
    Return a fresh list of nine plan-event dicts, one per Gagné event,
    each initialised with:
        event_id    = event id
        status      = "planned"
        notes       = ""
        activity    = ""  (teacher fills in)
        question_ids= []
        skill_id    = ""
        duration_min= None
    """
    return [
        {
            "event_id":     e["id"],
            "status":       "planned",
            "notes":        "",
            "activity":     "",
            "question_ids": [],
            "skill_id":     "",
            "duration_min": None,
        }
        for e in GAGNE_EVENTS
    ]


def get_plan_event(plan: list[dict], event_id: str) -> dict | None:
    """Return the plan event for the given event_id, or None."""
    for pe in plan:
        if pe["event_id"] == event_id:
            return pe
    return None


def update_plan_event(
    plan: list[dict],
    event_id: str,
    status: str | None = None,
    notes: str | None = None,
    activity: str | None = None,
    question_ids: list[str] | None = None,
    skill_id: str | None = None,
    duration_min: int | float | None = None,
    clear_duration: bool = False,
) -> list[dict]:
    """
    Return a NEW list identical to *plan* except the event matching *event_id*
    has the specified fields updated.  Does NOT mutate the input list.

    Raises
    ------
    ValueError if event_id is not in EVENT_IDS.
    ValueError if status is provided but not in PLAN_STATUSES.
    ValueError if duration_min is not a finite number between 0 and 90.
    ValueError if clear_duration is combined with a duration value.
    """
    if event_id not in EVENT_IDS:
        raise ValueError(
            f"event_id must be one of {EVENT_IDS}. Got {event_id!r}."
        )
    if status is not None and status not in PLAN_STATUSES:
        raise ValueError(
            f"status must be one of {PLAN_STATUSES}. Got {status!r}."
        )
    if not isinstance(clear_duration, bool):
        raise ValueError("clear_duration must be a boolean.")
    if clear_duration and duration_min is not None:
        raise ValueError("duration_min cannot be set when clear_duration is True.")
    if duration_min is not None:
        if isinstance(duration_min, bool) or not isinstance(duration_min, (int, float)):
            raise ValueError("duration_min must be a number or None.")
        if duration_min < MIN_DURATION_MIN or duration_min > MAX_DURATION_MIN:
            raise ValueError(
                f"duration_min must be between {MIN_DURATION_MIN} and "
                f"{MAX_DURATION_MIN}. Got {duration_min!r}."
            )
        if not math.isfinite(duration_min):
            raise ValueError("duration_min must be finite.")

    new_plan = []
    for pe in plan:
        if pe["event_id"] == event_id:
            updated = dict(pe)
            if status       is not None: updated["status"]       = status
            if notes        is not None: updated["notes"]        = notes.strip()
            if activity     is not None: updated["activity"]     = activity.strip()
            if question_ids is not None: updated["question_ids"] = list(question_ids)
            if skill_id     is not None: updated["skill_id"]     = skill_id.strip()
            if clear_duration: updated["duration_min"] = None
            elif duration_min is not None: updated["duration_min"] = duration_min
            new_plan.append(updated)
        else:
            new_plan.append(pe)
    return new_plan


# ---------------------------------------------------------------------------
# Plan summary helpers
# ---------------------------------------------------------------------------

def plan_summary(plan: list[dict]) -> dict:
    """
    Summarise the status of all nine events.

    Returns
    -------
    dict:
        "total"      : int — always 9
        "planned"    : int
        "in_progress": int
        "done"       : int
        "skipped"    : int
        "untouched"  : int — events with status "planned" AND empty activity AND empty notes
        "completion_pct": float — % of events that are "done" or "skipped"

    Rules enforced
    --------------
    * "done" + "skipped" is NOT reported as "failure" for the remaining events.
    * No minimum completion level is required.
    """
    counts = {s: 0 for s in PLAN_STATUSES}
    untouched = 0
    for pe in plan:
        s = pe.get("status", "planned")
        counts[s] = counts.get(s, 0) + 1
        if s == "planned" and not pe.get("activity") and not pe.get("notes"):
            untouched += 1

    done_or_skipped = counts["done"] + counts["skipped"]
    total = len(plan)

    return {
        "total":           total,
        "planned":         counts["planned"],
        "in_progress":     counts["in_progress"],
        "done":            counts["done"],
        "skipped":         counts["skipped"],
        "untouched":       untouched,
        "completion_pct":  round(done_or_skipped / total * 100, 1) if total else 0.0,
    }


def events_done(plan: list[dict]) -> list[str]:
    """Return event_ids of events with status 'done'."""
    return [pe["event_id"] for pe in plan if pe.get("status") == "done"]


def events_skipped(plan: list[dict]) -> list[str]:
    """Return event_ids of events with status 'skipped'."""
    return [pe["event_id"] for pe in plan if pe.get("status") == "skipped"]


def events_pending(plan: list[dict]) -> list[str]:
    """Return event_ids of events with status 'planned' or 'in_progress'."""
    return [
        pe["event_id"]
        for pe in plan
        if pe.get("status") in {"planned", "in_progress"}
    ]
