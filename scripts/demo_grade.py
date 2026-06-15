#!/usr/bin/env python3
"""Assessment room, OFFLINE (no API): grade two student submissions deterministically
and walk one through the ai_draft -> reviewed -> finalized lifecycle with audit.

    python3 scripts/demo_grade.py
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


def _show(label, g):
    print(f"\n--- {label} ---")
    print(f"  status={g['status']} kpi={g['kpi_value']} numeric_pass={g['numeric_pass']}")
    print(f"  rubric_score={g['rubric_score']} rubric_pass={g['rubric_pass']} "
          f"(policy={g['pass_policy']})")
    print(f"  OVERALL PASS = {g['overall_pass']}")


def main() -> int:
    strong = grader.grade_submission(MODEL, RUBRIC,
                                     {"assignment": {"marketing_spend": 60000},
                                      "rubric_scores": {"c_o1": 2, "c_o2": 2}})
    _show("Student A (lean spend, strong analysis)", strong)

    weak = grader.grade_submission(MODEL, RUBRIC,
                                   {"assignment": {"marketing_spend": 400000},
                                    "rubric_scores": {"c_o1": 1, "c_o2": 0}})
    _show("Student B (overspent, thin analysis)", weak)

    print("\n=== lifecycle on Student A ===")
    reviewed = grader.review(strong, "prof_emory",
                             override_note="agree with AI", at="2026-06-14T12:00:00Z")
    print(f"  {strong['status']} -> {reviewed['status']} "
          f"by {reviewed['edited_by']} @ {reviewed['edited_at']} "
          f"note={reviewed['override_note']!r}")
    final = grader.finalize(reviewed, "prof_emory", at="2026-06-14T12:05:00Z")
    print(f"  {reviewed['status']} -> {final['status']} @ {final['edited_at']}")

    assert strong["overall_pass"] and not weak["overall_pass"]
    assert final["status"] == "finalized" and strong["status"] == "ai_draft"  # purity
    print("\nOK: grading discriminates pass/fail; lifecycle + audit work; originals immutable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
