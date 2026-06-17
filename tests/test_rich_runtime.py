#!/usr/bin/env python3
"""Agentic interviewer (offline floor) + staged-reveal runtime.

    python3 tests/test_rich_runtime.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.agents.interview_agent import AgenticInterviewer, REQUIRED   # noqa: E402
from caseband.agents.case_designer import example_case                     # noqa: E402
from caseband.runtime.staged_run import StagedRun, StagedPlayer, opening    # noqa: E402


def test_interview_floor_collects_then_finalizes():
    agent = AgenticInterviewer(live=False)
    s = agent.start()
    assert s["pending"] == "goal" and not s["ready"]
    answers = {"goal": "both — analysis and judgement",
               "method": "activity-based costing to find a bottleneck",
               "context": "fictional small cabinet maker deciding on an AI tool",
               "data": "invent realistic numbers from benchmarks",
               "grading": "A = finds the real driver and re-scopes the AI; C = buys to fix CNC",
               "duration": "60 minutes"}
    state = s["state"]
    last = s
    for _ in range(len(REQUIRED) + 1):
        if last["ready"]:
            break
        slot = last["pending"]
        last = agent.step(state, answers[slot])
        state = last["state"]
    assert last["ready"] is True
    assert last["checkpoints"] == 4               # 60 min -> 4 stages
    b = last["brief"]
    assert b["method"] and b["grading"] and b["context"]["goal"]
    assert last["plan"]                            # a build plan is surfaced


def test_interview_will_not_finalize_early():
    agent = AgenticInterviewer(live=False)
    s = agent.step({"collected": {"goal": "x"}, "pending": "method"}, "ABC")
    assert s["ready"] is False and s["pending"] == "context"


def test_opening_is_same_and_hides_answer():
    case = example_case()
    o = opening(case)
    assert o["company"]["name"] == "Brightwood Cabinetry"
    assert o["stage"]["key"] == "S1" and o["total_stages"] == 3
    blob = str(o)
    assert "true_driver" not in blob and "expected_insight" not in blob
    assert "worksheet" in o                        # stage 1 is an analysis stage
    assert all("total" not in a for a in o["worksheet"]["activities"])  # un-allocated


def test_staged_advance_reveals_next_and_completes():
    case = example_case()
    run = StagedRun(run_id="r1", case_id="c1", student_id="s1", case=case)
    player = StagedPlayer(live=False)

    r1 = player.advance(run, "I allocated overhead; order processing is the real driver.")
    assert r1["status"] == "active" and r1["stage_index"] == 1
    assert r1["reveal"]                            # S2 reveals the spec-ambiguity inject
    assert "ambiguous" in r1["reveal"].lower() or "spec" in r1["reveal"].lower()

    r2 = player.advance(run, "Don't buy as scoped; re-scope AI to spec capture.")
    assert r2["status"] == "active" and r2["stage_index"] == 2
    assert "Dev" in r2["reveal"]                   # S3 reveals the retention nuance

    r3 = player.advance(run, "Standardise specs first; retain Dev.")
    assert r3["status"] == "complete"
    assert len(run.responses) == 3


def _run_standalone():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
