#!/usr/bin/env python3
"""Eval harness + the tool-calling agent core (non-linear, state-driven).

    python3 tests/test_eval_agent.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.eval import run_eval                               # noqa: E402
from caseband.graph import tools as gtools                       # noqa: E402
from caseband.graph.registry import ToolRegistry                 # noqa: E402
from caseband.graph.agent_core import ToolAgent                  # noqa: E402


def test_eval_corpus_passes_offline():
    rep = run_eval(live=False)
    assert rep["failed"] == 0 and rep["passed"] == rep["total"]
    # every required check ran on each case
    names = {c["check"] for c in rep["cases"][0]["checks"]}
    assert {"solvable", "has_personas", "leak_free"} <= names


def _authoring_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.add("propose_backbone", "propose the analytical backbone numbers",
            lambda brief, feedback="", live=False: gtools.propose_backbone(brief, feedback, live), kind="llm")
    reg.add("validate_backbone", "deterministically check solvable + non-obvious",
            lambda backbone: gtools.validate_backbone(backbone), kind="det")
    reg.add("write_case", "write the case around a validated backbone",
            lambda brief, backbone, validation, live=False: gtools.write_case(brief, backbone, validation, live), kind="llm")
    reg.add("build_ui", "render the interactive case page",
            lambda case_dict, case_id: gtools.build_ui(case_dict, case_id), kind="det")
    return reg


def _policy(ctx):
    """State-driven, NOT a fixed sequence: each step is chosen from what exists."""
    if "backbone" not in ctx:
        return ("propose_backbone", {"brief": ctx["brief"], "live": False})
    if not ctx.get("validation", {}).get("validated"):
        return ("validate_backbone", {"backbone": ctx["backbone"]})
    if "case" not in ctx:
        return ("write_case", {"brief": ctx["brief"], "backbone": ctx["backbone"],
                               "validation": ctx["validation"], "live": False})
    if "ui" not in ctx:
        return ("build_ui", {"case_dict": ctx["case"], "case_id": ctx["case_id"]})
    return ("finish", {})


def test_agent_reaches_goal_by_choosing_tools_from_state():
    reg = _authoring_registry()
    events = []
    agent = ToolAgent("produce a validated, UI-ready case", reg,
                      policy=_policy, live=False, on_event=events.append)
    out = agent.run({"brief": {"context": {"topic": "ABC"}}, "case_id": "agent_test_1"})
    ctx = out["context"]
    assert ctx["validation"]["validated"] is True
    assert ctx["case"]["company"]["name"] == "Brightwood Cabinetry"
    assert ctx["ui"]["url"].endswith("agent_test_1.html")
    # the agent chose tools dynamically; trace reflects state-driven order
    tools_used = [t["tool"] for t in out["trace"]]
    assert tools_used == ["propose_backbone", "validate_backbone", "write_case", "build_ui"]
    assert events and events[-1]["tool"] == "finish"
    os.remove(ctx["ui"]["path"])


def test_agent_loops_back_when_a_gate_fails():
    """If validation reports not-validated, the policy re-invokes propose_backbone
    rather than marching on — proving it's state-driven, not linear."""
    reg = _authoring_registry()
    # force the first validation to fail by seeding a bad validation, then a policy
    # that re-proposes until validated
    calls = {"n": 0}

    def flaky_policy(ctx):
        if "backbone" not in ctx:
            return ("propose_backbone", {"brief": ctx["brief"], "live": False})
        if not ctx.get("validation", {}).get("validated"):
            calls["n"] += 1
            if calls["n"] == 1:
                # pretend the gate failed once: drop validation, re-propose
                ctx.pop("validation", None)
                return ("propose_backbone", {"brief": ctx["brief"], "live": False})
            return ("validate_backbone", {"backbone": ctx["backbone"]})
        return ("finish", {})

    agent = ToolAgent("validate a backbone", reg, policy=flaky_policy, live=False)
    out = agent.run({"brief": {"context": {}}, "case_id": "x"})
    tools_used = [t["tool"] for t in out["trace"]]
    assert tools_used.count("propose_backbone") >= 2   # looped back
    assert out["context"]["validation"]["validated"] is True


def _run_standalone():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
