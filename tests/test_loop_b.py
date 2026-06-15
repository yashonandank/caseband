#!/usr/bin/env python3
"""Loop B (Red-Team) invariants: solvability proof + structural critic + convergence.
No API needed (validator + critic are deterministic).

    python3 tests/test_loop_b.py
    pytest tests/test_loop_b.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.bus.local_bus import LocalBus                # noqa: E402
from caseband.conductor import Conductor                   # noqa: E402
from caseband.state_store import StateStore                # noqa: E402
from caseband.rooms import Room                            # noqa: E402
from caseband.reducer import apply                         # noqa: E402
from caseband.agents.intake import Parser                  # noqa: E402
from caseband.agents.writers_room import (                 # noqa: E402
    ObjectiveSetter, OutcomeModeler, CheckpointMapper, RubricCreator,
)
from caseband.agents.red_team import SolvabilityValidator, StructuralCritic  # noqa: E402

GOOD_MODEL = {
    "kind": "formula", "kpi_key": "roi",
    "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
    "decision_variables": [{"key": "marketing_spend", "bounds": [50000, 500000]}],
    "parameters": {"gain": 200000},
    "spec": {"expr": "(gain - marketing_spend) / marketing_spend"},
}
DEAD_MODEL = dict(GOOD_MODEL,  # x never moves the KPI -> zero-effect lever
                  decision_variables=[{"key": "x", "bounds": [0, 10]}],
                  parameters={"gain": 5},
                  spec={"expr": "gain + 0 * x"})


def _writers_pkg(model) -> Conductor:
    """Drive Loop A to a converged, well-formed package, then enter the Red-Team room."""
    c = Conductor(LocalBus(), StateStore(), room=Room.WRITERS.value)
    c.run_loop_a([
        Parser("T", "10K"),
        ObjectiveSetter([{"key": "o1", "text": "a"}, {"key": "o2", "text": "b"}]),
        OutcomeModeler(model),
        CheckpointMapper(),
        RubricCreator(),
    ])
    c.room = Room.REDTEAM.value
    return c


def test_loop_b_converges_clean_case():
    c = _writers_pkg(GOOD_MODEL)
    report = c.run_loop_b([SolvabilityValidator(), StructuralCritic()])
    assert report.converged
    assert c.pkg.redteam_clean()
    assert c.pkg.solvability["validated"] is True
    assert c.pkg.solvability["calibration"]["reachable"]
    assert c.pkg.open_blocking_findings() == []
    assert c.pkg.meta["status"] == Room.ASSESSMENT.value   # handoff to assessment fired


def test_loop_b_blocks_unsolvable_case():
    c = _writers_pkg(DEAD_MODEL)
    report = c.run_loop_b([SolvabilityValidator(), StructuralCritic()])
    assert not report.converged                            # cannot ship an unsolvable case
    assert c.pkg.solvability["validated"] is False
    kinds = {i["kind"] for i in c.pkg.solvability["issues"]}
    assert "zero_effect_variables" in kinds


def test_critic_raises_then_resolves():
    c = _writers_pkg(GOOD_MODEL)
    critic = StructuralCritic()
    # break a decision point -> critic must raise
    c.pkg.decision_points[0]["options"] = []
    raised = critic.act(c.pkg, c.room)
    assert any(m.payload["op"] == "add_finding" for m in raised)
    for m in raised:
        c.pkg = apply(c.pkg, m).package
    assert c.pkg.open_blocking_findings()
    # fix it -> critic must resolve the same finding
    c.pkg.decision_points[0]["options"] = [{"id": "a"}, {"id": "b"}]
    resolved = critic.act(c.pkg, c.room)
    assert any(m.payload["op"] == "resolve_finding" for m in resolved)
    for m in resolved:
        c.pkg = apply(c.pkg, m).package
    assert c.pkg.open_blocking_findings() == []


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
