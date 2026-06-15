#!/usr/bin/env python3
"""Reducer + Loop A invariants. Runs under pytest OR standalone:

    python3 tests/test_reducer.py
    pytest tests/test_reducer.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.models.case_package import CasePackage      # noqa: E402
from caseband.models.messages import BandMessage, Verb     # noqa: E402
from caseband.reducer import apply                         # noqa: E402
from caseband.bus.local_bus import LocalBus                # noqa: E402
from caseband.conductor import Conductor                   # noqa: E402
from caseband.state_store import StateStore                # noqa: E402
from caseband.rooms import Room                            # noqa: E402
from caseband.agents.intake import Parser                  # noqa: E402
from caseband.agents.writers_room import (                 # noqa: E402
    ObjectiveSetter, OutcomeModeler, CheckpointMapper, RubricCreator,
)


def _patch(sender, op, data):
    return BandMessage(verb=Verb.STATE_PATCH, sender=sender, room="r",
                       payload={"op": op, "data": data})


def test_owner_patch_applies():
    pkg = CasePackage()
    res = apply(pkg, _patch("objective_setter", "add_objective",
                            {"key": "o1", "text": "x"}))
    assert res.applied
    assert len(res.package.objectives) == 1
    # purity: input untouched
    assert len(pkg.objectives) == 0


def test_non_owner_patch_rejected():
    pkg = CasePackage()
    res = apply(pkg, _patch("checkpoint_mapper", "add_objective",
                            {"key": "o1", "text": "x"}))
    assert not res.applied
    assert "ownership" in res.reason
    assert len(res.package.objectives) == 0


def test_unknown_op_rejected():
    res = apply(CasePackage(), _patch("objective_setter", "delete_everything", {}))
    assert not res.applied and "unknown op" in res.reason


def test_non_patch_ignored():
    msg = BandMessage(verb=Verb.HANDOFF, sender="conductor", room="r")
    res = apply(CasePackage(), msg)
    assert not res.applied


def test_set_tested_by_links_objective():
    pkg = CasePackage()
    pkg = apply(pkg, _patch("objective_setter", "add_objective",
                            {"key": "o1", "text": "x"})).package
    res = apply(pkg, _patch("checkpoint_mapper", "set_tested_by",
                            {"objective_key": "o1", "dp_key": "dp1"}))
    assert res.applied
    assert res.package.objective("o1")["tested_by"] == "dp1"


def test_exit_predicate():
    pkg = CasePackage()
    assert not pkg.all_objectives_tested()           # empty -> not done
    pkg.objectives = [{"key": "o1", "tested_by": None}]
    assert not pkg.all_objectives_tested()
    pkg.objectives[0]["tested_by"] = "dp1"
    assert pkg.all_objectives_tested()


def test_loop_a_converges_end_to_end():
    bus, store = LocalBus(), StateStore()
    conductor = Conductor(bus, store, room=Room.WRITERS.value)
    agents = [
        Parser("T", "10K"),
        ObjectiveSetter([{"key": "o1", "text": "a"}, {"key": "o2", "text": "b"}]),
        OutcomeModeler({"kind": "formula", "kpi_key": "roi",
                        "target": {"value": 0.1, "comparator": ">=", "units": "ratio"}}),
        CheckpointMapper(),
        RubricCreator(),
    ]
    report = conductor.run_loop_a(agents)
    assert report.converged
    assert report.rejected == []
    assert conductor.pkg.all_objectives_tested()
    assert conductor.pkg.meta["status"] == Room.REDTEAM.value   # handoff fired
    assert len(conductor.pkg.decision_points) == 2
    assert len(conductor.pkg.rubric) == 2


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
