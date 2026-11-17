"""
test_gagne.py
-------------
Tests for shared/gagne.py — Gagné's Nine Events of Instruction.
Task 9 of SchoolFlow AI MVP.

All tests are pure Python (no Streamlit import needed).
"""

import sys
import os
import copy
import pytest

# ---------------------------------------------------------------------------
# Path setup — make shared/ importable from SchoolFlow_AI_MVP/
# ---------------------------------------------------------------------------
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "SchoolFlow_AI_MVP"),
)

# ---------------------------------------------------------------------------
# Lazy import wrapper (avoids hard failure if path is already on sys.path)
# ---------------------------------------------------------------------------
try:
    from shared.gagne import (
        GAGNE_EVENTS,
        EVENT_IDS,
        EVENT_BY_ID,
        PLAN_STATUSES,
        new_gagne_plan,
        get_plan_event,
        update_plan_event,
        plan_summary,
        events_done,
        events_skipped,
        events_pending,
    )
except ModuleNotFoundError:
    # Already on path (running from SchoolFlow_AI_MVP/)
    from shared.gagne import (
        GAGNE_EVENTS,
        EVENT_IDS,
        EVENT_BY_ID,
        PLAN_STATUSES,
        new_gagne_plan,
        get_plan_event,
        update_plan_event,
        plan_summary,
        events_done,
        events_skipped,
        events_pending,
    )


# ===========================================================================
# Constants
# ===========================================================================

class TestConstants:
    """Tests for the static data constants."""

    def test_gagne_events_count(self):
        assert len(GAGNE_EVENTS) == 9

    def test_event_ids_count(self):
        assert len(EVENT_IDS) == 9

    def test_event_by_id_count(self):
        assert len(EVENT_BY_ID) == 9

    def test_plan_statuses(self):
        assert set(PLAN_STATUSES) == {"planned", "in_progress", "done", "skipped"}

    def test_event_ids_match_events(self):
        for e in GAGNE_EVENTS:
            assert e["id"] in EVENT_IDS

    def test_event_by_id_values(self):
        for e in GAGNE_EVENTS:
            assert EVENT_BY_ID[e["id"]] is e

    def test_event_numbers_are_1_to_9(self):
        numbers = [e["number"] for e in GAGNE_EVENTS]
        assert sorted(numbers) == list(range(1, 10))

    def test_first_event_is_gain_attention(self):
        assert GAGNE_EVENTS[0]["id"] == "gain_attention"

    def test_last_event_is_retention_transfer(self):
        assert GAGNE_EVENTS[-1]["id"] == "retention_transfer"

    def test_every_event_has_required_keys(self):
        required = {
            "id", "number", "name_en", "name_ar",
            "description_en", "description_ar",
            "example_activities_en", "example_activities_ar",
        }
        for e in GAGNE_EVENTS:
            assert required <= set(e.keys()), f"Event {e['id']} missing keys"

    def test_every_event_name_en_nonempty(self):
        for e in GAGNE_EVENTS:
            assert e["name_en"], f"Event {e['id']} has empty name_en"

    def test_every_event_name_ar_nonempty(self):
        for e in GAGNE_EVENTS:
            assert e["name_ar"], f"Event {e['id']} has empty name_ar"

    def test_every_event_description_en_nonempty(self):
        for e in GAGNE_EVENTS:
            assert e["description_en"]

    def test_every_event_description_ar_nonempty(self):
        for e in GAGNE_EVENTS:
            assert e["description_ar"]

    def test_every_event_example_activities_en_nonempty(self):
        for e in GAGNE_EVENTS:
            assert len(e["example_activities_en"]) >= 1

    def test_every_event_example_activities_ar_nonempty(self):
        for e in GAGNE_EVENTS:
            assert len(e["example_activities_ar"]) >= 1

    def test_known_event_ids_present(self):
        known = [
            "gain_attention", "inform_objectives", "stimulate_recall",
            "present_content", "provide_guidance", "elicit_performance",
            "provide_feedback", "assess_performance", "retention_transfer",
        ]
        for eid in known:
            assert eid in EVENT_IDS

    def test_event_ids_are_unique(self):
        assert len(set(EVENT_IDS)) == len(EVENT_IDS)

    def test_event_numbers_are_unique(self):
        numbers = [e["number"] for e in GAGNE_EVENTS]
        assert len(set(numbers)) == len(numbers)


# ===========================================================================
# new_gagne_plan
# ===========================================================================

class TestNewGagnePlan:
    """Tests for new_gagne_plan()."""

    def test_returns_list(self):
        plan = new_gagne_plan()
        assert isinstance(plan, list)

    def test_returns_nine_events(self):
        plan = new_gagne_plan()
        assert len(plan) == 9

    def test_all_statuses_are_planned(self):
        plan = new_gagne_plan()
        for pe in plan:
            assert pe["status"] == "planned"

    def test_all_notes_are_empty(self):
        plan = new_gagne_plan()
        for pe in plan:
            assert pe["notes"] == ""

    def test_all_activities_are_empty(self):
        plan = new_gagne_plan()
        for pe in plan:
            assert pe["activity"] == ""

    def test_all_question_ids_are_empty_list(self):
        plan = new_gagne_plan()
        for pe in plan:
            assert pe["question_ids"] == []

    def test_all_skill_ids_are_empty(self):
        plan = new_gagne_plan()
        for pe in plan:
            assert pe["skill_id"] == ""

    def test_all_duration_min_are_none(self):
        plan = new_gagne_plan()
        for pe in plan:
            assert pe["duration_min"] is None

    def test_event_ids_match_gagne_events_order(self):
        plan = new_gagne_plan()
        expected_ids = [e["id"] for e in GAGNE_EVENTS]
        actual_ids = [pe["event_id"] for pe in plan]
        assert actual_ids == expected_ids

    def test_returns_independent_copies(self):
        plan1 = new_gagne_plan()
        plan2 = new_gagne_plan()
        plan1[0]["status"] = "done"
        assert plan2[0]["status"] == "planned"

    def test_question_ids_lists_are_independent(self):
        plan1 = new_gagne_plan()
        plan2 = new_gagne_plan()
        plan1[0]["question_ids"].append("q1")
        assert plan2[0]["question_ids"] == []

    def test_plan_event_has_all_keys(self):
        plan = new_gagne_plan()
        required = {"event_id", "status", "notes", "activity",
                    "question_ids", "skill_id", "duration_min"}
        for pe in plan:
            assert required <= set(pe.keys())


# ===========================================================================
# get_plan_event
# ===========================================================================

class TestGetPlanEvent:
    """Tests for get_plan_event()."""

    def test_returns_correct_event(self):
        plan = new_gagne_plan()
        pe = get_plan_event(plan, "gain_attention")
        assert pe is not None
        assert pe["event_id"] == "gain_attention"

    def test_returns_last_event(self):
        plan = new_gagne_plan()
        pe = get_plan_event(plan, "retention_transfer")
        assert pe is not None
        assert pe["event_id"] == "retention_transfer"

    def test_returns_none_for_unknown_id(self):
        plan = new_gagne_plan()
        assert get_plan_event(plan, "nonexistent_event") is None

    def test_returns_none_for_empty_string(self):
        plan = new_gagne_plan()
        assert get_plan_event(plan, "") is None

    def test_returns_none_on_empty_plan(self):
        assert get_plan_event([], "gain_attention") is None

    def test_returns_dict(self):
        plan = new_gagne_plan()
        pe = get_plan_event(plan, "present_content")
        assert isinstance(pe, dict)

    def test_returns_reference_not_copy(self):
        """get_plan_event returns the actual dict inside the plan."""
        plan = new_gagne_plan()
        pe = get_plan_event(plan, "gain_attention")
        pe["notes"] = "mutated"
        assert plan[0]["notes"] == "mutated"

    def test_all_event_ids_findable(self):
        plan = new_gagne_plan()
        for eid in EVENT_IDS:
            assert get_plan_event(plan, eid) is not None


# ===========================================================================
# update_plan_event
# ===========================================================================

class TestUpdatePlanEvent:
    """Tests for update_plan_event() — immutable update semantics."""

    def test_returns_list(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "gain_attention", status="done")
        assert isinstance(result, list)

    def test_returns_nine_events(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "gain_attention", status="done")
        assert len(result) == 9

    def test_does_not_mutate_input(self):
        plan = new_gagne_plan()
        original = copy.deepcopy(plan)
        update_plan_event(plan, "gain_attention", status="done")
        assert plan == original

    def test_update_status(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "gain_attention", status="done")
        pe = get_plan_event(result, "gain_attention")
        assert pe["status"] == "done"

    def test_update_notes(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "inform_objectives", notes="Show objectives slide")
        pe = get_plan_event(result, "inform_objectives")
        assert pe["notes"] == "Show objectives slide"

    def test_update_activity(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "stimulate_recall", activity="Think-pair-share")
        pe = get_plan_event(result, "stimulate_recall")
        assert pe["activity"] == "Think-pair-share"

    def test_update_question_ids(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "elicit_performance", question_ids=["q1", "q2"])
        pe = get_plan_event(result, "elicit_performance")
        assert pe["question_ids"] == ["q1", "q2"]

    def test_update_skill_id(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "assess_performance", skill_id="sk_fractions")
        pe = get_plan_event(result, "assess_performance")
        assert pe["skill_id"] == "sk_fractions"

    def test_update_duration_min(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "present_content", duration_min=15)
        pe = get_plan_event(result, "present_content")
        assert pe["duration_min"] == 15

    @pytest.mark.parametrize("duration", [0, 90])
    def test_duration_boundaries_are_accepted(self, duration):
        result = update_plan_event(
            new_gagne_plan(), "present_content", duration_min=duration
        )
        assert get_plan_event(result, "present_content")["duration_min"] == duration

    def test_other_events_unchanged(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "gain_attention", status="done")
        for pe in result:
            if pe["event_id"] != "gain_attention":
                assert pe["status"] == "planned"

    def test_raises_on_invalid_event_id(self):
        plan = new_gagne_plan()
        with pytest.raises(ValueError):
            update_plan_event(plan, "not_a_real_event", status="done")

    def test_raises_on_invalid_status(self):
        plan = new_gagne_plan()
        with pytest.raises(ValueError):
            update_plan_event(plan, "gain_attention", status="completed")

    def test_all_valid_statuses_accepted(self):
        plan = new_gagne_plan()
        for status in PLAN_STATUSES:
            result = update_plan_event(plan, "gain_attention", status=status)
            pe = get_plan_event(result, "gain_attention")
            assert pe["status"] == status

    def test_notes_stripped(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "gain_attention", notes="  note  ")
        pe = get_plan_event(result, "gain_attention")
        assert pe["notes"] == "note"

    def test_activity_stripped(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "gain_attention", activity="  act  ")
        pe = get_plan_event(result, "gain_attention")
        assert pe["activity"] == "act"

    def test_skill_id_stripped(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "gain_attention", skill_id="  sk1  ")
        pe = get_plan_event(result, "gain_attention")
        assert pe["skill_id"] == "sk1"

    def test_fractional_duration_is_preserved(self):
        plan = new_gagne_plan()
        result = update_plan_event(plan, "gain_attention", duration_min=10.7)
        pe = get_plan_event(result, "gain_attention")
        assert pe["duration_min"] == 10.7

    @pytest.mark.parametrize(
        "duration",
        [-1, 91, "10", "", True, float("nan"), float("inf"), float("-inf")],
    )
    def test_invalid_duration_is_rejected(self, duration):
        with pytest.raises(ValueError):
            update_plan_event(
                new_gagne_plan(), "gain_attention", duration_min=duration
            )

    def test_none_duration_keeps_existing_value_unless_cleared(self):
        plan = update_plan_event(
            new_gagne_plan(), "gain_attention", duration_min=15
        )
        unchanged = update_plan_event(plan, "gain_attention", duration_min=None)
        cleared = update_plan_event(
            plan, "gain_attention", duration_min=None, clear_duration=True
        )
        assert get_plan_event(unchanged, "gain_attention")["duration_min"] == 15
        assert get_plan_event(cleared, "gain_attention")["duration_min"] is None

    def test_duration_clear_rejects_simultaneous_value(self):
        with pytest.raises(ValueError):
            update_plan_event(
                new_gagne_plan(),
                "gain_attention",
                duration_min=15,
                clear_duration=True,
            )

    def test_chained_updates(self):
        plan = new_gagne_plan()
        plan = update_plan_event(plan, "gain_attention", status="done", notes="Done")
        plan = update_plan_event(plan, "inform_objectives", status="in_progress")
        plan = update_plan_event(plan, "stimulate_recall", status="skipped")
        assert get_plan_event(plan, "gain_attention")["status"] == "done"
        assert get_plan_event(plan, "inform_objectives")["status"] == "in_progress"
        assert get_plan_event(plan, "stimulate_recall")["status"] == "skipped"

    def test_question_ids_stored_as_copy(self):
        plan = new_gagne_plan()
        ids = ["q1", "q2"]
        result = update_plan_event(plan, "elicit_performance", question_ids=ids)
        ids.append("q3")
        pe = get_plan_event(result, "elicit_performance")
        assert pe["question_ids"] == ["q1", "q2"]


# ===========================================================================
# plan_summary
# ===========================================================================

class TestPlanSummary:
    """Tests for plan_summary()."""

    def test_fresh_plan_total_is_9(self):
        plan = new_gagne_plan()
        s = plan_summary(plan)
        assert s["total"] == 9

    def test_fresh_plan_all_planned(self):
        plan = new_gagne_plan()
        s = plan_summary(plan)
        assert s["planned"] == 9
        assert s["done"] == 0
        assert s["skipped"] == 0
        assert s["in_progress"] == 0

    def test_fresh_plan_untouched_is_9(self):
        plan = new_gagne_plan()
        s = plan_summary(plan)
        assert s["untouched"] == 9

    def test_fresh_plan_completion_pct_is_zero(self):
        plan = new_gagne_plan()
        s = plan_summary(plan)
        assert s["completion_pct"] == 0.0

    def test_one_done_event(self):
        plan = update_plan_event(new_gagne_plan(), "gain_attention", status="done")
        s = plan_summary(plan)
        assert s["done"] == 1
        assert s["planned"] == 8

    def test_one_skipped_event(self):
        plan = update_plan_event(new_gagne_plan(), "inform_objectives", status="skipped")
        s = plan_summary(plan)
        assert s["skipped"] == 1

    def test_one_in_progress_event(self):
        plan = update_plan_event(new_gagne_plan(), "present_content", status="in_progress")
        s = plan_summary(plan)
        assert s["in_progress"] == 1
        assert s["planned"] == 8

    def test_completion_pct_all_done(self):
        plan = new_gagne_plan()
        for eid in EVENT_IDS:
            plan = update_plan_event(plan, eid, status="done")
        s = plan_summary(plan)
        assert s["completion_pct"] == 100.0

    def test_completion_pct_all_skipped(self):
        plan = new_gagne_plan()
        for eid in EVENT_IDS:
            plan = update_plan_event(plan, eid, status="skipped")
        s = plan_summary(plan)
        assert s["completion_pct"] == 100.0

    def test_completion_pct_mixed(self):
        plan = new_gagne_plan()
        # 3 done out of 9 → 33.3%
        for eid in EVENT_IDS[:3]:
            plan = update_plan_event(plan, eid, status="done")
        s = plan_summary(plan)
        assert s["completion_pct"] == round(3 / 9 * 100, 1)

    def test_untouched_decreases_when_activity_added(self):
        plan = new_gagne_plan()
        plan = update_plan_event(plan, "gain_attention", activity="Show video")
        s = plan_summary(plan)
        assert s["untouched"] == 8

    def test_untouched_decreases_when_notes_added(self):
        plan = new_gagne_plan()
        plan = update_plan_event(plan, "gain_attention", notes="Some note")
        s = plan_summary(plan)
        assert s["untouched"] == 8

    def test_done_event_not_counted_as_untouched(self):
        plan = new_gagne_plan()
        plan = update_plan_event(plan, "gain_attention", status="done")
        s = plan_summary(plan)
        assert s["untouched"] == 8  # done event is not untouched

    def test_skipped_event_not_counted_as_untouched(self):
        plan = new_gagne_plan()
        plan = update_plan_event(plan, "gain_attention", status="skipped")
        s = plan_summary(plan)
        assert s["untouched"] == 8

    def test_summary_has_all_keys(self):
        s = plan_summary(new_gagne_plan())
        required = {"total", "planned", "in_progress", "done",
                    "skipped", "untouched", "completion_pct"}
        assert required <= set(s.keys())

    def test_empty_plan_completion_pct_zero(self):
        s = plan_summary([])
        assert s["completion_pct"] == 0.0
        assert s["total"] == 0


# ===========================================================================
# events_done / events_skipped / events_pending
# ===========================================================================

class TestEventFilters:
    """Tests for events_done(), events_skipped(), events_pending()."""

    def test_events_done_empty_on_fresh_plan(self):
        plan = new_gagne_plan()
        assert events_done(plan) == []

    def test_events_skipped_empty_on_fresh_plan(self):
        plan = new_gagne_plan()
        assert events_skipped(plan) == []

    def test_events_pending_all_on_fresh_plan(self):
        plan = new_gagne_plan()
        assert set(events_pending(plan)) == set(EVENT_IDS)

    def test_events_done_after_marking_done(self):
        plan = update_plan_event(new_gagne_plan(), "gain_attention", status="done")
        assert "gain_attention" in events_done(plan)
        assert len(events_done(plan)) == 1

    def test_events_skipped_after_marking_skipped(self):
        plan = update_plan_event(new_gagne_plan(), "inform_objectives", status="skipped")
        assert "inform_objectives" in events_skipped(plan)

    def test_events_pending_excludes_done(self):
        plan = update_plan_event(new_gagne_plan(), "gain_attention", status="done")
        assert "gain_attention" not in events_pending(plan)

    def test_events_pending_excludes_skipped(self):
        plan = update_plan_event(new_gagne_plan(), "gain_attention", status="skipped")
        assert "gain_attention" not in events_pending(plan)

    def test_events_pending_includes_in_progress(self):
        plan = update_plan_event(new_gagne_plan(), "gain_attention", status="in_progress")
        assert "gain_attention" in events_pending(plan)

    def test_counts_sum_to_nine(self):
        plan = new_gagne_plan()
        plan = update_plan_event(plan, "gain_attention", status="done")
        plan = update_plan_event(plan, "inform_objectives", status="skipped")
        plan = update_plan_event(plan, "stimulate_recall", status="in_progress")
        total = (len(events_done(plan)) + len(events_skipped(plan)) +
                 len(events_pending(plan)))
        assert total == 9

    def test_all_done_events_pending_is_empty(self):
        plan = new_gagne_plan()
        for eid in EVENT_IDS:
            plan = update_plan_event(plan, eid, status="done")
        assert events_pending(plan) == []
        assert len(events_done(plan)) == 9

    def test_all_skipped_events_pending_is_empty(self):
        plan = new_gagne_plan()
        for eid in EVENT_IDS:
            plan = update_plan_event(plan, eid, status="skipped")
        assert events_pending(plan) == []
        assert len(events_skipped(plan)) == 9

    def test_return_types_are_lists(self):
        plan = new_gagne_plan()
        assert isinstance(events_done(plan), list)
        assert isinstance(events_skipped(plan), list)
        assert isinstance(events_pending(plan), list)

    def test_multiple_done_events(self):
        plan = new_gagne_plan()
        for eid in EVENT_IDS[:4]:
            plan = update_plan_event(plan, eid, status="done")
        assert len(events_done(plan)) == 4

    def test_mixed_state_all_filters_correct(self):
        plan = new_gagne_plan()
        plan = update_plan_event(plan, EVENT_IDS[0], status="done")
        plan = update_plan_event(plan, EVENT_IDS[1], status="done")
        plan = update_plan_event(plan, EVENT_IDS[2], status="skipped")
        plan = update_plan_event(plan, EVENT_IDS[3], status="in_progress")
        # remaining 5 are still "planned"
        assert len(events_done(plan)) == 2
        assert len(events_skipped(plan)) == 1
        assert len(events_pending(plan)) == 6  # in_progress(1) + planned(5)
