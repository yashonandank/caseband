#!/usr/bin/env python3
"""outcome_engine invariants — the deterministic 'not random' core. No API needed.

    python3 tests/test_outcome_engine.py
    pytest tests/test_outcome_engine.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.tools import outcome_engine as engine     # noqa: E402

GOOD = {
    "kind": "formula", "kpi_key": "roi",
    "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
    "decision_variables": [{"key": "marketing_spend", "bounds": [50000, 500000]}],
    "parameters": {"gain": 200000},
    "spec": {"expr": "(gain - marketing_spend) / marketing_spend"},
}


def test_evaluate_arithmetic():
    assert engine.evaluate(GOOD, {"marketing_spend": 50000}) == 3.0
    assert engine.evaluate(GOOD, {"marketing_spend": 200000}) == 0.0


def test_passes_comparators():
    assert engine.passes(3.0, {"value": 0.15, "comparator": ">="})
    assert not engine.passes(-0.6, {"value": 0.15, "comparator": ">="})


def test_undefined_symbols_detected():
    bad = dict(GOOD, parameters={}, spec={"expr": "(gain - marketing_spend)"})
    assert engine.undefined_symbols(bad) == {"gain"}
    assert engine.undefined_symbols(GOOD) == set()


def test_calibrate_finds_reachable_witness():
    cal = engine.calibrate(GOOD)
    assert cal["reachable"]
    assert engine.passes(cal["kpi"], GOOD["target"])


def test_calibrate_unreachable():
    impossible = dict(GOOD, target={"value": 999, "comparator": ">=", "units": "ratio"})
    assert not engine.calibrate(impossible)["reachable"]


def test_sensitivity_flags_zero_effect():
    dead = {
        "kind": "formula", "kpi_key": "k",
        "target": {"value": 1, "comparator": ">="},
        "decision_variables": [{"key": "x", "bounds": [0, 10]}],
        "parameters": {"gain": 5},
        "spec": {"expr": "gain + 0 * x"},   # x is a decoy lever
    }
    sens = engine.sensitivity(dead)
    assert sens["x"]["moves"] is False
    # and a real lever does move it
    assert engine.sensitivity(GOOD)["marketing_spend"]["moves"] is True


def test_no_code_execution():
    # whitelisted AST: names/attrs/calls must be rejected, not evaluated
    danger = dict(GOOD, spec={"expr": "__import__('os')"}, parameters={}, decision_variables=[])
    try:
        engine.evaluate(danger, {})
    except (ValueError, engine.UnknownSymbol):
        return
    raise AssertionError("expression engine must refuse function calls")


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
