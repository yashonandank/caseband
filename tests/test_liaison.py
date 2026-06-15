#!/usr/bin/env python3
"""professor_liaison invariants: it never writes owned fields directly, and every
professor edit re-enters validation before the case can be approved. No API needed.

    python3 tests/test_liaison.py
    pytest tests/test_liaison.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.bus.local_bus import LocalBus                # noqa: E402
from caseband.conductor import Conductor                   # noqa: E402
from caseband.state_store import StateStore                # noqa: E402
from caseband.rooms import Room                            # noqa: E402
from caseband.ownership import FIELD_OWNER                 # noqa: E402
from caseband.models.messages import Verb                  # noqa: E402
from caseband.agents.intake import Parser                  # noqa: E402
from caseband.agents.writers_room import (                 # noqa: E402
    ObjectiveSetter, OutcomeModeler, CheckpointMapper, RubricCreator,
)
from caseband.agents.red_team import SolvabilityValidator, StructuralCritic  # noqa: E402
from caseband.agents.professor_liaison import ProfessorLiaison               # noqa: E402

MODEL = {
    "kind": "formula", "kpi_key": "roi", "pass_policy": "all",
    "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
    "decision_variables": [{"key": "marketing_spend", "bounds": [50000, 500000]}],
    "parameters": {"gain": 200000},
    "spec": {"expr": "(gain - marketing_spend) / marketing_spend"},
}


def _validated_package():
    c = Conductor(LocalBus(), StateStore(), room=Room.WRITERS.value)
    c.run_loop_a([
        Parser("T", "10K"),
        ObjectiveSetter([{"key": "o1", "text": "a"}, {"key": "o2", "text": "b"}]),
        OutcomeModeler(MODEL), CheckpointMapper(), RubricCreator(),
    ])
    c.room = Room.REDTEAM.value
    c.run_loop_b([SolvabilityValidator(), StructuralCritic()])
    assert c.pkg.redteam_clean()
    return c.pkg


def test_liaison_owns_no_field():
    assert "professor_liaison" not in FIELD_OWNER.values()


def test_propose_routes_to_owner_never_patches():
    liaison = ProfessorLiaison()
    msg = liaison.propose({"op": "set_outcome_target", "field": "outcome_model",
                           "value": 0.10}, room="redteam")
    assert msg.verb is Verb.REVISE_REQUEST          # not STATE_PATCH
    assert msg.sender == "professor_liaison"
    assert msg.to == ["outcome_modeler"]            # addressed to the field owner


def test_preview_diff():
    liaison = ProfessorLiaison()
    diff = liaison.preview_diff(_validated_package(),
                                {"op": "set_outcome_target", "field": "outcome_model",
                                 "value": 0.10})
    assert diff == {"field": "outcome_model.target.value", "before": 0.15, "after": 0.10}


def test_valid_edit_stays_approvable():
    pkg = _validated_package()
    res = ProfessorLiaison().apply_and_revalidate(
        pkg, {"op": "set_outcome_target", "field": "outcome_model", "value": 0.10})
    assert res.applied and res.approvable           # 0.10 still reachable
    assert res.package.outcome_model["target"]["value"] == 0.10
    assert res.package.solvability["validated"] is True
    assert pkg.outcome_model["target"]["value"] == 0.15   # purity: original untouched


def test_breaking_edit_blocks_approval():
    pkg = _validated_package()
    res = ProfessorLiaison().apply_and_revalidate(
        pkg, {"op": "set_outcome_target", "field": "outcome_model", "value": 999})
    assert res.applied                              # the edit lands...
    assert res.approvable is False                  # ...but cannot be approved
    assert res.package.solvability["validated"] is False
    assert "re-validation" in res.reason


# ---- gap b: generalized revise loop (objectives / decision prompts / rubric) ----

def test_propose_routes_new_ops_to_owners():
    liaison = ProfessorLiaison()
    cases = [
        ({"op": "add_objective", "value": {"key": "o3", "text": "c"}}, "objective_setter"),
        ({"op": "edit_objective", "key": "o1", "value": {"text": "z"}}, "objective_setter"),
        ({"op": "remove_objective", "key": "o2"}, "objective_setter"),
        ({"op": "edit_decision_prompt", "key": "dp1", "value": {"prompt": "p"}}, "checkpoint_mapper"),
        ({"op": "edit_rubric_prompt", "key": "c_o1", "value": {"prompt": "p"}}, "rubric_creator"),
    ]
    for intent, owner in cases:
        msg = liaison.propose(intent, room="redteam")
        assert msg.verb is Verb.REVISE_REQUEST       # never a STATE_PATCH
        assert msg.sender == "professor_liaison"
        assert msg.to == [owner]                      # routed to the field owner


def test_preview_diff_new_ops():
    pkg = _validated_package()
    liaison = ProfessorLiaison()

    d = liaison.preview_diff(pkg, {"op": "edit_decision_prompt", "key": "dp1",
                                   "value": {"prompt": "Reworded prompt"}})
    assert d["field"] == "decision_points[dp1].prompt"
    assert d["before"] == "Decision exercising: a"   # original authored prompt
    assert d["after"] == "Reworded prompt"

    d = liaison.preview_diff(pkg, {"op": "edit_objective", "key": "o1",
                                   "value": {"text": "new text"}})
    assert d == {"field": "objectives[o1].text", "before": "a", "after": "new text"}

    d = liaison.preview_diff(pkg, {"op": "remove_objective", "key": "o2"})
    assert d["field"] == "objectives[o2]" and d["after"] is None
    assert d["before"]["key"] == "o2"


def test_benign_decision_prompt_edit_stays_approvable():
    pkg = _validated_package()
    res = ProfessorLiaison().apply_and_revalidate(
        pkg, {"op": "edit_decision_prompt", "key": "dp1",
              "value": {"prompt": "A sharper decision prompt"}})
    assert res.applied and res.approvable
    dp = next(d for d in res.package.decision_points if d["dp_key"] == "dp1")
    assert dp["prompt"] == "A sharper decision prompt"
    assert res.package.solvability["validated"] is True
    # purity: the original package is untouched
    orig = next(d for d in pkg.decision_points if d["dp_key"] == "dp1")
    assert orig["prompt"] == "Decision exercising: a"


def test_benign_objective_reword_stays_approvable():
    pkg = _validated_package()
    res = ProfessorLiaison().apply_and_revalidate(
        pkg, {"op": "edit_objective", "key": "o1", "value": {"text": "reworded"}})
    assert res.applied and res.approvable
    assert res.package.objective("o1")["text"] == "reworded"
    assert pkg.objective("o1")["text"] == "a"          # purity


def test_adding_uncovered_objective_blocks_approval():
    pkg = _validated_package()
    res = ProfessorLiaison().apply_and_revalidate(
        pkg, {"op": "add_objective", "value": {"key": "o3", "text": "uncovered"}})
    assert res.applied                                  # the edit lands...
    assert res.approvable is False                      # ...but it has no rubric coverage
    assert "re-validation" in res.reason
    assert any(f["finding_key"] == "rubric_missing:o3"
               for f in res.package.open_blocking_findings())


def test_remove_objective_stays_approvable():
    pkg = _validated_package()
    res = ProfessorLiaison().apply_and_revalidate(
        pkg, {"op": "remove_objective", "key": "o2"})
    assert res.applied and res.approvable               # removing it removes its needs
    assert res.package.objective("o2") is None
    assert pkg.objective("o2") is not None              # purity


def test_revise_revalidate_fix_loop():
    """The loop that repeats until approve: a breaking edit blocks approval, and a
    follow-up edit on the revised package clears it."""
    pkg = _validated_package()
    liaison = ProfessorLiaison()

    # round 1: unreachable target -> not approvable
    r1 = liaison.apply_and_revalidate(
        pkg, {"op": "set_outcome_target", "field": "outcome_model", "value": 999})
    assert r1.applied and r1.approvable is False
    assert r1.package.solvability["validated"] is False

    # round 2: professor revises the SAME (revised) package back to a reachable
    # target -> re-validation now passes and approval is unblocked.
    r2 = liaison.apply_and_revalidate(
        r1.package, {"op": "set_outcome_target", "field": "outcome_model", "value": 0.10})
    assert r2.applied and r2.approvable is True
    assert r2.package.solvability["validated"] is True
    assert r2.reason == ""


def test_add_then_cover_objective_loop():
    """Add an objective (blocks: no rubric), then add a covering rubric criterion
    on the revised package -> approvable again."""
    pkg = _validated_package()
    liaison = ProfessorLiaison()

    r1 = liaison.apply_and_revalidate(
        pkg, {"op": "add_objective", "value": {"key": "o3", "text": "new"}})
    assert r1.approvable is False

    # re-balance existing weights + add a covering criterion so weights still sum ~1.0
    revised = r1.package
    n = len(revised.objectives)
    for c in revised.rubric:
        c["weight"] = round(1.0 / n, 3)
    r2 = liaison.apply_and_revalidate(
        revised, {"op": "add_rubric_criterion",
                  "value": {"criterion_key": "c_o3", "objective_key": "o3",
                            "weight": round(1.0 / n, 3),
                            "levels": [{"score": 0, "descriptor": "absent"}]}})
    assert r2.applied and r2.approvable is True
    assert any(c["criterion_key"] == "c_o3" for c in r2.package.rubric)


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
