#!/usr/bin/env python3
"""LangGraph authoring graph + tool library + UI builder (offline).

    python3 tests/test_authoring_graph.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.graph import tools                                   # noqa: E402
from caseband.graph import ui_builder                              # noqa: E402
from caseband.graph import authoring_graph as ag                   # noqa: E402
from caseband.models.rich_case import RichCase                     # noqa: E402
from caseband.agents.case_designer import example_case             # noqa: E402


def test_tools_backbone_propose_and_validate():
    bbn = tools.propose_backbone({"context": {}}, live=False)
    v = tools.validate_backbone(bbn)
    assert v["validated"] is True and v["true_driver"] == "order_processing"


def test_tools_leak_and_difficulty():
    case = tools.write_case({"context": {}}, example_case().backbone.__dict__,
                            {"true_driver": "order_processing"}, live=False)
    assert tools.leak_scan(case)["clean"] is True
    assert tools.difficulty_ok(case["backbone"])["ok"] is True


def test_ui_builder_is_interactive_and_hides_answer():
    html = ui_builder.render(example_case())
    assert "<table" in html and "worksheet" in html and "Allocate" in html
    assert "Stage 1" in html and "textarea" in html       # staged player, response box
    # the answer must not be in the page
    assert "true_driver" not in html and "answer_key" not in html
    assert "expected_insight" not in html and "rationale" not in html
    # allocated totals are NOT pre-rendered — the student computes them (cells start "—")
    assert html.count("class=\"num alloc\">—") >= 1


def test_graph_runs_end_to_end_offline(tmp_path=None):
    events = []
    out = ag.run_authoring({"context": {"topic": "ABC"}}, "case_test_1",
                           live=False, on_event=events.append)
    assert out["validation"]["validated"] is True
    assert out["case"]["company"]["name"] == "Brightwood Cabinetry"
    assert out["ui"]["url"].endswith("case_test_1.html")
    assert os.path.isfile(out["ui"]["path"])
    # the graph streamed phase events (the live progress feed)
    nodes = [e["node"] for e in events]
    assert "propose_backbone" in nodes and "validate" in nodes and "build_ui" in nodes
    os.remove(out["ui"]["path"])


def test_validate_gate_loops_back_on_bad_numbers():
    # obvious backbone -> gate routes back to propose_backbone (immediate feedback)
    bad = {"backbone": {"overhead_pool": 10, "activities": [
        {"key": "a", "label": "A", "direct_cost": 500, "overhead_driver": 9, "naive_signal": 500},
        {"key": "b", "label": "B", "direct_cost": 10, "overhead_driver": 1, "naive_signal": 10},
        {"key": "c", "label": "C", "direct_cost": 8, "overhead_driver": 1, "naive_signal": 8}]},
        "validation": tools.validate_backbone({"overhead_pool": 10, "activities": [
            {"key": "a", "label": "A", "direct_cost": 500, "overhead_driver": 9, "naive_signal": 500},
            {"key": "b", "label": "B", "direct_cost": 10, "overhead_driver": 1, "naive_signal": 10},
            {"key": "c", "label": "C", "direct_cost": 8, "overhead_driver": 1, "naive_signal": 8}]}),
        "bb_tries": 1}
    assert bad["validation"]["validated"] is False
    assert ag.after_validate(bad) == "propose_backbone"      # loops back with feedback
    bad["bb_tries"] = ag.MAX_BACKBONE_TRIES
    assert ag.after_validate(bad) == "write_case"            # gives up after the cap


def test_mermaid_renders():
    m = ag.mermaid()
    assert "propose_backbone" in m and "validate" in m and "build_ui" in m


def _run_standalone():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
