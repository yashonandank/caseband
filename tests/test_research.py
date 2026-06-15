#!/usr/bin/env python3
"""research invariants: ResearchScout adds exhibits only when research is needed,
idempotently. No API needed.

    python3 tests/test_research.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.models.case_package import CasePackage    # noqa: E402
from caseband.reducer import apply                       # noqa: E402
from caseband.agents.research import ResearchScout       # noqa: E402

FINDINGS = [{"label": "industry CAGR", "value": 7.5, "unit": "percent", "source": "report"},
            {"label": "competitor count", "value": 4, "unit": "count", "source": "news"}]


def _apply_all(pkg, msgs):
    for m in msgs:
        r = apply(pkg, m)
        assert r.applied, r.reason
        pkg = r.package
    return pkg


def test_skips_when_research_not_needed():
    p = CasePackage(); p.meta.update({"title": "t", "needs_research": False})
    assert ResearchScout(FINDINGS).act(p, "researching") == []


def test_adds_exhibits_when_needed():
    p = CasePackage(); p.meta.update({"title": "t", "needs_research": True})
    p = _apply_all(p, ResearchScout(FINDINGS).act(p, "researching"))
    assert len(p.exhibits) == 2
    assert p.exhibits[0]["kind"] == "research"
    assert p.exhibits[0]["label"] == "industry CAGR"


def test_idempotent():
    p = CasePackage(); p.meta.update({"title": "t", "needs_research": True})
    scout = ResearchScout(FINDINGS)
    p = _apply_all(p, scout.act(p, "researching"))
    assert scout.act(p, "researching") == []          # nothing new the second pass


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
