"""runner — generate cases for a corpus of briefs and score them against checks.

Offline (no key) the designer returns the deterministic example, so this verifies
the harness + checks themselves and acts as a regression guard. With a key, point
it at live generation to measure real agent output quality over time."""
from __future__ import annotations
from typing import Callable

from ..agents.case_designer import CaseDesigner
from ..models.rich_case import RichCase
from . import checks

# Corpus: briefs spanning topics. Expand this as new engines/topics land.
CORPUS = [
    {"id": "abc_ai_smallbiz", "brief": {"context": {
        "topic": "AI adoption in a small manufacturer using activity-based costing "
                 "to find the real bottleneck"}, "method": "activity-based costing"}},
    {"id": "abc_services", "brief": {"context": {
        "topic": "a professional-services firm mis-reading where its costs sit"},
        "method": "activity-based costing"}},
]


def evaluate_case(case: RichCase) -> dict:
    results = []
    ok_all = True
    for fn in checks.REQUIRED:
        ok, detail = fn(case)
        results.append({"check": fn.__name__, "ok": bool(ok), "detail": detail})
        ok_all = ok_all and ok
    return {"passed": ok_all, "checks": results}


def run_eval(*, live: bool | None = None, corpus: list | None = None) -> dict:
    corpus = corpus or CORPUS
    designer = CaseDesigner(live=live)
    rows = []
    passed = 0
    for item in corpus:
        case = designer.design(item["brief"])
        report = evaluate_case(case)
        rows.append({"id": item["id"], "title": case.title, **report})
        passed += int(report["passed"])
    return {"total": len(corpus), "passed": passed,
            "failed": len(corpus) - passed, "cases": rows}
