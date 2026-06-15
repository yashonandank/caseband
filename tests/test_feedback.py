#!/usr/bin/env python3
"""feedback invariants: qualitative feedback now, numbers only after finalize.
No API needed.

    python3 tests/test_feedback.py
    pytest tests/test_feedback.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.tools import grader                          # noqa: E402
from caseband.runtime import feedback                      # noqa: E402

MODEL = {
    "kind": "formula", "kpi_key": "roi", "pass_policy": "all",
    "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
    "decision_variables": [{"key": "marketing_spend", "bounds": [50000, 500000]}],
    "parameters": {"gain": 200000},
    "spec": {"expr": "(gain - marketing_spend) / marketing_spend"},
}
RUBRIC = [
    {"criterion_key": "c_o1", "objective_key": "o1", "weight": 0.5},
    {"criterion_key": "c_o2", "objective_key": "o2", "weight": 0.5},
]

# Numeric fields that must NEVER appear at the top level of a pre-finalize view.
_NUMERIC_KEYS = ("rubric_score", "overall_pass", "numeric_pass", "kpi_value")


def _mixed_grade():
    """c_o1 strong (2 -> met), c_o2 adequate (1 -> partially met); KPI passes."""
    return grader.grade_submission(MODEL, RUBRIC,
                                   {"assignment": {"marketing_spend": 50000},
                                    "rubric_scores": {"c_o1": 2, "c_o2": 1}})


def test_is_released_reflects_status():
    g = _mixed_grade()
    assert feedback.is_released(g) is False                 # ai_draft
    r = grader.review(g, "prof_1")
    assert feedback.is_released(r) is False                 # reviewed
    f = grader.finalize(r, "prof_1")
    assert feedback.is_released(f) is True                  # finalized


def test_pre_finalize_has_qualitative_levels():
    g = _mixed_grade()
    view = feedback.student_feedback(g)
    by_key = {o["criterion_key"]: o for o in view["objectives"]}
    assert by_key["c_o1"]["level"] == "met"                 # level 2
    assert by_key["c_o2"]["level"] == "partially met"       # level 1
    assert all(o["next_step"] for o in view["objectives"])  # encouraging prompts
    assert view["released"] is False


def test_revisit_mapping_for_absent_criterion():
    g = grader.grade_submission(MODEL, RUBRIC,
                                {"assignment": {"marketing_spend": 50000},
                                 "rubric_scores": {"c_o1": 0, "c_o2": 0}})
    view = feedback.student_feedback(g)
    assert all(o["level"] == "revisit" for o in view["objectives"])


def test_pre_finalize_has_no_numeric_grade():
    g = _mixed_grade()
    view = feedback.student_feedback(g)
    for k in _NUMERIC_KEYS:
        assert k not in view, f"{k} leaked into pre-finalize student view"
    assert "grade" not in view                              # no released block yet
    # objectives carry qualitative levels only — no raw scores/weights.
    for o in view["objectives"]:
        assert "score" not in o and "weight" not in o


def test_pre_finalize_kpi_is_qualitative_no_target_leak():
    g = _mixed_grade()                                       # numeric_pass True
    view = feedback.student_feedback(g)
    line = view["kpi_feedback"]
    assert "roi" in line and "met" in line.lower()
    # the hidden threshold (0.15) and the achieved value (3.0) must not appear.
    assert "0.15" not in line and "3.0" not in line and "3" not in line


def test_finalize_releases_numbers():
    g = _mixed_grade()
    f = grader.finalize(grader.review(g, "prof_1"), "prof_1")
    view = feedback.student_feedback(f)
    assert view["released"] is True
    assert "grade" in view
    grade = view["grade"]
    assert grade["overall_pass"] == f["overall_pass"]
    assert grade["rubric_score"] == f["rubric_score"]
    assert grade["numeric_pass"] == f["numeric_pass"]
    assert grade["kpi_key"] == "roi"
    assert grade["kpi_value"] == f["kpi_value"]             # now shown
    # qualitative body still present after finalize.
    assert view["objectives"] and "summary" in view


def test_student_feedback_does_not_mutate_input():
    g = _mixed_grade()
    before = dict(g)
    feedback.student_feedback(g)
    assert g == before


def test_rubric_only_case_has_no_kpi_line():
    model = dict(MODEL, pass_policy="rubric_only")
    # rubric_only still computes numeric_pass; use a model with no numeric half
    # to exercise the None branch: drop the formula.
    g = grader.grade_submission(None, RUBRIC,
                                {"assignment": {}, "rubric_scores": {"c_o1": 2, "c_o2": 2}})
    view = feedback.student_feedback(g)
    assert g["numeric_pass"] is None
    assert "kpi_feedback" not in view


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
