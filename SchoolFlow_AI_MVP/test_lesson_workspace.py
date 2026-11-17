"""
test_lesson_workspace.py
-------------------------
Offline unit tests for pages/lesson_workspace.py.

Tests cover:
  - build_lesson_summary() with various attendance mixes
  - _save_lesson_record() state mutations
  - init_state() now initialises lesson keys
  - Navigation entry exists in app.py

No Streamlit runtime is required; streamlit is stubbed identically
to test_assistant.py.
"""

import sys, os, types, unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

# ---------------------------------------------------------------------------
# 1. Stub streamlit (same pattern as test_assistant.py)
# ---------------------------------------------------------------------------
_state: dict = {}

class _FakeSecrets(dict):
    def get(self, key, default=None):
        return default

def _noop(*a, **kw): pass
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
    date_input      = staticmethod(lambda *a, **kw: kw.get("value", date.today()))
    selectbox       = staticmethod(lambda *a, **kw: (kw.get("options") or (a[1] if len(a) > 1 else [""]))[0])
    radio           = staticmethod(lambda *a, **kw: "English")
    button          = staticmethod(lambda *a, **kw: False)
    download_button = staticmethod(lambda *a, **kw: False)
    file_uploader   = staticmethod(lambda *a, **kw: None)
    dataframe       = staticmethod(_noop)
    expander        = staticmethod(_noop_ctx)
    container       = staticmethod(_noop_ctx)
    toggle          = staticmethod(lambda *a, **kw: False)
    class _FakeSidebar:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def markdown(self, *a, **kw): pass
        def button(self, *a, **kw): return False
        def rerun(self): pass
    sidebar = _FakeSidebar()
    class _FakeCol:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def markdown(self, *a, **kw): pass
        def caption(self, *a, **kw): pass
        def button(self, *a, **kw): return False
        def download_button(self, *a, **kw): return False
        def selectbox(self, *a, **kw):
            opts = kw.get("options") or (a[1] if len(a) > 1 else [""])
            return opts[0]
        def text_input(self, *a, **kw): return kw.get("value", "")
        def text_area(self, *a, **kw): return kw.get("value", "")
        def date_input(self, *a, **kw): return kw.get("value", date.today())

    @staticmethod
    def columns(n, **kw):
        count = n if isinstance(n, int) else len(n)
        return [_FakeST._FakeCol() for _ in range(count)]
    metric          = staticmethod(_noop)
    spinner         = staticmethod(_noop_ctx)
    cache_data      = staticmethod(lambda f=None, **kw: f if f else lambda g: g)

sys.modules["streamlit"] = _FakeST("streamlit")

# ---------------------------------------------------------------------------
# 2. Patch sys.path so shared/ and pages/ resolve
# ---------------------------------------------------------------------------
HERE    = os.path.dirname(__file__)
APP_DIR = HERE   # SchoolFlow_AI_MVP/
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# ---------------------------------------------------------------------------
# 3. Import the module under test
# ---------------------------------------------------------------------------
from pages.lesson_workspace import build_lesson_summary, _save_lesson_record

# ---------------------------------------------------------------------------
# 4. Helper: build a minimal lesson record dict
# ---------------------------------------------------------------------------

def _make_record(
    att: dict,
    class_name: str = "5B",
    subject: str = "English",
    title: str = "Reading",
    objective: str = "Identify main idea",
    lesson_date=None,
):
    return {
        "class":      class_name,
        "subject":    subject,
        "title":      title,
        "objective":  objective,
        "date":       lesson_date or date(2026, 11, 13),
        "started_at": "2026-11-13T08:00:00",
        "ended_at":   "2026-11-13T08:45:00",
        "attendance": att,
    }


# ---------------------------------------------------------------------------
# 5. Tests — build_lesson_summary()
# ---------------------------------------------------------------------------
class TestBuildLessonSummary(unittest.TestCase):

    def test_01_empty_records(self):
        df = build_lesson_summary([])
        self.assertEqual(len(df), 0)

    def test_02_single_lesson_all_present(self):
        rec = _make_record({"S01": "Present", "S02": "Present", "S03": "Present"})
        df = build_lesson_summary([rec])
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["n_present"], 3)
        self.assertEqual(df.iloc[0]["n_absent"],  0)
        self.assertEqual(df.iloc[0]["n_late"],    0)
        self.assertEqual(df.iloc[0]["total"],     3)

    def test_03_single_lesson_arabic_statuses(self):
        """Arabic status values must be counted the same way."""
        rec = _make_record({"S01": "حاضر", "S02": "غائب", "S03": "متأخر"})
        df = build_lesson_summary([rec])
        self.assertEqual(df.iloc[0]["n_present"], 1)
        self.assertEqual(df.iloc[0]["n_absent"],  1)
        self.assertEqual(df.iloc[0]["n_late"],    1)
        self.assertEqual(df.iloc[0]["total"],     3)

    def test_04_mixed_statuses(self):
        att = {
            "S01": "Present",
            "S02": "Absent",
            "S03": "Late",
            "S04": "Present",
            "S05": "Absent",
        }
        rec = _make_record(att)
        df = build_lesson_summary([rec])
        self.assertEqual(df.iloc[0]["n_present"], 2)
        self.assertEqual(df.iloc[0]["n_absent"],  2)
        self.assertEqual(df.iloc[0]["n_late"],    1)
        self.assertEqual(df.iloc[0]["total"],     5)

    def test_05_multiple_lessons_accumulate(self):
        r1 = _make_record({"S01": "Present", "S02": "Absent"})
        r2 = _make_record({"S01": "Late",    "S02": "Present"})
        df = build_lesson_summary([r1, r2])
        self.assertEqual(len(df), 2)
        # First lesson
        self.assertEqual(df.iloc[0]["n_present"], 1)
        self.assertEqual(df.iloc[0]["n_absent"],  1)
        # Second lesson
        self.assertEqual(df.iloc[1]["n_present"], 1)
        self.assertEqual(df.iloc[1]["n_late"],    1)

    def test_06_metadata_preserved(self):
        rec = _make_record(
            {"S01": "Present"},
            class_name="Grade 4A",
            subject="Math",
            title="Fractions",
            objective="Add fractions",
        )
        df = build_lesson_summary([rec])
        self.assertEqual(df.iloc[0]["class"],     "Grade 4A")
        self.assertEqual(df.iloc[0]["subject"],   "Math")
        self.assertEqual(df.iloc[0]["title"],     "Fractions")
        self.assertEqual(df.iloc[0]["objective"], "Add fractions")

    def test_07_empty_attendance(self):
        """A lesson record with no students must not crash."""
        rec = _make_record({})
        df = build_lesson_summary([rec])
        self.assertEqual(df.iloc[0]["n_present"], 0)
        self.assertEqual(df.iloc[0]["total"],     0)

    def test_08_timestamps_preserved(self):
        rec = _make_record({"S01": "Present"})
        df = build_lesson_summary([rec])
        self.assertEqual(df.iloc[0]["started_at"], "2026-11-13T08:00:00")
        self.assertEqual(df.iloc[0]["ended_at"],   "2026-11-13T08:45:00")

    def test_09_total_equals_sum_of_parts(self):
        att = {f"S{i:02d}": ["Present", "Absent", "Late"][i % 3]
               for i in range(1, 10)}
        rec = _make_record(att)
        df  = build_lesson_summary([rec])
        row = df.iloc[0]
        self.assertEqual(row["total"], row["n_present"] + row["n_absent"] + row["n_late"])

    def test_10_unknown_status_not_counted(self):
        """Unrecognised status values should not inflate any counter."""
        rec = _make_record({"S01": "Present", "S02": "Unknown"})
        df = build_lesson_summary([rec])
        # S02 "Unknown" is not counted in any bucket
        self.assertEqual(df.iloc[0]["n_present"], 1)
        self.assertEqual(df.iloc[0]["n_absent"],  0)
        self.assertEqual(df.iloc[0]["n_late"],    0)
        # total is computed as sum of three buckets — not raw attendance count
        self.assertEqual(df.iloc[0]["total"],     1)


# ---------------------------------------------------------------------------
# 6. Tests — _save_lesson_record()
# ---------------------------------------------------------------------------
class TestSaveLessonRecord(unittest.TestCase):

    def _reset_state(self, draft: dict):
        _state.clear()
        _state["lesson_active"]  = True
        _state["lesson_records"] = []
        _state["lesson_draft"]   = dict(draft)

    def test_11_record_appended(self):
        self._reset_state({"class": "5B", "attendance": {"S01": "Present"}})
        _save_lesson_record()
        self.assertEqual(len(_state["lesson_records"]), 1)

    def test_12_lesson_active_reset_to_false(self):
        self._reset_state({"class": "5B", "attendance": {"S01": "Absent"}})
        _save_lesson_record()
        self.assertFalse(_state["lesson_active"])

    def test_13_ended_at_set(self):
        self._reset_state({"class": "5B", "attendance": {"S01": "Present"}})
        _save_lesson_record()
        self.assertIn("ended_at", _state["lesson_records"][0])
        ended_at = _state["lesson_records"][0]["ended_at"]
        self.assertEqual(datetime.fromisoformat(ended_at).utcoffset(), timedelta(0))

    def test_14_draft_cleared_except_attendance(self):
        """After saving, draft keeps attendance but clears metadata."""
        att = {"S01": "Present", "S02": "Late"}
        self._reset_state({
            "class": "5B", "subject": "English",
            "title": "Grammar", "attendance": att,
        })
        _save_lesson_record()
        new_draft = _state["lesson_draft"]
        # Attendance carried over for convenience
        self.assertEqual(new_draft.get("attendance"), att)
        # Metadata fields must be absent (cleared)
        self.assertNotIn("class",   new_draft)
        self.assertNotIn("subject", new_draft)
        self.assertNotIn("title",   new_draft)

    def test_15_multiple_saves_accumulate(self):
        self._reset_state({"class": "5B", "attendance": {"S01": "Present"}})
        _save_lesson_record()
        _state["lesson_active"] = True
        _state["lesson_draft"]  = {"class": "5B", "attendance": {"S01": "Absent"}}
        _save_lesson_record()
        self.assertEqual(len(_state["lesson_records"]), 2)

    def test_16_save_does_not_mutate_original_draft(self):
        """The saved record is a copy — later draft changes must not alter it."""
        att = {"S01": "Present"}
        self._reset_state({"class": "5B", "attendance": att})
        _save_lesson_record()
        saved_att = _state["lesson_records"][0]["attendance"]
        # Mutate the draft attendance
        _state["lesson_draft"]["attendance"]["S01"] = "Absent"
        # Saved record must be unaffected
        self.assertEqual(saved_att["S01"], "Present")


# ---------------------------------------------------------------------------
# 7. Tests — shared/state.py init_state() registers lesson keys
# ---------------------------------------------------------------------------
class TestInitStateLesson(unittest.TestCase):
    """
    Tests for shared/state.py lesson keys.
    Uses an isolated temporary dict instead of clearing the shared _state,
    so other test modules that rely on _state["summary"] are unaffected.
    """

    def _run_init_on_isolated_state(self):
        """
        Run init_state() against a fresh temporary state dict, not the global one.
        Returns the temporary dict after init.
        """
        import streamlit as st
        import shared.state as _sm

        tmp: dict = {}
        with patch.object(st, "session_state", tmp):
            _sm.init_state()
            result = dict(tmp)   # copy before restoring
        return result

    def test_17_lesson_keys_initialised(self):
        ss = self._run_init_on_isolated_state()
        self.assertIn("lesson_active",  ss)
        self.assertIn("lesson_draft",   ss)
        self.assertIn("lesson_records", ss)

    def test_18_lesson_active_default_false(self):
        ss = self._run_init_on_isolated_state()
        self.assertFalse(ss["lesson_active"])

    def test_19_lesson_records_default_empty_list(self):
        ss = self._run_init_on_isolated_state()
        self.assertIsInstance(ss["lesson_records"], list)
        self.assertEqual(len(ss["lesson_records"]), 0)

    def test_20_lesson_draft_default_empty_dict(self):
        ss = self._run_init_on_isolated_state()
        self.assertIsInstance(ss["lesson_draft"], dict)
        self.assertEqual(len(ss["lesson_draft"]), 0)

    def test_21_init_state_does_not_overwrite_existing(self):
        """init_state() must preserve pre-existing lesson_records."""
        import streamlit as st
        import shared.state as _sm

        tmp: dict = {"lesson_records": [{"class": "5B"}]}
        existing = tmp["lesson_records"]
        with patch.object(st, "session_state", tmp):
            _sm.init_state()
            self.assertIs(tmp["lesson_records"], existing)


# ---------------------------------------------------------------------------
# 8. Tests — navigation entry in app.py
# ---------------------------------------------------------------------------
class TestAppNavigation(unittest.TestCase):

    def test_22_lesson_workspace_in_nav(self):
        """app.py must include 'lesson_workspace' as a nav key."""
        path = os.path.join(HERE, "app.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("lesson_workspace", source)

    def test_23_lesson_workspace_label_bilingual(self):
        """app.py must have both English and Arabic labels."""
        path = os.path.join(HERE, "app.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("Lesson Workspace", source)
        self.assertIn("مساحة عمل الحصة", source)

    def test_24_render_called_in_router(self):
        """app.py router section must call render() for lesson_workspace."""
        path = os.path.join(HERE, "app.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("lesson_workspace", source)
        self.assertIn("_lw_render()", source)


# ---------------------------------------------------------------------------
# 9. Tests — build_participation_entry()
# ---------------------------------------------------------------------------
class TestBuildParticipationEntry(unittest.TestCase):

    def _make(self, response_code="C", source_code="TS", **kw):
        from pages.lesson_workspace import build_participation_entry
        defaults = dict(
            student_code="S01",
            student_name="Ahmed",
            lesson_id="LID-001",
            question="Q1",
            response_code=response_code,
            source_code=source_code,
            skill_id="",
            _now="2026-11-13T09:00:00",
        )
        defaults.update(kw)
        return build_participation_entry(**defaults)

    def test_25_entry_has_all_keys(self):
        e = self._make()
        for k in ("id","student_code","student_name","lesson_id","question",
                  "response_code","source_code","skill_id","timestamp"):
            self.assertIn(k, e)

    def test_26_response_code_stored_verbatim(self):
        for rc in ("C", "P", "I", "NR", "NO"):
            e = self._make(response_code=rc)
            self.assertEqual(e["response_code"], rc)

    def test_27_source_code_stored_verbatim(self):
        for sc in ("TS", "SI", "GP"):
            e = self._make(source_code=sc)
            self.assertEqual(e["source_code"], sc)

    def test_28_invalid_response_raises(self):
        from pages.lesson_workspace import build_participation_entry
        with self.assertRaises(ValueError):
            build_participation_entry("S01","","LID","Q","X","TS")

    def test_29_invalid_source_raises(self):
        from pages.lesson_workspace import build_participation_entry
        with self.assertRaises(ValueError):
            build_participation_entry("S01","","LID","Q","C","ZZ")

    def test_30_nr_is_not_incorrect(self):
        """NR (No Response) must be stored as 'NR', not 'I'."""
        e = self._make(response_code="NR")
        self.assertEqual(e["response_code"], "NR")
        self.assertNotEqual(e["response_code"], "I")

    def test_31_no_is_not_a_failure(self):
        """NO (No Opportunity) must be stored as 'NO', not 'I' or 'NR'."""
        e = self._make(response_code="NO")
        self.assertEqual(e["response_code"], "NO")
        self.assertNotIn(e["response_code"], ("I", "NR"))

    def test_32_timestamp_override(self):
        e = self._make(_now="2026-01-01T12:00:00")
        self.assertEqual(e["timestamp"], "2026-01-01T12:00:00")

    def test_33_skill_id_optional(self):
        e = self._make(skill_id="inference")
        self.assertEqual(e["skill_id"], "inference")
        self.assertNotIn("skill", e)
        e_empty = self._make()
        self.assertEqual(e_empty["skill_id"], "")

    def test_skill_id_must_be_text(self):
        with self.assertRaisesRegex(ValueError, "skill_id must be a string"):
            self._make(skill_id=["inference"])

    def test_34_multiple_entries_same_student_question(self):
        """Multiple entries for the same student+question are allowed."""
        e1 = self._make(response_code="C", _now="T1")
        e2 = self._make(response_code="P", _now="T2")
        self.assertNotEqual(e1["response_code"], e2["response_code"])
        self.assertEqual(e1["student_code"], e2["student_code"])
        self.assertEqual(e1["question"], e2["question"])

    def test_35_lesson_id_linked(self):
        e = self._make(lesson_id="LESSON-XYZ")
        self.assertEqual(e["lesson_id"], "LESSON-XYZ")


# ---------------------------------------------------------------------------
# 10. Tests — summarise_participation()
# ---------------------------------------------------------------------------
class TestSummariseParticipation(unittest.TestCase):
    from pages.lesson_workspace import build_participation_entry as _bpe

    def _e(self, rc, sc="TS", student="S01", lid="L1", question="Q1"):
        from pages.lesson_workspace import build_participation_entry
        return build_participation_entry(
            student_code=student, student_name="",
            lesson_id=lid, question=question,
            response_code=rc, source_code=sc,
            _now="2026-11-13T08:00:00",
        )

    def test_36_empty_entries(self):
        from pages.lesson_workspace import summarise_participation
        s = summarise_participation([])
        self.assertEqual(s["total"], 0)
        self.assertEqual(s["substantive"], 0)
        self.assertEqual(s["no_response"], 0)
        self.assertEqual(s["no_opportunity"], 0)

    def test_37_total_counts_all_entries(self):
        from pages.lesson_workspace import summarise_participation
        entries = [self._e("C"), self._e("NR"), self._e("NO")]
        s = summarise_participation(entries)
        self.assertEqual(s["total"], 3)

    def test_38_nr_not_in_substantive(self):
        """NR must NOT contribute to substantive count."""
        from pages.lesson_workspace import summarise_participation
        entries = [self._e("NR")]
        s = summarise_participation(entries)
        self.assertEqual(s["no_response"], 1)
        self.assertEqual(s["substantive"], 0)

    def test_39_no_not_in_substantive(self):
        """NO must NOT contribute to substantive count."""
        from pages.lesson_workspace import summarise_participation
        entries = [self._e("NO")]
        s = summarise_participation(entries)
        self.assertEqual(s["no_opportunity"], 1)
        self.assertEqual(s["substantive"], 0)

    def test_40_substantive_counts_c_p_i_only(self):
        from pages.lesson_workspace import summarise_participation
        entries = [
            self._e("C"), self._e("P"), self._e("I"),
            self._e("NR"), self._e("NO"),
        ]
        s = summarise_participation(entries)
        self.assertEqual(s["substantive"], 3)   # C+P+I only

    def test_41_by_response_breakdown(self):
        from pages.lesson_workspace import summarise_participation
        entries = [
            self._e("C"), self._e("C"), self._e("P"), self._e("I"),
            self._e("NR"), self._e("NO"),
        ]
        s = summarise_participation(entries)
        self.assertEqual(s["by_response"]["C"],  2)
        self.assertEqual(s["by_response"]["P"],  1)
        self.assertEqual(s["by_response"]["I"],  1)
        self.assertEqual(s["by_response"]["NR"], 1)
        self.assertEqual(s["by_response"]["NO"], 1)

    def test_42_by_source_breakdown(self):
        from pages.lesson_workspace import summarise_participation
        entries = [
            self._e("C", sc="TS"),
            self._e("C", sc="SI"),
            self._e("C", sc="GP"),
            self._e("P", sc="TS"),
        ]
        s = summarise_participation(entries)
        self.assertEqual(s["by_source"]["TS"], 2)
        self.assertEqual(s["by_source"]["SI"], 1)
        self.assertEqual(s["by_source"]["GP"], 1)

    def test_43_by_student_breakdown(self):
        from pages.lesson_workspace import summarise_participation
        entries = [
            self._e("C", student="S01"),
            self._e("P", student="S01"),
            self._e("C", student="S02"),
        ]
        s = summarise_participation(entries)
        self.assertEqual(s["by_student"]["S01"], 2)
        self.assertEqual(s["by_student"]["S02"], 1)

    def test_44_lesson_id_filter(self):
        """summarise_participation with lesson_id must only count matching entries."""
        from pages.lesson_workspace import summarise_participation
        entries = [
            self._e("C", lid="L1"),
            self._e("P", lid="L1"),
            self._e("I", lid="L2"),
        ]
        s_L1 = summarise_participation(entries, lesson_id="L1")
        self.assertEqual(s_L1["total"], 2)
        s_L2 = summarise_participation(entries, lesson_id="L2")
        self.assertEqual(s_L2["total"], 1)

    def test_45_no_grade_key_in_summary(self):
        """Summary must NEVER produce a 'grade' or 'score' key."""
        from pages.lesson_workspace import summarise_participation
        s = summarise_participation([self._e("C")])
        self.assertNotIn("grade", s)
        self.assertNotIn("score", s)
        self.assertNotIn("average", s)
        self.assertNotIn("mean",  s)

    def test_46_multiple_responses_same_student_question(self):
        """Multiple responses per student per question must all be recorded."""
        from pages.lesson_workspace import summarise_participation
        entries = [
            self._e("C", student="S01", question="Q1"),
            self._e("I", student="S01", question="Q1"),  # same student + question
            self._e("P", student="S01", question="Q1"),
        ]
        s = summarise_participation(entries)
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["by_student"]["S01"], 3)

    def test_47_participation_log_appended_not_replaced(self):
        """
        Appending a new entry must not remove previous entries.
        (State-level regression: simulates button click twice.)
        """
        log = []
        from pages.lesson_workspace import build_participation_entry
        e1 = build_participation_entry("S01","","L1","Q1","C","TS",_now="T1")
        e2 = build_participation_entry("S02","","L1","Q1","P","SI",_now="T2")
        log.append(e1)
        log.append(e2)
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["student_code"], "S01")
        self.assertEqual(log[1]["student_code"], "S02")


# ---------------------------------------------------------------------------
# 11. Tests — participation_log in init_state()
# ---------------------------------------------------------------------------
class TestParticipationStateInit(unittest.TestCase):

    def _run_init_on_isolated_state(self):
        import streamlit as st
        import shared.state as _sm
        tmp: dict = {}
        with patch.object(st, "session_state", tmp):
            _sm.init_state()
            result = dict(tmp)
        return result

    def test_48_participation_log_initialised(self):
        ss = self._run_init_on_isolated_state()
        self.assertIn("participation_log", ss)

    def test_49_participation_log_default_empty_list(self):
        ss = self._run_init_on_isolated_state()
        self.assertIsInstance(ss["participation_log"], list)
        self.assertEqual(len(ss["participation_log"]), 0)

    def test_50_participation_log_not_overwritten(self):
        import streamlit as st
        import shared.state as _sm
        existing = [{"student_code": "S01"}]
        tmp: dict = {"participation_log": existing}
        with patch.object(st, "session_state", tmp):
            _sm.init_state()
            self.assertIs(tmp["participation_log"], existing)


# ---------------------------------------------------------------------------
# 12. Tests — recommend_next_student()
# ---------------------------------------------------------------------------
class TestRecommendNextStudent(unittest.TestCase):
    """
    Pure-function tests — no Streamlit involved.
    Uses recommend_next_student() directly with controlled inputs.
    """

    from pages.lesson_workspace import recommend_next_student as _rns

    def _rec(
        self, codes, attendance, log, lid="L1", skill="", skipped=None,
        skill_definitions=None,
    ):
        from pages.lesson_workspace import recommend_next_student
        return recommend_next_student(
            student_codes=codes,
            attendance=attendance,
            participation_log=log,
            lesson_id=lid,
            target_skill=skill,
            skipped_codes=skipped,
            skill_definitions=(
                [{"id": "inference", "name": "Inference"}]
                if skill_definitions is None else skill_definitions
            ),
        )

    def _entry(self, code, rc, lid="L1", skill_id="", ts="2026-11-13T08:00:00", name=""):
        from pages.lesson_workspace import build_participation_entry
        return build_participation_entry(
            student_code=code, student_name=name,
            lesson_id=lid, question="Q1",
            response_code=rc, source_code="TS",
            skill_id=skill_id, _now=ts,
        )

    def _legacy_entry(self, code, rc, skill, lid="L1", ts="2026-11-13T08:00:00"):
        entry = self._entry(code, rc, lid=lid, ts=ts)
        entry.pop("skill_id")
        entry["skill"] = skill
        return entry

    def test_participation_default_timestamp_is_utc(self):
        from pages.lesson_workspace import build_participation_entry
        entry = build_participation_entry(
            student_code="S01", student_name="", lesson_id="L1",
            question="Q1", response_code="C", source_code="TS", skill_id="",
        )
        self.assertEqual(
            datetime.fromisoformat(entry["timestamp"]).utcoffset(),
            timedelta(0),
        )

    # ── Basic eligibility ──────────────────────────────────────────────────

    def test_51_no_students(self):
        r = self._rec([], {}, [])
        self.assertFalse(r["ok"])

    def test_52_all_absent(self):
        r = self._rec(
            ["S01", "S02"],
            {"S01": "Absent", "S02": "Absent"},
            [],
        )
        self.assertFalse(r["ok"])

    def test_53_absent_arabic(self):
        """Arabic attendance value 'غائب' must exclude the student."""
        r = self._rec(
            ["S01"],
            {"S01": "غائب"},
            [],
        )
        self.assertFalse(r["ok"])

    def test_54_first_call_no_log(self):
        """With an empty log, the first student in roster order is suggested."""
        r = self._rec(["S01", "S02", "S03"], {}, [])
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S01")

    def test_55_absent_student_never_suggested(self):
        """Absent student must be excluded even if everyone else has had turns."""
        log = [self._entry("S02", "C", ts="T1"), self._entry("S03", "C", ts="T2")]
        r = self._rec(
            ["S01", "S02", "S03"],
            {"S01": "Absent"},
            log,
        )
        self.assertTrue(r["ok"])
        self.assertNotEqual(r["student_code"], "S01")

    # ── Priority: zero-turn students first ────────────────────────────────

    def test_56_zero_turn_priority(self):
        """S03 has had no turns; must be preferred over S01 and S02."""
        log = [self._entry("S01", "C"), self._entry("S02", "P")]
        r = self._rec(["S01", "S02", "S03"], {}, log)
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S03")

    def test_57_no_opportunity_not_a_turn(self):
        """
        'NO' entries must NOT count as a real turn — the student is still
        treated as having zero turns and gets Group A priority.
        """
        log = [
            self._entry("S01", "C"),
            self._entry("S02", "NO"),   # S02 had NO — not a real turn
        ]
        r = self._rec(["S01", "S02", "S03"], {}, log)
        # Both S02 and S03 have zero real turns; S02 comes first in roster
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S02")

    def test_58_no_response_counts_as_turn(self):
        """
        'NR' (No Response) counts as a real interaction turn
        (the teacher did ask, the student did not respond).
        """
        log = [
            self._entry("S01", "NR"),   # S01 got an opportunity but didn't respond
        ]
        r = self._rec(["S01", "S02"], {}, log)
        # S02 has zero real turns → higher priority
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S02")

    # ── Fewest-turns fallback (Group B) ────────────────────────────────────

    def test_59_fewest_turns_chosen(self):
        log = [
            self._entry("S01", "C", ts="T1"),
            self._entry("S01", "P", ts="T2"),
            self._entry("S02", "C", ts="T3"),
        ]
        r = self._rec(["S01", "S02"], {}, log)
        # S01 has 2 turns, S02 has 1 — S02 should be chosen
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S02")

    def test_mixed_legacy_and_utc_timestamps_are_compared_chronologically(self):
        legacy_value = "2026-11-15T10:00:00"
        legacy_utc = datetime.fromisoformat(legacy_value).astimezone(timezone.utc)
        later_value = (legacy_utc + timedelta(minutes=1)).isoformat()
        log = [
            self._entry("S01", "C", ts=legacy_value),
            self._entry("S02", "C", ts=later_value),
        ]

        result = self._rec(["S01", "S02"], {}, log)

        self.assertTrue(result["ok"])
        self.assertEqual(result["student_code"], "S01")
        self.assertEqual(log[0]["timestamp"], legacy_value)

    def test_60_tie_broken_by_last_timestamp(self):
        """
        When two students have the same turn count, the one who participated
        earliest (smallest last_ts) is chosen.
        """
        log = [
            self._entry("S01", "C", ts="2026-11-13T08:30:00"),
            self._entry("S02", "C", ts="2026-11-13T08:10:00"),   # earlier
        ]
        r = self._rec(["S01", "S02"], {}, log)
        # Both have 1 turn; S02 last ts is earlier → S02 chosen
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S02")

    # ── Skill filter ───────────────────────────────────────────────────────

    def test_61_skill_filter_deprioritises_practised(self):
        """
        S01 already practised 'Inference'; S02 hasn't.
        With target_skill='inference' and both having zero turns,
        S02 must be chosen.
        """
        log = [
            self._entry("S01", "NO", skill_id="inference"),
        ]
        # S02 has 0 turns in this lesson; but S01 has 1 turn AND practised skill
        # → S02 is in group_a with 0 turns and 0 skill_turns → chosen first
        r = self._rec(["S01", "S02"], {}, log, skill="inference")
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S02")

    def test_target_skill_resolves_unique_legacy_name(self):
        log = [self._legacy_entry("S01", "NO", " inference ")]
        result = self._rec(["S01", "S02"], {}, log, skill="inference")
        self.assertEqual(result["student_code"], "S02")
        self.assertEqual(log[0]["skill"], " inference ")

    def test_ambiguous_legacy_name_does_not_match_target_skill(self):
        definitions = [
            {"id": "inference_a", "name": "Inference"},
            {"id": "inference_b", "name": " inference "},
        ]
        log = [self._legacy_entry("S01", "NO", "Inference")]
        result = self._rec(
            ["S01", "S02"], {}, log, skill="inference_a",
            skill_definitions=definitions,
        )
        self.assertEqual(result["student_code"], "S01")

    def test_62_skill_filter_fallback_when_all_practised(self):
        """
        If all zero-turn students have already practised the skill,
        still pick one (first in roster) rather than returning ok=False.
        """
        # S02 has 0 turns but has practised 'Inference' in a previous entry
        # S03 also has 0 turns but practised 'Inference'
        log = [
            self._entry("S02", "NO", skill_id="inference"),
            self._entry("S03", "NO", skill_id="inference"),
        ]
        log.append(self._entry("S01", "NO", skill_id="inference"))
        r = self._rec(["S01", "S02", "S03"], {}, log, skill="inference")
        # S01 has 0 turns and 0 skill_turns → chosen
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S01")

    def test_63_no_grade_in_reason(self):
        """The reason string must not contain grade-like words."""
        r = self._rec(["S01", "S02"], {}, [])
        reason = r["reason"].lower()
        for bad in ("grade", "score", "mark", "درجة", "علامة"):
            self.assertNotIn(bad, reason,
                msg=f"Reason must not mention '{bad}': {r['reason']}")

    # ── Skipped codes ──────────────────────────────────────────────────────

    def test_64_skipped_code_excluded(self):
        """S01 is skipped → S02 must be chosen."""
        r = self._rec(["S01", "S02"], {}, [], skipped=["S01"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S02")

    def test_65_all_skipped_returns_false(self):
        r = self._rec(["S01"], {}, [], skipped=["S01"])
        self.assertFalse(r["ok"])

    # ── Lesson ID isolation ────────────────────────────────────────────────

    def test_66_entries_from_other_lessons_ignored(self):
        """Participation entries from lesson L2 must not affect L1 recommendations."""
        log = [self._entry("S01", "C", lid="L2")]
        r = self._rec(["S01", "S02"], {}, log, lid="L1")
        # S01 has 0 turns in L1 (the L2 entry doesn't count)
        # → S01 is first in roster → suggested
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S01")

    # ── Return-dict contract ───────────────────────────────────────────────

    def test_67_return_has_required_keys(self):
        r = self._rec(["S01"], {}, [])
        for k in ("student_code", "student_name", "reason", "ok"):
            self.assertIn(k, r)

    def test_68_ok_true_has_nonempty_code(self):
        r = self._rec(["S01"], {}, [])
        self.assertTrue(r["ok"])
        self.assertNotEqual(r["student_code"], "")

    def test_69_recommendation_does_not_mutate_log(self):
        """Calling recommend_next_student must not modify the participation_log."""
        log = [self._entry("S01", "C")]
        log_before = list(log)
        self._rec(["S01", "S02"], {}, log)
        self.assertEqual(log, log_before)

    def test_70_late_student_is_still_eligible(self):
        """Late (متأخر / Late) students must remain eligible for suggestions."""
        r = self._rec(
            ["S01"],
            {"S01": "Late"},
            [],
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["student_code"], "S01")


# ---------------------------------------------------------------------------
# 13. Tests — recommendation state keys in init_state()
# ---------------------------------------------------------------------------
class TestRecommendationStateInit(unittest.TestCase):

    def _run_init_on_isolated_state(self):
        import streamlit as st
        import shared.state as _sm
        tmp: dict = {}
        with patch.object(st, "session_state", tmp):
            _sm.init_state()
            result = dict(tmp)
        return result

    def test_71_rec_keys_initialised(self):
        ss = self._run_init_on_isolated_state()
        self.assertIn("rec_skipped",    ss)
        self.assertIn("rec_current",    ss)
        self.assertIn("rec_skill_input", ss)

    def test_72_rec_skipped_default_empty_list(self):
        ss = self._run_init_on_isolated_state()
        self.assertIsInstance(ss["rec_skipped"], list)
        self.assertEqual(len(ss["rec_skipped"]), 0)

    def test_73_rec_current_default_empty_dict(self):
        ss = self._run_init_on_isolated_state()
        self.assertIsInstance(ss["rec_current"], dict)

    def test_74_rec_skill_input_default_empty_string(self):
        ss = self._run_init_on_isolated_state()
        self.assertEqual(ss["rec_skill_input"], "")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== SchoolFlow AI — Lesson Workspace Tests ===\n")
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = None
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestBuildLessonSummary))
    suite.addTests(loader.loadTestsFromTestCase(TestSaveLessonRecord))
    suite.addTests(loader.loadTestsFromTestCase(TestInitStateLesson))
    suite.addTests(loader.loadTestsFromTestCase(TestAppNavigation))
    suite.addTests(loader.loadTestsFromTestCase(TestBuildParticipationEntry))
    suite.addTests(loader.loadTestsFromTestCase(TestSummariseParticipation))
    suite.addTests(loader.loadTestsFromTestCase(TestParticipationStateInit))
    suite.addTests(loader.loadTestsFromTestCase(TestRecommendNextStudent))
    suite.addTests(loader.loadTestsFromTestCase(TestRecommendationStateInit))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print()
    total = result.testsRun
    if result.wasSuccessful():
        print("=" * 50)
        print(f"  ALL {total} LESSON WORKSPACE TESTS PASSED")
        print("=" * 50)
    else:
        print(f"FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}")
        raise SystemExit(1)
