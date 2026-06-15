#!/usr/bin/env python3
"""Runtime invariants: proctor turn token + submit->grade path on a deployed case.
No API needed.

    python3 tests/test_runtime.py
    pytest tests/test_runtime.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.bus.local_bus import LocalBus                # noqa: E402
from caseband.conductor import Conductor                   # noqa: E402
from caseband.state_store import StateStore                # noqa: E402
from caseband.rooms import Room                            # noqa: E402
from caseband.agents.intake import Parser                  # noqa: E402
from caseband.agents.writers_room import (                 # noqa: E402
    ObjectiveSetter, OutcomeModeler, CheckpointMapper, RubricCreator,
)
from caseband.agents.red_team import SolvabilityValidator, StructuralCritic  # noqa: E402
from caseband.runtime.case_run import CaseRun, Proctor, TurnError, RunError   # noqa: E402
from caseband.runtime.redact import student_view, leaks                       # noqa: E402

MODEL = {
    "kind": "formula", "kpi_key": "roi", "pass_policy": "all",
    "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
    "decision_variables": [{"key": "marketing_spend", "bounds": [50000, 500000]}],
    "parameters": {"gain": 200000},
    "spec": {"expr": "(gain - marketing_spend) / marketing_spend"},
}


def _deployed_package():
    """Author + red-team a case offline, returning the frozen package to deploy."""
    c = Conductor(LocalBus(), StateStore(), room=Room.WRITERS.value)
    c.run_loop_a([
        Parser("T", "10K"),
        ObjectiveSetter([{"key": "o1", "text": "a"}, {"key": "o2", "text": "b"}]),
        OutcomeModeler(MODEL), CheckpointMapper(), RubricCreator(),
    ])
    c.room = Room.REDTEAM.value
    c.run_loop_b([SolvabilityValidator(), StructuralCritic()])
    assert c.pkg.redteam_clean()                  # only deploy a clean case
    return c.pkg


def _run():
    return CaseRun(run_id="r1", case_id="c1", student_id="stu_1", package=_deployed_package())


def test_submit_grades_and_releases_ai_draft():
    run, proctor = _run(), Proctor()
    grade = proctor.submit(run, {"marketing_spend": 60000}, {"c_o1": 2, "c_o2": 2})
    assert grade["status"] == "ai_draft"          # released to student immediately
    assert grade["overall_pass"] is True
    assert run.status == "graded" and run.grade is grade
    # transcript captured submit + feedback, all local (never Band)
    events = [m.payload.get("event") for m in run.transcript]
    assert events == ["submit", "feedback"]
    assert all(m.payload.get("via") == "local" for m in run.transcript)
    assert all(m.payload.get("case_run_id") == "r1" for m in run.transcript)


def test_turn_token_blocks_talkover():
    proctor = Proctor()
    proctor.grant("coach")
    try:
        proctor.grant("facilitator")
    except TurnError:
        proctor.release("coach")
        proctor.grant("facilitator")              # free once released
        return
    raise AssertionError("turn token must block a second speaker")


def test_token_released_after_submit():
    run, proctor = _run(), Proctor()
    proctor.submit(run, {"marketing_spend": 60000}, {"c_o1": 2, "c_o2": 2})
    assert proctor.holder is None                 # proctor gave the turn back


def test_double_submit_rejected():
    run, proctor = _run(), Proctor()
    proctor.submit(run, {"marketing_spend": 60000}, {"c_o1": 2, "c_o2": 2})
    try:
        proctor.submit(run, {"marketing_spend": 60000}, {"c_o1": 2, "c_o2": 2})
    except RunError:
        return
    raise AssertionError("a graded run must not accept another submission")


def test_student_view_never_leaks_the_answer():
    pkg = _deployed_package()
    view = student_view(pkg)
    assert leaks(view) == []                      # hard invariant: no answer fields
    om = view["outcome_model"]
    assert "spec" not in om and "parameters" not in om      # formula + constants hidden
    assert om["kpi_key"] == "roi" and om["target"]          # goal + KPI still shown
    assert om["decision_variables"][0]["key"] == "marketing_spend"  # levers visible
    assert all("weight" not in c for c in view["rubric"])   # rubric weights hidden
    # purity: redaction did not mutate the deployed package
    assert pkg.outcome_model["spec"]["expr"]


def test_trigger_wakes_exactly_one_agent():
    proctor = Proctor()
    assert proctor.wake_for("stuck") == "coach"
    assert proctor.wake_for("checkpoint") == "facilitator"
    assert proctor.wake_for("idle") == "facilitator"
    assert proctor.wake_for("ask", addressed_to="cfo") == "cfo"  # stakeholder isolation


def test_ask_without_addressee_rejected():
    try:
        Proctor().wake_for("ask")
    except RunError:
        return
    raise AssertionError("'ask' must require an addressed stakeholder")


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
