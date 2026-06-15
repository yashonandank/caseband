#!/usr/bin/env python3
"""qa_critic invariants: raises quality findings, resolves when fixed, composes
with StructuralCritic without clearing its findings. No API needed.

    python3 tests/test_qa_critic.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.models.case_package import CasePackage    # noqa: E402
from caseband.reducer import apply                       # noqa: E402
from caseband.agents.qa_critic import QACritic           # noqa: E402
from caseband.agents.red_team import StructuralCritic    # noqa: E402


def _pkg():
    p = CasePackage()
    p.meta["title"] = "t"
    p.objectives = [{"key": "o1", "text": "Understand stuff", "tested_by": "dp1"}]  # weak verb
    p.decision_points = [{"dp_key": "dp1", "maps_to_objective": "o1",
                          "prompt": "Choose the best marketing spend level for next quarter",
                          "options": [{"id": "a"}, {"id": "b"}]}]
    p.rubric = [{"criterion_key": "c_o1", "objective_key": "o1", "weight": 1.0, "levels": []}]
    return p


def _apply_all(pkg, msgs):
    for m in msgs:
        r = apply(pkg, m)
        assert r.applied, r.reason
        pkg = r.package
    return pkg


def test_raises_quality_findings():
    pkg = _pkg()
    msgs = QACritic().act(pkg, "redteam")
    ops = [m.payload["op"] for m in msgs]
    assert ops and all(o == "add_finding" for o in ops)
    keys = {m.payload["data"]["finding_key"] for m in msgs}
    assert any(k.startswith("qa_obj_verb") for k in keys)     # weak objective verb
    assert any(k.startswith("qa_rubric_levels") for k in keys)  # empty levels


def test_resolves_when_fixed():
    pkg = _pkg()
    pkg = _apply_all(pkg, QACritic().act(pkg, "redteam"))
    assert pkg.open_blocking_findings()                        # rubric_levels is major
    # fix: add levels + a measurable verb
    pkg.rubric[0]["levels"] = [{"score": 0}, {"score": 1}, {"score": 2}]
    pkg.objectives[0]["text"] = "Analyze the marketing ROI"
    pkg = _apply_all(pkg, QACritic().act(pkg, "redteam"))
    assert [f for f in pkg.redteam_findings if f["status"] == "open"] == []


def test_composes_with_structural_critic():
    # a structural finding (dp <2 options) must NOT be resolved by QACritic, and vice versa
    pkg = _pkg()
    pkg.decision_points[0]["options"] = []                     # structural violation
    pkg = _apply_all(pkg, StructuralCritic().act(pkg, "redteam"))
    pkg = _apply_all(pkg, QACritic().act(pkg, "redteam"))
    open_keys = {f["finding_key"] for f in pkg.redteam_findings if f["status"] == "open"}
    assert any(k.startswith("dp_options") for k in open_keys)   # structural survived QA pass
    assert any(k.startswith("qa_") for k in open_keys)          # qa survived structural pass


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
