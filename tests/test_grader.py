#!/usr/bin/env python3
"""grader invariants: deterministic scoring, pass policy, and grade lifecycle.
No API needed.

    python3 tests/test_grader.py
    pytest tests/test_grader.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.tools import grader                          # noqa: E402

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


def test_full_pass():
    g = grader.grade_submission(MODEL, RUBRIC,
                                {"assignment": {"marketing_spend": 50000},
                                 "rubric_scores": {"c_o1": 2, "c_o2": 2}})
    assert g["status"] == "ai_draft"
    assert g["kpi_value"] == 3.0 and g["numeric_pass"] is True
    assert g["rubric_score"] == 1.0 and g["rubric_pass"] is True
    assert g["overall_pass"] is True


def test_numeric_fail_blocks_under_all_policy():
    g = grader.grade_submission(MODEL, RUBRIC,
                                {"assignment": {"marketing_spend": 500000},  # ROI -0.6
                                 "rubric_scores": {"c_o1": 2, "c_o2": 2}})
    assert g["numeric_pass"] is False
    assert g["rubric_pass"] is True
    assert g["overall_pass"] is False           # 'all' requires both


def test_rubric_fail_blocks_under_all_policy():
    g = grader.grade_submission(MODEL, RUBRIC,
                                {"assignment": {"marketing_spend": 50000},
                                 "rubric_scores": {"c_o1": 0, "c_o2": 0}})
    assert g["numeric_pass"] is True
    assert g["rubric_pass"] is False
    assert g["overall_pass"] is False


def test_rubric_only_policy_ignores_numeric():
    model = dict(MODEL, pass_policy="rubric_only")
    g = grader.grade_submission(model, RUBRIC,
                                {"assignment": {"marketing_spend": 500000},
                                 "rubric_scores": {"c_o1": 2, "c_o2": 2}})
    assert g["numeric_pass"] is False
    assert g["overall_pass"] is True


def test_undefined_symbols_rejected():
    bad = dict(MODEL, parameters={})            # 'gain' now undefined
    try:
        grader.grade_submission(bad, RUBRIC,
                                {"assignment": {"marketing_spend": 50000}, "rubric_scores": {}})
    except grader.GradeError:
        return
    raise AssertionError("grader must refuse a non-computable outcome_model")


def test_lifecycle_happy_path_with_audit():
    g = grader.grade_submission(MODEL, RUBRIC,
                                {"assignment": {"marketing_spend": 50000},
                                 "rubric_scores": {"c_o1": 2, "c_o2": 2}})
    r = grader.review(g, "prof_1", override_note="looks right", at="2026-06-14T12:00:00Z")
    assert r["status"] == "reviewed"
    assert r["edited_by"] == "prof_1" and r["edited_at"] == "2026-06-14T12:00:00Z"
    assert r["override_note"] == "looks right"
    assert g["status"] == "ai_draft"            # purity: original untouched
    f = grader.finalize(r, "prof_1", at="2026-06-14T12:05:00Z")
    assert f["status"] == "finalized"


def test_review_override_recomputes():
    g = grader.grade_submission(MODEL, RUBRIC,
                                {"assignment": {"marketing_spend": 50000},
                                 "rubric_scores": {"c_o1": 0, "c_o2": 0}})
    assert g["overall_pass"] is False
    r = grader.review(g, "prof_1", rubric=RUBRIC,
                      score_overrides={"c_o1": 2, "c_o2": 2})
    assert r["rubric_score"] == 1.0
    assert r["overall_pass"] is True            # numeric already passed; rubric now passes


def test_illegal_transitions_rejected():
    g = grader.grade_submission(MODEL, RUBRIC,
                                {"assignment": {"marketing_spend": 50000}, "rubric_scores": {}})
    for bad in (lambda: grader.finalize(g, "p"),                 # ai_draft -> finalized
                lambda: grader.finalize(grader.finalize(
                    grader.review(g, "p"), "p"), "p")):           # finalized -> finalized
        try:
            bad()
        except grader.GradeError:
            continue
        raise AssertionError("illegal lifecycle transition must raise")


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
