#!/usr/bin/env python3
"""sim_agent invariants: live KPI + what-if levers, no answer leak. No API needed.

    python3 tests/test_sim_agent.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.agents.sim_agent import SimAgent          # noqa: E402

MODEL = {
    "kind": "formula", "kpi_key": "roi",
    "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
    "decision_variables": [{"key": "marketing_spend", "bounds": [50000, 500000]}],
    "parameters": {"gain": 200000},
    "spec": {"expr": "(gain - marketing_spend) / marketing_spend"},
}


def test_kpi_matches_formula():
    assert SimAgent().kpi(MODEL, {"marketing_spend": 50000}) == 3.0


def test_kpi_defaults_missing_var_to_midpoint():
    # midpoint 275000 -> (200000-275000)/275000
    expected = (200000 - 275000) / 275000
    assert abs(SimAgent().kpi(MODEL, {}) - expected) < 1e-9


def test_what_if_reports_direction_no_target():
    out = SimAgent().what_if(MODEL, {"marketing_spend": 100000})
    lever = out["levers"]["marketing_spend"]
    assert lever["at_low"] > lever["at_high"]          # less spend -> higher ROI
    assert lever["raises_kpi_toward"] == "low"
    # never reveals target / pass
    flat = str(out)
    assert "target" not in flat and "pass" not in flat


def test_rejects_non_numeric_model():
    try:
        SimAgent().kpi({"kind": "rubric_only"}, {})
    except ValueError:
        return
    raise AssertionError("sim_agent must refuse non-numeric models")


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
