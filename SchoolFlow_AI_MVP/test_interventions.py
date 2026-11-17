"""
test_interventions.py
----------------------
Offline unit tests for shared/interventions.py
(Student Interventions & Recommendations — Task 7).

Tests cover:
  - Intervention record creation and validation (new_intervention)
  - Status updates (update_intervention)
  - Store operations (add_intervention, replace_intervention, etc.)
  - Auto-flag logic (flag_students_for_intervention)
  - Progress checkpoint creation and before/after comparison
  - Design constraints (teacher control, no participation-based flags,
    no automatic status changes, no fabricated data)
  - State initialisation (shared/state.py)
  - App wiring (nav entry + router in app.py)

No Streamlit runtime required; streamlit is stubbed.
"""

import sys
import os
import types
import unittest
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# 1. Stub streamlit
# ---------------------------------------------------------------------------
_state: dict = {}


class _FakeSecrets(dict):
    def get(self, key, default=None):
        return default


def _noop(*a, **kw):
    pass


def _noop_ctx(*a, **kw):
    import contextlib
    return contextlib.nullcontext()


class _FakeST(types.ModuleType):
    session_state = _state
    secrets       = _FakeSecrets()
    set_page_config = staticmethod(_noop)
    markdown        = staticmethod(_noop)
    title           = staticmethod(_noop)
    caption         = staticmethod(_noop)
    info            = staticmethod(_noop)
    success         = staticmethod(_noop)
    warning         = staticmethod(_noop)
    error           = staticmethod(_noop)
    write           = staticmethod(_noop)
    divider         = staticmethod(_noop)
    subheader       = staticmethod(_noop)
    stop            = staticmethod(_noop)
    rerun           = staticmethod(_noop)
    text_input      = staticmethod(lambda *a, **kw: kw.get("value", ""))
    text_area       = staticmethod(lambda *a, **kw: kw.get("value", ""))
    selectbox       = staticmethod(
        lambda *a, **kw: (kw.get("options") or (a[1] if len(a) > 1 else [""]))[0]
    )
    radio           = staticmethod(lambda *a, **kw: "English")
    button          = staticmethod(lambda *a, **kw: False)
    download_button = staticmethod(lambda *a, **kw: False)
    file_uploader   = staticmethod(lambda *a, **kw: None)
    dataframe       = staticmethod(_noop)
    expander        = staticmethod(_noop_ctx)
    container       = staticmethod(_noop_ctx)
    toggle          = staticmethod(lambda *a, **kw: False)
    number_input    = staticmethod(lambda *a, **kw: kw.get("value", 0.0))
    date_input      = staticmethod(lambda *a, **kw: kw.get("value", None))
    tabs            = staticmethod(lambda labels: [_noop_ctx() for _ in labels])
    columns         = staticmethod(lambda n, **kw: [
        type("Col", (), {
            "markdown": _noop, "caption": _noop,
            "button": lambda *a, **kw: False,
            "selectbox": lambda *a, **kw:
                (kw.get("options") or (a[1] if len(a) > 1 else [""]))[0],
            "text_input": lambda *a, **kw: kw.get("value", ""),
            "__enter__": lambda s: s, "__exit__": lambda s, *a: None,
        })()
        for _ in range(n if isinstance(n, int) else len(n))
    ])
    metric          = staticmethod(_noop)
    spinner         = staticmethod(_noop_ctx)
    cache_data      = staticmethod(lambda f=None, **kw: f if f else lambda g: g)

    class _FakeSidebar:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def markdown(self, *a, **kw): pass
        def button(self, *a, **kw): return False
    sidebar = _FakeSidebar()


sys.modules["streamlit"] = _FakeST("streamlit")

# ---------------------------------------------------------------------------
# 2. Patch sys.path
# ---------------------------------------------------------------------------
HERE = os.path.dirname(__file__)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ---------------------------------------------------------------------------
# 3. Import functions under test
# ---------------------------------------------------------------------------
from shared.interventions import (
    new_intervention,
    update_intervention,
    add_intervention,
    replace_intervention,
    get_intervention,
    student_interventions,
    active_interventions,
    flag_students_for_intervention,
    new_progress_checkpoint,
    intervention_checkpoints,
    compare_before_after,
    timestamp_sort_key,
    INTERVENTION_STATUSES,
    MTSS_TIERS,
    MIN_ASSESSMENTS_FOR_FLAG,
)
from shared.skills import new_skill, new_assessment

# ---------------------------------------------------------------------------
# 4. Fixtures
# ---------------------------------------------------------------------------

def _intervention(
    student="S01",
    skill_id="inference",
    skill_name="Inference",
    reason="Test reason",
    action="Test action",
    snapshot=None,
    mtss_tier=0,
    _id="test_id_001",
    _now="2026-11-01T08:00:00+00:00",
):
    return new_intervention(
        student_code=student,
        skill_id=skill_id,
        skill_name=skill_name,
        reason=reason,
        proposed_action=action,
        evidence_snapshot=snapshot or {"count": 2, "mean_pct": 35.0, "mastery_level": "Beginning"},
        mtss_tier=mtss_tier,
        _id=_id,
        _now=_now,
    )


def _skill(name="Inference", subject="English", grade="Grade 5", skill_id=None):
    return new_skill(name=name, subject=subject, grade=grade,
                     skill_id=skill_id or name.lower().replace(" ", "_"))


def _ass(skill_id, student, score, max_score=10.0, date="2026-11-01"):
    return new_assessment(
        skill_id=skill_id,
        student_code=student,
        score=score,
        max_score=max_score,
        date=date,
    )


def _checkpoint(int_id, student, skill_id, score, max_score=10.0, date="2026-11-10"):
    return new_progress_checkpoint(
        intervention_id=int_id,
        student_code=student,
        skill_id=skill_id,
        score=score,
        max_score=max_score,
        date=date,
    )


# ---------------------------------------------------------------------------
# 5. Tests — new_intervention()
# ---------------------------------------------------------------------------
class TestNewIntervention(unittest.TestCase):

    def test_01_has_required_keys(self):
        rec = _intervention()
        for key in ("id", "student_code", "skill_id", "skill_name",
                    "reason", "proposed_action", "mtss_tier", "status",
                    "start_date", "end_date", "teacher_notes",
                    "created_at", "updated_at", "evidence_snapshot"):
            self.assertIn(key, rec, msg=f"Missing key: {key}")

    def test_default_created_and_updated_timestamps_are_utc(self):
        rec = new_intervention("S01", "inference", "Inference", "reason", "action")
        for field in ("created_at", "updated_at"):
            self.assertEqual(
                datetime.fromisoformat(rec[field]).utcoffset(),
                timedelta(0),
            )

    def test_02_status_always_proposed(self):
        """Interventions always start as 'Proposed' — never auto-approved."""
        rec = _intervention()
        self.assertEqual(rec["status"], "Proposed")

    def test_03_empty_student_code_raises(self):
        with self.assertRaises(ValueError):
            new_intervention("", "sk", "Skill", "reason", "action")

    def test_04_empty_skill_id_raises(self):
        with self.assertRaises(ValueError):
            new_intervention("S01", "", "Skill", "reason", "action")

    def test_05_invalid_mtss_tier_raises(self):
        with self.assertRaises(ValueError):
            new_intervention("S01", "sk", "Skill", "r", "a", mtss_tier=99)

    def test_06_valid_mtss_tiers(self):
        for tier in (0, 1, 2, 3):
            rec = new_intervention("S01", "sk", "Skill", "r", "a", mtss_tier=tier)
            self.assertEqual(rec["mtss_tier"], tier)

    def test_07_evidence_snapshot_stored(self):
        snap = {"count": 3, "mean_pct": 42.0, "mastery_level": "Emerging"}
        rec = new_intervention("S01", "sk", "Skill", "r", "a", evidence_snapshot=snap)
        self.assertEqual(rec["evidence_snapshot"]["mastery_level"], "Emerging")

    def test_evidence_snapshot_is_deep_copied_and_preserves_types(self):
        snap = {
            "history": [{"scores": (7, 9)}],
            "captured_at": datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc),
        }
        rec = new_intervention(
            "S01", "sk", "Skill", "r", "a", evidence_snapshot=snap
        )

        snap["history"][0]["scores"] = (0,)
        snap["captured_at"] = None

        saved = rec["evidence_snapshot"]
        self.assertEqual(saved["history"][0]["scores"], (7, 9))
        self.assertIsInstance(saved["captured_at"], datetime)

    def test_08_no_grade_or_ranking_key(self):
        rec = _intervention()
        for bad in ("grade", "ranking", "rank", "diagnosis"):
            self.assertNotIn(bad, rec)


# ---------------------------------------------------------------------------
# 6. Tests — update_intervention()
# ---------------------------------------------------------------------------
class TestUpdateIntervention(unittest.TestCase):

    def test_09_does_not_mutate_original(self):
        rec = _intervention()
        original_status = rec["status"]
        update_intervention(rec, status="Approved")
        self.assertEqual(rec["status"], original_status)

    def test_10_status_updated(self):
        rec = _intervention()
        updated = update_intervention(rec, status="Approved")
        self.assertEqual(updated["status"], "Approved")

    def test_11_invalid_status_raises(self):
        rec = _intervention()
        with self.assertRaises(ValueError):
            update_intervention(rec, status="AutoApproved")

    def test_12_invalid_mtss_tier_raises(self):
        rec = _intervention()
        with self.assertRaises(ValueError):
            update_intervention(rec, mtss_tier=5)

    def test_13_all_statuses_valid(self):
        rec = _intervention()
        for s in INTERVENTION_STATUSES:
            updated = update_intervention(rec, status=s)
            self.assertEqual(updated["status"], s)

    def test_14_notes_updated(self):
        rec = _intervention()
        updated = update_intervention(rec, teacher_notes="New note")
        self.assertEqual(updated["teacher_notes"], "New note")

    def test_15_updated_at_changes(self):
        rec = _intervention()
        updated = update_intervention(
            rec, status="Approved", _now="2026-11-15T10:00:00+00:00"
        )
        self.assertEqual(updated["updated_at"], "2026-11-15T10:00:00+00:00")
        # original should retain its own timestamp
        self.assertEqual(rec["updated_at"], "2026-11-01T08:00:00+00:00")

    def test_default_updated_at_is_utc(self):
        updated = update_intervention(_intervention(), status="Approved")
        self.assertEqual(
            datetime.fromisoformat(updated["updated_at"]).utcoffset(),
            timedelta(0),
        )

    def test_updated_record_has_independent_evidence_snapshot(self):
        rec = _intervention(snapshot={"history": [{"scores": [7, 9]}]})
        updated = update_intervention(rec, status="Approved")

        updated["evidence_snapshot"]["history"][0]["scores"].append(10)

        self.assertEqual(
            rec["evidence_snapshot"]["history"][0]["scores"], [7, 9]
        )


# ---------------------------------------------------------------------------
# 7. Tests — add_intervention / replace_intervention / get / filter
# ---------------------------------------------------------------------------
class TestInterventionStore(unittest.TestCase):

    def test_16_add_appends(self):
        store = []
        rec = _intervention()
        result = add_intervention(store, rec)
        self.assertEqual(len(result), 1)

    def test_17_add_does_not_mutate_original(self):
        store = []
        add_intervention(store, _intervention())
        self.assertEqual(len(store), 0)

    def test_18_add_duplicate_active_raises(self):
        rec = _intervention()
        store = add_intervention([], rec)
        # Same student + skill, still Proposed (active)
        rec2 = _intervention(_id="test_id_002")
        with self.assertRaises(ValueError):
            add_intervention(store, rec2)

    def test_19_add_allows_after_completed(self):
        rec = _intervention(_id="id1")
        completed = update_intervention(rec, status="Completed")
        store = add_intervention([], completed)
        rec2 = _intervention(_id="id2")
        result = add_intervention(store, rec2)
        self.assertEqual(len(result), 2)

    def test_20_add_allows_after_dismissed(self):
        rec = _intervention(_id="id1")
        dismissed = update_intervention(rec, status="Dismissed")
        store = add_intervention([], dismissed)
        rec2 = _intervention(_id="id2")
        result = add_intervention(store, rec2)
        self.assertEqual(len(result), 2)

    def test_21_replace_updates_record(self):
        rec = _intervention()
        store = add_intervention([], rec)
        updated = update_intervention(rec, status="Approved")
        new_store = replace_intervention(store, updated)
        self.assertEqual(new_store[0]["status"], "Approved")

    def test_replace_rejects_evidence_snapshot_changes(self):
        rec = _intervention(snapshot={"history": [{"scores": [7, 9]}]})
        store = add_intervention([], rec)
        updated = update_intervention(rec, status="Approved")
        updated["evidence_snapshot"]["history"][0]["scores"].append(10)

        with self.assertRaisesRegex(ValueError, "evidence_snapshot cannot be changed"):
            replace_intervention(store, updated)

    def test_replace_keeps_snapshot_independent_from_replacement_record(self):
        rec = _intervention(snapshot={"history": [{"scores": [7, 9]}]})
        store = add_intervention([], rec)
        updated = update_intervention(rec, status="Approved")
        new_store = replace_intervention(store, updated)

        updated["evidence_snapshot"]["history"][0]["scores"].append(10)

        self.assertEqual(
            new_store[0]["evidence_snapshot"]["history"][0]["scores"], [7, 9]
        )

    def test_22_replace_not_found_raises(self):
        rec = _intervention(_id="xxx")
        store = []
        with self.assertRaises(ValueError):
            replace_intervention(store, rec)

    def test_23_get_found(self):
        rec = _intervention()
        store = add_intervention([], rec)
        found = get_intervention(store, rec["id"])
        self.assertIsNotNone(found)

    def test_24_get_not_found_returns_none(self):
        result = get_intervention([], "nope")
        self.assertIsNone(result)

    def test_25_student_interventions_filters_by_student(self):
        s01 = _intervention("S01", _id="id_s01")
        s02 = new_intervention("S02", "vocab", "Vocab", "r", "a", _id="id_s02",
                               _now="2026-11-01T09:00:00+00:00")
        store = add_intervention(add_intervention([], s01), s02)
        result = student_interventions(store, "S01")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["student_code"], "S01")

    def test_student_interventions_sorts_legacy_and_utc_timestamps(self):
        legacy = _intervention(student="S01", _id="legacy")
        legacy["created_at"] = "2026-11-15T10:00:00"
        legacy["updated_at"] = "2026-11-15T10:00:00"
        legacy_instant = datetime.fromisoformat(legacy["created_at"]).astimezone(
            timezone.utc
        )
        newer = _intervention(
            student="S01",
            _id="newer",
            _now=(legacy_instant + timedelta(minutes=1)).isoformat(),
        )

        result = student_interventions([legacy, newer], "S01")
        self.assertEqual([record["id"] for record in result], ["newer", "legacy"])
        self.assertEqual(legacy["created_at"], "2026-11-15T10:00:00")

        updated_order = sorted(
            [legacy, newer],
            key=lambda record: timestamp_sort_key(record["updated_at"]),
            reverse=True,
        )
        self.assertEqual([record["id"] for record in updated_order], ["newer", "legacy"])
        self.assertEqual(legacy["updated_at"], "2026-11-15T10:00:00")

    def test_26_active_interventions_excludes_completed_dismissed(self):
        r1 = _intervention(_id="id1")
        r2 = new_intervention("S02", "vocab", "Vocab", "r", "a", _id="id2",
                               _now="2026-11-01T09:00:00+00:00")
        c1 = update_intervention(r1, status="Completed")
        store = [c1, r2]
        result = active_interventions(store)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "id2")


# ---------------------------------------------------------------------------
# 8. Tests — flag_students_for_intervention()
# ---------------------------------------------------------------------------
class TestFlagStudents(unittest.TestCase):

    def _setup_skills_and_assessments(self):
        skills = [_skill("Inference", skill_id="inference")]
        assessments = [
            _ass("inference", "S01", 2.0, date="2026-11-01"),
            _ass("inference", "S01", 3.0, date="2026-11-10"),
        ]
        return skills, assessments

    def test_27_flags_low_mastery_student(self):
        skills, ass = self._setup_skills_and_assessments()
        flags = flag_students_for_intervention(["S01"], skills, ass, [])
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["student_code"], "S01")

    def test_28_no_flag_insufficient_assessments(self):
        skills = [_skill("Inference", skill_id="inference")]
        ass = [_ass("inference", "S01", 2.0)]  # only 1 assessment
        flags = flag_students_for_intervention(["S01"], skills, ass, [])
        self.assertEqual(len(flags), 0)

    def test_29_no_flag_good_mastery(self):
        skills = [_skill("Inference", skill_id="inference")]
        ass = [
            _ass("inference", "S01", 9.0, date="2026-11-01"),
            _ass("inference", "S01", 9.5, date="2026-11-10"),
        ]
        flags = flag_students_for_intervention(["S01"], skills, ass, [])
        self.assertEqual(len(flags), 0)

    def test_30_no_flag_when_active_intervention_exists(self):
        """If an active intervention already exists, no new flag should be raised."""
        skills, ass = self._setup_skills_and_assessments()
        existing = [_intervention("S01", "inference")]
        flags = flag_students_for_intervention(["S01"], skills, ass, existing)
        self.assertEqual(len(flags), 0)

    def test_31_flag_raised_after_intervention_completed(self):
        """After completion, a new flag CAN be raised if mastery is still low."""
        skills, ass = self._setup_skills_and_assessments()
        completed = update_intervention(_intervention("S01", "inference"), status="Completed")
        flags = flag_students_for_intervention(["S01"], skills, ass, [completed])
        self.assertEqual(len(flags), 1)

    def test_32_participation_alone_does_not_flag(self):
        """With no assessments (only participation), no flag is raised."""
        skills = [_skill("Inference", skill_id="inference")]
        flags = flag_students_for_intervention(["S01"], skills, [], [])
        self.assertEqual(len(flags), 0)

    def test_33_flag_has_required_keys(self):
        skills, ass = self._setup_skills_and_assessments()
        flags = flag_students_for_intervention(["S01"], skills, ass, [])
        self.assertEqual(len(flags), 1)
        flag = flags[0]
        for key in ("student_code", "skill_id", "skill_name", "mastery_level",
                    "mean_pct", "assessment_count", "suggested_action",
                    "reason_template"):
            self.assertIn(key, flag, msg=f"Flag missing key: {key}")

    def test_34_flag_mastery_level_is_support_level(self):
        skills, ass = self._setup_skills_and_assessments()
        flags = flag_students_for_intervention(["S01"], skills, ass, [])
        self.assertIn(flags[0]["mastery_level"], {"Beginning", "Emerging"})

    def test_35_no_fabricated_data_no_skills(self):
        flags = flag_students_for_intervention(["S01"], [], [], [])
        self.assertEqual(flags, [])

    def test_36_min_assessments_for_flag_constant(self):
        self.assertGreaterEqual(MIN_ASSESSMENTS_FOR_FLAG, 2)


# ---------------------------------------------------------------------------
# 9. Tests — new_progress_checkpoint()
# ---------------------------------------------------------------------------
class TestProgressCheckpoint(unittest.TestCase):

    def test_37_valid_checkpoint(self):
        cp = _checkpoint("int1", "S01", "inference", 7.0)
        self.assertEqual(cp["score"], 7.0)
        self.assertEqual(cp["intervention_id"], "int1")

    def test_default_timestamp_is_utc_and_date_is_preserved(self):
        cp = new_progress_checkpoint(
            "int1", "S01", "inference", 7.0, max_score=10.0, date="2026-11-14"
        )
        self.assertEqual(datetime.fromisoformat(cp["created_at"]).utcoffset(), timedelta(0))
        self.assertEqual(cp["date"], "2026-11-14")

    def test_38_max_score_zero_raises(self):
        with self.assertRaises(ValueError):
            new_progress_checkpoint("int1", "S01", "sk", 5.0, max_score=0.0)

    def test_39_negative_score_raises(self):
        with self.assertRaises(ValueError):
            new_progress_checkpoint("int1", "S01", "sk", -1.0, max_score=10.0)

    def test_40_score_exceeds_max_raises(self):
        with self.assertRaises(ValueError):
            new_progress_checkpoint("int1", "S01", "sk", 11.0, max_score=10.0)

    def test_41_zero_score_valid(self):
        cp = new_progress_checkpoint("int1", "S01", "sk", 0.0, max_score=10.0)
        self.assertEqual(cp["score"], 0.0)

    def test_42_has_required_keys(self):
        cp = _checkpoint("int1", "S01", "sk", 5.0)
        for key in ("id", "intervention_id", "student_code", "skill_id",
                    "date", "score", "max_score", "notes", "created_at"):
            self.assertIn(key, cp)

    def test_43_intervention_checkpoints_filters_and_sorts(self):
        cp1 = _checkpoint("int1", "S01", "sk", 5.0, date="2026-11-10")
        cp2 = _checkpoint("int1", "S01", "sk", 7.0, date="2026-11-05")
        cp3 = _checkpoint("int2", "S01", "sk", 8.0, date="2026-11-01")
        result = intervention_checkpoints([cp1, cp2, cp3], "int1")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["date"], "2026-11-05")  # ascending

    def test_44_intervention_checkpoints_empty(self):
        result = intervention_checkpoints([], "int1")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# 10. Tests — compare_before_after()
# ---------------------------------------------------------------------------
class TestCompareBeforeAfter(unittest.TestCase):

    def _snap(self, mean_pct=35.0, count=2):
        return {"mean_pct": mean_pct, "count": count}

    def test_45_no_checkpoints_returns_na(self):
        result = compare_before_after(self._snap(), [])
        self.assertEqual(result["direction"], "N/A")
        self.assertFalse(result["sufficient_data"])
        self.assertIsNone(result["post_mean_pct"])

    def test_46_improvement_detected(self):
        snap = self._snap(mean_pct=30.0)
        checks = [_checkpoint("i1", "S01", "sk", 8.0, date="2026-11-10")]
        result = compare_before_after(snap, checks)
        self.assertEqual(result["direction"], "improved")

    def test_47_decline_detected(self):
        snap = self._snap(mean_pct=85.0)
        checks = [_checkpoint("i1", "S01", "sk", 2.0, date="2026-11-10")]
        result = compare_before_after(snap, checks)
        self.assertEqual(result["direction"], "declined")

    def test_48_stable_detected(self):
        snap = self._snap(mean_pct=70.0)
        checks = [_checkpoint("i1", "S01", "sk", 7.0, date="2026-11-10")]
        result = compare_before_after(snap, checks)
        self.assertEqual(result["direction"], "stable")

    def test_49_no_pre_data_returns_na(self):
        result = compare_before_after({}, [_checkpoint("i1", "S01", "sk", 7.0)])
        self.assertEqual(result["direction"], "N/A")
        self.assertIsNone(result["delta_pct"])

    def test_50_sufficient_data_true_with_checkpoints(self):
        snap = self._snap()
        checks = [_checkpoint("i1", "S01", "sk", 7.0)]
        result = compare_before_after(snap, checks)
        self.assertTrue(result["sufficient_data"])

    def test_51_no_diagnosis_key_in_result(self):
        result = compare_before_after(self._snap(), [])
        for bad in ("diagnosis", "grade", "classification", "mtss_tier"):
            self.assertNotIn(bad, result)

    def test_52_delta_pct_computed_correctly(self):
        snap = self._snap(mean_pct=40.0)
        checks = [_checkpoint("i1", "S01", "sk", 8.0)]  # 80%
        result = compare_before_after(snap, checks)
        self.assertAlmostEqual(result["delta_pct"], 40.0, places=1)


# ---------------------------------------------------------------------------
# 11. Tests — Design constraints
# ---------------------------------------------------------------------------
class TestDesignConstraints(unittest.TestCase):

    def test_53_interventions_module_no_streamlit(self):
        path = os.path.join(HERE, "shared", "interventions.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("import streamlit", src)

    def test_54_new_intervention_always_proposed(self):
        """No matter what, a new intervention starts as Proposed."""
        rec = new_intervention("S01", "sk", "Skill", "r", "a")
        self.assertEqual(rec["status"], "Proposed")

    def test_55_cannot_create_intervention_as_approved(self):
        """There is no parameter to create an intervention as Approved."""
        # new_intervention does not accept status parameter at all
        import inspect
        sig = inspect.signature(new_intervention)
        self.assertNotIn("status", sig.parameters)

    def test_56_mtss_tiers_describe_support_not_identity(self):
        """MTSS tiers 1-3 must exist and tier 0 = not set."""
        self.assertIn(0, MTSS_TIERS)
        en_0, _ = MTSS_TIERS[0]
        self.assertIn("not set", en_0.lower())

    def test_57_intervention_checkpoints_do_not_mutate_original(self):
        cp_list = [_checkpoint("i1", "S01", "sk", 5.0)]
        original = list(cp_list)
        intervention_checkpoints(cp_list, "i1")
        self.assertEqual(cp_list, original)

    def test_58_flag_does_not_mutate_assessments(self):
        skills = [_skill("Inference", skill_id="inference")]
        ass = [
            _ass("inference", "S01", 2.0, date="2026-11-01"),
            _ass("inference", "S01", 3.0, date="2026-11-10"),
        ]
        original = list(ass)
        flag_students_for_intervention(["S01"], skills, ass, [])
        self.assertEqual(ass, original)

    def test_59_replace_does_not_mutate_original_list(self):
        rec = _intervention()
        store = add_intervention([], rec)
        original_store = list(store)
        updated = update_intervention(rec, status="Approved")
        replace_intervention(store, updated)
        self.assertEqual(store, original_store)


# ---------------------------------------------------------------------------
# 12. Tests — State initialisation
# ---------------------------------------------------------------------------
class TestStateInit(unittest.TestCase):

    def _src(self, filename):
        path = os.path.join(HERE, "shared", filename)
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_60_interventions_in_state(self):
        self.assertIn("interventions", self._src("state.py"))

    def test_61_intervention_checkpoints_in_state(self):
        self.assertIn("intervention_checkpoints", self._src("state.py"))

    def test_62_intervention_student_code_in_state(self):
        self.assertIn("intervention_student_code", self._src("state.py"))

    def test_63_mutable_includes_interventions(self):
        src = self._src("state.py")
        self.assertIn('"interventions"', src)
        self.assertIn('"intervention_checkpoints"', src)


# ---------------------------------------------------------------------------
# 13. Tests — App wiring
# ---------------------------------------------------------------------------
class TestInterventionsAppWiring(unittest.TestCase):

    def _app_src(self):
        path = os.path.join(HERE, "app.py")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_64_nav_entry_exists(self):
        self.assertIn("interventions", self._app_src())

    def test_65_nav_bilingual(self):
        src = self._app_src()
        self.assertIn("Interventions", src)
        self.assertIn("التدخلات", src)

    def test_66_router_calls_int_render(self):
        self.assertIn("_int_render()", self._app_src())

    def test_67_interventions_py_exists(self):
        path = os.path.join(HERE, "shared", "interventions.py")
        self.assertTrue(os.path.isfile(path))

    def test_68_interventions_page_exists(self):
        path = os.path.join(HERE, "pages", "interventions.py")
        self.assertTrue(os.path.isfile(path))

    def test_69_student_profile_links_to_interventions(self):
        path = os.path.join(HERE, "pages", "student_profile.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("interventions", src)
        self.assertIn("intervention_student_code", src)

    def test_70_academic_progress_links_to_interventions(self):
        path = os.path.join(HERE, "pages", "academic_progress.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("interventions", src)
        self.assertIn("intervention_student_code", src)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== SchoolFlow AI — Interventions & Recommendations Tests ===\n")
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = None
    suite = unittest.TestSuite()
    for cls in [
        TestNewIntervention,
        TestUpdateIntervention,
        TestInterventionStore,
        TestFlagStudents,
        TestProgressCheckpoint,
        TestCompareBeforeAfter,
        TestDesignConstraints,
        TestStateInit,
        TestInterventionsAppWiring,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print()
    total = result.testsRun
    if result.wasSuccessful():
        print("=" * 58)
        print(f"  ALL {total} INTERVENTIONS TESTS PASSED")
        print("=" * 58)
    else:
        print(f"FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}")
        raise SystemExit(1)
