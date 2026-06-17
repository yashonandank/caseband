#!/usr/bin/env python3
"""RichCase schema + backbone gate + offline designer.

    python3 tests/test_rich_case.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.models.rich_case import RichCase                         # noqa: E402
from caseband.tools import backbone as bb                              # noqa: E402
from caseband.agents.case_designer import CaseDesigner, example_case   # noqa: E402


def test_example_backbone_validates():
    case = example_case()
    res = bb.validate(case.backbone.__dict__)
    assert res.validated is True
    assert res.true_driver == "order_processing"
    assert res.naive_guess == "cnc_machining"
    assert res.margin >= bb.MIN_MARGIN


def test_backbone_flags_trivial_when_obvious():
    # make the highest direct cost ALSO the highest overhead driver -> obvious
    trivial = {
        "overhead_pool": 100_000,
        "activities": [
            {"key": "a", "label": "A", "direct_cost": 500_000, "overhead_driver": 900, "naive_signal": 500_000},
            {"key": "b", "label": "B", "direct_cost": 100_000, "overhead_driver": 50, "naive_signal": 100_000},
            {"key": "c", "label": "C", "direct_cost": 80_000, "overhead_driver": 50, "naive_signal": 80_000},
        ],
        "answer_key": {"true_driver": "a", "naive_guess": "a"},
    }
    res = bb.validate(trivial)
    assert res.validated is False
    assert any("trivial" in r for r in res.reasons)


def test_backbone_flags_no_clear_winner():
    flat = {
        "overhead_pool": 5_000,
        "activities": [
            {"key": "a", "label": "A", "direct_cost": 100_000, "overhead_driver": 100, "naive_signal": 100_000},
            {"key": "b", "label": "B", "direct_cost": 102_000, "overhead_driver": 300, "naive_signal": 100_000},
            {"key": "c", "label": "C", "direct_cost": 90_000, "overhead_driver": 100, "naive_signal": 90_000},
        ],
    }
    res = bb.validate(flat)
    # b edges a after allocation but by a thin (<10%) margin -> no clear answer
    assert res.validated is False
    assert any("clear cost driver" in r for r in res.reasons)


def test_backbone_rejects_malformed():
    try:
        bb.validate({"overhead_pool": 1000, "activities": [{"key": "a", "direct_cost": 1}]})
        assert False, "expected BackboneError"
    except bb.BackboneError:
        pass


def test_student_table_hides_answer():
    case = example_case()
    st = bb.student_table(case.backbone.__dict__)
    blob = str(st)
    assert "order_processing" in blob or "Order processing" in str(st)  # the row is shown
    assert "true_driver" not in blob and "answer_key" not in blob       # answer not leaked
    # no per-activity allocated total is exposed (student must compute it)
    assert all("total" not in a for a in st["activities"])


def test_richcase_roundtrip():
    case = example_case()
    again = RichCase.from_dict(case.to_dict())
    assert again.title == case.title
    assert again.company.name == "Brightwood Cabinetry"
    assert len(again.stages) == 3
    assert again.stage("S2").reveal_on_entry  # reveal survives round-trip
    assert again.stages[0].rubric[0].dimension == "analysis"


def test_offline_designer_produces_valid_case():
    case = CaseDesigner(live=False).design({"context": {"topic": "ABC"}})
    assert case.company.name and len(case.stages) >= 2
    assert bb.validate(case.backbone.__dict__).validated is True
    assert case.meta.get("brief")


def _run_standalone():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
